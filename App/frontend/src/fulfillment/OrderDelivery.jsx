import { useEffect, useState } from 'react';
import { hasAssignment, isPrivileged, dateTime } from './orderModel';
import { buttonClass, inputClass, Field, Reason, DataError } from './operationUi';

export default function OrderDelivery({ order, role, commands, run, busy, can = null }) {
  const [riders, setRiders] = useState(null);
  const [error, setError] = useState('');
  const [rider, setRider] = useState('');
  const [reason, setReason] = useState('');
  const [confirmReturn, setConfirmReturn] = useState(false);
  const [action, setAction] = useState('');
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  const [riderName, setRiderName] = useState('');
  const assigned = hasAssignment(order);
  const shipment = order.envio;
  const beforeDeparture = assigned && shipment.estado === 'ASIGNADO' && shipment.estado_viaje === 'PLANIFICADO' && !shipment.salida_en;
  const canAssign = (!can || can('delivery.planificar')) && order.tipo_entrega === 'DELIVERY' && order.estado === 'LISTO' && !assigned;
  const canReadTrip = !can || can('delivery.ver');
  useEffect(() => {
    if ((!beforeDeparture && !canAssign) || (can && !can('delivery.planificar'))) return undefined;
    const controller = new AbortController();
    commands.riders(controller.signal).then((data) => { if (!controller.signal.aborted) {
      setRiders(data);
      setRider((selected) => data.some((item) => String(item.id) === selected) ? selected : '');
      setError('');
    } }).catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  // La versión remonta el formulario; los comandos no mantienen estado.
  }, [order.id, order.version, beforeDeparture, canAssign, availabilityRevision]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!shipment?.viaje_id || !canReadTrip) return undefined;
    const controller = new AbortController();
    commands.trip(shipment.viaje_id, controller.signal).then((trip) => { if (!controller.signal.aborted) setRiderName(trip.repartidor_nombre); }).catch((failure) => { if (!controller.signal.aborted) setError(`No se pudo consultar el repartidor. ${failure.message}`); });
    return () => controller.abort();
  }, [shipment?.viaje_id, availabilityRevision, canReadTrip]); // eslint-disable-line react-hooks/exhaustive-deps
  if (order.tipo_entrega !== 'DELIVERY') return null;
  const actions = [];
  if (canAssign) actions.push(['asignar', 'Asignar repartidor']);
  if (beforeDeparture && (!can || can('delivery.planificar'))) actions.push(['desasignar', 'Desasignar antes de salir'], ['reasignar', 'Cambiar repartidor antes de salir']);
  if ((!can || can('delivery.operar')) && assigned && shipment.estado === 'EN_CAMINO') actions.push(['fallo', 'Registrar problema de entrega']);
  if ((!can || can('delivery.planificar')) && assigned && shipment.estado === 'FALLIDO') actions.push(['regreso', 'Confirmar regreso físico al local']);
  if (shipment?.viaje_id && shipment.estado === 'ENTREGADO' && order.estado === 'ENTREGADO' && (can ? can('delivery.corregir') : isPrivileged(role))) actions.push(['corregir-entrega', 'Corregir entrega errónea con regreso real']);
  const selectedAction = action || actions[0]?.[0] || '';
  const actionLabel = actions.find(([id]) => id === selectedAction)?.[1];
  const needsRider = ['asignar', 'reasignar'].includes(selectedAction);
  const validRider = !needsRider || riders?.some((item) => String(item.id) === rider);
  const needsReturn = ['regreso', 'corregir-entrega'].includes(selectedAction);
  const perform = () => {
    if (busy || !actionLabel || !validRider) return;
    const annotation = reason.trim() || `Reparto desde el panel: ${actionLabel}.`;
    const body = { motivo: annotation, ...(needsRider ? { repartidor_id: Number(rider) } : {}), ...(needsReturn ? { version_esperada: order.version } : {}), ...(selectedAction === 'corregir-entrega' ? { regreso_confirmado: true } : {}) };
    void run(() => selectedAction === 'asignar' ? commands.assign(order.id, Number(rider), annotation) : commands.shipment(shipment.id, selectedAction, body), 'Reparto actualizado.');
  };
  const submit = (event) => {
    event.preventDefault();
    if (busy) return;
    if (needsReturn) setConfirmReturn(true);
    else perform();
  };
  const refreshRiders = () => { setRiders(null); setAvailabilityRevision((value) => value + 1); };
  return <section className="space-y-3">
    <h3 className="font-extrabold text-monu-dark">Reparto</h3>
    <p className="text-sm text-monu-text">{assigned ? `${riderName || 'Repartidor asignado'}. ${shipment.estado === 'FALLIDO' ? 'Problema de entrega: coordinar regreso.' : beforeDeparture ? 'Pedido todavía en el local.' : 'Viaje en curso.'}` : 'Sin repartidor asignado.'}</p>
    {shipment?.salida_en && <p className="text-sm">Salida registrada: {dateTime(shipment.salida_en)}</p>}
    <DataError message={error} retry={refreshRiders} busy={busy} />
    {actions.length > 0 && <form onSubmit={submit} className="space-y-3">
      {actions.length > 1 && <Field label="Acción de reparto"><select value={selectedAction} disabled={busy} onChange={(event) => { setAction(event.target.value); setConfirmReturn(false); }} className={inputClass}>{actions.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></Field>}
      {needsRider && <><Field label="Repartidor disponible"><select required value={rider} onChange={(event) => setRider(event.target.value)} disabled={busy || !riders} className={inputClass}><option value="">{riders ? 'Elegir repartidor' : 'Consultando disponibilidad...'}</option>{riders?.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}</select>{riders?.length === 0 && <span>No hay repartidores disponibles.</span>}</Field><button type="button" disabled={busy} onClick={refreshRiders} className={buttonClass}>Consultar disponibilidad nuevamente</button></>}
      {selectedAction === 'fallo' && <p className="text-sm text-orange-900">El pedido sigue asignado hasta registrar su regreso al local.</p>}
      <Reason value={reason} onChange={setReason} disabled={busy} />
      {confirmReturn ? <div className="rounded-xl bg-orange-50 p-3 space-y-3 text-sm text-orange-950"><p>¿El pedido #{order.numero} ya regresó físicamente al local? Volverá a listo para una nueva entrega.</p><div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={perform} className={`${buttonClass} bg-monu-green text-white`}>Confirmar regreso al local</button><button type="button" disabled={busy} onClick={() => setConfirmReturn(false)} className={buttonClass}>Volver</button></div></div>
        : <button disabled={busy || !actionLabel || !validRider} className={`${buttonClass} bg-monu-green text-white`}>{needsReturn ? 'Registrar regreso al local' : actionLabel}</button>}
    </form>}
  </section>;
}
