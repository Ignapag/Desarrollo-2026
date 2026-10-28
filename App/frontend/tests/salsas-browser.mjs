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
const allSauces = [...names, 'Salsa Monu'];
const products = allSauces.map((nombre, i) => ({ id: i + 1, nombre, categoria_id: 7, categoria: 'Dips Extra', descripcion: 'Dip de prueba', precio_base: '900.00', activo: true, disponible: true, imagen_url: null, variantes: [], ingredientes_quitables: [nombre] }));
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
      for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }, { width: 320, height: 740 }, { width: 390, height: 844, deviceScaleFactor: 2 }]) {
        const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, deviceScaleFactor: viewport.deviceScaleFactor || 1 }); const page = await context.newPage();
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
              const layout = await img.evaluate((node) => { const frame = node.parentElement.getBoundingClientRect(); const card = node.parentElement.parentElement.getBoundingClientRect(); const button = node.parentElement.parentElement.querySelector('button').getBoundingClientRect(); return { frameWidth: frame.width, frameHeight: frame.height, cardHeight: card.height, imageWidth: node.getBoundingClientRect().width, imageHeight: node.getBoundingClientRect().height, buttonWidth: button.width, buttonHeight: button.height, buttonOutside: button.left >= frame.right }; });
              assert.ok(layout.frameWidth <= 100 && layout.frameHeight <= 100, 'Cuadro compacto para una foto pequeña');
              assert.ok(layout.imageWidth / layout.frameWidth >= 0.98 && layout.imageHeight / layout.frameHeight >= 0.98, 'La foto aprovecha el cuadro sin márgenes grandes');
              assert.ok(layout.cardHeight < 250, 'La tarjeta no conserva el espacio vacío del cuadro grande');
              assert.ok(layout.buttonOutside && layout.buttonWidth >= 44 && layout.buttonHeight >= 44, 'Agregar no tapa la foto y conserva el área táctil');
            }
          }
          if (mode === 'clientes') {
            assert.equal(await page.locator('details, input[type=checkbox]').count(), 0, 'Las salsas no permiten personalizar');
            assert.equal(await page.getByText('Quitar ingredientes', { exact: true }).count(), 0);
            assert.equal(await page.getByText('Otros cambios se consultan por WhatsApp.', { exact: true }).count(), 0);
            for (const name of allSauces) await page.getByRole('heading', { name, exact: true }).waitFor();
          }
          assert.equal(loaded.size, 5);
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Sin desborde horizontal');
        }
        await page.screenshot({ path: path.join(evidence, mode + '-' + viewport.width + '-dpr' + (viewport.deviceScaleFactor || 1) + '.png'), fullPage: true, animations: 'disabled' });
        if (mode === 'clientes') {
          const add = page.getByRole('button', { name: 'Agregar Alioli al carrito', exact: true });
          await add.focus(); await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab');
          assert.ok(await add.evaluate((node) => node === document.activeElement), 'Tab permite alcanzar Agregar');
          await page.keyboard.press('Enter');
          await page.getByRole('button', { name: 'Abrir carrito, 1 productos', exact: true }).waitFor();
          for (const name of allSauces.filter((name) => name !== 'Alioli')) await page.getByRole('button', { name: 'Agregar ' + name + ' al carrito', exact: true }).click();
          await page.getByRole('button', { name: 'Abrir carrito, 6 productos', exact: true }).click();
          const cart = page.getByRole('dialog'); await cart.waitFor();
          assert.equal(await cart.locator('li').count(), 6, 'Se agregan las seis salsas completas');
          assert.equal(await cart.locator('li p').count(), 0, 'Sin notas de ingredientes retirados');
          for (const name of allSauces) await cart.getByRole('heading', { name, exact: true }).waitFor();
        }
        report.results.push({ mode, viewport: viewport.width, deviceScaleFactor: viewport.deviceScaleFactor || 1, fivePhotos: true, reload: true, wholeSaucesAdded: mode === 'clientes', noUpscaling: mode === 'clientes' });
        await context.close();
      }
    } finally { await server.close(); }
  }
  assert.deepEqual(report.pageErrors, []); assert.deepEqual(report.unknownRequests, []);
  assert.ok(report.images.length >= 30); assert.ok(report.images.every((entry) => entry.status === 200));
} catch (error) { report.failure = error.message; throw error; }
finally { await writeFile(path.join(evidence, 'report.json'), JSON.stringify(report, null, 2)); await browser?.close(); console.log('Evidencias: ' + evidence); }
