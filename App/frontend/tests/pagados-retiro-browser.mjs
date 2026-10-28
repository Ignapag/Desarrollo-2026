// Sólo fixtures locales: prueba pagos y retiro sin backend ni base de datos.
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
const evidence = path.join(tmpdir(), 'monu-pagados-retiro', Date.now() + '-' + process.pid);
await mkdir(evidence, { recursive: true });
const server = await createServer({ root, configFile: path.join(root, 'vite.config.ts'), mode: 'personal',
  cacheDir: path.join(root, 'node_modules/.vite-tests/pagados-retiro-' + process.pid),
  plugins: [{ name: 'pagados-sin-backend', configResolved(config) { config.server.proxy = {}; } }],
  server: { host: '127.0.0.1', port: 0, hmr: false, open: false },
});
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
const user = { id: 1, username: 'pagos-fixture', nombre: 'Pagos', apellido: 'Prueba', rol: 'EMPLEADO', permisos: ['pedidos.ver', 'pedidos.cambiar_estado', 'pagos.ver', 'pagos.registrar', 'pagos.conciliar'] };
const makeOrder = (id, estado, extra = {}) => ({ id, numero: id, version: 1, cliente_id: 1, cliente: 'Cliente de prueba', telefono: null,
  tipo_entrega: 'RETIRO', direccion_id: null, direccion: null, estado, metodo_pago_acordado: 'EFECTIVO',
  total: '1000.00', subtotal: '1000.00', costo_envio: '0.00', neto_cobrado: '0.00', saldo_pendiente: '1000.00',
  creado_en: new Date().toISOString(), items: [{ id: id * 10, cantidad: 1, nombre_producto: 'Clásica' }], pagos: [], historial: [], ...extra });
