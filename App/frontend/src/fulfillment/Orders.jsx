import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useData } from '../shared/store/DataContext';
import { apiFetch } from '../shared/api/http';
import { ORDER_STATES, mapOrder, ordersPath, dateTime, money } from './orderModel';
import { buttonClass, inputClass, DataError } from './operationUi';
import WhatsAppInbox from './WhatsAppInbox';
import OrderDetail from './OrderDetail';

export default function Orders() {
  const { state, refreshOrders, watchOrders, orderOperationPending } = useData();
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const query = params.get('q') || '';
  const clientValue = Number(params.get('cliente_id'));
  const clientId = Number.isSafeInteger(clientValue) && clientValue > 0 ? clientValue : undefined;
  const [scope, setScope] = useState(clientId ? 'all' : 'active');
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState(null);
  const loadedPath = useRef('');
  const remote = Boolean(query.trim()) || scope !== 'active' || clientId != null;
  const queryPath = ordersPath({ q: query, cliente_id: clientId, activos: scope === 'history' ? false : scope === 'active' ? true : undefined });
  useEffect(() => { if (!remote) return watchOrders?.(); return undefined; }, [remote, watchOrders]);
  useEffect(() => {
    if (!remote) return undefined;
    const timer = setInterval(() => { if (!document.hidden) setRevision((value) => value + 1); }, 8000);
    return () => clearInterval(timer);
  }, [remote]);
  useEffect(() => {
    if (!remote) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      if (loadedPath.current !== queryPath) setLoading(true);
      setError('');
      apiFetch(queryPath, { signal: controller.signal })
        .then((orders) => { if (!controller.signal.aborted) { loadedPath.current = queryPath; setResults({ path: queryPath, orders: orders.map(mapOrder) }); } })
        .catch((failure) => { if (!controller.signal.aborted) setError(`No se pudo consultar el historial. ${failure.message}`); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [remote, queryPath, revision, state.orders]);
  const orders = remote ? results?.path === queryPath ? results.orders : [] : state.orders;
  const countsKnown = remote ? results?.path === queryPath : state.ordersStatus === 'ready' || orders.length > 0;
  const columns = ORDER_STATES.filter(([id]) => scope === 'history' ? ['ENTREGADO', 'CANCELADO'].includes(id) : scope === 'active' ? !['ENTREGADO', 'CANCELADO'].includes(id) : true);
  const refresh = () => { if (remote) setRevision((value) => value + 1); else void refreshOrders(undefined, true).catch(() => undefined); };
  return <div className="space-y-5">
    <div className="flex flex-wrap gap-3 justify-between items-start"><div><h1 className="text-3xl font-extrabold font-heading text-monu-dark">Gestión de pedidos</h1><p className="text-monu-text/80">Operación, historial y correcciones sobre el mismo pedido.</p></div><Link to="/delivery" className={buttonClass}>Gestionar reparto</Link></div>
    <WhatsAppInbox section={params.get('bandeja')} requestKey={location.key} />
    {clientId && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-monu-bone p-3 text-sm"><p>Pedidos de <strong>{params.get('cliente') || `cliente #${clientId}`}</strong></p><Link to="/dashboard/orders" className={buttonClass}>Ver todos los clientes</Link></div>}
    <div className="flex flex-wrap gap-3 items-end">
      <label className="block flex-1 min-w-48 space-y-1 text-sm font-bold">Buscar por número de pedido, cliente o teléfono<input value={query} onChange={(event) => { const next = new URLSearchParams(params); next.delete('bandeja'); if (event.target.value) next.set('q', event.target.value); else next.delete('q'); setParams(next, { replace: true }); }} className={inputClass} /></label>
      <label className="block space-y-1 text-sm font-bold">Mostrar<select value={scope} onChange={(event) => { setResults(null); setScope(event.target.value); }} className={inputClass}><option value="active">Activos</option><option value="history">Cerrados / historial</option><option value="all">Todos los estados</option></select></label>
      <button type="button" onClick={refresh} disabled={loading} className={buttonClass}>Actualizar pedidos</button>
    </div>
    <DataError message={state.ordersError || error} retry={refresh} busy={loading} />
    {(loading || (!remote && state.ordersStatus === 'loading')) && <p role="status">Consultando pedidos...</p>}
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 items-start">
      {columns.map(([id, label]) => <section key={id} aria-label={label} className="rounded-2xl bg-monu-bone border border-monu-green/20 p-4 space-y-4 min-w-0">
        <h2 className="font-extrabold text-monu-dark flex justify-between gap-3"><span>{label}</span><span aria-label={countsKnown ? `${orders.filter((order) => order.estado === id).length} pedidos` : 'Cantidad sin consultar'}>{countsKnown ? orders.filter((order) => order.estado === id).length : '—'}</span></h2>
        {orders.filter((order) => order.estado === id).map((order) => <article key={order.id} className="bg-white rounded-xl border border-monu-green/20 p-4 space-y-3">
          <div><h3 className="font-extrabold text-monu-dark">Pedido #{order.number}</h3><p className="text-sm">{dateTime(order.date)}</p></div>
          <p className="font-bold break-words">{order.client}</p><p className="text-sm break-words">{order.address}</p>
          <ul className="text-sm space-y-1">{order.items.map((item, index) => <li key={index} className="break-words">{item}</li>)}</ul>
          <p className="text-sm">Total: {money(order.total)} · Saldo: {money(order.saldo_pendiente)}</p>
          {orderOperationPending(order.id) && <p role="status" className="text-sm font-bold text-monu-green">Acción en segundo plano</p>}
          <button type="button" disabled={orderOperationPending(order.id)} onClick={() => setSelected(order.id)} className={`${buttonClass} w-full bg-monu-dark text-white`}>Ver detalle y operar #{order.number}</button>
        </article>)}
        {!orders.some((order) => order.estado === id) && <p className="text-sm text-monu-text/80">{state.ordersStatus === 'error' || error ? 'Información sin actualizar.' : loading || state.ordersStatus === 'loading' ? 'Consultando...' : 'Sin pedidos en este estado.'}</p>}
      </section>)}
    </div>
    {selected && <OrderDetail key={selected} id={selected} onClose={() => setSelected(null)} />}
  </div>;
}
