// Desde App/frontend: npm run test:caja-browser.
// Requiere Playwright y Chromium instalados externamente; MONU_PLAYWRIGHT_PATH permite
// usar un paquete existente. Todas las respuestas API son fixtures, sin backend ni BD.
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
const evidenceDir = path.join(tmpdir(), 'monu-caja-browser', `${Date.now()}-${process.pid}`);
await mkdir(evidenceDir, { recursive: true });
process.chdir(root);
const server = await createServer({
  root, configFile: path.join(root, 'vite.config.ts'), mode: 'personal',
  cacheDir: path.join(root, `node_modules/.vite-tests/caja-browser-${process.pid}`),
  plugins: [{ name: 'caja-browser-sin-backend', configResolved(config) { config.server.proxy = {}; } }],
  server: { host: '127.0.0.1', port: 0, open: false, hmr: false },
});
const permissions = ['caja.ver', 'caja.generar', 'caja.aprobar'];
const operator = { id: 4, username: 'caja-fixture', nombre: 'Caja', apellido: 'Fixture', rol: 'EMPLEADO', permisos: permissions };
const makeConsolidado = () => ({
  fecha: '2026-10-26', turno: 'NOCHE', desde: '2026-10-26T20:00:00', hasta: '2026-10-27T02:00:00',
  total_efectivo: '50.00', total_billeteras: '20.00', total_devoluciones: '5.00', total_general: '69.00',
  total_propinas: '4.00', cantidad_pedidos: 2, cantidad_pagos: 3, pagos_pendientes_conciliacion: 1,
  desglose_metodos: [{ metodo_pago: 'EFECTIVO', total: '50.00', cantidad: 2 }],
});
const makeCierre = (extra = {}) => ({
  id: 31, fecha: '2026-10-26', turno: 'NOCHE', abierto_en: '2026-10-26T20:00:00', cerrado_en: '2026-10-27T02:01:00',
  total_efectivo: '100.00', total_billeteras: '45.00', total_devoluciones: '5.00', total_general: '140.00',
  cantidad_pedidos: 3, estado: 'PENDIENTE_APROBACION', generado_por: 4, aprobado_por: null, aprobado_en: null,
  observaciones: 'Nota anterior conservada', ...extra,
});
const report = { startedAt: new Date().toISOString(), fixturesOnly: true, results: [], errors: [] };
let browser;
function deferred() { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; }
async function waitFor(check, description) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) { if (await check()) return; await new Promise((done) => setTimeout(done, 25)); }
  throw new Error(`No se cumplió: ${description}`);
}
async function visible(locator) { await locator.waitFor({ state: 'visible' }); }
async function screenshot(page, viewport, name) {
  const file = path.join(evidenceDir, `${viewport}-${name}.png`);
  await page.screenshot({ path: file, fullPage: true }); return file;
}

