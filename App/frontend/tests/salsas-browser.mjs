// Catálogo ficticio local; no conecta a backend ni modifica productos reales.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.MONU_PLAYWRIGHT_PATH || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const evidence = path.join(tmpdir(), 'monu-salsas', Date.now() + '-' + process.pid);
await mkdir(evidence, { recursive: true });
const names = ['Alioli', 'Barbacoa', 'Mayonesa', 'Ketchup', 'Mostaza'];
const products = [...names, 'Salsa Monu'].map((nombre, i) => ({ id: i + 1, nombre, categoria_id: 7, categoria: 'Dips Extra', descripcion: 'Dip de prueba', precio_base: '900.00', activo: true, disponible: true, imagen_url: null, variantes: [], ingredientes_quitables: [] }));
const user = { id: 1, username: 'fotos-fixture', nombre: 'Fotos', apellido: 'Prueba', rol: 'EMPLEADO', permisos: ['productos.gestionar'] };
const report = { fixturesOnly: true, results: [], pageErrors: [], unknownRequests: [], images: [] };
let browser;
try {
  browser = await chromium.launch({ headless: true, ...(process.env.MONU_CHROMIUM_PATH ? { executablePath: process.env.MONU_CHROMIUM_PATH } : {}) });
  for (const mode of ['clientes', 'personal']) {
    const server = await createServer({ root, configFile: path.join(root, 'vite.config.ts'), mode,
      cacheDir: path.join(root, 'node_modules/.vite-tests/salsas-' + mode + '-' + process.pid),
      plugins: [{ name: 'salsas-sin-backend', configResolved(config) { config.server.proxy = {}; } }],
      server: { host: '127.0.0.1', port: 0, hmr: false, open: false },
    });
    try {
      await server.listen(); const origin = 'http://127.0.0.1:' + server.httpServer.address().port;
      for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }, { width: 320, height: 740 }]) {
        const context = await browser.newContext({ viewport }); const page = await context.newPage();
        page.on('pageerror', (error) => report.pageErrors.push(error.message));
        const loaded = new Set();
        page.on('response', (response) => {
          const url = new URL(response.url());
          if (url.pathname.startsWith('/images/salsas/')) {
            report.images.push({ mode, viewport: viewport.width, path: url.pathname, status: response.status() });
            if (response.ok()) loaded.add(url.pathname);
          }
        });
        await context.route('**/*', async (route) => {
          const request = route.request(); const url = new URL(request.url());
          if (url.origin !== origin) return route.abort();
          if (!url.pathname.startsWith('/api/')) return route.continue();
          const send = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
          if (request.method() === 'GET') {
            if (url.pathname === '/api/productos') return send(products);
            if (url.pathname === '/api/chat-demo/config') return send({ habilitado: false });
            if (url.pathname === '/api/auth/me') return send(user);
          }
          report.unknownRequests.push(request.method() + ' ' + url.pathname); return send({}, 404);
        });
        const destination = mode === 'clientes' ? '/menu?categoria=Dips%20Extra' : '/dashboard/catalog';
        await page.goto(origin + destination);
        for (let pass = 0; pass < 2; pass += 1) {
          if (pass) await page.reload();
          await page.getByRole('img', { name: 'Mostaza', exact: true }).waitFor();
          await page.waitForLoadState('networkidle');
          for (const name of names) {
            const img = page.getByRole('img', { name, exact: true });
            assert.equal(await img.count(), 1);
            const dimensions = await img.evaluate((node) => ({ src: new URL(node.src).pathname, width: node.naturalWidth, height: node.naturalHeight, complete: node.complete, fit: getComputedStyle(node).objectFit, renderedWidth: node.getBoundingClientRect().width, renderedHeight: node.getBoundingClientRect().height }));
            assert.equal(dimensions.src, '/images/salsas/' + name.toLowerCase() + '.webp');
            assert.equal(dimensions.complete, true); assert.equal(dimensions.width, 138); assert.equal(dimensions.height, 135);
            assert.equal(dimensions.fit, 'contain');
            if (mode === 'clientes') {
              assert.ok(dimensions.renderedWidth <= 138 && dimensions.renderedHeight <= 135, 'No amplía la foto original');
              assert.ok(Math.abs(dimensions.renderedWidth / dimensions.renderedHeight - 138 / 135) < 0.01, 'Conserva proporción');
            }
          }
          assert.equal(loaded.size, 5);
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Sin desborde horizontal');
        }
        await page.screenshot({ path: path.join(evidence, mode + '-' + viewport.width + '.png'), fullPage: true, animations: 'disabled' });
        report.results.push({ mode, viewport: viewport.width, fivePhotos: true, reload: true, noUpscaling: mode === 'clientes' });
        await context.close();
      }
    } finally { await server.close(); }
  }
  assert.deepEqual(report.pageErrors, []); assert.deepEqual(report.unknownRequests, []);
  assert.ok(report.images.length >= 30); assert.ok(report.images.every((entry) => entry.status === 200));
} catch (error) { report.failure = error.message; throw error; }
finally { await writeFile(path.join(evidence, 'report.json'), JSON.stringify(report, null, 2)); await browser?.close(); console.log('Evidencias: ' + evidence); }
