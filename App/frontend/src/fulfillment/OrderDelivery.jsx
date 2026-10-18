import { useEffect, useState } from 'react';
import { hasAssignment, isPrivileged, dateTime } from './orderModel';
import { buttonClass, inputClass, Field, Reason, Confirmation, DataError } from './operationUi';

export default function OrderDelivery({ order, role, commands, run, busy }) {
  const [riders, setRiders] = useState(null);
  const [error, setError] = useState('');
  const [rider, setRider] = useState('');
  const [reason, setReason] = useState('');
  const [returned, setReturned] = useState(false);
  const [action, setAction] = useState('');
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  const [riderName, setRiderName] = useState('');
  const assigned = hasAssignment(order);
  const shipment = order.envio;
  const beforeDeparture = assigned && shipment.estado === 'ASIGNADO' && shipment.estado_viaje === 'PLANIFICADO' && !shipment.salida_en;
  const canAssign = order.tipo_entrega === 'DELIVERY' && order.estado === 'LISTO' && !assigned;
  useEffect(() => {
    if (!beforeDeparture && !canAssign) return undefined;
    const controller = new AbortController();
    commands.riders(controller.signal).then((data) => { if (!controller.signal.aborted) { setRiders(data); setError(''); } }).catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  // La versión remonta el formulario; los comandos no mantienen estado.
  }, [order.id, order.version, beforeDeparture, canAssign, availabilityRevision]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!shipment?.viaje_id) return undefined;
    const controller = new AbortController();
    commands.trip(shipment.viaje_id, controller.signal).then((trip) => { if (!controller.signal.aborted) setRiderName(trip.repartidor_nombre); }).catch((failure) => { if (!controller.signal.aborted) setError(`No se pudo consultar el repartidor. ${failure.message}`); });
    return () => controller.abort();
  }, [shipment?.viaje_id, availabilityRevision]); // eslint-disable-line react-hooks/exhaustive-deps
  if (order.tipo_entrega !== 'DELIVERY') return <p className="text-sm text-monu-text">Retiro en local: registrar la entrega desde Estado y correcciones.</p>;
  const actions = [];
  if (canAssign) actions.push(['asignar', 'Asignar repartidor']);
  if (beforeDeparture) actions.push(['desasignar', 'Desasignar antes de salir'], ['reasignar', 'Cambiar repartidor antes de salir']);
  if (assigned && shipment.estado === 'EN_CAMINO') actions.push(['fallo', 'Registrar problema de entrega']);
  if (assigned && shipment.estado === 'FALLIDO') actions.push(['regreso', 'Confirmar regreso físico al local']);
  if (shipment?.viaje_id && shipment.estado === 'ENTREGADO' && order.estado === 'ENTREGADO' && isPrivileged(role)) actions.push(['corregir-entrega', 'Corregir entrega errónea con regreso real']);
  const needsRider = ['asignar', 'reasignar'].includes(action);
  const needsReturn = ['regreso', 'corregir-entrega'].includes(action);
  const submit = (event) => {
    event.preventDefault();
    if (!reason.trim() || !action || (needsReturn && !returned)) return;
    const body = { motivo: reason.trim(), ...(needsRider ? { repartidor_id: Number(rider) } : {}), ...(needsReturn ? { version_esperada: order.version } : {}), ...(action === 'corregir-entrega' ? { regreso_confirmado: true } : {}) };
    void run(() => action === 'asignar' ? commands.assign(order.id, Number(rider), reason.trim()) : commands.shipment(shipment.id, action, body), 'Operación de reparto registrada.');
  };
  return <section className="space-y-3">
    <h3 className="font-extrabold text-monu-dark">Reparto</h3>
    <p className="text-sm text-monu-text">{assigned ? `${riderName || 'Repartidor asignado'}. ${shipment.estado === 'FALLIDO' ? 'Problema de entrega: coordinar regreso.' : beforeDeparture ? 'Pedido todavía en el local.' : 'Viaje en curso.'}` : 'Sin repartidor asignado.'}</p>
    {shipment?.salida_en && <p className="text-sm">Salida registrada: {dateTime(shipment.salida_en)}</p>}
    <DataError message={error} retry={() => setAvailabilityRevision((value) => value + 1)} busy={busy} />
    {actions.length > 0 && <form onSubmit={submit} className="space-y-3">
      <Field label="Acción de reparto"><select required value={action} disabled={busy} onChange={(event) => { setAction(event.target.value); setReturned(false); }} className={inputClass}><option value="">Elegir acción</option>{actions.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></Field>
      {needsRider && <><Field label="Repartidor disponible"><select required value={rider} onChange={(event) => setRider(event.target.value)} disabled={busy || !riders} className={inputClass}><option value="">{riders ? 'Elegir repartidor' : 'Consultando disponibilidad...'}</option>{riders?.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}</select>{riders?.length === 0 && <span>No hay repartidores disponibles.</span>}</Field><button type="button" disabled={busy} onClick={() => setAvailabilityRevision((value) => value + 1)} className={buttonClass}>Consultar disponibilidad nuevamente</button></>}
      {action === 'fallo' && <p className="text-sm text-orange-900">Registrar el fallo conserva el viaje y la asignación. Confirmá el regreso solo cuando el pedido vuelva físicamente al local.</p>}
      <Reason value={reason} onChange={setReason} disabled={busy} />
      {needsReturn && <Confirmation checked={returned} onChange={setReturned} disabled={busy}>Confirmo que el pedido regresó físicamente al local. Se conserva el consumo de insumos y vuelve a listo.</Confirmation>}
      <button disabled={busy || !action || (needsRider && !rider) || (needsReturn && !returned)} className={`${buttonClass} bg-monu-green text-white`}>Registrar reparto</button>
    </form>}
  </section>;
}
