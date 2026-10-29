// Detalle de un pedido en un diálogo modal: datos del cliente, entrega, productos e
// historial, y las operaciones del personal (estado, reparto, pagos y edición)
// según permisos. Toda operación pasa por la cola de mutaciones de DataContext.
import { UserFacingError, userErrorMessage } from '../shared/api/userErrors.js';
import { extrasLabel } from '../ordering/ingredientExtras';
import { useCallback, useEffect, useRef, useState } from 'react';
import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { apiFetch } from '../shared/api/http';
import { createOrderCommands } from './orderCommands';
import { addressLabel, confirmedOrder, dateTime, knownLabel, money, paymentMethodLabel, stateLabel } from './orderModel';
import { buttonClass, DataError } from './operationUi';
import { EditOperation, StateOperation } from './OrderOperationForms';
import OrderDelivery from './OrderDelivery';
import OrderPayments from './OrderPayments';

// Comandos HTTP de pedidos compartidos por el detalle y sus secciones.
const commands = createOrderCommands(apiFetch);

/**
 * Diálogo de detalle del pedido `id`. Usa el detalle en caché si existe y lo
 * refresca desde la API (`requireFresh` obliga a esperar el dato nuevo).
 * `onClose` recibe `{ changed }` al cerrarse.
 */
