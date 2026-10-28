import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';
let server, dom, createRoot, Inventory, model, UserFacingError;
const admin = { id: 1, backendRole: 'ADMINISTRADOR' };
const carne = () => ({ id: 12, name: 'Carne', category: 'GR', stock: 200, min: 100, status: 'estable' });
const find = (container, tag) => elements(container, (node) => node.localName === tag);
const button = (container, text) => find(container, 'button').find((node) => node.textContent.trim() === text || reactProps(node)['aria-label'] === text);
const change = async (node, value) => act(async () => reactProps(node).onChange({ target: { value } }));
const submit = () => reactProps(find(document.body, 'form')[0]).onSubmit({ preventDefault() {} });
before(async () => {
  dom = installMinimalDom(); ({ createRoot } = await import('react-dom/client'));
  globalThis.__replenishArea = { user: admin, data: null, toasts: [] };
  server = await createTestServer({ configFile: false, plugins: [{ name: 'replenish-area', enforce: 'pre', resolveId(source) { return source === 'sonner' ? '\0replenish-toast' : null; }, load(id) {
    if (id === '\0replenish-toast') return 'export const toast={error(...args){globalThis.__replenishArea.toasts.push(["error",...args])},success(...args){globalThis.__replenishArea.toasts.push(["success",...args])},info(){}};';
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return 'export const useAuth=()=>({user:globalThis.__replenishArea.user,refreshSession:async()=>{}});';
    if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) return 'export const useData=()=>globalThis.__replenishArea.data;';
    return null;
  } }, react()], ssr: { noExternal: ['sonner'] }, server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Inventory } = await server.ssrLoadModule('/src/inventory/Inventory.jsx'));
  model = await server.ssrLoadModule('/src/inventory/replenishment.js');
  ({ UserFacingError } = await server.ssrLoadModule('/src/shared/api/userErrors.js'));
});
after(async () => { delete globalThis.__replenishArea; await server?.close(); dom?.restore(); });

async function mount(t, { user = admin, replenishIngredient = async () => ({ stock: 0, movementId: 1 }), inventory = [carne()] } = {}) {
  const area = globalThis.__replenishArea;
  area.user = user; area.toasts = [];
  area.data = { state: { inventory, inventoryStatus: 'ready' }, refreshInventory: async () => {}, createIngredient: async () => {}, replenishIngredient };
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  const render = () => act(async () => root.render(createElement(MemoryRouter, null, createElement(Inventory))));
  await render();
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return { container, render };
}
async function openDialog(container) {
  const trigger = button(container, 'Reponer una cantidad de Carne');
  await act(async () => reactProps(trigger).onClick({ currentTarget: trigger }));
  return { trigger, input: find(container, 'input')[0] };
}

test('la cantidad acepta enteros y decimales con coma o punto, hasta 3 decimales', () => {
  for (const [text, amount] of [['2500', '2500'], ['2,5', '2.5'], ['0,125', '0.125'], ['12', '12'], [' 7.25 ', '7.25'], ['0001', '1']]) {
    const parsed = model.parseReplenishQuantity(text);
    assert.equal(parsed.valid, true, text); assert.equal(parsed.amount, amount, text);
  }
});

test('la cantidad rechaza vacío, texto, negativos, cero, exceso de decimales, fracciones y miles ambiguos', () => {
  const cases = { '': /Ingresá/, '   ': /Ingresá/, abc: /solo números/, '1e3': /solo números/, '-5': /mayor que cero/, '0': /mayor que cero/, '0,000': /mayor que cero/, '0,0001': /3 decimales/, '1/4': /solo números/, '2.500': /millar o un decimal/, '1000000000': /máximo/, 'Infinity': /solo números/ };
  for (const [text, message] of Object.entries(cases)) {
    const parsed = model.parseReplenishQuantity(text);
    assert.equal(parsed.valid, false, text); assert.match(parsed.error, message, text);
  }
});

