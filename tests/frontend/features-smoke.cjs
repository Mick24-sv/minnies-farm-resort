// Run with PLAYWRIGHT_PATH pointing to an installed playwright or playwright-core module.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const errors = [], passed = [], requests = [];
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  let profileFailure = false;
  let loginFailure = false;
  let reviewMode = 'rated';
  let revenueMode = 'paid';
  let submittedBooking;
  let bookingTimesEnabled = true;
  const user = { id: 7, name: 'Ana Reyes', email: 'qa@example.com', role: 'staff', is_verified: true };
  const booking = { id: 1, user_id: 7, guest_name: 'Ana Reyes', room_id: 1, room_name: 'Garden Room', status: 'confirmed', check_in: '2026-12-01', check_out: '2026-12-02', guest_count: 2, total_price: 2200, amount_paid: 2200, balance_due: 0, payment_status: 'paid' };
  await context.route(/^http:\/\/127\.0\.0\.1:5000\/api\//, async route => {
    const req = route.request(), url = new URL(req.url());
    requests.push(url.pathname);
    let data = {}, status = 200;
    if (url.pathname.endsWith('/profile')) {
      if (profileFailure) { status = 503; data = { error: 'Test save failure' }; }
      else { user.name = req.postDataJSON().name; data = { user }; }
    } else if (url.pathname.endsWith('/me')) data = { user };
    else if (url.pathname.endsWith('/login')) {
      if (loginFailure) { status = 401; data = { error: 'Invalid email or password.' }; }
      else data = { user, token: 'qa-token' };
    }
    else if (url.pathname.endsWith('/google')) data = { user, token: 'qa-token' };
    else if (url.pathname.endsWith('/notifications')) data = { notifications: [], unread_count: 0 };
    else if (url.pathname === '/api/staff/revenue') {
      if (revenueMode === 'error') { status=503; data={error:'Revenue unavailable'}; }
      else {
        const today=new Date(), months=Array.from({length:12},(_,i)=>{const date=new Date(today.getFullYear(),today.getMonth()-11+i,1);const room_payments=revenueMode==='empty'?0:100+i*10,service_payments=revenueMode==='empty'?0:20.25;return{month:date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0'),room_payments,service_payments,total:room_payments+service_payments};});
        data={currency:'PHP',as_of:today.toISOString(),months};
      }
    }
    else if (url.pathname.endsWith('/reviews')) {
      if (reviewMode === 'error') { status = 503; data = { error: 'Reviews unavailable' }; }
      else if (reviewMode === 'empty') data = { reviews: [], average_rating: 0, total_reviews: 0, rating_breakdown: {'5':0,'4':0,'3':0,'2':0,'1':0} };
      else data = { reviews: [{id:1,room_id:1,rating:5,guest_name:'QA reviewer',review:'Test review'}], average_rating:4.2,total_reviews:5,rating_breakdown:{'5':2,'4':2,'3':1,'2':0,'1':0} };
    }
    else if (url.pathname.endsWith('/bookings')) {
      if (req.method() === 'POST') {
        submittedBooking = req.postDataJSON();
        Object.assign(booking, {check_in:submittedBooking.check_in_date,check_out:submittedBooking.check_out_date,check_in_time:submittedBooking.check_in_time,check_out_time:submittedBooking.check_out_time,reference_code:'QA-TIMES'});
        data = {booking};
      } else data = { bookings: [booking] };
    }
    else if (url.pathname.endsWith('/rooms')) data = { rooms: [{ id: 1, name: 'Garden Room', type: 'Standard', room_number: '101', price_per_night: 2000, capacity: 2, is_available: true, amenities: [] }] };
    else if (url.pathname.endsWith('/avails')) data = { avails: [] };
    else if (url.pathname.endsWith('/services')) data = { services: [] };
    else data = { configured: true, booking_times_enabled: bookingTimesEnabled, accounts: [], payments: [] };
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await context.addInitScript(() => sessionStorage.setItem('token', 'qa-token'));
  await context.addInitScript(() => window.addEventListener('error', event => console.log('WINDOW_ERROR_SOURCE', JSON.stringify({ message: event.message, filename: event.filename, line: event.lineno, column: event.colno }))));
  const page = await context.newPage();
  page.on('response', response => {
    if (response.request().resourceType() === 'script' && response.status() >= 400) {
      const url = new URL(response.url()); console.log('EXTERNAL SCRIPT FAILURE', response.status(), url.origin + url.pathname);
    }
  });
  page.on('console', message => { if (message.text().startsWith('WINDOW_ERROR_SOURCE')) console.log(message.text()); });
  const devtools = await context.newCDPSession(page);
  await devtools.send('Runtime.enable');
  devtools.on('Runtime.exceptionThrown', event => console.log('EXCEPTION DETAILS', JSON.stringify(event.exceptionDetails)));
  page.on('pageerror', e => { errors.push(e.message); console.log('BROWSER ERROR', e.stack); });
  const check = async (name, fn) => { await fn(); passed.push(name); console.log('PASS', name); };
  const state = fn => page.evaluate(fn);
  await page.goto('http://127.0.0.1:5000');
  await page.waitForSelector('#main-navigation [data-section="dashboard"]');
  await check('Vue, GSAP, DrawSVG and Lenis load', async () => {
    assert.ok(await state(() => !!window.gsap && !!window.DrawSVGPlugin && !!window.Lenis));
  });
  await check('Staff receipts use API data, period totals, empty/error/retry states', async () => {
    await page.locator('#main-navigation [data-section="dashboard"]').click();
    await page.locator('.staff-revenue').waitFor();
    await page.locator('.revenue-metric>strong').waitFor();
    assert.equal(await page.locator('.revenue-metric>strong').innerText(), '₱1,231.50');
    for (const n of [3, 6, 12]) {
      await page.getByRole('button', { name: n + 'M', exact: true }).click();
      assert.equal(await page.locator('.revenue-column').count(), n);
    }
    assert.equal(await page.locator('.revenue-metric>strong').innerText(), '₱2,103.00');
    revenueMode='error';await state(()=>__app._container._vnode.component.proxy.fetchRevenue());
    await page.locator('.staff-revenue [role="alert"]').waitFor();
    assert.equal(await page.locator('.revenue-metric').count(),0);
    revenueMode='empty';await page.getByRole('button',{name:'Retry revenue',exact:true}).click();
    await page.getByText('No recorded receipts in this period.',{exact:true}).waitFor();
    assert.equal(await page.locator('.revenue-metric>strong').innerText(),'₱0.00');
    revenueMode='paid';await state(()=>__app._container._vnode.component.proxy.fetchRevenue());
    await page.locator('.revenue-column').first().waitFor();
  });
  await check('Room ratings use API data and handle empty/error states', async () => {
    assert.equal(await page.locator('.staff-rating,.room-rating').count(), 0);
    await state(() => { const vm=__app._container._vnode.component.proxy; vm.viewRoom(vm.rooms[0]); });
    await page.locator('.room-rating').waitFor();
    await page.locator('.room-rating').scrollIntoViewIfNeeded();
    assert.equal(await page.getByRole('button', { name: 'Replay rating animation', exact: true }).count(), 0);
    await page.waitForTimeout(1700);
    assert.ok((await page.locator('.rating-number').innerText()).includes('4.2'));
    const fill = await page.locator('.rating-star-fill').last().evaluate(e => parseFloat(e.style.width));
    assert.ok(Math.abs(fill - 20) < .01);
    assert.equal(await page.locator('.rating-row').count(), 5);
    assert.equal(await page.locator('.rating-count').first().innerText(), '2');
    reviewMode = 'empty';
    await state(() => __app._container._vnode.component.proxy.fetchReviews(1));
    await page.locator('.detail-no-reviews').waitFor();
    assert.equal(await page.locator('.room-rating').count(), 0);
    reviewMode = 'error';
    await state(() => __app._container._vnode.component.proxy.fetchReviews(1));
    await page.locator('.detail-reviews [role="alert"]').waitFor();
    assert.equal(await page.locator('.detail-no-reviews').count(), 0);
    reviewMode = 'rated';
    await page.getByRole('button', {name:'Retry',exact:true}).click();
    await page.locator('.room-rating').waitFor();
    await page.locator('#main-navigation [data-section="dashboard"]').click();
  });
  await check('Customer-selected times reach API, confirmation, guest and staff lists', async () => {
    await state(() => {const vm=__app._container._vnode.component.proxy;vm.currentUser={...vm.currentUser,role:'guest'};vm.viewRoom(vm.rooms[0]);});
    await page.locator('#detail-check-in').fill('2035-06-01');
    await page.locator('#detail-check-out').fill('2035-06-02');
    assert.ok(await page.locator('.detail-book-button').isDisabled());
    await page.locator('#detail-arrival-time').fill('14:30');
    await page.locator('#detail-departure-time').fill('09:15');
    await page.locator('.detail-book-button').click();
    await page.locator('.reservation-receipt').waitFor();
    assert.equal(submittedBooking.check_in_time,'14:30');
    assert.equal(submittedBooking.check_out_time,'09:15');
    assert.match(await page.locator('.reservation-receipt').innerText(),/2:30 PM PHT/);
    assert.match(await page.locator('.reservation-receipt').innerText(),/9:15 AM PHT/);
    await state(()=>__app._container._vnode.component.proxy.navigate('dashboard'));
    await page.locator('#guest-bookings-heading').waitFor();
    assert.ok((await page.locator('.booking-selected-time').allTextContents()).includes('2:30 PM PHT'));
    await state(()=>{const vm=__app._container._vnode.component.proxy;vm.currentUser={...vm.currentUser,role:'staff'};vm.navigate('dashboard');});
    await page.locator('.staff-dashboard .booking-selected-time').first().waitFor();
    assert.ok((await page.locator('.staff-dashboard .booking-selected-time').allTextContents()).includes('9:15 AM PHT'));
    bookingTimesEnabled=false;
    await state(()=>{const vm=__app._container._vnode.component.proxy;vm.paymentOptions.booking_times_enabled=false;vm.viewRoom(vm.rooms[0]);});
    assert.ok(await page.locator('#detail-arrival-time').isDisabled());
    assert.ok(await page.locator('#detail-departure-time').isDisabled());
    await page.getByText('Time selection is temporarily unavailable. Contact the resort to confirm arrival and departure times.',{exact:true}).waitFor();
    bookingTimesEnabled=true;
    await state(async()=>{const vm=__app._container._vnode.component.proxy;await vm.fetchPaymentOptions();vm.navigate('dashboard');});
  });
  await check('Profile edit, discard, failure and save', async () => {
    assert.equal(await page.locator('#main-navigation [data-section="profile"]').count(), 0);
    await page.locator('.staff-tabs').getByRole('button', { name: 'Profile', exact: true }).click();
    await page.locator('#profile-first').fill('Amelia');
    await page.locator('.profile-save-bar').waitFor();
    await page.getByRole('button', { name: 'Discard', exact: true }).click();
    await page.waitForSelector('.profile-save-bar', { state: 'detached' });
    assert.equal(await page.locator('#profile-first').inputValue(), 'Ana');
    await page.locator('#profile-first').fill('Amelia'); profileFailure = true;
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.locator('.profile-error').waitFor();
    assert.ok(await page.locator('.profile-save-bar').isVisible()); profileFailure = false;
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.locator('.profile-message').waitFor();
    await page.waitForSelector('.profile-save-bar', { state: 'detached' });
    assert.equal(user.name, 'Amelia Reyes');
  });
  await check('Payment success draws and completes', async () => {
    await state(() => {
      const vm = __app._container._vnode.component.proxy;
      vm.lastBooking = { status: 'confirmed', room: 'Garden Room', total: 2200, amount_paid: 2200, balance_due: 0, guests: 2, checkIn: '2026-12-01', checkOut: '2026-12-02' };
      vm.navigate('confirm');
    });
    await page.locator('.payment-draw-ring').waitFor(); await page.waitForTimeout(2000);
    const opacity = await page.locator('.payment-pulse-ring').evaluate(e => +getComputedStyle(e).opacity);
    assert.equal(opacity, 0);
    assert.equal(await page.locator('.payment-radial-tick').count(), 8);
  });
  await check('Lenis scroll and active pill', async () => {
    await page.locator('#main-navigation [data-section="services"]').click();
    await page.waitForTimeout(1500);
    assert.equal(await page.locator('#main-navigation [data-section="services"]').getAttribute('aria-current'), 'location');
    const top = await page.locator('#section-services').evaluate(e => e.getBoundingClientRect().top);
    assert.ok(Math.abs(top - 80) < 12, 'section top: ' + top);
    assert.equal(await page.locator('.sticky-nav-pill').evaluate(e => e.style.opacity), '1');
  });
  await check('Tour single spotlight, next, back and Escape', async () => {
    await page.getByRole('button', { name: 'Customer guide', exact: true }).click();
    assert.equal(await page.locator('.tour-spotlight').count(), 1);
    await page.locator('[data-next]').click(); await page.waitForTimeout(700);
    assert.ok((await page.locator('#tour-title').innerText()).includes('stay'));
    await page.locator('[data-back]').click();
    await page.keyboard.press('Escape'); await page.waitForSelector('.onboarding-tour', { state: 'detached' });
  });
  await check('Customer guide covers five essential steps on mobile and desktop', async () => {
    await state(() => { const vm = __app._container._vnode.component.proxy; vm.currentUser = { ...vm.currentUser, role: 'guest' }; vm.navigate('dashboard'); });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      if (width <= 1100) await page.locator('.mobile-menu-btn').click();
      const help = page.getByRole('button', { name: 'Customer guide', exact: true });
      assert.ok(await help.isVisible());
      assert.equal(await help.innerText(), '');
      await help.click();
      const expected = ['Plan your visit.', 'Reserve your stay.', 'Just visiting for the day?', 'Track your bookings.', 'Keep your details up to date.'];
      for (let n = 0; n < expected.length; n++) {
        await page.getByRole('heading', { name: expected[n], exact: true }).waitFor();
        await page.waitForTimeout(700);
        assert.equal(await page.locator('.tour-dot').count(), 5);
        const card = await page.locator('.tour-card').boundingBox();
        assert.ok(card.x >= 0 && card.x + card.width <= width + 1 && card.y >= 0 && card.y + card.height <= 1001);
        if (n === 1) assert.match(await page.locator('#tour-description').innerText(), /50%.*staff verify/);
        await page.locator('[data-next]').click();
      }
      await page.waitForSelector('.onboarding-tour', { state: 'detached' });
      await page.locator('.guest-dashboard').waitFor();
    }
    await state(() => { const vm = __app._container._vnode.component.proxy; vm.currentUser = null; vm.navigate('auth'); });
    await page.setViewportSize({ width: 900, height: 1000 });
    await page.locator('.mobile-menu-btn').click();
    await page.getByRole('button', { name: 'Customer guide', exact: true }).click();
    for (let n = 0; n < 5; n++) await page.locator('[data-next]').click();
    await page.waitForSelector('.onboarding-tour', { state: 'detached' });
    await page.locator('.auth-page').waitFor();
    await page.evaluate(u => { const vm = __app._container._vnode.component.proxy; vm.currentUser = u; vm.navigate('services'); }, user);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.waitForTimeout(1400);
  });
  await check('Curtain footer reveals and social hover/press', async () => {
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(800);
    assert.equal(await page.locator('.accent-footer').evaluate(e => e.inert), false);
    const button = page.locator('.footer-social-button').first(); await button.hover(); await page.waitForTimeout(280);
    assert.notEqual(await button.evaluate(e => getComputedStyle(e).transform), 'none');
    await page.mouse.down(); await page.waitForTimeout(100);
    assert.ok(await button.evaluate(e => e.matches(':active'))); await page.mouse.move(1, 1); await page.mouse.up();
  });
  await check('Mobile tabs and liquid indicator', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.mobile-bottom-tabs button').nth(1).click(); await page.waitForTimeout(1400);
    await page.locator('.mobile-bottom-tabs button').nth(2).click(); await page.waitForTimeout(1400);
    assert.equal(await page.locator('.mobile-bottom-tabs button').nth(2).getAttribute('aria-current'), 'page');
    assert.equal(await page.locator('.liquid-tab-indicator').evaluate(e => e.style.opacity), '1');
  });
  await check('Mobile pull to refresh fetches rows', async () => {
    await page.locator('.mobile-bottom-tabs button').nth(3).click();
    await page.locator('.staff-dashboard').waitFor(); await page.waitForTimeout(300);
    const before = requests.filter(p => p === '/api/bookings').length;
    await page.evaluate(() => {
      window.scrollTo(0, 0);
      const root = document.querySelector('.staff-dashboard');
      const touch = y => new Touch({ identifier: 1, target: root, clientX: 180, clientY: y });
      root.dispatchEvent(new TouchEvent('touchstart', { touches: [touch(90)], targetTouches: [touch(90)], changedTouches: [touch(90)], bubbles: true }));
      root.dispatchEvent(new TouchEvent('touchmove', { touches: [touch(410)], targetTouches: [touch(410)], changedTouches: [touch(410)], bubbles: true, cancelable: true }));
      root.dispatchEvent(new TouchEvent('touchend', { touches: [], changedTouches: [touch(410)], bubbles: true }));
    });
    await page.waitForTimeout(1000);
    assert.ok(requests.filter(p => p === '/api/bookings').length > before);
    assert.equal(await page.locator('.pull-refresh-panel').evaluate(e => e.style.height), '0px');
  });
  await check('Guest profile lives inside My Bookings on desktop and mobile', async () => {
    await state(() => { const vm = __app._container._vnode.component.proxy; vm.currentUser = { ...vm.currentUser, role: 'guest' }; vm.navigate('dashboard'); });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.locator('.guest-account-nav').getByRole('button', { name: 'Profile settings', exact: true }).click();
      await page.locator('#profile-first').fill('Edited');
      await page.locator('.profile-save-bar').waitFor();
      if (width === 390) {
        await page.waitForTimeout(400);
        const bar = await page.locator('.profile-save-bar').boundingBox();
        const tabs = await page.locator('.mobile-bottom-tabs').boundingBox();
        assert.ok(bar.y + bar.height <= tabs.y, JSON.stringify({ saveBar: bar, bottomTabs: tabs }));
      }
      await page.getByRole('button', { name: 'Discard', exact: true }).click();
      await page.locator('.guest-account-nav').getByRole('button', { name: 'Your bookings', exact: true }).click();
      await page.locator('#guest-bookings-heading').waitFor();
      assert.equal(await page.locator('#main-navigation [data-section="dashboard"]').getAttribute('aria-current'), 'location');
    }
  });
  await check('Login animation appears only after successful sign-in', async () => {
    await state(() => { const vm = __app._container._vnode.component.proxy; vm.currentUser = null; vm.navigate('auth'); });
    await page.locator('#login-email').waitFor();
    assert.equal(await page.locator('.login-logo-motion').count(), 0);
    assert.equal(await page.locator('.login-success-dialog').count(), 0);
    await page.locator('#login-email').fill('qa@example.com'); await page.locator('#login-password').fill('qa-password');
    loginFailure = true;
    await page.locator('.auth-submit').click();
    await page.locator('.alert-error').waitFor();
    assert.equal(await page.locator('.login-success-dialog').count(), 0);
    assert.ok(await page.locator('.auth-page').isVisible());
    loginFailure = false;
    await page.locator('.auth-submit').click();
    await page.locator('.login-success-dialog[open]').waitFor();
    assert.ok(await page.locator('.login-success-dialog .login-logo-motion').isVisible());
    assert.equal(await page.locator('.auth-page').count(), 0);
    assert.ok(await page.locator('.staff-dashboard').isVisible());
    await page.keyboard.press('Escape');
    assert.ok(await page.locator('.login-success-dialog').isVisible());
    await page.waitForSelector('.login-success-dialog', { state: 'detached', timeout: 6000 });
  });
  await check('Google sign-in uses the same post-login overlay', async () => {
    await context.route('https://www.googleapis.com/oauth2/v3/userinfo', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ email: user.email, name: user.name }) }));
    await state(() => {
      const vm = __app._container._vnode.component.proxy; vm.currentUser = null; vm.navigate('auth');
      window.google = { accounts: { oauth2: { initTokenClient: ({ callback }) => ({ requestAccessToken: () => callback({ access_token: 'qa-google-token' }) }) } } };
    });
    await page.locator('.auth-google').click();
    await page.locator('.login-success-dialog[open]').waitFor();
    assert.equal(await page.locator('.auth-page').count(), 0);
    await page.waitForSelector('.login-success-dialog', { state: 'detached', timeout: 6000 });
  });
  await check('Separate booking and delete demo', async () => {
    const demo = await context.newPage();
    await demo.goto(pathToFileURL(path.resolve(__dirname, '../../examples/stillwell-booking/dist/index.html')).href);
    await demo.locator('.day:not(:disabled)').first().click(); await demo.locator('.slot:not(:disabled)').first().click();
    await demo.locator('#confirm').click(); assert.ok(await demo.locator('#summary').isVisible());
    await demo.locator('.project-delete-trigger').click(); await demo.waitForTimeout(700);
    await demo.mouse.click(10, 10); assert.ok(await demo.locator('.delete-dialog').isVisible());
    await demo.locator('#delete-cancel').click(); await demo.close();
  });
  assert.deepEqual(errors, [], 'Uncaught browser errors');
  console.log(JSON.stringify({ passed, uncaughtErrors: errors, data: 'mocked; no database writes' }, null, 2));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
