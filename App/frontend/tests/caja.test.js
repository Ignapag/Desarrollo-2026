import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createCajaController } from '../src/cash/cajaController.js';
import { validDate, validateSelection, validateFilters, cierreValido, consolidadoValido, formatDate, formatTimestamp } from '../src/cash/cajaContract.js';
import { deferred } from './minimal-dom.js';

export const cierre = (extra = {}) => ({ id: 31, fecha: '2026-10-26', turno: 'NOCHE', abierto_en: '2026-10-26T20:00:00', cerrado_en: '2026-10-27T02:01:00', total_efectivo: '100.00', total_billeteras: '45.00', total_devoluciones: '5.00', total_general: '140.00', cantidad_pedidos: 3, estado: 'PENDIENTE_APROBACION', generado_por: 4, aprobado_por: null, aprobado_en: null, observaciones: 'Nota previa', ...extra });
export const consolidado = (extra = {}) => ({ fecha: '2026-10-26', turno: 'NOCHE', desde: '2026-10-26T20:00:00', hasta: '2026-10-27T02:00:00', total_efectivo: '50.00', total_billeteras: '20.00', total_devoluciones: '5.00', total_general: '69.00', total_propinas: '4.00', cantidad_pedidos: 2, cantidad_pagos: 3, pagos_pendientes_conciliacion: 1, desglose_metodos: [{ metodo_pago: 'EFECTIVO', total: '50.00', cantidad: 2 }], ...extra });
const employee = (permisos = ['caja.ver', 'caja.generar', 'caja.aprobar']) => ({ id: 4, backendRole: 'EMPLEADO', permisos });
function setup(request, user = employee()) { return createCajaController({ user, request, refreshSession: async () => {} }); }
const approved = () => cierre({ estado: 'APROBADO', aprobado_por: 4, aprobado_en: '2026-10-27T03:00:00' });

test('fechas reales, fecha nocturna sin UTC y rango coherente', () => {
  for (const value of ['2026-02-29', '0000-01-01', '2026-04-31', '', '2026-1-1']) assert.equal(validDate(value), false);
  assert.equal(validDate('2024-02-29'), true);
  assert.match(formatDate('2026-10-26'), /26.*10.*2026/);
  assert.match(formatTimestamp('2190-10-27T17:00:00-03:00'), /2190/);
  assert.throws(() => validateSelection({ mode: 'specific', fecha: '2026-10-26', turno: '' }), /turno/i);
  assert.throws(() => validateFilters({ desde: '2026-10-27', hasta: '2026-10-26' }), /rango|hasta/i);
  assert.equal(consolidadoValido(consolidado()), true);
  assert.equal(consolidadoValido(consolidado({ total_propinas: undefined })), false);
  assert.equal(cierreValido(cierre({ observaciones: undefined })), false);
  assert.equal(cierreValido(approved()), true);
});

test('ninguna consulta ni escritura sin caja.ver, permisos separados y administrador', async () => {
  let calls = 0;
  for (const user of [null, employee([]), employee(['caja.generar', 'caja.aprobar'])]) {
    const c = setup(async () => { calls++; }, user);
    await c.loadConsolidado(); await c.loadHistory(); await c.loadDetail(31); await c.prepareGenerate(); await c.prepareApprove(31); await c.confirm();
  }
  assert.equal(calls, 0);
  const read = setup(async (path) => { calls++; return path.includes('consolidado') ? consolidado() : []; }, employee(['caja.ver']));
  await read.loadConsolidado(); await read.prepareGenerate(); await read.prepareApprove(31);
  assert.equal(calls, 1);
  const admin = setup(async () => consolidado(), { id: 1, backendRole: 'ADMINISTRADOR' });
  await admin.loadConsolidado(); assert.equal(admin.getSnapshot().consolidado.status, 'ready');
});

test('actual del servidor, específico explícito y selección parcial jamás cierra actual', async () => {
  const calls = []; const c = setup(async (path, opts) => { calls.push([path, opts]); return consolidado(); });
  await c.loadConsolidado(); assert.equal(calls[0][0], '/api/caja/turnos/actual/consolidado');
  c.setSelection({ mode: 'specific', fecha: '2026-10-26', turno: 'NOCHE' }); await c.loadConsolidado();
  assert.match(calls[1][0], /fecha=2026-10-26&turno=NOCHE/);
  c.setSelection({ mode: 'specific', fecha: '2026-10-26', turno: '' }); await c.loadConsolidado(); await c.prepareGenerate();
  assert.equal(calls.length, 2); assert.equal(c.getSnapshot().consolidado.data, null);
});