test('el plan calcula el saldo exacto, marca cantidades grandes por unidad y evita desbordes', () => {
  const plan = model.replenishmentPlan({ ...carne(), stock: 0.1 }, '0,2');
  assert.equal(model.formatScaled(plan.resulting), '0,3');
  assert.equal(model.replenishmentPlan(carne(), '4999').large, false);
  assert.equal(model.replenishmentPlan(carne(), '5000').large, true);
  assert.equal(model.replenishmentPlan({ ...carne(), category: 'KG' }, '50').large, true);
  assert.equal(model.replenishmentPlan({ ...carne(), category: 'UNIDAD' }, '12').large, false);
  assert.match(model.replenishmentPlan({ ...carne(), stock: 999999999 }, '1').error, /superaría el máximo/);
  assert.equal(model.replenishmentSummary(carne(), model.replenishmentPlan(carne(), '2500')), 'Vas a sumar 2.500 g a Carne; quedará en 2.700 g.');
  assert.equal(model.replenishmentSummary({ ...carne(), name: 'Pan', category: 'UNIDAD', stock: 0 }, model.replenishmentPlan({ ...carne(), category: 'UNIDAD', stock: 0 }, '1')), 'Vas a sumar 1 unidad a Pan; quedará en 1 unidad.');
});

test('el diálogo muestra unidad y stock actual, y no envía una cantidad inválida', async (t) => {
  let calls = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; } });
  const { input } = await openDialog(container);
  assert.match(container.textContent, /Reponer Carne/);
  assert.match(container.textContent, /Stock actual: 200 g/);
  assert.match(container.textContent, /Cantidad a reponer \(g\)/);
  assert.equal(find(container, 'label')[0].getAttribute('for'), input.getAttribute('id'));
  for (const invalid of ['', 'abc', '-3', '0', '1,2345']) {
    await change(input, invalid);
    await act(async () => submit());
    assert.equal(calls, 0, invalid);
    assert.equal(reactProps(input)['aria-invalid'], true, invalid);
    assert.equal(document.activeElement, input, invalid);
  }
  assert.match(container.textContent, /3 decimales/);
  await change(input, '2500');
  assert.equal(reactProps(input)['aria-invalid'], false);
  assert.match(container.textContent, /Quedará en 2\.700 g/);
});

test('una cantidad grande pide confirmación con el resumen y envía una sola vez', async (t) => {
  const wait = deferred(); const sent = [];
  const { container } = await mount(t, { replenishIngredient: async (...args) => { sent.push(args); return wait.promise; } });
  const { trigger, input } = await openDialog(container);
  await change(input, '6000');
  await act(async () => submit());
  assert.equal(sent.length, 0);
  assert.match(container.textContent, /Vas a sumar 6\.000 g a Carne; quedará en 6\.200 g\./);
  const confirm = button(container, 'Confirmar reposición');
  assert.equal(document.activeElement, confirm);
  await act(async () => { const click = reactProps(confirm).onClick; click(); click(); submit(); });
  assert.equal(sent.length, 1);
  assert.deepEqual(sent[0], [12, '6000']);
  assert.equal(button(container, 'Reponiendo…').disabled, true);
  assert.equal(button(container, 'Cerrar reposición').disabled, true);
  await act(async () => { wait.resolve({ stock: 6190, movementId: 77 }); await wait.promise; });
  assert.equal(find(container, 'dialog').length, 0);
  assert.match(container.textContent, /Carne quedó en 6\.190 g\. Movimiento #77 registrado en el historial\./);
  assert.equal(document.activeElement, trigger);
  assert.equal(globalThis.__replenishArea.toasts.filter(([kind]) => kind === 'success').length, 1);
});

test('una cantidad chica se envía directo y dos envíos en el mismo evento generan una sola reposición', async (t) => {
  const wait = deferred(); let calls = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; return wait.promise; } });
  const { input } = await openDialog(container);
  await change(input, '250,5');
  let first, second;
  await act(async () => { first = submit(); second = submit(); });
  assert.equal(calls, 1);
  assert.equal(input.disabled || find(container, 'fieldset')[0].disabled, true);
  await act(async () => { wait.resolve({ stock: 450.5, movementId: 3 }); await Promise.all([first, second, wait.promise]); });
  assert.equal(calls, 1);
  assert.match(container.textContent, /450,5 g/);
});

