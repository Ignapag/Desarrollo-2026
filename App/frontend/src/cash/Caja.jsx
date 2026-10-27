import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { Banknote, RefreshCw, LockKeyhole } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { can } from '../auth/permissions';
import { apiFetch } from '../shared/api/http';
import { createCajaController } from './cajaController';
import { ESTADOS, TURNOS, METODOS, formatMoney, formatDate, formatTimestamp, sameTarget } from './cajaContract';

const panel = 'bg-white rounded-2xl border border-monu-green/10 p-4 sm:p-6 shadow-sm';
const input = 'min-h-11 w-full rounded-xl border border-monu-green/30 bg-white px-3 py-2 focus:outline-2 focus:outline-monu-green';
const primary = 'min-h-11 rounded-xl px-4 py-2 font-bold bg-monu-green text-white hover:bg-monu-dark disabled:opacity-50';
const secondary = 'min-h-11 rounded-xl px-4 py-2 font-bold border border-monu-green/30 hover:bg-monu-cream disabled:opacity-50';

function MoneySummary({ data, consolidated = false }) {
  const fields = [['Total general', 'total_general'], ['Efectivo', 'total_efectivo'], ['Billeteras', 'total_billeteras'], ['Devoluciones', 'total_devoluciones']];
  if (consolidated) fields.push(['Propinas', 'total_propinas']);
  return <dl className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
    {fields.map(([label, field]) => <div key={field} className={`min-w-0 rounded-xl p-3 ${field === 'total_general' ? 'bg-monu-green text-white' : 'bg-monu-cream/60'}`}>
      <dt className="text-sm font-semibold">{label}</dt><dd className="text-xl sm:text-2xl font-extrabold tabular-nums break-words">{formatMoney(data[field])}</dd>
    </div>)}
    <div className="rounded-xl bg-monu-cream/60 p-3"><dt className="text-sm font-semibold">Pedidos</dt><dd className="text-2xl font-extrabold tabular-nums">{data.cantidad_pedidos}</dd></div>
  </dl>;
}
function Status({ resource, onRetry }) {
  if (resource.status === 'loading') return <p role="status" className="py-4 flex gap-2 items-center"><RefreshCw aria-hidden="true" className="w-4 h-4 motion-safe:animate-spin" />Consultando…</p>;
  if (resource.status === 'error') return <div className="rounded-xl bg-red-50 text-red-800 p-4 space-y-2"><p role="alert">{resource.error}</p>{onRetry && <button type="button" className={secondary} onClick={onRetry}>Reintentar consulta</button>}</div>;
  return null;
}
function RecordInfo({ data }) {
  return <><p className="font-bold">{formatDate(data.fecha)} · {TURNOS[data.turno]} · {ESTADOS[data.estado]}</p><MoneySummary data={data} />
    <dl className="grid sm:grid-cols-2 gap-3 text-sm">
      <div><dt className="font-bold">Registrado en</dt><dd>{formatTimestamp(data.abierto_en)}</dd></div>
      <div><dt className="font-bold">Generado / recalculado en</dt><dd>{formatTimestamp(data.cerrado_en)}</dd></div>
      <div><dt className="font-bold">Generado por</dt><dd>{data.generado_por ? `Usuario #${data.generado_por}` : 'Sin responsable informado'}</dd></div>
      <div><dt className="font-bold">Aprobado por</dt><dd>{data.aprobado_por ? `Usuario #${data.aprobado_por}` : 'Sin aprobación'}</dd></div>
      <div><dt className="font-bold">Aprobado en</dt><dd>{formatTimestamp(data.aprobado_en)}</dd></div>
      <div className="sm:col-span-2"><dt className="font-bold">Observaciones registradas</dt><dd className="whitespace-pre-wrap break-words">{data.observaciones || 'Sin observaciones'}</dd></div>
    </dl></>;
}
function Confirmation({ state, controller, returnFocus }) {
  const ref = useRef(null), cancelRef = useRef(null), alertRef = useRef(null);
  const [replacementConsent, setReplacementConsent] = useState(null);
  const dialog = state.dialog, generating = dialog.kind === 'generate';
  const record = generating ? dialog.existing : dialog.cierre;
  const target = generating ? dialog.target : record;
  const notes = controller.dialogNotes();
  const replacement = Boolean(record?.observaciones && notes.trim());
  const replaceNotes = replacementConsent !== null && replacementConsent === record?.observaciones;
  const title = generating ? record ? 'Recalcular cierre' : 'Generar cierre' : 'Aprobar cierre';
  useEffect(() => {
    const opener = returnFocus.current || document.activeElement;
    ref.current.showModal(); cancelRef.current?.focus();
    const element = ref.current;
    return () => { element.close(); if (opener?.isConnected !== false) opener?.focus(); };
  }, [returnFocus]);
  useEffect(() => { if (state.notice) alertRef.current?.focus(); }, [state.notice]);
  return <dialog ref={ref} aria-labelledby="caja-confirm-title" aria-describedby="caja-confirm-help" onCancel={(event) => { event.preventDefault(); controller.closeDialog(); }} className="m-auto w-[calc(100%-2rem)] max-w-2xl max-h-[85dvh] overflow-y-auto rounded-2xl bg-white p-4 sm:p-6 text-monu-text shadow-xl backdrop:bg-black/50">
    <div className="space-y-4">
      <h2 id="caja-confirm-title" className="text-xl font-extrabold">{title}{record ? ` #${record.id}` : ''}</h2>
      <p className="font-bold">Fecha contable {formatDate(target.fecha)} · Turno {TURNOS[target.turno]}</p>
      <p id="caja-confirm-help">{generating ? 'Esta operación registra o recalcula un cierre pendiente de aprobación. Puede incluir pagos conciliados anteriores sin otro cierre (arrastre); el resultado puede diferir del consolidado de la ventana.' : 'La aprobación vuelve inalterable el cierre. Revisá sus totales y observaciones antes de confirmar.'}</p>
      {record && <RecordInfo data={record} />}
      <p className="text-sm">Otras personas pueden recalcular o aprobar mientras revisás. Se vuelve a consultar antes de aprobar; la API no ofrece control de versión entre esa lectura y la escritura.</p>
      <div><label htmlFor="caja-notes" className="block font-bold mb-1">Observaciones opcionales</label>
        <textarea id="caja-notes" rows={3} value={notes} onChange={(event) => controller.setNotes(event.target.value)} disabled={Boolean(state.busy) || Boolean(state.uncertain)} className={input} aria-describedby="caja-notes-help" />
        <p id="caja-notes-help" className="text-sm mt-1">Dejá el campo vacío para conservar las observaciones registradas. Un texto nuevo reemplaza las observaciones anteriores.</p>
      </div>
      {replacement && <label className="flex items-start gap-3 min-h-11"><input type="checkbox" className="mt-1 size-5" checked={replaceNotes} disabled={Boolean(state.busy) || Boolean(state.uncertain)} onChange={(event) => setReplacementConsent(event.target.checked ? record.observaciones : null)} /><span>Confirmo reemplazar las observaciones registradas por el texto nuevo.</span></label>}
      {state.notice && <p ref={alertRef} tabIndex={-1} role="alert" className="rounded-xl bg-monu-cream p-3 focus:outline-2 focus:outline-monu-green">{state.notice.text}</p>}
      {state.uncertain && <button type="button" className={primary} disabled={Boolean(state.busy)} onClick={controller.reconcile}>{state.busy ? 'Comprobando…' : 'Comprobar resultado'}</button>}
      <div className="flex flex-wrap justify-end gap-3">
        <button ref={cancelRef} type="button" className={secondary} disabled={Boolean(state.busy) || Boolean(state.uncertain)} onClick={controller.closeDialog}>Cancelar</button>
        <button type="button" className={primary} onClick={controller.confirm} disabled={Boolean(state.busy) || Boolean(state.uncertain) || replacement && !replaceNotes}>
          {state.busy === 'write' ? 'Procesando…' : generating ? record ? 'Confirmar recálculo' : 'Confirmar generación' : 'Confirmar aprobación'}
        </button>
      </div>
    </div>
  </dialog>;
}
function CajaSession({ user, refreshSession }) {
  const controller = useMemo(() => createCajaController({ user, request: apiFetch, refreshSession }), [user, refreshSession]);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const selectionError = useRef(null), historyError = useRef(null), notice = useRef(null);
  const returnFocus = useRef(null);
  const [detailRetry, setDetailRetry] = useState(null);
  useEffect(() => { controller.start(); return controller.stop; }, [controller]);
  useEffect(() => { if (state.consolidado.status === 'error') selectionError.current?.focus(); }, [state.consolidado]);
  useEffect(() => { if (state.history.status === 'error') historyError.current?.focus(); }, [state.history]);
  useEffect(() => { if (state.notice && !state.dialog) notice.current?.focus(); }, [state.notice, state.dialog]);
  const disabled = Boolean(state.busy), selection = state.selection, filters = state.filters;
  const data = state.consolidado.data, detail = state.detail.data;
  const knownApproved = data && [detail, ...(state.history.data || [])].some((record) => record?.estado === 'APROBADO' && sameTarget(record, data));
  const generating = can(user, 'caja.generar'), approving = can(user, 'caja.aprobar');
  const setSelection = (key, value) => controller.setSelection({ ...selection, [key]: value });
  const setFilter = (key, value) => controller.setFilters({ ...filters, [key]: value });
  if (state.denied) return <section className={panel}><h1 className="text-2xl font-extrabold">Caja</h1><p role="alert" className="py-4">{state.notice.text}</p><button className={secondary} onClick={refreshSession}>Revalidar sesión</button></section>;
  return <div className="space-y-6 max-w-7xl mx-auto">
    <header><h1 className="text-3xl font-extrabold font-heading flex items-center gap-3"><Banknote aria-hidden="true" />Caja</h1><p className="mt-2">Consultá turnos, revisá cierres y registrá su aprobación.</p></header>
    {state.notice && !state.dialog && <p ref={notice} tabIndex={-1} role={state.notice.tone === 'error' ? 'alert' : 'status'} className="rounded-xl bg-white border border-monu-green/20 p-4 focus:outline-2 focus:outline-monu-green">{state.notice.text}</p>}
    {state.uncertain && !state.dialog && <button type="button" className={primary} disabled={disabled} onClick={controller.reconcile}>Comprobar resultado</button>}
    <section className={`${panel} space-y-4`} aria-labelledby="caja-consolidado-title">
      <h2 id="caja-consolidado-title" className="text-xl font-extrabold">Consolidado del turno</h2>
      <form noValidate onSubmit={(event) => { event.preventDefault(); void controller.loadConsolidado(); }} className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4 items-end">
        <div><label htmlFor="caja-mode" className="block font-bold mb-1">Consulta</label><select id="caja-mode" value={selection.mode} disabled={disabled} className={input} onChange={(event) => setSelection('mode', event.target.value)}><option value="actual">Turno actual</option><option value="specific">Fecha y turno</option></select></div>
        {selection.mode === 'specific' && <>
          <div><label htmlFor="caja-fecha" className="block font-bold mb-1">Fecha contable</label><input id="caja-fecha" type="date" value={selection.fecha} disabled={disabled} onChange={(event) => setSelection('fecha', event.target.value)} className={input} aria-describedby={state.consolidado.error ? 'caja-selection-error' : undefined} aria-invalid={Boolean(state.consolidado.error)} /></div>
          <div><label htmlFor="caja-turno" className="block font-bold mb-1">Turno</label><select id="caja-turno" value={selection.turno} disabled={disabled} onChange={(event) => setSelection('turno', event.target.value)} className={input} aria-describedby={state.consolidado.error ? 'caja-selection-error' : undefined} aria-invalid={Boolean(state.consolidado.error)}><option value="">Seleccioná un turno</option>{Object.entries(TURNOS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        </>}
        <button type="submit" className={secondary} disabled={disabled || state.consolidado.status === 'loading'}>Consultar consolidado</button>
      </form>
      <p className="text-sm">El turno actual y su fecha contable los determina el servidor. Noche puede terminar al día siguiente.</p>
      {state.consolidado.error && <div id="caja-selection-error" ref={selectionError} tabIndex={-1}><Status resource={state.consolidado} onRetry={controller.loadConsolidado} /></div>}
      {state.consolidado.status === 'loading' && <Status resource={state.consolidado} />}
      {data && <div className="space-y-4">
        <p className="font-bold text-lg">{formatDate(data.fecha)} · {TURNOS[data.turno]}</p>
        <p className="text-sm">Ventana: {formatTimestamp(data.desde)} — {formatTimestamp(data.hasta)}</p>
        <MoneySummary data={data} consolidated />
        <p>Pagos: <strong>{data.cantidad_pagos}</strong></p>
        <p className="rounded-xl border border-monu-orange/40 bg-monu-cream p-3"><strong>{data.pagos_pendientes_conciliacion} pagos pendientes de conciliación.</strong> No representan dinero confirmado y no se incluyen como ingresos conciliados. Su existencia no impide generar el cierre.</p>
        <h3 className="font-bold">Desglose por método</h3>
        {data.desglose_metodos.length ? <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">{data.desglose_metodos.map((item) => <div className="rounded-xl border border-monu-green/15 p-3" key={item.metodo_pago}><dt className="font-bold">{METODOS[item.metodo_pago]}</dt><dd className="tabular-nums">{formatMoney(item.total)} · {item.cantidad} movimientos</dd></div>)}</dl> : <p>No hay movimientos en esta ventana.</p>}
        <p className="text-sm">Los importes provienen de la API. El cierre puede incorporar arrastre de conciliados anteriores y diferir de este consolidado.</p>
        {knownApproved ? <p className="font-bold">El cierre de este turno está aprobado y es inalterable.</p> : generating && <button type="button" className={primary} onClick={(event) => { returnFocus.current = event?.currentTarget || document.activeElement; void controller.prepareGenerate(); }} disabled={disabled || Boolean(state.uncertain)}>Generar cierre</button>}
      </div>}
    </section>
    <section className={`${panel} space-y-4`} aria-labelledby="caja-history-title">
      <h2 id="caja-history-title" className="text-xl font-extrabold">Historial de cierres</h2>
      <form noValidate onSubmit={(event) => { event.preventDefault(); void controller.loadHistory(); }} className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4 items-end">
        <div><label htmlFor="caja-desde" className="block font-bold mb-1">Desde</label><input id="caja-desde" type="date" value={filters.desde} disabled={disabled} onChange={(event) => setFilter('desde', event.target.value)} className={input} aria-describedby={state.history.error ? 'caja-history-error' : undefined} aria-invalid={Boolean(state.history.error)} /></div>
        <div><label htmlFor="caja-hasta" className="block font-bold mb-1">Hasta</label><input id="caja-hasta" type="date" value={filters.hasta} disabled={disabled} onChange={(event) => setFilter('hasta', event.target.value)} className={input} aria-describedby={state.history.error ? 'caja-history-error' : undefined} aria-invalid={Boolean(state.history.error)} /></div>
        <div><label htmlFor="caja-estado" className="block font-bold mb-1">Estado</label><select id="caja-estado" value={filters.estado} disabled={disabled} onChange={(event) => setFilter('estado', event.target.value)} className={input}><option value="">Todos</option>{Object.entries(ESTADOS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <button type="submit" disabled={disabled || state.history.status === 'loading'} className={secondary}>Consultar historial</button>
      </form>
      {state.history.error && <div id="caja-history-error" ref={historyError} tabIndex={-1}><Status resource={state.history} onRetry={controller.loadHistory} /></div>}
      {state.history.status === 'loading' && <Status resource={state.history} />}
      {state.history.status === 'ready' && (state.history.data.length ? <ul className="grid lg:grid-cols-2 gap-4">{state.history.data.map((item) => <li key={item.id} className="rounded-xl border border-monu-green/20 p-4 space-y-2 min-w-0">
        <h3 className="font-bold">Cierre #{item.id} · {formatDate(item.fecha)} · {TURNOS[item.turno]}</h3>
        <p className="font-semibold">{ESTADOS[item.estado]}</p><p className="font-bold tabular-nums">Total general: {formatMoney(item.total_general)}</p>
        <p className="text-sm">Efectivo: {formatMoney(item.total_efectivo)} · Billeteras: {formatMoney(item.total_billeteras)} · Devoluciones: {formatMoney(item.total_devoluciones)}</p>
        <p className="text-sm">Generado por: {item.generado_por ? `Usuario #${item.generado_por}` : 'Sin informar'} · Aprobado por: {item.aprobado_por ? `Usuario #${item.aprobado_por}` : 'Sin aprobación'}</p>
        <button type="button" className={secondary} disabled={disabled} onClick={() => { setDetailRetry(item.id); void controller.loadDetail(item.id); }}>Ver detalle #{item.id}</button>
      </li>)}</ul> : <p>No hay cierres para estos filtros.</p>)}
      <p className="text-sm">“Abierto” es un estado del contrato existente. Esta pantalla no ofrece apertura de caja.</p>
    </section>
    {state.detail.status !== 'idle' && <section className={`${panel} space-y-4`} aria-labelledby="caja-detail-title">
      <h2 id="caja-detail-title" className="text-xl font-extrabold">Detalle del cierre{detail ? ` #${detail.id}` : ''}</h2>
      <Status resource={state.detail} onRetry={detailRetry ? () => controller.loadDetail(detailRetry) : undefined} />
      {detail && <><RecordInfo data={detail} />
        {detail.estado === 'APROBADO' ? <p className="flex items-center gap-2 font-bold"><LockKeyhole aria-hidden="true" className="size-5" />Cierre aprobado e inalterable</p> : approving && <button type="button" className={primary} onClick={(event) => { returnFocus.current = event?.currentTarget || document.activeElement; void controller.prepareApprove(detail.id); }} disabled={disabled || Boolean(state.uncertain)}>Aprobar cierre</button>}
      </>}
    </section>}
    {state.busy === 'prepare' && <p role="status">Comprobando el estado del cierre…</p>}
    {state.dialog && <Confirmation state={state} controller={controller} returnFocus={returnFocus} />}
  </div>;
}
export default function Caja() {
  const { user, refreshSession } = useAuth();
  if (!can(user, 'caja.ver')) return <section className={panel}><h1 className="text-2xl font-extrabold">Caja</h1><p role="alert">Sin permiso para consultar Caja.</p></section>;
  return <CajaSession key={JSON.stringify(user)} user={user} refreshSession={refreshSession} />;
}