export default function OrderDetail({ id, onClose, requireFresh = false }) {
  const { user, refreshSession } = useAuth();
  const { state, startOrderOperation, orderOperationPending } = useData();
  // Detalle mostrado, estado de carga/error y si quedó desactualizado (stale) tras un fallo.
  const cached = state.orders.find((candidate) => candidate.id === id)?.detail;
  const [order, setOrder] = useState(cached || null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(requireFresh || !cached);
  const [stale, setStale] = useState(false);
  const [editRevision, setEditRevision] = useState(0);
  // Refs de control: bloqueo de operaciones, número de lectura vigente, el <dialog>,
  // si sigue montado y la lectura en curso (para abortarla).
  const lock = useRef(false);
  const request = useRef(0);
  const dialog = useRef(null);
  const mounted = useRef(true);
  const readController = useRef(null);
  const busy = loading || orderOperationPending(id);
  // Lee el detalle desde la API, valida que sea el pedido pedido y descarta respuestas viejas;
  // ante 401/403 oculta los datos y revalida la sesión.
  const load = useCallback(async () => {
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    const ticket = ++request.current;
    try {
      const result = await commands.detail(id, controller.signal);
      if (!confirmedOrder(result, id)) throw new UserFacingError('No se pudo verificar el detalle recibido. Actualizá antes de operar.');
      if (!controller.signal.aborted && mounted.current && ticket === request.current) { setOrder(result); setStale(false); }
    } catch (failure) {
      if (!controller.signal.aborted && mounted.current && ticket === request.current && [401, 403].includes(failure.status)) {
        setOrder(null);
        setStale(true);
        void refreshSession?.();
      }
      if (!controller.signal.aborted) throw failure;
    } finally {
      if (readController.current === controller) readController.current = null;
    }
  }, [id, refreshSession]);
  // Abre el diálogo nativo y carga el detalle al montar; al desmontar invalida todo lo pendiente.
  useEffect(() => {
    let active = true;
    mounted.current = true;
    dialog.current.showModal();
    Promise.resolve().then(() => { if (active) return load(); return undefined; })
      .catch((failure) => { if (active && mounted.current) { setStale(true); setError(userErrorMessage(failure, 'No pudimos cargar el pedido. Intentá nuevamente.')); } })
      .finally(() => { if (active && mounted.current) setLoading(false); });
    return () => { active = false; mounted.current = false; lock.current = false; request.current += 1; readController.current?.abort(); };
  }, [load]);
  // Cierra el diálogo sin cambios y cancela la lectura en curso.
  const close = () => {
    mounted.current = false;
    request.current += 1;
    readController.current?.abort();
    dialog.current?.close();
    onClose({ changed: false });
  };
  // Actualización manual del detalle.
  const reload = async () => {
    if (lock.current) return;
    lock.current = true;
    setLoading(true);
    setError('');
    try { await load(); } catch (failure) { if (mounted.current) setError(userErrorMessage(failure, 'No pudimos actualizar el pedido. Intentá nuevamente.')); }
    finally { lock.current = false; if (mounted.current) setLoading(false); }
  };
  // Lanza una operación del pedido vía `startOrderOperation`. Con `keepOpen` el diálogo
  // sigue abierto y muestra el pedido actualizado (o el error); si no, se cierra al aceptarse.
  const run = (operation, success, { keepOpen = false, optimisticOrder, resetEdit = false } = {}) => {
    if (lock.current || busy || stale) return;
    lock.current = true;
    const ticket = ++request.current;
    const accepted = startOrderOperation({
      id, number: order.numero, operation, success, optimisticOrder,
      onSuccess: keepOpen ? (updated) => {
        if (!mounted.current || ticket !== request.current) return;
        lock.current = false;
        request.current += 1;
        readController.current?.abort();
        setOrder(updated);
        if (resetEdit) setEditRevision((value) => value + 1);
        setStale(false);
        setError('');
      } : undefined,
      onError: keepOpen ? (message) => {
        if (!mounted.current || ticket !== request.current) return;
        lock.current = false;
        setStale(true);
        setError(message);
      } : undefined,
    });
    if (accepted && !keepOpen) close();
    else if (!accepted) lock.current = false;
  };
  return <dialog ref={dialog} aria-labelledby="order-detail-title" aria-busy={busy} onCancel={(event) => { event.preventDefault(); close(); }} className="m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-3xl rounded-2xl bg-monu-bone p-0 text-monu-text backdrop:bg-black/50">
    <div className="p-4 sm:p-6 space-y-5 overflow-y-auto">
      {/* Título y cierre del diálogo */}
      <div className="flex flex-wrap justify-between items-center gap-3"><h2 id="order-detail-title" className="text-2xl font-extrabold text-monu-dark">{order ? `Pedido #${order.numero}` : 'Detalle del pedido'}</h2><button type="button" onClick={close} className={buttonClass}>Cerrar detalle</button></div>
      {/* Actualización manual y errores de carga */}
      <button type="button" disabled={busy} onClick={() => { void reload(); }} className={buttonClass}>{loading ? 'Consultando detalle...' : 'Actualizar detalle'}</button>
      <DataError message={error} />
      {order && <>
        {/* Datos principales del pedido */}
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
          <dt className="font-bold">Cliente</dt><dd>{order.cliente}</dd>
          <dt className="font-bold">Estado</dt><dd>{stateLabel(order.estado)}</dd>
          <dt className="font-bold">Entrega</dt><dd>{order.tipo_entrega === 'RETIRO' ? 'Retiro en local' : addressLabel(order.direccion)}{order.direccion?.referencia && ` · ${order.direccion.referencia}`}</dd>
          <dt className="font-bold">Contacto</dt><dd>{order.telefono ? <a href={`tel:${order.telefono.replace(/[^+\d]/g, '')}`} className="underline inline-flex items-center min-h-11">{order.telefono}</a> : 'Teléfono no disponible'}</dd>
          <dt className="font-bold">Pago</dt><dd>{paymentMethodLabel(order.metodo_pago_acordado)}</dd>
          <dt className="font-bold">Total</dt><dd className="text-xl font-extrabold text-monu-dark">{money(order.total)}</dd>
          {order.observaciones && <><dt className="font-bold">Nota</dt><dd className="whitespace-pre-wrap break-words">{order.observaciones}</dd></>}
        </dl>
        {/* Productos del pedido */}
        <ul className="space-y-2">{order.items.map((item) => <li key={item.id} className="text-sm font-bold">{item.cantidad} × {item.nombre_producto}{item.aclaraciones ? ` · ${item.aclaraciones}` : ''}{item.extras?.length ? ` · ${extrasLabel(item.extras)}` : ''}</li>)}</ul>
        {/* Operaciones de estado y reparto; la key las remonta cuando cambia la versión o el envío */}
        {user && <div key={`${order.id}:${order.version}:${order.envio?.viaje_id}:${order.envio?.estado}:${order.envio?.estado_viaje}`} className="space-y-6 border-t border-monu-green/20 pt-5">
          {(can(user, 'pedidos.cambiar_estado') || can(user, 'pedidos.recuperar')) && <StateOperation can={(key) => can(user, key)} order={order} role={user.backendRole} commands={commands} run={run} busy={busy || stale} />}
          {(can(user, 'delivery.planificar') || can(user, 'delivery.operar') || can(user, 'delivery.corregir')) && <OrderDelivery can={(key) => can(user, key)} order={order} role={user.backendRole} commands={commands} run={run} busy={busy || stale} />}
        </div>}
        {/* Pagos y edición de dirección/entrega/pago */}
        {can(user, 'pagos.ver') && <OrderPayments can={(key) => can(user, key)} key={user.id} order={order} userId={user.id} commands={commands} run={run} busy={busy || stale} />}
        {can(user, 'pedidos.editar') && <EditOperation can={(key) => can(user, key)} key={`edit:${order.id}:${editRevision}`} order={order} role={user.backendRole} commands={commands} run={run} busy={busy || stale} />}
        {/* Historial de estados con sus marcas de tiempo y tratamiento de stock */}
        <details className="space-y-3 border-t border-monu-green/20 pt-3"><summary className="cursor-pointer min-h-11 flex items-center font-bold text-monu-green">Historial y detalles</summary>
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">{[['creado_en', 'Creado'], ['confirmado_en', 'Confirmado'], ['preparacion_en', 'Preparación'], ['listo_en', 'Listo'], ['entregado_en', 'Entregado'], ['cancelado_en', 'Cancelado']].filter(([key]) => order[key]).map(([key, label]) => <div className="contents" key={key}><dt className="font-bold">{label}</dt><dd>{dateTime(order[key])}</dd></div>)}</dl>
          <ol className="space-y-3">{order.historial.map((event) => <li key={event.id} className="border-l-2 border-monu-green/30 pl-3 text-sm space-y-1"><p className="font-bold">{stateLabel(event.estado_anterior)} → {stateLabel(event.estado_nuevo)}</p><p>{dateTime(event.creado_en)} · {event.actor || 'Sistema'}</p><p className="break-words">{event.observacion || 'Cambio de estado'}</p>{event.tratamiento_stock && <p>Stock: {knownLabel({ CONSERVAR: 'consumo conservado', RECONSUMIR: 'nuevo consumo', MERMA: 'merma declarada', RESERVA_DEVUELTA: 'reserva devuelta' }, event.tratamiento_stock)}</p>}</li>)}</ol>
        </details>
      </>}
    </div>
  </dialog>;
}