test('un timeout avisa revisar el inventario, no reintenta solo y exige confirmar antes de repetir', async (t) => {
  let calls = 0;
  const uncertain = () => new UserFacingError('Se agotó el tiempo de espera. Comprobá su estado antes de repetir la acción para evitar duplicaciones.', { kind: 'timeout', uncertain: true });
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; throw uncertain(); } });
  const { input } = await openDialog(container);
  await change(input, '100');
  await act(async () => submit());
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
  assert.equal(calls, 1);
  assert.ok(find(container, 'dialog').length, 'el diálogo sigue abierto');
  const alert = elements(container, (node) => reactProps(node).role === 'alert')[0];
  assert.match(alert.textContent, /Comprobá el inventario antes de repetir|Comprobá su estado antes de repetir/);
  assert.equal(find(container, 'input')[0].value, '100');
  await act(async () => submit());
  assert.equal(calls, 1, 'repetir exige confirmación explícita');
  assert.match(container.textContent, /Un intento anterior no se pudo confirmar\. El stock actual ya está consultado/);
  assert.match(container.textContent, /Vas a sumar 100 g a Carne/);
  await act(async () => reactProps(button(container, 'Confirmar reposición')).onClick());
  assert.equal(calls, 2);
});

test('tras un error incierto no se puede confirmar hasta que vuelve la consulta del stock', async (t) => {
  let calls = 0; const refresh = deferred(); let refreshes = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; throw new TypeError('Failed to fetch'); } });
  let pendingRefresh = refresh.promise;
  globalThis.__replenishArea.data.refreshInventory = async (_signal, force) => { if (force) { refreshes++; return pendingRefresh; } };
  const { input } = await openDialog(container);
  await change(input, '100');
  await act(async () => submit());
  assert.equal(refreshes, 1);
  await act(async () => submit());
  assert.match(container.textContent, /Consultando el stock actual/);
  assert.equal(button(container, 'Confirmar reposición').disabled, true);
  await act(async () => { refresh.reject(new Error('sin red')); await refresh.promise.catch(() => {}); });
  assert.match(container.textContent, /No pudimos consultar el stock actual/);
  assert.equal(button(container, 'Confirmar reposición').disabled, true);
  await act(async () => reactProps(button(container, 'Confirmar reposición')).onClick());
  assert.equal(calls, 1);
  pendingRefresh = Promise.resolve();
  await act(async () => reactProps(button(container, 'Volver a consultar')).onClick());
  assert.equal(refreshes, 2);
  assert.equal(button(container, 'Confirmar reposición').disabled, false);
});

test('un +1 incierto no se repite directo: abre el diálogo con 1 y exige confirmar', async (t) => {
  let calls = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; throw new TypeError('Failed to fetch'); } });
  const plus = button(container, 'Reponer 1 g de Carne');
  await act(async () => reactProps(plus).onClick({ currentTarget: plus }));
  assert.equal(calls, 1);
  await act(async () => reactProps(button(container, 'Reponer 1 g de Carne')).onClick({ currentTarget: plus }));
  assert.equal(calls, 1);
  assert.equal(find(container, 'input')[0].value, '1');
  await act(async () => submit());
  assert.equal(calls, 1);
  assert.match(container.textContent, /Vas a sumar 1 g a Carne/);
});

test('cerrar y reabrir el diálogo conserva la exigencia de confirmar tras un error incierto', async (t) => {
  let calls = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; throw new TypeError('Failed to fetch'); } });
  let { input } = await openDialog(container);
  await change(input, '5');
  await act(async () => submit());
  await act(async () => reactProps(button(container, 'Cerrar reposición')).onClick());
  ({ input } = await openDialog(container));
  await change(input, '5');
  await act(async () => submit());
  assert.equal(calls, 1);
  assert.ok(button(container, 'Confirmar reposición'));
});

test('"2,500" se confirma mostrando la cantidad interpretada y "0.125" se acepta', async (t) => {
  const sent = [];
  const { container } = await mount(t, { replenishIngredient: async (...args) => { sent.push(args); return { stock: 202.5, movementId: 5 }; } });
  const { input } = await openDialog(container);
  await change(input, '2,500');
  await act(async () => submit());
  assert.equal(sent.length, 0);
  assert.match(container.textContent, /Vas a sumar 2,5 g a Carne; quedará en 202,5 g\./);
  assert.equal(model.parseReplenishQuantity('0.125').amount, '0.125');
});

