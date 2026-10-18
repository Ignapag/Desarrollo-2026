import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Phone, Navigation } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { apiFetch } from '../shared/api/http';
import { createOrderCommands } from './orderCommands';
import { dateTime, isStaff, money } from './orderModel';
import { buttonClass, Reason, Confirmation, DataError } from './operationUi';
import OrderDetail from './OrderDetail';

const commands = createOrderCommands(apiFetch);

export default function DeliveryPanel() {
  const { user, logout } = useAuth();
  const { runOrderMutation, state } = useData();
  const [trips, setTrips] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [selected, setSelected] = useState(null);
  const lock = useRef(false);
  const generation = useRef(0);
  const load = useCallback(async (signal) => {
    const ticket = ++generation.current;
    const list = await commands.trips(signal);
    const details = await Promise.all(list.map((trip) => commands.trip(trip.id, signal)));
    if (!signal?.aborted && ticket === generation.current) { setTrips(details); setError(''); }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const update = () => {
      if (document.hidden || lock.current) return;
      void load(controller.signal).catch((failure) => { if (!controller.signal.aborted) setError(`No se pudieron actualizar los viajes. Se conserva la última información. ${failure.message}`); });
    };
    update();
    const timer = setInterval(update, 8000);
    document.addEventListener('visibilitychange', update);
    return () => { generation.current += 1; controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, [load]);
  const refresh = async () => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try { await load(); } catch (failure) { setError(`No se pudieron actualizar los viajes. ${failure.message}`); }
    finally { lock.current = false; setBusy(false); }
  };
  const run = async (operation) => {
    if (lock.current) return;
    lock.current = true;
    generation.current += 1;
    setBusy(true);
    setError('');
    setFeedback('');
    try {
      await runOrderMutation(operation);
      setFeedback('Operación de reparto registrada.');
      try { await load(); } catch (failure) { setError(`La operación se registró, pero falta actualizar los viajes. ${failure.message}`); }
    } catch (failure) { setError(`${failure.message} Actualizá y revisá el viaje antes de reintentar.`); }
    finally { lock.current = false; setBusy(false); }
  };
  return <main className="space-y-6 max-w-4xl mx-auto p-4 sm:p-6 min-h-screen bg-monu-cream text-monu-text">
    <div className="flex flex-wrap justify-between items-start gap-3"><div><h1 className="text-3xl font-extrabold font-heading text-monu-dark">Reparto</h1><p>Viajes y envíos asignados en el sistema.</p></div><div className="flex flex-wrap gap-2">{isStaff(user?.backendRole) && <Link to="/dashboard/orders" className={buttonClass}>Volver a pedidos</Link>}<button type="button" onClick={() => { void logout(); }} className={buttonClass}>Cerrar sesión</button></div></div>
    <button type="button" disabled={busy} onClick={() => { void refresh(); }} className={buttonClass}>{busy ? 'Procesando...' : 'Actualizar viajes'}</button>
    <DataError message={error || state.ordersError} />
    {feedback && <p role="status" className="font-bold text-monu-green">{feedback}</p>}
    {!trips && !error && <p role="status">Consultando viajes asignados...</p>}
    {trips?.length === 0 && <p>No hay viajes activos asignados.</p>}
    {trips?.map((trip) => <section key={trip.id} aria-labelledby={`trip-${trip.id}`} className="bg-white rounded-2xl border border-monu-green/20 p-4 sm:p-5 space-y-4">
      <h2 id={`trip-${trip.id}`} className="text-xl font-extrabold text-monu-dark">Viaje de {trip.repartidor_nombre}</h2>
      <p className="text-sm">{trip.estado === 'PLANIFICADO' ? 'Asignado, todavía en el local' : 'En ruta'} · Creado: {dateTime(trip.creado_en)} · Salida: {dateTime(trip.salida_en)}</p>
      {trip.estado === 'PLANIFICADO' && <StartTrip trip={trip} run={run} busy={busy} />}
      <div className="space-y-4">{trip.envios.map((shipment) => <Shipment key={`${shipment.id}:${shipment.estado}`} trip={trip} shipment={shipment} run={run} busy={busy} onDetail={isStaff(user?.backendRole) ? () => setSelected(shipment.pedido_id) : null} />)}</div>
    </section>)}
    {selected && <OrderDetail key={selected} id={selected} onClose={() => { setSelected(null); void refresh(); }} />}
  </main>;
}

function StartTrip({ trip, run, busy }) {
  const [confirmed, setConfirmed] = useState(false);
  return <div className="space-y-2"><Confirmation checked={confirmed} onChange={setConfirmed} disabled={busy}>Confirmo la salida física del repartidor con estos pedidos.</Confirmation><button type="button" disabled={busy || !confirmed} onClick={() => { void run(() => commands.startTrip(trip.id)); }} className={`${buttonClass} bg-monu-green text-white`}>Registrar salida del viaje</button></div>;
}

function Shipment({ shipment, trip, run, busy, onDetail }) {
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState('');
  const address = [shipment.calle, shipment.altura, shipment.piso_depto, shipment.zona_nombre].filter(Boolean).join(', ');
  const phone = shipment.telefono_cliente?.replace(/[^+\d]/g, '');
  const onRoad = trip.estado === 'EN_RUTA' && Boolean(trip.salida_en) && shipment.estado === 'EN_CAMINO';
  return <article className="rounded-xl bg-monu-bone border border-monu-green/20 p-4 space-y-3">
    <h3 className="text-xl font-extrabold text-monu-dark">Pedido #{shipment.numero}</h3>
    <p className="text-sm font-bold">{({ ASIGNADO: 'Asignado', EN_CAMINO: 'En camino', FALLIDO: 'Entrega con problema: coordinar regreso', ENTREGADO: 'Entregado' })[shipment.estado] || shipment.estado}</p>
    <p className="font-bold">{shipment.cliente_nombre}</p>
    <p className="flex gap-2 break-words"><MapPin aria-hidden="true" className="h-5 w-5 shrink-0" />{address || 'Dirección no disponible: consultá con el local.'}</p>
    {shipment.referencia && <p className="text-sm break-words">Referencia: {shipment.referencia}</p>}
    <p className="text-sm">Total: {money(shipment.total)} · Saldo pendiente: {money(shipment.saldo_pendiente)}</p>
    {Number(shipment.saldo_pendiente) > 0 && <p className="text-sm text-orange-900">Coordiná el cobro con el local. Entregar el pedido no registra dinero recibido.</p>}
    <div className="flex flex-wrap gap-3">
      {phone ? <a href={`tel:${phone}`} className={`${buttonClass} inline-flex gap-2 items-center`}><Phone aria-hidden="true" className="h-5 w-5" />Llamar al cliente</a> : <p className="text-sm">Teléfono no disponible</p>}
      {shipment.calle && <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`} target="_blank" rel="noopener noreferrer" className={`${buttonClass} inline-flex gap-2 items-center`}><Navigation aria-hidden="true" className="h-5 w-5" />Ver dirección<span className="sr-only"> (otra pestaña)</span></a>}
      {onDetail && <button type="button" onClick={onDetail} disabled={busy} className={buttonClass}>Detalle y correcciones</button>}
    </div>
    {onRoad && <div className="space-y-3">
      <Confirmation checked={confirmed} onChange={setConfirmed} disabled={busy}>Confirmo que entregué físicamente este pedido al cliente.</Confirmation>
      <button type="button" disabled={busy || !confirmed} onClick={() => { void run(() => commands.shipment(shipment.id, 'entregar')); }} className={`${buttonClass} bg-monu-dark text-white`}>Registrar entrega real</button>
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); if (reason.trim()) void run(() => commands.shipment(shipment.id, 'fallo', { motivo: reason.trim() })); }}><Reason value={reason} onChange={setReason} disabled={busy} /><button disabled={busy || !reason.trim()} className={buttonClass}>Registrar problema de entrega</button><p className="text-sm">El fallo mantiene la asignación. El personal del local confirma el regreso físico.</p></form>
    </div>}
  </article>;
}