test('generación concreta, doble envío bloqueado, arrastre real y notas vacías null', async () => {
  const wait = deferred(); const started = deferred(); const writes = []; let history = [];
  const c = setup(async (path, opts = {}) => {
    if (opts.method === 'POST') { writes.push(JSON.parse(opts.body)); started.resolve(); return wait.promise; }
    return path.includes('consolidado') ? consolidado() : history;
  });
  await c.loadConsolidado(); await c.prepareGenerate();
  assert.equal(c.getSnapshot().dialog.kind, 'generate');
  const first = c.confirm(); const second = c.confirm();
  await started.promise;
  assert.equal(writes.length, 1); assert.deepEqual(writes[0], { fecha: '2026-10-26', turno: 'NOCHE', observaciones: null });
  history = [cierre()]; wait.resolve(cierre()); await Promise.all([first, second]);
  assert.equal(c.getSnapshot().detail.data.total_general, '140.00');
  assert.match(c.getSnapshot().notice.text, /confirmad/i);
});

test('acuse que no conserva observaciones enviadas no anuncia guardado', async () => {
  const c = setup(async (path, opts = {}) => opts.method === 'POST' ? cierre({ observaciones: 'Nota ajena' }) : path.includes('consolidado') ? consolidado() : []);
  await c.loadConsolidado(); await c.prepareGenerate(); c.setNotes('Mi nota nueva'); await c.confirm();
  assert.ok(c.getSnapshot().uncertain); assert.doesNotMatch(c.getSnapshot().notice.text, /generación confirmada/i);
});

test('recálculo identifica existente, conserva nota por null y aprobado no ofrece recalcular', async () => {
  let record = cierre(); let body;
  const c = setup(async (path, opts = {}) => {
    if (opts.method === 'POST') { body = JSON.parse(opts.body); return record; }
    return path.includes('consolidado') ? consolidado() : [record];
  });
  await c.loadConsolidado(); await c.prepareGenerate(); assert.equal(c.getSnapshot().dialog.existing.id, 31);
  await c.confirm(); assert.equal(body.observaciones, null);
  record = approved(); await c.prepareGenerate();
  assert.equal(c.getSnapshot().dialog, null); assert.match(c.getSnapshot().notice.text, /inalterable/i);
});

test('aprobación refresca detalle y usa usuario sesión, no confirma acuse incompleto', async () => {
  let writes = 0; const c = setup(async (path, opts = {}) => {
    if (opts.method === 'POST') { writes++; assert.equal(JSON.parse(opts.body).aprobado_por, 4); return {}; }
    return cierre();
  });
  await c.prepareApprove(31); assert.equal(c.getSnapshot().dialog.cierre.id, 31);
  c.setNotes('Conservar esta nota'); await c.confirm();
  assert.equal(writes, 1); assert.equal(c.getSnapshot().uncertain.kind, 'approve');
  assert.doesNotMatch(c.getSnapshot().notice.text, /aprobación confirmada/i);
  await c.reconcile(); assert.equal(c.getSnapshot().uncertain, null);
  assert.equal(c.getSnapshot().notes['approve:31'], 'Conservar esta nota');
});

test('aprobación válida confirma ID y estado esperados; ya aprobado es inalterable', async () => {
  let record = cierre(); const c = setup(async (_path, opts = {}) => opts.method === 'POST' ? (record = approved()) : record);
  await c.prepareApprove(31); await c.confirm();
  assert.equal(c.getSnapshot().detail.data.estado, 'APROBADO'); assert.match(c.getSnapshot().notice.text, /confirmada/i);
  await c.prepareApprove(31); assert.equal(c.getSnapshot().dialog, null);
});

test('otro operador recalcula o crea durante confirmación: vuelve a mostrar datos antes de escribir', async () => {
  for (const action of ['generate', 'approve']) {
    let record = cierre(), writes = 0;
    const c = setup(async (path, opts = {}) => {
      if (opts.method === 'POST') { writes++; return action === 'generate' ? record : approved(); }
      return path.includes('consolidado') ? consolidado() : path.includes('?') ? [record] : record;
    });
    await c.loadConsolidado();
    if (action === 'generate') await c.prepareGenerate(); else await c.prepareApprove(31);
    record = cierre({ observaciones: 'Otra persona agregó una nota', total_general: '280.00' });
    await c.confirm(); assert.equal(writes, 0);
    assert.match(c.getSnapshot().notice.text, /modific|cambi/i);
    const dialog = c.getSnapshot().dialog;
    assert.equal((dialog.existing || dialog.cierre).observaciones, 'Otra persona agregó una nota');
    await c.confirm(); assert.equal(writes, 1);
  }
});