test('si el navegador cierra el diálogo mientras envía, se vuelve a abrir', async (t) => {
  const wait = deferred();
  const { container } = await mount(t, { replenishIngredient: async () => wait.promise });
  const { input } = await openDialog(container);
  await change(input, '10');
  await act(async () => submit());
  const dialog = find(container, 'dialog')[0];
  dialog.open = false;
  await act(async () => reactProps(dialog).onClose());
  assert.equal(dialog.open, true);
  assert.equal(find(container, 'dialog').length, 1);
  await act(async () => { wait.resolve({ stock: 210, movementId: 6 }); await wait.promise; });
  assert.equal(find(container, 'dialog').length, 0);
});

test('un error sin estado conocido también se trata como incierto', async (t) => {
  let calls = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; throw new Error('SQL /srv secreto'); } });
  const { input } = await openDialog(container);
  await change(input, '10');
  await act(async () => submit());
  assert.doesNotMatch(container.textContent, /SQL|srv|secreto/);
  assert.match(container.textContent, /Comprobá el inventario antes de repetir/);
  await act(async () => submit());
  assert.equal(calls, 1);
  assert.ok(button(container, 'Confirmar reposición'));
});

test('un rechazo definitivo de la API se muestra sin forzar la confirmación', async (t) => {
  let calls = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; throw new UserFacingError('No tenés acceso a esta acción.', { status: 403 }); } });
  const { input } = await openDialog(container);
  await change(input, '10');
  await act(async () => submit());
  assert.match(container.textContent, /No tenés acceso a esta acción/);
  assert.equal(button(container, 'Confirmar reposición'), undefined);
  await act(async () => submit());
  assert.equal(calls, 2);
});

test('sin stock.reponer no aparecen las opciones de reposición', async (t) => {
  const { container } = await mount(t, { user: { id: 3, backendRole: 'EMPLEADO', permisos: ['stock.ver'] } });
  assert.match(container.textContent, /Carne/);
  assert.equal(button(container, 'Reponer una cantidad de Carne'), undefined);
  assert.equal(button(container, 'Reponer 1 g de Carne'), undefined);
  assert.equal(find(container, 'dialog').length, 0);
});

test('con stock.reponer aparecen la carga manual y el +1 rápido', async (t) => {
  const sent = [];
  const { container } = await mount(t, { user: { id: 4, backendRole: 'EMPLEADO', permisos: ['stock.ver', 'stock.reponer'] }, replenishIngredient: async (...args) => { sent.push(args); return { stock: 201, movementId: 9 }; } });
  assert.ok(button(container, 'Reponer una cantidad de Carne'));
  await act(async () => reactProps(button(container, 'Reponer 1 g de Carne')).onClick());
  assert.deepEqual(sent, [[12, 1]]);
  assert.match(container.textContent, /Carne quedó en 201 g/);
});

test('mientras un +1 está en curso no se puede abrir otra reposición del mismo insumo', async (t) => {
  const wait = deferred();
  const { container } = await mount(t, { replenishIngredient: async () => wait.promise });
  let pending;
  await act(async () => { pending = reactProps(button(container, 'Reponer 1 g de Carne')).onClick(); });
  assert.equal(button(container, 'Reponer una cantidad de Carne').disabled, true);
  await act(async () => { wait.resolve({ stock: 201, movementId: 2 }); await pending; });
  assert.equal(button(container, 'Reponer una cantidad de Carne').disabled, false);
});

test('Escape cierra el diálogo sin enviar y devuelve el foco al botón', async (t) => {
  let calls = 0;
  const { container } = await mount(t, { replenishIngredient: async () => { calls++; } });
  const { trigger } = await openDialog(container);
  let prevented = false;
  await act(async () => reactProps(find(container, 'dialog')[0]).onCancel({ preventDefault() { prevented = true; } }));
  assert.equal(prevented, true);
  assert.equal(find(container, 'dialog').length, 0);
  assert.equal(document.activeElement, trigger);
  assert.equal(calls, 0);
});