const paid = { neto_cobrado: '1000.00', saldo_pendiente: '0.00' };
const report = { fixturesOnly: true, results: [], pageErrors: [], unknownRequests: [] };
let browser;
try {
  await server.listen(); const origin = 'http://127.0.0.1:' + server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, ...(process.env.MONU_CHROMIUM_PATH ? { executablePath: process.env.MONU_CHROMIUM_PATH } : {}) });
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }, { width: 320, height: 740 }]) {
    const context = await browser.newContext({ viewport }); const page = await context.newPage();
    page.on('pageerror', (error) => report.pageErrors.push(error.message));
    const orders = [makeOrder(1, 'PENDIENTE'), makeOrder(2, 'CONFIRMADO'), makeOrder(3, 'PENDIENTE', paid), makeOrder(4, 'EN_PREPARACION', paid),
      makeOrder(5, 'LISTO', { ...paid, metodo_pago_acordado: 'TRANSFERENCIA' }), makeOrder(6, 'LISTO', { metodo_pago_acordado: 'TRANSFERENCIA' }), makeOrder(7, 'LISTO')];
    const writes = []; const paymentSeen = deferred(); const releasePayment = deferred();
    await context.route('**/*', async (route) => {
      const request = route.request(); const url = new URL(request.url());
      if (url.origin !== origin) return route.abort();
      if (!url.pathname.startsWith('/api/')) return route.continue();
      const send = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (request.method() === 'GET') {
        if (url.pathname === '/api/auth/me') return send(user);
        if (url.pathname === '/api/pedidos') return send(orders.filter((order) => !['ENTREGADO', 'CANCELADO'].includes(order.estado)));
        const found = orders.find((order) => url.pathname === '/api/pedidos/' + order.id);
        if (found) return send(found);
      }
      if (request.method() === 'POST' && url.pathname === '/api/pagos/efectivo') {
        const body = request.postDataJSON(); writes.push({ path: url.pathname, body }); paymentSeen.resolve();
        await releasePayment.promise;
        assert.equal(body.pedido_id, 1); assert.equal(body.conciliar_inmediato, true); assert.ok(body.clave_operacion);
        const order = orders[0]; Object.assign(order, paid, { version: 2 });
        const pago = { id: 501, pedido_id: 1, tipo: 'COBRO', estado: 'CONCILIADO', metodo_pago: 'EFECTIVO', monto: '1000.00' };
        order.pagos = [pago];
        return send({ pago, pedido: order, detalle: { monto_cobrado: '1000.00', monto_recibido: '1000.00', propina: '0.00', vuelto: '0.00', saldo_restante: '0.00', total_pedido: '1000.00' } });
      }
      if (request.method() === 'PATCH' && /^\/api\/pedidos\/[0-9]+\/estado$/.test(url.pathname)) {
        const body = request.postDataJSON(); const order = orders.find((candidate) => url.pathname === '/api/pedidos/' + candidate.id + '/estado');
        writes.push({ path: url.pathname, body });
        assert.equal(body.estado, 'ENTREGADO'); assert.equal(body.estado_esperado, 'LISTO'); assert.equal(body.version_esperada, order.version);
        if (order.metodo_pago_acordado !== 'EFECTIVO' && order.saldo_pendiente !== '0.00') return send({ mensaje: 'El retiro requiere pago completo o cobro en efectivo' }, 409);
        order.estado = 'ENTREGADO'; order.version += 1; return send(order);
      }
      report.unknownRequests.push(url.pathname); return send({}, 404);
    });
    await page.goto(origin + '/dashboard/orders');
    const status = (name) => page.getByRole('button', { name: new RegExp('^' + name + ':') });
    await status('Nuevos').waitFor();
    await page.waitForFunction(() => document.querySelector('[aria-label^="Nuevos: 2 pedidos"]'));
    assert.match(await status('PAGADOS').getAttribute('aria-label'), /1 pedido/);
    assert.equal(await page.getByRole('button', { name: /^Confirmados:/ }).count(), 0);
    await status('Nuevos').click(); await page.getByRole('button', { name: 'Abrir pedido #1', exact: true }).click();
    let dialog = page.getByRole('dialog', { name: 'Pedido #1', exact: true });
    await dialog.getByRole('button', { name: /^Cobrar .* en efectivo$/ }).click(); await paymentSeen.promise;
    await dialog.waitFor({ state: 'detached' });
    assert.match(await status('PAGADOS').getAttribute('aria-label'), /1 pedido/, 'Antes de confirmar no inventa pago');
    releasePayment.resolve();
    await page.waitForFunction(() => document.querySelector('[aria-label^="PAGADOS: 2 pedidos"]'));
    assert.match(await status('Nuevos').getAttribute('aria-label'), /1 pedido/);
    await status('PAGADOS').click();
    assert.equal(await status('PAGADOS').getAttribute('aria-pressed'), 'true');
    assert.equal(await status('Nuevos').getAttribute('aria-pressed'), 'false');
    assert.equal(await page.getByRole('button', { name: 'Abrir pedido #1', exact: true }).count(), 1);
    assert.equal(await page.getByRole('button', { name: 'Abrir pedido #3', exact: true }).count(), 1);
    await page.screenshot({ path: path.join(evidence, viewport.width + '-pagados.png'), fullPage: true, animations: 'disabled' });
    await status('Listos').click(); await page.getByRole('button', { name: 'Abrir pedido #6', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Pedido #6', exact: true });
    await dialog.getByText(/Para registrar el retiro, confirmá el pago completo/).waitFor();
    assert.equal(await dialog.getByRole('button', { name: 'Registrar retiro entregado', exact: true }).count(), 0);
    await dialog.getByRole('button', { name: 'Cerrar detalle', exact: true }).click();
    for (const id of [5, 7]) {
      await page.getByRole('button', { name: 'Abrir pedido #' + id, exact: true }).click();
      dialog = page.getByRole('dialog', { name: 'Pedido #' + id, exact: true });
      await dialog.getByRole('button', { name: 'Registrar retiro entregado', exact: true }).click();
      await dialog.waitFor({ state: 'detached' });
      await page.getByRole('button', { name: 'Abrir pedido #' + id, exact: true }).waitFor({ state: 'detached' });
    }
    assert.deepEqual(writes.map((entry) => entry.path), ['/api/pagos/efectivo', '/api/pedidos/5/estado', '/api/pedidos/7/estado']);
    assert.equal(orders[6].neto_cobrado, '0.00', 'Retirar en efectivo no inventa un ingreso de dinero');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    report.results.push({ viewport: viewport.width, paymentMovesOnce: true, pickupPaid: true, pickupCash: true, transferBlocked: true, noDuplicatePayments: true });
    await context.close();
  }
  assert.deepEqual(report.pageErrors, []); assert.deepEqual(report.unknownRequests, []);
} catch (error) { report.failure = error.message; throw error; }
finally { await writeFile(path.join(evidence, 'report.json'), JSON.stringify(report, null, 2)); await browser?.close(); await server.close(); console.log('Evidencias: ' + evidence); }
