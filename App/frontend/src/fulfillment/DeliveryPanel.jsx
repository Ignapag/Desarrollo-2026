// Panel de reparto (delivery): lista los viajes asignados al repartidor con sus
// envíos y permite salir a repartir, marcar entregas o registrar problemas.
// Se actualiza solo cada 8 s y toda acción física queda registrada en la API.
import { UserFacingError, userErrorMessage } from '../shared/api/userErrors.js';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Phone, Navigation } from 'lucide-react';
import { can, canVisit } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { apiFetch } from '../shared/api/http';
import { createOrderCommands } from './orderCommands';
import { dateTime, knownLabel, money } from './orderModel';
import { buttonClass, Reason, DataError } from './operationUi';
import OrderDetail from './OrderDetail';
import WhatsAppAttentionNotice from './WhatsAppAttentionNotice';

// Comandos HTTP de pedidos y reparto compartidos por todo el panel.
const commands = createOrderCommands(apiFetch);

/** Pantalla principal de reparto para repartidores y personal con permiso de delivery. */
export default function DeliveryPanel() {
  const { user, logout, refreshSession } = useAuth();
  const { runOrderMutation, state } = useData();
  // Viajes cargados, estado de operación en curso, errores, avisos y pedido abierto en detalle.
  const [trips, setTrips] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [selected, setSelected] = useState(null);
  // `lock` impide operaciones simultáneas y `generation` descarta cargas viejas.
  const lock = useRef(false);
  const generation = useRef(0);
  // Si la API niega el acceso, limpia los datos visibles y revalida la sesión.
  const withdrawForbidden = useCallback((failure) => {
    if (![401, 403].includes(failure.status)) return;
    setTrips(null);
    setSelected(null);
    setFeedback('');
    void refreshSession?.();
  }, [refreshSession]);
  // Carga los viajes activos y el detalle de cada uno (con sus envíos), validando la respuesta.
  const load = useCallback(async (signal) => {
    const ticket = ++generation.current;
    try {
      const list = await commands.trips(signal);
      if (!Array.isArray(list) || !list.every((trip) => Number.isSafeInteger(trip?.id) && trip.id > 0)) throw new UserFacingError('No pudimos cargar los viajes. Intentá nuevamente.');
      const details = await Promise.all(list.map((trip) => commands.trip(trip.id, signal)));
      if (!details.every((trip, index) => trip?.id === list[index].id && Array.isArray(trip.envios))) throw new UserFacingError('No pudimos cargar los viajes. Intentá nuevamente.');
      if (!signal?.aborted && ticket === generation.current) { setTrips(details); setError(''); }
    } catch (failure) {
      if (!signal?.aborted && ticket === generation.current) withdrawForbidden(failure);
      throw failure;
    }
  }, [withdrawForbidden]);
  // Sondeo de viajes: al montar, cada 8 s y al volver a la pestaña (si no hay una acción en curso).
  useEffect(() => {
    const controller = new AbortController();
    const update = () => {
      if (document.hidden || lock.current) return;
      void load(controller.signal).catch((failure) => { if (!controller.signal.aborted) setError(userErrorMessage(failure, 'No pudimos actualizar los viajes. Se conserva la última información. Intentá nuevamente.')); });
    };
    update();
    const timer = setInterval(update, 8000);
    document.addEventListener('visibilitychange', update);
    return () => { generation.current += 1; controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, [load]);
  // Actualización manual de viajes desde el botón.
  const refresh = async () => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try { await load(); } catch (failure) { setError(userErrorMessage(failure, 'No pudimos actualizar los viajes. Intentá nuevamente.')); }
    finally { lock.current = false; setBusy(false); }
  };
  // Ejecuta una acción de reparto como mutación de pedidos, valida el acuse con `accepts`
  // y recarga los viajes; si falla, pide revisar el viaje antes de reintentar.
  const run = async (operation, accepts) => {
    if (lock.current) return;
    lock.current = true;
    generation.current += 1;
    setBusy(true);
    setError('');
    setFeedback('');
    try {
      await runOrderMutation(async () => {
        const result = await operation();
        if (!accepts(result)) throw new UserFacingError('No pudimos confirmar la acción de reparto. Actualizá y revisá el viaje antes de reintentar.');
        return result;
      });
      setFeedback('Operación de reparto registrada.');
      try { await load(); } catch (failure) { setError(`La operación se registró, pero falta actualizar los viajes. ${userErrorMessage(failure, 'Intentá actualizar nuevamente.')}`); }
    } catch (failure) { withdrawForbidden(failure); setError(`${userErrorMessage(failure, 'No pudimos confirmar la acción de reparto.')} Actualizá y revisá el viaje antes de reintentar.`); }
    finally { lock.current = false; setBusy(false); }
  };
  return <main className="space-y-6 max-w-4xl mx-auto p-4 sm:p-6 min-h-screen bg-monu-cream text-monu-text">
    {/* Aviso de conversaciones de WhatsApp que requieren atención del personal */}
    <WhatsAppAttentionNotice />
    {/* Encabezado con accesos a pedidos y cierre de sesión */}
    <div className="flex flex-wrap justify-between items-start gap-3"><div><h1 className="text-3xl font-extrabold font-heading text-monu-dark">Reparto</h1><p>Viajes y envíos asignados en el sistema.</p></div><div className="flex flex-wrap gap-2">{canVisit(user, '/dashboard/orders') && <Link to="/dashboard/orders" className={buttonClass}>Volver a pedidos</Link>}<button type="button" onClick={() => { void logout(); }} className={buttonClass}>Cerrar sesión</button></div></div>
    {/* Estado de la carga: actualización manual, errores, avisos y lista vacía */}
    <button type="button" disabled={busy} onClick={() => { void refresh(); }} className={buttonClass}>{busy ? 'Procesando...' : 'Actualizar viajes'}</button>
    <DataError message={error || state.ordersError} />
    {feedback && <p role="status" className="font-bold text-monu-green">{feedback}</p>}
    {!trips && !error && <p role="status">Consultando viajes asignados...</p>}
    {trips?.length === 0 && <p>No hay viajes activos asignados.</p>}
    {/* Un bloque por viaje con sus envíos */}
    {trips?.map((trip) => <section key={trip.id} aria-labelledby={`trip-${trip.id}`} className="bg-white rounded-2xl border border-monu-green/20 p-4 sm:p-5 space-y-4">
      <h2 id={`trip-${trip.id}`} className="text-xl font-extrabold text-monu-dark">Viaje de {trip.repartidor_nombre}</h2>
      <p className="text-sm">{trip.estado === 'PLANIFICADO' ? 'Asignado, todavía en el local' : 'En ruta'} · Creado: {dateTime(trip.creado_en)} · Salida: {dateTime(trip.salida_en)}</p>
      {can(user, 'delivery.operar') && trip.estado === 'PLANIFICADO' && <StartTrip trip={trip} run={run} busy={busy} />}
      <div className="space-y-4">{trip.envios.map((shipment) => <Shipment key={`${shipment.id}:${shipment.estado}`} trip={trip} shipment={shipment} run={run} busy={busy || !can(user, 'delivery.operar')} onDetail={can(user, 'pedidos.ver') ? () => setSelected(shipment.pedido_id) : null} />)}</div>
    </section>)}
    {/* Detalle del pedido (correcciones) abierto desde un envío */}
    {selected && <OrderDetail key={selected} id={selected} onClose={({ changed }) => { setSelected(null); if (changed) void refresh(); }} />}
  </main>;
}

/** Botón para iniciar un viaje planificado: pasa sus pedidos a "en camino". */
function StartTrip({ trip, run, busy }) {
  return <button type="button" disabled={busy} onClick={() => { if (!busy) void run(() => commands.startTrip(trip.id), (result) => result?.viaje_id === trip.id && Array.isArray(result.pedidos_en_camino)); }} className={`${buttonClass} bg-monu-green text-white`}>Salir a repartir</button>;
}

/**
 * Tarjeta de un envío: datos del cliente, dirección (con enlace a Google Maps),
 * saldo a cobrar y acciones de entrega o de problema mientras el viaje está en ruta.
 */
function Shipment({ shipment, trip, run, busy, onDetail }) {
  // Nota del problema de entrega y datos derivados del envío (dirección, teléfono, si está en ruta).
  const [reason, setReason] = useState('');
  const address = [shipment.calle, shipment.altura, shipment.piso_depto, shipment.zona_nombre].filter(Boolean).join(', ');
  const phone = shipment.telefono_cliente?.replace(/[^+\d]/g, '');
  const onRoad = trip.estado === 'EN_RUTA' && Boolean(trip.salida_en) && shipment.estado === 'EN_CAMINO';
  // Un acuse válido debe corresponder a este envío y a su pedido.
  const accepts = (result) => result?.envio_id === shipment.id && result.pedido_id === shipment.pedido_id;
  return <article className="rounded-xl bg-monu-bone border border-monu-green/20 p-4 space-y-3">
    {/* Datos del pedido y del cliente */}
    <h3 className="text-xl font-extrabold text-monu-dark">Pedido #{shipment.numero}</h3>
    <p className="text-sm font-bold">{knownLabel({ ASIGNADO: 'Asignado', EN_CAMINO: 'En camino', FALLIDO: 'Entrega con problema: coordinar regreso', ENTREGADO: 'Entregado' }, shipment.estado)}</p>
    <p className="font-bold">{shipment.cliente_nombre}</p>
    <p className="flex gap-2 break-words"><MapPin aria-hidden="true" className="h-5 w-5 shrink-0" />{address || 'Dirección no disponible: consultá con el local.'}</p>
    {shipment.referencia && <p className="text-sm break-words">Referencia: {shipment.referencia}</p>}
    <p className="text-sm">Total: {money(shipment.total)} · Saldo pendiente: {money(shipment.saldo_pendiente)}</p>
    {Number(shipment.saldo_pendiente) > 0 && <p className="text-sm text-orange-900">Coordiná el cobro con el local. Entregar el pedido no registra dinero recibido.</p>}
    {/* Contacto: llamada, mapa y detalle del pedido */}
    <div className="flex flex-wrap gap-3">
      {phone ? <a href={`tel:${phone}`} className={`${buttonClass} inline-flex gap-2 items-center`}><Phone aria-hidden="true" className="h-5 w-5" />Llamar al cliente</a> : <p className="text-sm">Teléfono no disponible</p>}
      {shipment.calle && <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`} target="_blank" rel="noopener noreferrer" className={`${buttonClass} inline-flex gap-2 items-center`}><Navigation aria-hidden="true" className="h-5 w-5" />Ver dirección<span className="sr-only"> (otra pestaña)</span></a>}
      {onDetail && <button type="button" onClick={onDetail} disabled={busy} className={buttonClass}>Detalle y correcciones</button>}
    </div>
    {/* Acciones disponibles solo con el envío en camino */}
    {onRoad && <div className="space-y-3">
      <button type="button" disabled={busy} onClick={() => { if (!busy) void run(() => commands.shipment(shipment.id, 'entregar'), accepts); }} className={`${buttonClass} bg-monu-dark text-white`}>Marcar entregado</button>
      <details><summary className="cursor-pointer min-h-11 flex items-center text-sm font-bold text-monu-green">Problema con la entrega</summary><form className="space-y-2" onSubmit={(event) => { event.preventDefault(); if (!busy) void run(() => commands.shipment(shipment.id, 'fallo', { motivo: reason.trim() || 'Problema de entrega registrado por el repartidor.' }), accepts); }}><Reason value={reason} onChange={setReason} disabled={busy} /><button disabled={busy} className={buttonClass}>Registrar problema de entrega</button><p className="text-sm">El pedido sigue asignado hasta registrar su regreso al local.</p></form></details>
    </div>}
  </article>;
}