async function runViewport(name, viewport) {
  const context = await browser.newContext({ viewport, locale: 'es-AR', timezoneId: 'America/Argentina/Buenos_Aires', reducedMotion: 'reduce', serviceWorkers: 'block' });
  const state = { user: null, calls: [], unknown: [], errors: [], records: [], readFailure: null, generateFailure: null, approveFailure: null, readWait: null, writeWait: null };
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', (error) => state.errors.push(error.message));
  const cajaCalls = (method = 'GET') => state.calls.filter((call) => call.method === method && call.path.startsWith('/api/caja/'));
  const posts = (suffix) => cajaCalls('POST').filter((call) => call.path.endsWith(suffix));
  await context.route('**/*', async (route) => {
    const request = route.request(); const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/')) return url.origin === report.origin ? route.continue() : route.abort('blockedbyclient');
    const call = { method: request.method(), path: url.pathname, query: url.search, body: request.postDataJSON() };
    state.calls.push(call);
    const send = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (call.path === '/api/auth/me') return state.user ? send(state.user) : send({ detail: 'Sin sesión fixture' }, 401);
    if (call.path === '/api/auth/login') { state.user = { ...operator }; return send(state.user); }
    if (call.path === '/api/auth/logout') { state.user = null; return route.fulfill({ status: 204 }); }
    if (call.path === '/api/caja/turnos/actual/consolidado' || call.path === '/api/caja/turnos/consolidado') {
      await state.readWait?.promise;
      if (state.readFailure) {
        const status = state.readFailure; state.readFailure = null;
        if (status === 403) state.user = { ...operator, permisos: [] };
        return send({ detail: `Consulta fixture rechazada ${status}` }, status);
      }
      return send({ ...makeConsolidado(), ...(url.searchParams.get('fecha') ? { fecha: url.searchParams.get('fecha'), turno: url.searchParams.get('turno') } : {}) });
    }
    if (call.path === '/api/caja/cierres' && call.method === 'GET') {
      const { desde, hasta, estado } = Object.fromEntries(url.searchParams);
      return send(state.records.filter((record) => (!desde || record.fecha >= desde) && (!hasta || record.fecha <= hasta) && (!estado || record.estado === estado)));
    }
    if (call.path === '/api/caja/cierres/generar' && call.method === 'POST') {
      await state.writeWait?.promise;
      if (state.generateFailure) { const status = state.generateFailure; state.generateFailure = null; return send({ detail: `Generación fixture rechazada ${status}` }, status); }
      const record = makeCierre({ observaciones: call.body.observaciones || 'Nota anterior conservada' });
      state.records = [record]; return send(record, 201);
    }
    if (call.path === '/api/caja/cierres/31/aprobar' && call.method === 'POST') {
      await state.writeWait?.promise;
      if (state.approveFailure) { const status = state.approveFailure; state.approveFailure = null; return send({ detail: `Aprobación fixture rechazada ${status}` }, status); }
      const record = { ...state.records[0], estado: 'APROBADO', aprobado_por: 4, aprobado_en: '2026-10-27T03:00:00', observaciones: call.body.observaciones || state.records[0].observaciones };
      state.records = [record]; return send(record);
    }
    if (call.path === '/api/caja/cierres/31' && call.method === 'GET') return send(state.records[0] || makeCierre());
    // No se habilitan endpoints ajenos a Caja para este operador.
    state.unknown.push(call); return send({ detail: 'Endpoint sin fixture: bloqueado' }, 501);
  });
  const passed = (flow, details, image) => { report.results.push({ viewport: name, flow, status: 'passed', details, ...(image ? { screenshot: image } : {}) }); console.log(`${name}: ${flow}`); };
  try {
    await page.goto(`${report.origin}/dashboard/caja`);
    await visible(page.getByRole('heading', { name: 'Iniciar sesión' }));
    assert.equal(cajaCalls().length, 0);
    await page.getByLabel('Usuario', { exact: true }).focus(); await page.keyboard.type('caja-fixture');
    await page.keyboard.press('Tab'); await page.keyboard.type('clave-fixture'); await page.keyboard.press('Enter');
    await visible(page.getByRole('heading', { name: 'Caja', exact: true }));
    assert.equal(new URL(page.url()).pathname, '/dashboard/caja');
    passed('Ruta privada e inicio con teclado', 'Login real de UI usa sesión fixture y dirige a Caja.');

    await exerciseCaja(page, state, { cajaCalls, posts, passed, name });

    state.user = { ...operator, permisos: ['caja.ver'] };
    await page.goto(`${report.origin}/dashboard/caja`);
    await visible(page.getByRole('heading', { name: 'Caja', exact: true }));
    assert.equal(await page.getByRole('button', { name: /Generar cierre|Aprobar cierre/ }).count(), 0);
    passed('Permisos separados', 'caja.ver permite lectura y oculta generación y aprobación.');

    state.readFailure = 403;
    await page.getByRole('button', { name: 'Consultar consolidado', exact: true }).click();
    await visible(page.getByRole('heading', { name: 'Sin acceso a esta sección' }));
    assert.equal(await page.getByRole('heading', { name: 'Caja', exact: true }).count(), 0);
    passed('403 retira datos y revalida permisos', 'El error borra Caja y la sesión revalidada bloquea la ruta.');

    const beforeDenied = cajaCalls().length;
    await page.goto(`${report.origin}/dashboard/caja`);
    await visible(page.getByRole('heading', { name: 'Sin acceso a esta sección' }));
    assert.equal(cajaCalls().length, beforeDenied);
    await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click();
    await visible(page.getByRole('heading', { name: 'Iniciar sesión' }));
    passed('Ruta sin permiso y logout', 'Sin caja.ver no hay consultas y cerrar sesión vuelve a login.');
    assert.deepEqual(state.unknown, [], 'Sin llamadas a endpoints ajenos al fixture.');
    assert.deepEqual(state.errors, [], 'Sin excepciones del navegador.');
  } catch (error) {
    report.errors.push({ viewport: name, message: error.message, stack: error.stack, screenshot: await screenshot(page, name, 'fallo').catch(() => null) });
  } finally {
    state.readWait?.resolve(); state.writeWait?.resolve();
    report.results.push({ viewport: name, flow: 'Red aislada', status: state.unknown.length || state.errors.length ? 'failed' : 'passed', apiRequests: state.calls, unknownApi: state.unknown, runtimeErrors: state.errors });
    await context.close();
  }
}

