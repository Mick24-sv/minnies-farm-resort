const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const publicRoot = path.join(root, 'public');
let assets = 0;
for (const name of ['index.html', 'privacy.html']) {
  const html = fs.readFileSync(path.join(publicRoot, name), 'utf8');
  for (const match of html.matchAll(/(?:src|href)="(assets\/[^"?#]+)(?:\?[^"#]*)?"/g)) {
    assert.ok(fs.existsSync(path.join(publicRoot, match[1])), `${name}: missing ${match[1]}`);
    assets++;
  }
}
const html = fs.readFileSync(path.join(publicRoot, 'index.html'), 'utf8');
const pinnedCDNScripts = [...html.matchAll(/<script src="https:\/\/(?:cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)\/[^>]+>/g)];
assert.equal(pinnedCDNScripts.length, 4);
for (const [tag] of pinnedCDNScripts) assert.match(tag, /integrity="sha384-[^"]+" crossorigin="anonymous"/);
const scripts = [...html.matchAll(/<script src="(assets\/js\/[^"?]+)(?:\?[^"]*)?"/g)].map(match => match[1]);
assert.equal(scripts.at(-1), 'assets/js/app.js', 'Feature modules must load before the Vue app');
const features = fs.readdirSync(path.join(publicRoot, 'assets/js/features')).filter(name => name.endsWith('.js'));
for (const name of features) assert.ok(scripts.includes('assets/js/features/' + name), `Unloaded feature: ${name}`);
for (const file of [...scripts, 'assets/js/app.js']) execFileSync(process.execPath, ['--check', path.join(publicRoot, file)], { stdio: 'pipe' });
assert.ok(fs.existsSync(path.join(root, 'examples/stillwell-booking/dist/index.html')));
console.log(`PASS: ${assets} HTML assets exist; ${features.length} features load before app.js; JavaScript syntax and example path are valid.`);
