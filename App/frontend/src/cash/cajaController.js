import { can } from '../auth/permissions.js';
import { checked, cierreValido, consolidadoValido, sameTarget, validateSelection, validateFilters, fingerprint } from './cajaContract.js';

const empty = () => ({ status: 'idle', data: null, error: '' });
const query = (values) => new URLSearchParams(Object.entries(values).filter(([, value]) => value)).toString();
const noteKey = (dialog) => dialog.kind === 'generate' ? `generate:${dialog.target.fecha}:${dialog.target.turno}` : `approve:${dialog.cierre.id}`;
const validList = (data) => Array.isArray(data) && data.every(cierreValido);

// Un controlador por identidad/permisos. Los epochs invalidan todas las lecturas
// anteriores a una escritura; cada canal además descarta respuestas fuera de orden.
export function createCajaController({ user, request, refreshSession }) {
  let alive = true, epoch = 0;
  const listeners = new Set(), channels = new Map();
  let state = {
    selection: { mode: 'actual', fecha: '', turno: '' }, filters: { desde: '', hasta: '', estado: '' },
    consolidado: empty(), history: empty(), detail: empty(), dialog: null, notes: {},
    busy: '', uncertain: null, notice: null, denied: false,
  };
  const emit = (patch) => { state = { ...state, ...patch }; for (const listener of listeners) listener(); };
  const allowed = (permission = 'caja.ver') => alive && !state.denied && can(user, 'caja.ver') && can(user, permission);
  const cancel = (channel) => { channels.get(channel)?.abort(); channels.delete(channel); };
  const invalidate = () => { epoch++; for (const controller of channels.values()) controller.abort(); channels.clear(); };
  const notify = (text, tone = 'error') => emit({ notice: { text, tone } });
  function denied(error) {
    if (![401, 403].includes(error?.status)) return false;
    invalidate();
    emit({ denied: true, consolidado: empty(), history: empty(), detail: empty(), dialog: null, notes: {}, uncertain: null, busy: '', notice: { tone: 'error', text: 'El servidor rechazó el acceso. Retiramos los datos de Caja y estamos revalidando la sesión.' } });
    void Promise.resolve(refreshSession?.()).catch(() => {});
    return true;
  }
  async function read(channel, path, valid, expected = () => true) {
    cancel(channel); const controller = new AbortController(); channels.set(channel, controller); const token = epoch;
    try {
      const data = checked(await request(path, { signal: controller.signal }), valid);
      if (!alive || token !== epoch || channels.get(channel) !== controller) return null;
      if (!expected(data)) throw new Error('La respuesta corresponde a otra fecha, turno o cierre. Volvé a consultar.');
      return data;
    } catch (error) {
      if (!alive || token !== epoch || channels.get(channel) !== controller) return null;
      if (!denied(error)) throw error;
      return null;
    } finally { if (channels.get(channel) === controller) channels.delete(channel); }
  }
  const idleReads = () => {
    const patch = {};
    for (const key of ['consolidado', 'history', 'detail']) if (state[key].status === 'loading') patch[key] = empty();
    return patch;
  };
  async function loadConsolidado() {
    if (!allowed() || state.busy) return;
    const selection = { ...state.selection };
    try { validateSelection(selection); }
    catch (error) { emit({ consolidado: { ...empty(), status: 'error', error: error.message } }); return; }
    emit({ consolidado: { ...empty(), status: 'loading' } });
    try {
      const path = selection.mode === 'actual' ? '/api/caja/turnos/actual/consolidado' : `/api/caja/turnos/consolidado?${query({ fecha: selection.fecha, turno: selection.turno })}`;
      const data = await read('consolidado', path, consolidadoValido, (value) => selection.mode === 'actual' || sameTarget(value, selection));
      if (data) emit({ consolidado: { status: 'ready', data, error: '' } });
    } catch (error) { emit({ consolidado: { ...empty(), status: 'error', error: error.message } }); }
  }
  async function loadHistory() {
    if (!allowed() || state.busy) return;
    const filters = { ...state.filters };
    try { validateFilters(filters); }
    catch (error) { emit({ history: { ...empty(), status: 'error', error: error.message } }); return; }
    emit({ history: { ...empty(), status: 'loading' } });
    try {
      const suffix = query(filters);
      const data = await read('history', `/api/caja/cierres${suffix ? `?${suffix}` : ''}`, validList,
        (values) => values.every((value) => (!filters.desde || value.fecha >= filters.desde) && (!filters.hasta || value.fecha <= filters.hasta) && (!filters.estado || value.estado === filters.estado)));
      if (data) emit({ history: { status: 'ready', data, error: '' } });
    } catch (error) { emit({ history: { ...empty(), status: 'error', error: error.message } }); }
  }
  async function loadDetail(id) {
    if (!allowed() || state.busy || !Number.isSafeInteger(id) || id <= 0) return;
    emit({ detail: { ...empty(), status: 'loading' } });
    try {
      const data = await read('detail', `/api/caja/cierres/${id}`, cierreValido, (value) => value.id === id);
      if (data) emit({ detail: { status: 'ready', data, error: '' } });
    } catch (error) { emit({ detail: { ...empty(), status: 'error', error: error.message } }); }
  }
  async function prepareGenerate() {
    if (!allowed('caja.generar') || state.busy || state.uncertain || state.consolidado.status !== 'ready') return;
    const target = { fecha: state.consolidado.data.fecha, turno: state.consolidado.data.turno };
    emit({ busy: 'prepare', dialog: null, notice: null });
    const token = epoch;
    try {
      const data = await read('prepare', `/api/caja/cierres?${query({ desde: target.fecha, hasta: target.fecha })}`, validList,
        (values) => values.every((value) => value.fecha === target.fecha));
      if (!data || token !== epoch) return;
      const matches = data.filter((item) => sameTarget(item, target));
      if (matches.length > 1) throw new Error('El servidor devolvió más de un cierre para el turno. Revisá el historial.');
      const existing = matches[0] || null;
      if (existing?.estado === 'APROBADO') {
        emit({ detail: { status: 'ready', data: existing, error: '' } }); notify('El cierre ya está aprobado y es inalterable.', 'info');
      } else emit({ dialog: { kind: 'generate', target, existing } });
    } catch (error) { if (alive && token === epoch) notify(error.message); }
    finally { if (alive && token === epoch) emit({ busy: '' }); }
  }
  async function prepareApprove(id) {
    if (!allowed('caja.aprobar') || state.busy || state.uncertain || !Number.isSafeInteger(id) || id <= 0) return;
    emit({ busy: 'prepare', dialog: null, notice: null }); const token = epoch;
    try {
      const data = await read('prepare', `/api/caja/cierres/${id}`, cierreValido, (value) => value.id === id);
      if (!data || token !== epoch) return;
      emit({ detail: { status: 'ready', data, error: '' } });
      if (data.estado === 'APROBADO') notify('El cierre ya está aprobado y es inalterable.', 'info');
      else emit({ dialog: { kind: 'approve', cierre: data } });
    } catch (error) { if (alive && token === epoch) notify(error.message); }
    finally { if (alive && token === epoch) emit({ busy: '' }); }
  }
  async function confirm() {
    const dialog = state.dialog;
    if (!dialog || state.busy || state.uncertain || !allowed(dialog.kind === 'generate' ? 'caja.generar' : 'caja.aprobar')) return;
    if (dialog.kind === 'approve' && (!Number.isSafeInteger(user.id) || user.id <= 0)) { notify('No se pudo comprobar la identidad de la sesión. Volvé a ingresar.'); return; }
    invalidate(); const token = epoch;
    emit({ ...idleReads(), busy: 'write', notice: null });
    const notes = state.notes[noteKey(dialog)];
    const observaciones = notes?.trim() ? notes : null;
    let sent = false;
    try {
      if (dialog.kind === 'generate') {
        const values = checked(await request(`/api/caja/cierres?${query({ desde: dialog.target.fecha, hasta: dialog.target.fecha })}`, {}), validList);
        if (!alive || token !== epoch) return;
        if (values.some((value) => value.fecha !== dialog.target.fecha)) throw new Error('El historial recibido no corresponde a la fecha elegida.');
        const matches = values.filter((item) => sameTarget(item, dialog.target));
        if (matches.length > 1) throw new Error('No se pudo identificar un único cierre del turno.');
        const fresh = matches[0] || null;
        if (fresh?.estado === 'APROBADO') {
          emit({ dialog: null, detail: { status: 'ready', data: fresh, error: '' } }); notify('El cierre figura aprobado y es inalterable.', 'info'); return;
        }
        if (fingerprint(fresh) !== fingerprint(dialog.existing)) {
          emit({ dialog: { ...dialog, existing: fresh } }); notify('Otra persona modificó el cierre. Revisá los nuevos datos y confirmá nuevamente.', 'info'); return;
        }
      }
      // Refrescar justo antes del POST: si otro operador recalculó mientras se
      // revisaba el diálogo, se vuelve a pedir confirmación de los nuevos datos.
      if (dialog.kind === 'approve') {
        const fresh = checked(await request(`/api/caja/cierres/${dialog.cierre.id}`, {}), cierreValido);
        if (!alive || token !== epoch) return;
        if (fresh.id !== dialog.cierre.id || !sameTarget(fresh, dialog.cierre)) throw new Error('El detalle recibido no corresponde al cierre elegido.');
        emit({ detail: { status: 'ready', data: fresh, error: '' } });
        if (fresh.estado === 'APROBADO') { emit({ dialog: null }); notify('El cierre figura aprobado y es inalterable.', 'info'); return; }
        if (fingerprint(fresh) !== fingerprint(dialog.cierre)) {
          emit({ dialog: { ...dialog, cierre: fresh } }); notify('Otra persona modificó el cierre. Revisá los nuevos datos y confirmá nuevamente.', 'info'); return;
        }
      }
      const path = dialog.kind === 'generate' ? '/api/caja/cierres/generar' : `/api/caja/cierres/${dialog.cierre.id}/aprobar`;
      const body = dialog.kind === 'generate' ? { ...dialog.target, observaciones } : { aprobado_por: user.id, observaciones };
      sent = true;
      const data = checked(await request(path, { method: 'POST', body: JSON.stringify(body) }), cierreValido);
      if (!alive || token !== epoch) return;
      if (dialog.kind === 'generate' ? !sameTarget(data, dialog.target) || data.estado !== 'PENDIENTE_APROBACION' || dialog.existing && data.id !== dialog.existing.id
        : data.id !== dialog.cierre.id || !sameTarget(data, dialog.cierre) || data.estado !== 'APROBADO') throw new Error('El acuse no identifica el cierre y estado esperados.');
      if (observaciones !== null && data.observaciones !== observaciones) throw new Error('El acuse no confirma las observaciones enviadas.');
      if (dialog.kind === 'generate' ? data.generado_por !== user.id : data.aprobado_por !== user.id) throw new Error('El acuse no corresponde al usuario autenticado.');
      emit({ detail: { status: 'ready', data, error: '' }, history: empty(), dialog: null });
      const changed = dialog.kind === 'approve' && ['total_general', 'total_efectivo', 'total_billeteras', 'total_devoluciones', 'cantidad_pedidos', 'observaciones'].some((key) => {
        const expected = key === 'observaciones' && observaciones !== null ? observaciones : dialog.cierre[key];
        return String(data[key]) !== String(expected);
      });
      notify(changed ? 'El servidor confirmó el cierre aprobado, pero sus datos cambiaron durante la aprobación. Revisá el resultado real; la API no ofrece control de versión.' : dialog.kind === 'generate' ? 'Generación confirmada. El detalle muestra el cierre real, que puede incluir arrastre.' : 'Aprobación confirmada. El cierre es inalterable.', changed ? 'info' : 'success');
    } catch (error) {
      if (!alive || token !== epoch || denied(error)) return;
      const uncertain = sent && (!error.status || error.status >= 500 || error.status === 408);
      emit({ uncertain: uncertain ? { kind: dialog.kind, target: dialog.target, id: dialog.cierre?.id } : null });
      notify(uncertain ? `${error.message} Resultado incierto: comprobá el estado antes de volver a enviar.` : `${error.message}${error.status === 409 ? ' Otra persona puede haber cambiado el cierre. Consultá nuevamente su estado.' : ''}`);
    } finally { if (alive && token === epoch) emit({ busy: '' }); }
  }
  async function reconcile() {
    if (!allowed() || !state.uncertain || state.busy) return;
    const pending = state.uncertain; emit({ busy: 'reconcile' }); const token = epoch;
    try {
      const data = pending.kind === 'approve'
        ? await read('reconcile', `/api/caja/cierres/${pending.id}`, cierreValido, (value) => value.id === pending.id)
        : await read('reconcile', `/api/caja/cierres?${query({ desde: pending.target.fecha, hasta: pending.target.fecha })}`, validList, (values) => values.every((value) => value.fecha === pending.target.fecha));
      if (!data || token !== epoch) return;
      const matches = pending.kind === 'approve' ? [data] : data.filter((item) => sameTarget(item, pending.target));
      if (matches.length > 1) throw new Error('No se pudo identificar un único cierre del turno.');
      emit({ uncertain: null, dialog: null, detail: matches[0] ? { status: 'ready', data: matches[0], error: '' } : empty(), history: empty() });
      notify(pending.kind === 'approve' && matches[0].estado === 'APROBADO' ? 'El cierre figura aprobado en el servidor y es inalterable.' : matches[0]
        ? 'Encontramos el cierre. No podemos confirmar ni atribuir el resultado de tu envío; revisá su detalle y observaciones antes de decidir un nuevo intento.'
        : 'La consulta no encontró un cierre para ese turno. El envío anterior sigue sin confirmarse; podés revisar y confirmar un nuevo intento.', 'info');
    } catch (error) { if (alive && token === epoch) notify(`${error.message} Todavía no pudimos comprobar el resultado. No vuelvas a enviar.`); }
    finally { if (alive && token === epoch) emit({ busy: '' }); }
  }
  return {
    getSnapshot: () => state, subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    start() { alive = true; void loadConsolidado(); void loadHistory(); },
    stop() { alive = false; invalidate(); emit({ consolidado: empty(), history: empty(), detail: empty(), dialog: null, notes: {}, uncertain: null, busy: '' }); },
    setSelection(selection) { if (!allowed() || state.busy) return; cancel('consolidado'); emit({ selection, consolidado: empty(), dialog: null }); },
    setFilters(filters) { if (!allowed() || state.busy) return; cancel('history'); emit({ filters, history: empty() }); },
    setNotes(value) { if (allowed() && state.dialog && !state.busy) emit({ notes: { ...state.notes, [noteKey(state.dialog)]: value } }); },
    closeDialog() { if (!state.busy && !state.uncertain) emit({ dialog: null }); },
    dialogNotes: () => state.dialog ? state.notes[noteKey(state.dialog)] || '' : '',
    loadConsolidado, loadHistory, loadDetail, prepareGenerate, prepareApprove, confirm, reconcile,
  };
}