async function exerciseCaja(page, state, { cajaCalls, posts, passed, name }) {
  const consult = page.getByRole('button', { name: 'Consultar consolidado', exact: true });
  await waitFor(async () => !(await consult.isDisabled()), 'consulta habilitada');
  state.readWait = deferred();
  const beforeRead = cajaCalls().length;
  await consult.click(); await waitFor(() => cajaCalls().length > beforeRead, 'lectura consolidado pendiente');
  assert.equal(await consult.isDisabled(), true);
  state.readWait.resolve(); state.readWait = null;
  await waitFor(async () => !(await consult.isDisabled()), 'fin de carga consolidado');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  passed('Carga y responsive', 'Consultar se bloquea mientras carga; sin desborde horizontal.', await screenshot(page, name, 'consolidado'));

  state.readFailure = 503;
  await consult.click();
  await visible(page.getByRole('alert').filter({ hasText: 'Consulta fixture rechazada 503' }));
  await consult.click();
  await waitFor(async () => !(await consult.isDisabled()), 'reintento consulta');
  passed('Lectura fallida y reintento', '503 permanece visible y una consulta explícita recupera el consolidado.');

  await page.getByLabel('Consulta', { exact: true }).selectOption('specific');
  await page.getByLabel('Fecha contable', { exact: true }).fill('2026-10-26');
  const beforePartial = cajaCalls().length;
  await consult.click();
  await visible(page.getByRole('alert').filter({ hasText: 'Seleccioná un turno válido.' }));
  assert.equal(cajaCalls().length, beforePartial);
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'caja-selection-error');
  await page.getByLabel('Turno', { exact: true }).selectOption('NOCHE');
  await consult.click();
  await visible(page.getByRole('button', { name: 'Generar cierre', exact: true }));
  assert.ok(state.calls.some((call) => call.path === '/api/caja/turnos/consolidado' && call.query === '?fecha=2026-10-26&turno=NOCHE'));
  await visible(page.getByText('26/10/2026 · Noche', { exact: true }));
  passed('Fecha y turno explícitos', 'Selección parcial no consulta; error recibe foco; Noche conserva la fecha contable del servidor.');

  const generate = page.getByRole('button', { name: 'Generar cierre', exact: true });
  await generate.click();
  let dialog = page.getByRole('dialog'); await visible(dialog);
  assert.equal(await dialog.evaluate((element) => element.contains(document.activeElement)), true);
  await page.keyboard.press('Escape'); await dialog.waitFor({ state: 'hidden' });
  assert.equal(await generate.evaluate((element) => element === document.activeElement), true);
  await generate.click(); dialog = page.getByRole('dialog'); await visible(dialog);
  const focusable = dialog.locator('button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), a[href]');
  await focusable.first().focus(); await page.keyboard.press('Shift+Tab');
  // showModal mantiene inerte el documento; Chromium permite pasar a su propia
  // barra de navegador (activeElement BODY), sin enfocar controles del fondo.
  assert.equal(await dialog.evaluate((element) => element.contains(document.activeElement) || document.activeElement === document.body), true);
  await page.keyboard.press('Tab');
  assert.equal(await focusable.first().evaluate((element) => element === document.activeElement), true);
  await dialog.getByLabel('Observaciones opcionales', { exact: true }).fill('Nota de generación fixture');
  state.writeWait = deferred();
  await dialog.getByRole('button', { name: 'Confirmar generación', exact: true }).evaluate((button) => { button.click(); button.click(); });
  await waitFor(() => posts('/generar').length === 1, 'un POST generación');
  assert.equal(await dialog.getByRole('button', { name: 'Procesando…', exact: true }).isDisabled(), true);
  state.writeWait.resolve(); state.writeWait = null;
  await visible(page.getByRole('heading', { name: 'Detalle del cierre #31', exact: true }));
  assert.deepEqual(posts('/generar')[0].body, { fecha: '2026-10-26', turno: 'NOCHE', observaciones: 'Nota de generación fixture' });
  passed('Generación y confirmación accesible', 'Escape restaura foco; doble submit envía un POST concreto con notas; muestra cierre confirmado.', await screenshot(page, name, 'cierre-generado'));

  const approve = page.getByRole('button', { name: 'Aprobar cierre', exact: true }).first();
  await approve.click(); dialog = page.getByRole('dialog'); await visible(dialog);
  await dialog.getByLabel('Observaciones opcionales', { exact: true }).fill('Nota de aprobación conservada');
  await dialog.getByRole('checkbox', { name: 'Confirmo reemplazar las observaciones registradas por el texto nuevo.' }).check();
  state.approveFailure = 409;
  await dialog.getByRole('button', { name: 'Confirmar aprobación', exact: true }).click();
  await visible(page.getByRole('alert').filter({ hasText: 'Aprobación fixture rechazada 409' }));
  assert.equal(await page.getByRole('dialog').getByLabel('Observaciones opcionales', { exact: true }).inputValue(), 'Nota de aprobación conservada');
  state.writeWait = deferred();
  await dialog.getByRole('button', { name: 'Confirmar aprobación', exact: true }).evaluate((button) => { button.click(); button.click(); });
  await waitFor(() => posts('/aprobar').length === 2, 'un POST adicional aprobación');
  state.writeWait.resolve(); state.writeWait = null;
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  assert.deepEqual(posts('/aprobar')[1].body, { aprobado_por: 4, observaciones: 'Nota de aprobación conservada' });
  assert.equal(await page.getByRole('button', { name: 'Aprobar cierre', exact: true }).count(), 0);
  passed('Aprobación, error y notas', '409 conserva observaciones; reintento confirmado usa usuario de sesión y bloquea nueva aprobación.', await screenshot(page, name, 'cierre-aprobado'));

  const historyButton = page.getByRole('button', { name: 'Consultar historial', exact: true });
  await page.getByLabel('Desde', { exact: true }).fill('2026-10-27');
  await page.getByLabel('Hasta', { exact: true }).fill('2026-10-26');
  const beforeInvalid = cajaCalls().length;
  await historyButton.click();
  await visible(page.getByRole('alert').filter({ hasText: /rango|Hasta debe/i }));
  assert.equal(cajaCalls().length, beforeInvalid);
  await page.getByLabel('Desde', { exact: true }).fill('2026-10-26');
  await page.getByLabel('Estado', { exact: true }).selectOption('APROBADO');
  await historyButton.click();
  const detailButton = page.getByRole('button', { name: /Ver detalle/ }).first();
  await visible(detailButton); await detailButton.click();
  await visible(page.getByRole('heading', { name: 'Detalle del cierre #31', exact: true }));
  assert.ok(state.calls.some((call) => call.path === '/api/caja/cierres' && call.query === '?desde=2026-10-26&hasta=2026-10-26&estado=APROBADO'));
  passed('Historial filtrado y detalle', 'Rango invertido se rechaza sin red; fechas y estado llegan a la API; abre detalle por ID.');
}

try {
  await server.listen();
  report.origin = `http://127.0.0.1:${server.httpServer.address().port}`;
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
