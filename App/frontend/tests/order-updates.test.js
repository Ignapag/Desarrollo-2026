import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createOrderPoller } from '../src/fulfillment/orderUpdates.js';
import { deferred } from './minimal-dom.js';

function setup(overrides = {}) {
  const state = { now: 0, revision: 'a', checks: 0, downloads: 0, enabled: true, errors: [] };
  const poller = createOrderPoller({
    enabled: () => state.enabled,
    clock: () => state.now,
    readRevision: async () => { state.checks += 1; return state.revision; },
    refresh: async () => { state.downloads += 1; return true; },
    onError: (error) => state.errors.push(error),
    ...overrides,
  });
  return { state, poller };
}

test('sin cambios solo comprueba la huella; cambios descargan el tablero', async () => {
  const { state, poller } = setup();
  await poller.update();
  await poller.update();
  assert.equal(state.checks, 2);
  assert.equal(state.downloads, 1);
  state.revision = 'b';
  await poller.update();
  assert.equal(state.downloads, 2);
  state.now = 60000;
  await poller.update();
  assert.equal(state.downloads, 3);
});

test('no consulta pantallas inactivas ni solapa pedidos lentos', async () => {
  const waiting = deferred();
  const { state, poller } = setup({ readRevision: async () => waiting.promise });
  state.enabled = false;
  await poller.update();
  assert.equal(state.downloads, 0);
  state.enabled = true;
  const running = poller.update();
  await poller.update();
  await poller.update();
  waiting.resolve('a');
  await running;
  assert.equal(state.downloads, 1);
});

test('una pausa cancela la lectura y no publica una respuesta tardía', async () => {
  const waiting = deferred();
  let signal;
  const { state, poller } = setup({ readRevision: async (value) => { signal = value; return waiting.promise; } });
  const running = poller.update();
  poller.pause();
  assert.equal(signal.aborted, true);
  waiting.resolve('a');
  await running;
  assert.equal(state.downloads, 0);
  assert.deepEqual(state.errors, []);
});

test('los errores espacian reintentos y una sesión rechazada detiene el sondeo', async () => {
  let calls = 0;
  const error = Object.assign(new Error('Fallo'), { status: 503 });
  const { state, poller } = setup({ readRevision: async () => { calls += 1; throw error; } });
  await poller.update();
  await poller.update();
  assert.equal(calls, 1);
  state.now = 10000;
  await poller.update();
  assert.equal(calls, 2);
  error.status = 403;
  state.now = 30000;
  await poller.update();
  state.now = 300000;
  await poller.update();
  assert.equal(calls, 3);
});

test('si la valla de mutación rechaza el GET, vuelve a pedirlo en el siguiente ciclo', async () => {
  let accepted = false;
  let calls = 0;
  const { poller } = setup({ refresh: async () => { calls += 1; return accepted; } });
  await poller.update();
  accepted = true;
  await poller.update();
  await poller.update();
  assert.equal(calls, 2);
});
