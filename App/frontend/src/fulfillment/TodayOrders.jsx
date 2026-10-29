import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { apiFetch } from '../shared/api/http';
import { userErrorMessage } from '../shared/api/userErrors';
import { isOrderPaid, mapOrder, money, ordersPath } from './orderModel';
import { buttonClass, DataError } from './operationUi';

const closedTime = new Intl.DateTimeFormat('es-AR', {
  timeZone: 'America/Argentina/Buenos_Aires', hour: '2-digit', minute: '2-digit',
});

/** Historial diario a demanda: no descarga pedidos mientras permanece plegado. */
export default function TodayOrders({ clientId, onOpen, pending }) {
  const [expanded, setExpanded] = useState(false);
  return <section className="rounded-2xl border border-monu-green/20 bg-monu-bone">
    <h2><button type="button" aria-expanded={expanded} aria-controls="today-orders" onClick={() => setExpanded((value) => !value)}
      className="flex min-h-11 w-full items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left font-bold text-monu-dark hover:bg-monu-green/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green">
      Pedidos de hoy<ChevronDown aria-hidden="true" className={`h-5 w-5 shrink-0 ${expanded ? 'rotate-180' : ''}`} />
    </button></h2>
    <div id="today-orders" hidden={!expanded}>
      {expanded && <TodayList clientId={clientId} onOpen={onOpen} pending={pending} />}
    </div>
  </section>;
}

function TodayList({ clientId, onOpen, pending }) {
  const { user, refreshSession } = useAuth();
  const [snapshot, setSnapshot] = useState(null);
  const [busy, setBusy] = useState(true);
  const [revision, setRevision] = useState(0);
  const path = ordersPath({ cliente_id: clientId, finalizados_hoy: true });
  const current = snapshot?.owner === user && snapshot.path === path ? snapshot : null;
  const orders = current?.orders;
  const error = current?.error;
  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      setBusy(true);
      try {
        const rows = await apiFetch(path, { signal: controller.signal });
        if (!controller.signal.aborted) setSnapshot({ owner: user, path, orders: rows.map(mapOrder) });
      } catch (failure) {
        if (!controller.signal.aborted) {
          const forbidden = [401, 403].includes(failure.status);
          if (forbidden) void refreshSession?.();
          setSnapshot((previous) => ({ owner: user, path,
            orders: !forbidden && previous?.owner === user && previous.path === path ? previous.orders : undefined,
            error: userErrorMessage(failure, 'No pudimos consultar los pedidos de hoy. Intentá nuevamente.'),
          }));
        }
      } finally {
        inFlight = false;
        if (!controller.signal.aborted) setBusy(false);
      }
    };
    void load();
    const update = () => { if (!document.hidden) void load(); };
    const timer = setInterval(update, 8000);
    document.addEventListener('visibilitychange', update);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, [path, user, revision, refreshSession]);
  const refresh = () => setRevision((value) => value + 1);
  return <div className="space-y-3 border-t border-monu-green/15 p-3 sm:p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-monu-text/80">Entregados y cancelados hoy · Hora Argentina{orders && ` · ${orders.length} ${orders.length === 1 ? 'pedido' : 'pedidos'}`}</p>
      <button type="button" disabled={busy} aria-busy={busy} onClick={refresh} className={buttonClass}>{busy ? 'Consultando...' : 'Actualizar pedidos de hoy'}</button>
    </div>
    <DataError message={error} retry={refresh} busy={busy} />
    {busy && !orders && <p role="status" className="text-sm">Consultando los pedidos finalizados de hoy...</p>}
    {orders?.length === 0 && !error && <p className="text-sm text-monu-text/80">Todavía no hay pedidos finalizados hoy.</p>}
    {orders?.length > 0 && <ul className="space-y-2">
      {orders.map((order) => {
        const closedAt = order.estado === 'CANCELADO' ? order.cancelado_en : order.entregado_en;
        return <li key={order.id}>
          <button type="button" aria-label={`Ver pedido #${order.number}`} disabled={pending?.(order.id)} onClick={(event) => onOpen(order.id, event.currentTarget)}
            className={`${buttonClass} w-full bg-white text-left flex flex-wrap items-center justify-between gap-x-4 gap-y-1`}>
            <span className="min-w-0 break-words">#{order.number} · {order.client}</span>
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-normal">
              <span>{order.estado === 'CANCELADO' ? 'Cancelado' : 'Entregado'}{closedAt && ` · ${closedTime.format(new Date(closedAt))}`}</span>
              <strong>{money(order.total)}</strong>
              {order.estado !== 'CANCELADO' && <span className={isOrderPaid(order) ? 'text-monu-green' : 'text-monu-burnt'}>{isOrderPaid(order) ? 'Pagado' : 'Por cobrar'}</span>}
            </span>
          </button>
        </li>;
      })}
    </ul>}
  </div>;
}
