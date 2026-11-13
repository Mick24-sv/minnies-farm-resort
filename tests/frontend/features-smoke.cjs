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
    else if (url.pathname.endsWith('/login')) data = { user, token: 'qa-token' };
    else if (url.pathname.endsWith('/notifications')) data = { notifications: [], unread_count: 0 };
    else if (url.pathname.endsWith('/bookings')) data = { bookings: [booking] };
    else if (url.pathname.endsWith('/rooms')) data = { rooms: [{ id: 1, name: 'Garden Room', type: 'Standard', room_number: '101', price_per_night: 2000, capacity: 2, is_available: true, amenities: [] }] };
    else if (url.pathname.endsWith('/avails')) data = { avails: [] };
    else if (url.pathname.endsWith('/services')) data = { services: [] };
    else data = { configured: true, accounts: [], payments: [] };
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
  await page.waitForSelector('#main-navigation [data-section="profile"]');
  await check('Vue, GSAP, DrawSVG and Lenis load', async () => {
    assert.ok(await state(() => !!window.gsap && !!window.DrawSVGPlugin && !!window.Lenis));
  });
  await check('Staff revenue ranges and pesos', async () => {
    await page.locator('#main-navigation [data-section="dashboard"]').click();
    await page.locator('.staff-revenue').waitFor();
    assert.equal(await page.locator('.revenue-metric>strong').innerText(), '₱142,800');
    for (const n of [3, 6, 12]) {
      await page.getByRole('button', { name: n + 'M', exact: true }).click();
      assert.equal(await page.locator('.revenue-column').count(), n);
    }
  });
  await check('Rating reaches 4.8 and fifth star 80%', async () => {
    await page.locator('.staff-rating').scrollIntoViewIfNeeded();
    await page.locator('.rating-replay').click();
    await page.waitForTimeout(1700);
    assert.ok((await page.locator('.rating-number').innerText()).includes('4.8'));
    const fill = await page.locator('.rating-star-fill').last().evaluate(e => parseFloat(e.style.width));
    assert.ok(Math.abs(fill - 80) < .01);
    assert.equal(await page.locator('.rating-row').count(), 5);
  });
  await check('Profile edit, discard, failure and save', async () => {
    await page.locator('#main-navigation [data-section="profile"]').click();
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
    await page.locator('#main-navigation').getByRole('button', { name: 'Take a tour' }).click();
    assert.equal(await page.locator('.tour-spotlight').count(), 1);
    await page.locator('[data-next]').click(); await page.waitForTimeout(700);
    assert.ok((await page.locator('#tour-title').innerText()).includes('stay'));
    await page.locator('[data-back]').click();
    await page.keyboard.press('Escape'); await page.waitForSelector('.onboarding-tour', { state: 'detached' });
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
  await check('Successful login runs logo animation and redirects', async () => {
    await state(() => { const vm = __app._container._vnode.component.proxy; vm.currentUser = null; vm.navigate('auth'); });
    await page.locator('#login-email').fill('qa@example.com'); await page.locator('#login-password').fill('qa-password');
    await page.locator('.auth-submit').click();
    await page.waitForTimeout(250);
    assert.ok(await page.locator('.login-logo-motion').isVisible());
    await page.locator('.staff-dashboard').waitFor({ timeout: 6000 });
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
