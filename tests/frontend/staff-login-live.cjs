// Credentials arrive only on stdin; never log or save them.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', async () => {
  let browser;
  try {
    const credentials = JSON.parse(input); input = '';
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const cors = { 'access-control-allow-origin': 'http://127.0.0.1:5012', 'access-control-allow-headers': 'Content-Type, Authorization, Cache-Control, Pragma', 'access-control-allow-methods': 'GET, POST, OPTIONS' };
    await page.route(/^http:\/\/127\.0\.0\.1:(5000|5012)\/api\//, async route => {
      const request = route.request(), url = new URL(request.url());
      if (['/api/auth/login', '/api/auth/me'].includes(url.pathname)) {
        const response = await route.fetch({ url: 'http://127.0.0.1:5012' + url.pathname });
        await route.fulfill({ response, headers: { ...response.headers(), ...cors } });
        return;
      }
      // Avoid GET-triggered hold expiration, notification jobs, or any transaction writes.
      const data = url.pathname.endsWith('/notifications') ? { notifications: [], unread_count: 0 }
        : url.pathname.endsWith('/rooms') ? { rooms: [] }
        : url.pathname.endsWith('/bookings') ? { bookings: [] }
        : url.pathname.endsWith('/avails') ? { avails: [] }
        : url.pathname.endsWith('/services') ? { services: [] }
        : { configured: true, accounts: [] };
      await route.fulfill({ headers: cors, contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto('http://127.0.0.1:5012');
    await page.locator('#main-navigation').getByRole('button', { name: 'Login / Register' }).click();
    assert.equal(await page.locator('.auth-card .login-logo-motion').count(), 0);
    await page.locator('#login-email').fill(credentials.email);
    await page.locator('#login-password').fill(credentials.password);
    credentials.password = '';
    await page.locator('.auth-submit').click();
    await page.locator('.login-success-dialog[open]').waitFor({ timeout: 30000 });
    await page.waitForSelector('.login-success-dialog', { state: 'detached', timeout: 10000 });
    await page.locator('.staff-dashboard').waitFor();
    assert.equal(await page.locator('#main-navigation [data-section="dashboard"]').innerText(), 'Staff Dashboard');
    console.log('PASS: real staff credentials accepted in the browser; success animation completed and Staff Dashboard opened. Dashboard data was mocked; no booking/payment/email side effects.');
  } catch {
    console.error('Live staff browser verification failed. Credentials were not logged.');
    process.exitCode = 1;
  } finally {
    await browser?.close();
  }
});
