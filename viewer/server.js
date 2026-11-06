/* Local viewer server. It serves only the viewer and presentations, so source, data and .git are not served. */
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { buildManifest, renderManifest, writeManifest } = require('./build-manifest.js');

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp' };
const PUBLIC = [/^\/index\.html$/, /^\/viewer\/[^/]+\.(html|js|css)$/, /^\/presentations\/[a-z0-9-]+\/[^/]+$/];

function createServer(root) {
  return http.createServer((req, res) => {
    const send = (status, body, type = 'text/plain; charset=utf-8') => {
      res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' });
      res.end(body);
    };
    let route;
    try {
      route = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    } catch {
      return send(400, 'Bad request');
    }
    if (route === '/') route = '/index.html';
    if (route.split('/').some((part) => part === '..' || part.startsWith('.')) || !PUBLIC.some((r) => r.test(route))) return send(404, 'Not found');
    if (route === '/viewer/manifest.js') {
      try {
        return send(200, renderManifest(buildManifest(root)), TYPES['.js']);
      } catch (error) {
        return send(500, `console.error(${JSON.stringify(error.message)});`, TYPES['.js']);
      }
    }
    const type = TYPES[path.extname(route)];
    if (!type) return send(404, 'Not found');
    return fs.readFile(path.join(root, route), (error, data) => (error ? send(404, 'Not found') : send(200, data, type)));
  });
}

function listen(server, port, attemptsLeft = 20) {
  server.once('error', (error) => {
    if (error.code === 'EADDRINUSE' && attemptsLeft > 0) return listen(server, port + 1, attemptsLeft - 1);
    throw error;
  });
  server.listen(port, '127.0.0.1', () => console.log(`Presentations: http://127.0.0.1:${server.address().port}/`));
}

if (require.main === module) {
  const root = path.resolve(__dirname, '..');
  writeManifest(root);
  listen(createServer(root), Number(process.env.PORT) || 4173);
}

module.exports = { createServer };
