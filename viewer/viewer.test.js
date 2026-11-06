const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { buildManifest, renderManifest } = require('./build-manifest.js');
const { createServer } = require('./server.js');

const repo = path.resolve(__dirname, '..');

function fixture(deck = { title: 'Deck', summary: 'S', minutes: 5, scripts: ['slides.js'] }) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'viewer-'));
  const dir = path.join(root, 'presentations/intro');
  fs.mkdirSync(dir, { recursive: true });
  fs.mkdirSync(path.join(root, 'src'));
  fs.mkdirSync(path.join(root, 'viewer'));
  fs.writeFileSync(path.join(root, 'index.html'), '<h1>home</h1>');
  fs.writeFileSync(path.join(root, 'viewer/app.js'), 'ok');
  fs.writeFileSync(path.join(root, 'src/secret.py'), 'private');
  fs.writeFileSync(path.join(root, 'research.md'), 'not a deck');
  fs.writeFileSync(path.join(root, 'project.json'), JSON.stringify({ title: 'Demo', field: 'F', status: 'researching', summary: 'S' }));
  fs.writeFileSync(path.join(dir, 'presentation.json'), JSON.stringify(deck));
  fs.writeFileSync(path.join(dir, 'slides.js'), 'ok');
  return root;
}

test('manifest finds projects and presentations', () => {
  const { projects } = buildManifest(fixture());
  assert.equal(projects[0].slug, 'project');
  assert.equal(projects[0].presentations[0].path, 'presentations/intro');
});

test('manifest keeps a project with no presentations', () => {
  const root = fixture();
  fs.rmSync(path.join(root, 'presentations'), { recursive: true });
  assert.deepEqual(buildManifest(root).projects[0].presentations, []);
});

test('manifest ignores a project without project.json', () => {
  const root = fixture();
  fs.rmSync(path.join(root, 'project.json'));
  assert.deepEqual(buildManifest(root).projects, []);
});

test('manifest rejects missing fields and missing scripts', () => {
  assert.throws(() => buildManifest(fixture({ title: 'x', minutes: 1, scripts: ['slides.js'] })), /missing "summary"/);
  assert.throws(() => buildManifest(fixture({ title: 'x', summary: 's', minutes: 1, scripts: ['nope.js'] })), /missing script/);
});

test('manifest rejects script paths that leave the deck folder', () => {
  assert.throws(() => buildManifest(fixture({ title: 'x', summary: 's', minutes: 1, scripts: ['../slides.js'] })), /invalid script/);
});

test('committed manifest matches the repo', () => {
  const committed = fs.readFileSync(path.join(repo, 'viewer/manifest.js'), 'utf8');
  assert.equal(committed, renderManifest(buildManifest(repo)), 'Run npm run manifest');
});

test('every presentation in this repo is valid and has unique slide ids', () => {
  const { projects } = buildManifest(repo);
  assert.ok(projects.some((p) => p.presentations.length > 0));
  projects.forEach((p) => p.presentations.forEach((d) => {
    const src = fs.readFileSync(path.join(repo, d.path, d.scripts[d.scripts.length - 1]), 'utf8');
    assert.match(src, /Viewer\.present\(/);
    const ids = [...src.matchAll(/^\s*id: '([a-z0-9-]+)', /gm)].map((m) => m[1]);
    assert.ok(ids.length > 0);
    assert.equal(new Set(ids).size, ids.length);
  }));
});

test('server serves the viewer and decks but nothing private', async (t) => {
  const root = fixture();
  const server = createServer(root);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  t.after(() => server.close());
  const base = `http://127.0.0.1:${server.address().port}`;
  const status = async (p) => (await fetch(base + p)).status;

  assert.equal(await status('/'), 200);
  assert.equal(await status('/viewer/app.js'), 200);
  assert.equal(await status('/viewer/manifest.js'), 200);
  assert.equal(await status('/presentations/intro/slides.js'), 200);
  for (const p of ['/src/secret.py', '/research.md', '/project.json', '/.git/config', '/viewer/%2e%2e/src/secret.py', '/presentations/intro/%2e%2e%2f%2e%2e%2fsrc%2fsecret.py']) {
    assert.equal(await status(p), 404, p);
  }
});

test('server builds the manifest live', async (t) => {
  const root = fixture();
  const server = createServer(root);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  t.after(() => server.close());
  const text = await (await fetch(`http://127.0.0.1:${server.address().port}/viewer/manifest.js`)).text();
  assert.match(text, /QUANT_MANIFEST/);
  assert.match(text, /presentations\/intro/);
});
