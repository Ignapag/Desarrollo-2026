import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { apiFetch } from '../shared/api/http';
import { createOrderCommands } from './orderCommands';
import { addressLabel, dateTime, isStaff, money, stateLabel } from './orderModel';
import { buttonClass, DataError } from './operationUi';
import { EditOperation, StateOperation } from './OrderOperationForms';
import OrderDelivery from './OrderDelivery';
import OrderPayments from './OrderPayments';

const commands = createOrderCommands(apiFetch);

export default function OrderDetail({ id, onClose, requireFresh = false }) {
  const { user } = useAuth();
  const { state, startOrderOperation, orderOperationPending } = useData();
  const cached = state.orders.find((candidate) => candidate.id === id)?.detail;
  const [order, setOrder] = useState(cached || null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(requireFresh || !cached);
  const [stale, setStale] = useState(false);
  const lock = useRef(false);
  const request = useRef(0);
  const dialog = useRef(null);
  const mounted = useRef(true);
  const readController = useRef(null);
  const busy = loading || orderOperationPending(id);
  const load = useCallback(async () => {
    readController.current?.abort();
    const controller = new AbortController();
    readController.current = controller;
    const ticket = ++request.current;
    try {
      const result = await commands.detail(id, controller.signal);
      if (!controller.signal.aborted && mounted.current && ticket === request.current) { setOrder(result); setStale(false); }
    } catch (failure) {
      if (!controller.signal.aborted) throw failure;
    } finally {
      if (readController.current === controller) readController.current = null;
    }
  }, [id]);
  useEffect(() => {
    let active = true;
    mounted.current = true;
    dialog.current.showModal();
    Promise.resolve().then(() => { if (active) return load(); return undefined; })
      .catch((failure) => { if (active && mounted.current) { setStale(true); setError(failure.message); } })
      .finally(() => { if (active && mounted.current) setLoading(false); });
    return () => { active = false; mounted.current = false; lock.current = false; request.current += 1; readController.current?.abort(); };
  }, [load]);
  const close = () => {
    mounted.current = false;
    request.current += 1;
    readController.current?.abort();
    dialog.current?.close();
    onClose({ changed: false });
  };
  const reload = async () => {
    if (lock.current) return;
    lock.current = true;
    setLoading(true);
    setError('');
    try { await load(); } catch (failure) { if (mounted.current) setError(`No se pudo actualizar el detalle. ${failure.message}`); }
    finally { lock.current = false; if (mounted.current) setLoading(false); }
  };
  const run = (operation, success, { keepOpen = false, optimisticOrder } = {}) => {
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
      <div className="flex flex-wrap justify-between items-center gap-3"><h2 id="order-detail-title" className="text-2xl font-extrabold text-monu-dark">{order ? `Pedido #${order.numero}` : 'Detalle del pedido'}</h2><button type="button" onClick={close} className={buttonClass}>Cerrar detalle</button></div>
      <button type="button" disabled={busy} onClick={() => { void reload(); }} className={buttonClass}>{loading ? 'Consultando detalle...' : 'Actualizar detalle'}</button>
      <DataError message={error} />
      {order && <>
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
          <dt className="font-bold">Cliente</dt><dd>{order.cliente}</dd>
          <dt className="font-bold">Estado</dt><dd>{stateLabel(order.estado)}</dd>
          <dt className="font-bold">Entrega</dt><dd>{order.tipo_entrega === 'RETIRO' ? 'Retiro en local' : addressLabel(order.direccion)}{order.direccion?.referencia && ` · ${order.direccion.referencia}`}</dd>
          <dt className="font-bold">Contacto</dt><dd>{order.telefono ? <a href={`tel:${order.telefono.replace(/[^+\d]/g, '')}`} className="underline inline-flex items-center min-h-11">{order.telefono}</a> : 'Teléfono no disponible'}</dd>
          <dt className="font-bold">Pago</dt><dd>{order.metodo_pago_acordado === 'TRANSFERENCIA' ? 'Transferencia' : 'Efectivo'}</dd>
          <dt className="font-bold">Total</dt><dd className="text-xl font-extrabold text-monu-dark">{money(order.total)}</dd>
          {order.observaciones && <><dt className="font-bold">Nota</dt><dd className="whitespace-pre-wrap break-words">{order.observaciones}</dd></>}
        </dl>
        <ul className="space-y-2">{order.items.map((item) => <li key={item.id} className="text-sm font-bold">{item.cantidad} × {item.nombre_producto}{item.aclaraciones ? ` · ${item.aclaraciones}` : ''}</li>)}</ul>
        {isStaff(user?.backendRole) && <div key={`${order.id}:${order.version}:${order.envio?.viaje_id}:${order.envio?.estado}:${order.envio?.estado_viaje}`} className="space-y-6 border-t border-monu-green/20 pt-5">
          <StateOperation order={order} role={user.backendRole} commands={commands} run={run} busy={busy || stale} />
          <OrderDelivery order={order} role={user.backendRole} commands={commands} run={run} busy={busy || stale} />
        </div>}
        {isStaff(user?.backendRole) && <OrderPayments key={user.id} order={order} userId={user.id} commands={commands} run={run} busy={busy || stale} />}
        {isStaff(user?.backendRole) && <EditOperation key={`edit:${order.id}:${order.version}`} order={order} role={user.backendRole} commands={commands} run={run} busy={busy || stale} />}
        <details className="space-y-3 border-t border-monu-green/20 pt-3"><summary className="cursor-pointer min-h-11 flex items-center font-bold text-monu-green">Historial y detalles</summary>
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">{[['creado_en', 'Creado'], ['confirmado_en', 'Confirmado'], ['preparacion_en', 'Preparación'], ['listo_en', 'Listo'], ['entregado_en', 'Entregado'], ['cancelado_en', 'Cancelado']].filter(([key]) => order[key]).map(([key, label]) => <div className="contents" key={key}><dt className="font-bold">{label}</dt><dd>{dateTime(order[key])}</dd></div>)}</dl>
          <ol className="space-y-3">{order.historial.map((event) => <li key={event.id} className="border-l-2 border-monu-green/30 pl-3 text-sm space-y-1"><p className="font-bold">{stateLabel(event.estado_anterior)} → {stateLabel(event.estado_nuevo)}</p><p>{dateTime(event.creado_en)} · {event.actor || 'Sistema'}</p><p className="break-words">{event.observacion || 'Cambio de estado'}</p>{event.tratamiento_stock && <p>Stock: {({ CONSERVAR: 'consumo conservado', RECONSUMIR: 'nuevo consumo', MERMA: 'merma declarada', RESERVA_DEVUELTA: 'reserva devuelta' })[event.tratamiento_stock] || event.tratamiento_stock}</p>}</li>)}</ol>
        </details>
      </>}
    </div>
  </dialog>;
}
