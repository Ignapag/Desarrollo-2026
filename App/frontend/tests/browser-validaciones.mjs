// Ejecutar desde App/frontend: node tests/browser-validaciones.mjs
// Sólo fixtures: no requiere backend ni base de datos. Evidencias: TEMP/monu-browser-audit.
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
const evidenceDir = path.join(tmpdir(), 'monu-browser-audit', `${Date.now()}-${process.pid}`);
await mkdir(evidenceDir, { recursive: true });
process.chdir(root);
const server = await createServer({
  root, configFile: path.join(root, 'vite.config.ts'),
  mode: 'development', cacheDir: path.join(root, `node_modules/.vite-tests/browser-${process.pid}`),
  plugins: [{ name: 'browser-audit-no-backend', configResolved(config) { config.server.proxy = {}; } }],
  server: { host: '127.0.0.1', port: 5187, strictPort: true, open: false, hmr: false, watch: { ignored: ['**/src/**'] } },
});
let browser;
const report = { startedAt: new Date().toISOString(), fixturesOnly: true, origin: 'http://127.0.0.1:5187', results: [], errors: [] };
const permissions = ['pedidos.ver', 'pedidos.cambiar_estado', 'clientes.ver', 'stock.ver', 'stock.gestionar', 'stock.reponer', 'productos.gestionar', 'productos.ver_receta', 'pagos.ver', 'pagos.registrar', 'pagos.conciliar', 'reportes.ver', 'reportes.financieros'];
const admin = { id: 19, username: 'auditoria', nombre: 'Auditoría', apellido: 'Local', rol: 'ADMINISTRADOR', permisos: permissions };
const product = { id: 1, categoria_id: 1, categoria: 'Nuestras Burgers', nombre: 'Burger de prueba', descripcion: 'Producto de fixture', precio_base: '12000', activo: true, disponible: true, ingredientes_quitables: ['Cheddar'], variantes: [] };
const ingredient = { id: 1, nombre: 'Pan de fixture', unidad_medida: 'UNIDAD', cantidad_actual: 10, umbral_minimo: 2, nivel: 'NORMAL' };
const dashboard = { fecha_desde: '2026-10-01', fecha_hasta: '2026-10-27', pedidos_dia: 0, pedidos_semana: 0, pedidos_mes: 0, alertas_stock: [], ingredientes_criticos: [], ranking_productos: [], actualizado_en: '2026-10-27T12:00:00Z', ingreso_neto_confirmado: '0', ingresos_por_metodo: [] };
function deferred() { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; }
async function waitFor(check, description) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) { if (await check()) return; await new Promise((done) => setTimeout(done, 25)); }
  throw new Error(`No se cumplió: ${description}`);
}
async function visible(locator) { await locator.waitFor({ state: 'visible', timeout: 10000 }); }
async function screenshot(page, size, name) {
  const file = path.join(evidenceDir, `${size}-${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}
async function runViewport(name, viewport) {
  const context = await browser.newContext({ viewport, reducedMotion: 'reduce', locale: 'es-AR', serviceWorkers: 'block' });
  const state = { user: null, loginCount: 0, calls: [], unknown: [], external: [], runtimeErrors: [], stockWait: null, draftWait: null, productDelayMs: 0 };
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  page.setDefaultNavigationTimeout(15000);
  page.on('pageerror', (error) => state.runtimeErrors.push(error.message));
  await context.route('**/*', async (route) => {
    const request = route.request(); const url = new URL(request.url());
    if (url.pathname.startsWith('/api/')) {
      const call = { method: request.method(), path: url.pathname, query: url.search, body: request.postDataJSON() };
      state.calls.push(call);
      const send = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (url.pathname === '/api/auth/me') return state.user ? send(state.user) : send({ detail: 'Sin sesión de prueba' }, 401);
      if (url.pathname === '/api/auth/login') {
        state.loginCount += 1;
        if (state.loginCount === 1) return send({ detail: 'Credenciales de prueba rechazadas' }, 401);
        state.user = admin; return send(admin);
      }
      if (url.pathname === '/api/auth/logout') { state.user = null; return route.fulfill({ status: 204 }); }
      if (url.pathname === '/api/productos' && request.method() === 'GET') {
        if (state.productDelayMs) await new Promise((done) => setTimeout(done, state.productDelayMs));
        return send([product]);
      }
      if (url.pathname === '/api/stock/ingredientes' && request.method() === 'GET') return send([ingredient]);
      if (url.pathname === '/api/stock/ingredientes' && request.method() === 'POST') {
        await state.stockWait?.promise; return send({ detail: 'Stock simulado no disponible' }, 503);
      }
      if (url.pathname === '/api/pedidos' && request.method() === 'GET') return send([]);
      if (url.pathname === '/api/reportes/dashboard') return send(dashboard);
      if (url.pathname === '/api/reportes/ventas' || url.pathname === '/api/reportes/rentabilidad') return send([]);
      if (url.pathname === '/api/chat-demo/config') return send({ habilitado: false });
      if (url.pathname === '/api/whatsapp/avisos' && request.method() === 'GET') return send({ comprobantes_pendientes: 0, atenciones_pendientes: 0 });
      if (url.pathname === '/api/whatsapp/borradores') {
        await state.draftWait?.promise; return send({ detail: 'Borrador simulado no disponible' }, 503);
      }
      state.unknown.push(call); return send({ detail: 'API sin fixture: acceso bloqueado' }, 501);
    }
    if (url.origin === report.origin) return route.continue();
    state.external.push(request.url()); return route.abort('blockedbyclient');
  });
  const passed = (flow, details, image) => { report.results.push({ viewport: name, flow, status: 'passed', details, ...(image ? { screenshot: image } : {}) }); console.log(`${name}: ${flow}`); };
  try {
    await page.goto(`${report.origin}/dashboard/inventory`);
    await visible(page.getByRole('heading', { name: 'Iniciar sesión' }));
    assert.equal(new URL(page.url()).pathname, '/login');
    assert.equal(state.calls.filter((call) => call.path.includes('/stock/')).length, 0);
    passed('Ruta privada sin sesión', 'Redirige a login sin consultar inventario.');

    // Teclado real: usuario → Tab → contraseña → Enter; reintento sin perder datos.
    await page.getByLabel('Usuario', { exact: true }).focus();
    await page.keyboard.type('auditoria'); await page.keyboard.press('Tab');
    await page.keyboard.type('clave-fixture'); await page.keyboard.press('Enter');
    await visible(page.getByRole('alert').filter({ hasText: 'Credenciales de prueba rechazadas' }));
    assert.equal(await page.getByLabel('Usuario', { exact: true }).inputValue(), 'auditoria');
    assert.equal(await page.getByLabel('Contraseña', { exact: true }).inputValue(), 'clave-fixture');
    const loginImage = await screenshot(page, name, 'login-error');
    await page.getByLabel('Contraseña', { exact: true }).focus(); await page.keyboard.press('Enter');
    await visible(page.getByRole('heading', { name: 'Panel de Control' }));
    assert.equal(state.loginCount, 2);
    passed('Login con teclado y reintento', 'Error 401 conserva usuario/contraseña; segundo Enter inicia sesión.', loginImage);

    state.user = { ...admin, id: 20, rol: 'EMPLEADO', permisos: ['pedidos.ver'] };
    const beforeRestricted = state.calls.filter((call) => call.path.includes('/stock/')).length;
    await page.goto(`${report.origin}/dashboard/inventory`);
    await visible(page.getByRole('heading', { name: 'Sin acceso a esta sección' }));
    assert.equal(state.calls.filter((call) => call.path.includes('/stock/')).length, beforeRestricted);
    passed('Ruta directa con rol restringido', 'EMPLEADO sin stock.ver ve rechazo y no consulta inventario.', await screenshot(page, name, 'permiso-rechazado'));

    state.user = admin;
    await page.goto(`${report.origin}/dashboard/inventory`);
    await visible(page.getByText('Pan de fixture', { exact: true }));
    await page.getByRole('button', { name: 'Añadir Insumo', exact: true }).click();
    const inventory = page.getByRole('dialog', { name: 'Añadir Nuevo Insumo' });
    await visible(inventory);
    await inventory.getByLabel('Nombre', { exact: true }).fill('   ');
    await inventory.getByLabel('Stock Inicial', { exact: true }).fill('no');
    await inventory.getByLabel('Stock Mínimo', { exact: true }).fill('0');
    await inventory.getByRole('button', { name: 'Guardar Insumo' }).click();
    await visible(inventory.getByText('Ingresá el nombre del insumo.', { exact: true }));
    assert.equal(state.calls.filter((call) => call.method === 'POST' && call.path === '/api/stock/ingredientes').length, 0);
    assert.ok(await page.evaluate(() => document.activeElement?.textContent.includes('Revisá los campos indicados.')));
    await inventory.getByLabel('Nombre', { exact: true }).fill('Tomate conservado');
    await inventory.getByLabel('Unidad de medida').selectOption('KG');
    await inventory.getByLabel('Stock Inicial', { exact: true }).fill('1,5');
    await inventory.getByLabel('Stock Mínimo', { exact: true }).fill('1/2');
    state.stockWait = deferred();
    await inventory.locator('form').evaluate((form) => { form.requestSubmit(); form.requestSubmit(); });
    await waitFor(() => state.calls.filter((call) => call.method === 'POST' && call.path === '/api/stock/ingredientes').length === 1, 'una única escritura de stock');
    assert.equal(await inventory.getByRole('button', { name: 'Guardando…' }).isDisabled(), true);
    const stockCall = state.calls.find((call) => call.method === 'POST' && call.path === '/api/stock/ingredientes');
    assert.equal(stockCall.body.cantidad_actual, 1.5); assert.equal(stockCall.body.umbral_minimo, 0.5);
    state.stockWait.resolve();
    await visible(inventory.getByText('Stock simulado no disponible', { exact: true }));
    assert.equal(await inventory.getByLabel('Nombre', { exact: true }).inputValue(), 'Tomate conservado');
    assert.equal(await inventory.getByLabel('Stock Inicial', { exact: true }).inputValue(), '1,5');
    assert.ok(await page.evaluate(() => document.activeElement?.textContent.includes('Stock simulado no disponible')));
    passed('Inventario: validación, doble envío y error', 'Blancos/número inválido/cero rechazados; coma y fracción normalizadas; dos submits generan un POST; 503 conserva formulario y enfoca error.', await screenshot(page, name, 'inventario-error'));
    await inventory.getByRole('button', { name: 'Cerrar formulario de insumo' }).click();

    await page.goto(`${report.origin}/dashboard/catalog`);
    await visible(page.getByRole('heading', { name: 'Catálogo de Menú' }));
    await page.getByRole('button', { name: 'Nuevo Producto' }).click();
    await page.getByLabel('Nombre', { exact: true }).fill('   ');
    await page.getByLabel('Precio base ($)', { exact: true }).fill('-1');
    await page.getByRole('button', { name: 'Guardar Producto', exact: true }).click();
    await visible(page.locator('#new-product-name-error').filter({ hasText: 'Ingresá un nombre' }));
    await visible(page.locator('#new-product-price-error').filter({ hasText: 'mayor que cero' }));
    assert.equal(state.calls.filter((call) => call.method === 'POST' && call.path === '/api/productos').length, 0);
    assert.ok(await page.evaluate(() => document.activeElement?.textContent.includes('Ingresá un nombre')));
    if (viewport.width === 375) {
      const tableContainer = page.locator('table').locator('..');
      const layout = await tableContainer.evaluate((element) => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth, overflowX: getComputedStyle(element).overflowX, tabIndex: element.tabIndex, label: element.getAttribute('aria-label') }));
      if (layout.scrollWidth > layout.clientWidth) {
        assert.match(layout.overflowX, /^(auto|scroll)$/, `La tabla móvil debe permitir desplazar las acciones: ${JSON.stringify(layout)}`);
        assert.equal(layout.tabIndex, 0, 'La región de tabla debe permitir foco por teclado.');
        assert.ok(layout.label, 'La región desplazable necesita nombre accesible.');
        await tableContainer.focus(); await page.keyboard.press('ArrowRight');
        await waitFor(() => tableContainer.evaluate((element) => element.scrollLeft > 0), 'tabla móvil desplazable por teclado');
      }
    }
    passed('Catálogo: validación y acciones móviles', 'Nombre en blanco y precio negativo muestran errores asociados; no envían POST; resumen recibe foco. En móvil la tabla desbordada permite acceso por teclado y desplazamiento.', await screenshot(page, name, 'catalogo-validacion'));

    // La sesión llega antes que productos para reproducir la carrera de montaje.
    state.productDelayMs = 100;
    await page.goto(`${report.origin}/menu`);
    await visible(page.getByRole('button', { name: 'Agregar Burger de prueba al carrito', exact: true }));
    state.productDelayMs = 0;
    passed('Menú con sesión del personal', 'El catálogo termina de cargar con ADMINISTRADOR aunque /auth/me resuelva antes que productos.');

    // El recorrido de clientes usa una sesión anónima, como el portal público.
    state.user = null;
    await page.goto(`${report.origin}/menu`);
    await visible(page.getByRole('button', { name: 'Agregar Burger de prueba al carrito', exact: true }));
    await page.getByLabel('Personalizar Burger de prueba').click();
    await page.getByRole('checkbox', { name: 'Sin Cheddar', exact: true }).check();
    await page.getByRole('button', { name: 'Agregar Burger de prueba al carrito', exact: true }).click();
    const cartTrigger = page.getByRole('button', { name: 'Abrir carrito, 1 productos' });
    await cartTrigger.click();
    const cart = page.getByRole('dialog', { name: 'Tu pedido' }); await visible(cart);
    assert.equal(await page.getByRole('button', { name: 'Cerrar carrito', exact: true }).evaluate((element) => element === document.activeElement), true);
    await cart.getByLabel('Nombre', { exact: true }).fill('   ');
    await cart.getByLabel('Apellido', { exact: true }).fill('Prueba');
    await cart.getByLabel('Tu WhatsApp', { exact: true }).fill('2215550101');
    await cart.locator('#checkout-delivery').selectOption('DELIVERY');
    await cart.locator('#checkout-zone').selectOption('Ensenada');
    await cart.getByLabel('Calle', { exact: true }).fill('   ');
    await cart.getByLabel('Número', { exact: true }).fill('123');
    await cart.getByRole('button', { name: 'Continuar por WhatsApp', exact: true }).click();
    assert.equal(await page.evaluate(() => document.activeElement.id), 'checkout-first-name');
    await cart.locator('#checkout-first-name').fill('Ana');
    await cart.getByRole('button', { name: 'Continuar por WhatsApp', exact: true }).click();
    assert.equal(await page.evaluate(() => document.activeElement.id), 'checkout-street');
    assert.equal(state.calls.filter((call) => call.path === '/api/whatsapp/borradores').length, 0);
    await cart.locator('#checkout-street').fill('Calle de prueba');
    state.draftWait = deferred();
    await cart.locator('form').evaluate((form) => { form.requestSubmit(); form.requestSubmit(); });
    await waitFor(() => state.calls.filter((call) => call.path === '/api/whatsapp/borradores').length === 1, 'un único borrador');
    state.draftWait.resolve();
    await visible(cart.getByRole('alert').filter({ hasText: 'Borrador simulado no disponible' }));
    assert.equal(await cart.locator('#checkout-first-name').inputValue(), 'Ana');
    assert.equal(await cart.locator('#checkout-street').inputValue(), 'Calle de prueba');
    await visible(cart.getByText('Sin Cheddar', { exact: true }));
    assert.ok(await page.evaluate(() => document.activeElement?.textContent.includes('Borrador simulado no disponible')));
    assert.equal(state.calls.find((call) => call.path === '/api/whatsapp/borradores').body.items[0].aclaraciones, 'Sin Cheddar');
    passed('Carrito: blancos, dirección, personalización y error', 'Nombre/calle con espacios enfocan su campo; 503 conserva contacto, dirección y Sin Cheddar; doble submit genera un borrador; error enfocado.', await screenshot(page, name, 'carrito-error'));
    await cart.getByRole('button', { name: 'Cerrar carrito', exact: true }).click();
    assert.equal(await cartTrigger.evaluate((element) => element === document.activeElement), true);
    passed('Carrito: foco al cerrar', 'Cerrar el dialog devuelve el foco al botón que abrió el carrito.');
    assert.deepEqual(state.unknown, [], 'Todos los endpoints consultados tienen fixture explícito.');
    assert.deepEqual(state.runtimeErrors, [], 'Sin excepciones de navegador.');
  } catch (error) {
    report.errors.push({ viewport: name, message: error.message, stack: error.stack, screenshot: await screenshot(page, name, 'fallo').catch(() => null) });
  } finally {
    report.results.push({ viewport: name, flow: 'Red aislada', status: state.unknown.length ? 'failed' : 'passed', apiRequests: state.calls, unknownApi: state.unknown, externalBlocked: state.external, runtimeErrors: state.runtimeErrors });
    state.stockWait?.resolve(); state.draftWait?.resolve();
    await context.close();
  }
}
try {
  await server.listen();
  browser = await chromium.launch({ headless: true, ...(process.env.MONU_CHROMIUM_PATH ? { executablePath: process.env.MONU_CHROMIUM_PATH } : {}) });
  await runViewport('desktop', { width: 1440, height: 1000 });
  await runViewport('mobile375', { width: 375, height: 812 });
} catch (error) { report.errors.push({ message: error.message, stack: error.stack }); }
finally {
  report.finishedAt = new Date().toISOString();
  await writeFile(path.join(evidenceDir, 'evidence.json'), JSON.stringify(report, null, 2));
  await browser?.close(); await server.close();
}
console.log(JSON.stringify({ evidenceDir, checks: report.results.filter((result) => result.status === 'passed').length, errors: report.errors }, null, 2));
if (report.errors.length || report.results.some((result) => result.status === 'failed')) process.exitCode = 1;