test('respuesta perdida no reenvía, reconciliación generación no atribuye cierre preexistente', async () => {
  let writes = 0; let offline = false;
  const c = setup(async (path, opts = {}) => {
    if (opts.method === 'POST') { writes++; throw new Error('Conexión perdida'); }
    if (offline) throw new Error('Sin conexión');
    return path.includes('consolidado') ? consolidado() : [cierre()];
  });
  await c.loadConsolidado(); await c.prepareGenerate(); c.setNotes('No perder'); await c.confirm();
  assert.equal(c.getSnapshot().uncertain.kind, 'generate');
  await c.confirm(); assert.equal(writes, 1);
  offline = true; await c.reconcile(); assert.ok(c.getSnapshot().uncertain);
  offline = false; await c.reconcile(); assert.equal(c.getSnapshot().uncertain, null);
  assert.match(c.getSnapshot().notice.text, /no.*confirmar|no.*atribuir/i);
  assert.equal(c.getSnapshot().notes['generate:2026-10-26:NOCHE'], 'No perder');
  assert.equal(writes, 1);
});

test('reconciliar aprobación consulta por ID y verifica estado aprobado', async () => {
  let record = cierre(); const c = setup(async (path, opts = {}) => {
    assert.equal(path, opts.method === 'POST' ? '/api/caja/cierres/31/aprobar' : '/api/caja/cierres/31');
    if (opts.method === 'POST') { record = approved(); throw new Error('timeout'); }
    return record;
  });
  await c.prepareApprove(31); await c.confirm(); await c.reconcile();
  assert.equal(c.getSnapshot().detail.data.estado, 'APROBADO'); assert.match(c.getSnapshot().notice.text, /figura aprobado/i);
});

test('GET fuera de orden, cambio selección y lecturas previas no pisan mutación', async () => {
  const slow = deferred(); let gets = 0;
  const c = setup(async (path, opts = {}) => {
    if (opts.method === 'POST') return cierre();
    if (path.includes('consolidado')) return consolidado();
    if (path === '/api/caja/cierres/31') return slow.promise;
    gets++; return [];
  });
  const old = c.loadDetail(31); await c.loadConsolidado(); await c.prepareGenerate(); await c.confirm();
  slow.resolve(cierre({ total_general: '1.00' })); await old;
  assert.equal(c.getSnapshot().detail.data.total_general, '140.00');
  const a = deferred(); const b = deferred(); let n = 0;
  const other = setup(async () => (++n === 1 ? a.promise : b.promise));
  const first = other.loadConsolidado(); other.setSelection({ mode: 'specific', fecha: '2026-10-25', turno: 'NOCHE' }); const next = other.loadConsolidado();
  b.resolve(consolidado({ fecha: '2026-10-25' })); await next; a.resolve(consolidado()); await first;
  assert.equal(other.getSnapshot().consolidado.data.fecha, '2026-10-25'); assert.ok(gets);
});

test('401/403 retiran todos los privados, revalidan y bloquean handlers; stop impide sesión anterior', async () => {
  for (const status of [401, 403]) {
    let revoked = false, refreshes = 0, calls = 0;
    const c = createCajaController({ user: employee(), refreshSession: async () => { refreshes++; }, request: async () => { calls++; if (revoked) throw Object.assign(new Error('Sin acceso'), { status }); return consolidado(); } });
    await c.loadConsolidado(); revoked = true; await c.loadHistory();
    assert.equal(c.getSnapshot().consolidado.data, null); assert.equal(c.getSnapshot().denied, true); assert.equal(refreshes, 1);
    await c.loadConsolidado(); assert.equal(calls, 2);
  }
  const wait = deferred(); const c = setup(async () => wait.promise); const pending = c.loadConsolidado(); c.stop(); wait.resolve(consolidado()); await pending;
  assert.equal(c.getSnapshot().consolidado.data, null); await c.prepareGenerate(); assert.equal(c.getSnapshot().dialog, null);
});

for (const status of [400, 404, 409, 422, 429, 500, 503]) {
  test(`HTTP ${status} conserva filtros/notas y no anuncia éxito`, async () => {
    const c = setup(async (path, opts = {}) => {
      if (opts.method === 'POST') throw Object.assign(new Error(`Error HTTP ${status}`), { status });
      return path.includes('consolidado') ? consolidado() : [];
    });
    await c.loadConsolidado(); await c.prepareGenerate(); c.setNotes('Pendiente de guardar'); await c.confirm();
    assert.equal(c.getSnapshot().notes['generate:2026-10-26:NOCHE'], 'Pendiente de guardar');
    assert.doesNotMatch(c.getSnapshot().notice.text, /confirmad[oa]/i);
    assert.equal(Boolean(c.getSnapshot().uncertain), status >= 500);
  });
}
