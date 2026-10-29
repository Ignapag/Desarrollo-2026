// Pantalla "Gestión de pedidos": tablero por estado con búsqueda, filtros de vista
// (activos, historial, todos), bandeja de WhatsApp y apertura del detalle de cada pedido.
// Los pedidos activos llegan en vivo desde DataContext; búsquedas e historial se consultan a la API.
import { userErrorMessage } from '../shared/api/userErrors.js';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { can, canVisit } from '../auth/permissions';
import { useData } from '../shared/store/DataContext';
import { apiFetch } from '../shared/api/http';
import { mapOrder, ordersPath } from './orderModel';
import { BOARD_MEDIA, groupOrders, scopeStates, useMediaQuery } from './orderBoard';
import { buttonClass, inputClass, DataError } from './operationUi';
import { OrderList, StatusBar } from './OrderStatusBoard';
import WhatsAppInbox from './WhatsAppInbox';
import OrderDetail from './OrderDetail';
import TodayOrders from './TodayOrders';

/** Tablero de gestión de pedidos del personal. */
export default function Orders() {
  const { user, refreshSession } = useAuth();
  const { state, refreshOrders, watchOrders, orderOperationPending, projectOrder } = useData();
  // Filtros que viven en la URL: búsqueda (q) y cliente (cliente_id).
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const query = params.get('q') || '';
  const clientValue = Number(params.get('cliente_id'));
  const clientId = Number.isSafeInteger(clientValue) && clientValue > 0 ? clientValue : undefined;
  // Vista elegida, resultados remotos, pedido abierto, estado enfocado y reloj para las esperas.
  const [scope, setScope] = useState(clientId ? 'all' : 'active');
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshFeedback, setRefreshFeedback] = useState(null);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState(null);
  const [focus, setFocus] = useState(null);
  const [now, setNow] = useState(() => Date.now());
  // Refs: última ruta cargada, botones que abren cada pedido (para devolver el foco) y estado elegido.
  const loadedPath = useRef('');
  const refreshRequest = useRef(null);
  const openers = useRef(new Map());
  const selectedState = useRef(null);
  const returnFocus = useRef(null);
  const todayOpener = useRef(null);
  const board = useMediaQuery(BOARD_MEDIA);
  // "Remoto" = búsqueda, historial o cliente: se consulta a la API en lugar de usar los pedidos en vivo.
  const remote = Boolean(query.trim()) || scope !== 'active' || clientId != null;
  const queryPath = ordersPath({ q: query, cliente_id: clientId, activos: scope === 'history' ? false : scope === 'active' ? true : undefined });
  const refreshStatus = refreshFeedback?.path === queryPath && refreshFeedback.user === user ? refreshFeedback.status : 'idle';
  useEffect(() => () => {
    refreshRequest.current?.controller?.abort();
    refreshRequest.current = null;
    setRefreshFeedback(null);
  }, [queryPath, user]);
  // Sin filtros remotos, se suscribe al seguimiento en vivo de pedidos activos.
  useEffect(() => { if (!remote) return watchOrders?.(); return undefined; }, [remote, watchOrders]);
  // Con filtros remotos, vuelve a consultar cada 8 s mientras la pestaña está visible.
  useEffect(() => {
    if (!remote) return undefined;
    const timer = setInterval(() => { if (!document.hidden) setRevision((value) => value + 1); }, 8000);
    return () => clearInterval(timer);
  }, [remote]);
  // Actualiza el reloj cada 30 s para recalcular esperas.
  useEffect(() => {
    const timer = setInterval(() => { if (!document.hidden) setNow(Date.now()); }, 30000);
    return () => clearInterval(timer);
  }, []);
  // Consulta remota con espera de 250 ms (debounce) al escribir; ante 401/403 cierra el detalle y revalida la sesión.
  useEffect(() => {
    if (!remote) return undefined;
    const controller = new AbortController();
    const manual = refreshRequest.current;
    const timer = setTimeout(() => {
      if (loadedPath.current !== queryPath) setLoading(true);
      setError('');
      apiFetch(queryPath, { signal: controller.signal })
        .then((orders) => { if (!controller.signal.aborted) {
          loadedPath.current = queryPath; setResults({ path: queryPath, orders: orders.map(mapOrder) });
          if (manual && refreshRequest.current === manual) setRefreshFeedback({ path: queryPath, user, status: 'done' });
        } })
        .catch((failure) => { if (!controller.signal.aborted) {
          if ([401, 403].includes(failure.status)) { setResults(null); setSelected((open) => { if (open != null) returnFocus.current = open; return null; }); loadedPath.current = ''; void refreshSession?.(); }
          setError(userErrorMessage(failure, 'No pudimos cargar el historial de pedidos. Intentá nuevamente.'));
          setRefreshFeedback(null);
        } })
        .finally(() => { if (!controller.signal.aborted) { setLoading(false); if (refreshRequest.current === manual) refreshRequest.current = null; } });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [remote, queryPath, revision, state.orders, refreshSession, user]);
  // Pedidos a mostrar y agrupación por estado con los totales.
  const orders = remote ? results?.path === queryPath ? results.orders.map((order) => projectOrder?.(order) || order) : [] : state.orders;
  const countsKnown = remote ? results?.path === queryPath : state.ordersStatus === 'ready' || orders.length > 0;
  const availableStates = scopeStates(scope);
  const groups = groupOrders(orders, availableStates, now);
  const states = availableStates.filter(([id]) => id !== 'POR_COBRAR' || groups[id].count > 0 || focus === id);
  groups.ALL = Object.values(groups).reduce((total, group) => ({ count: total.count + group.count, longWait: total.longWait + group.longWait }), { count: 0, longWait: 0 });
  // Sin elección válida: tablero completo si entra en una fila; si no, el primer estado con pedidos.
  const validFocus = focus === 'ALL' ? board : states.some(([id]) => id === focus);
  const current = validFocus ? focus : board ? 'ALL' : (states.find(([id]) => groups[id].count > 0) || states[0])[0];
  const options = board ? [['ALL', 'Todos'], ...states] : states;
  const loadingOrders = loading || (!remote && state.ordersStatus === 'loading');
  const stale = state.ordersStatus === 'error' || Boolean(error);
  const emptyMessage = stale ? 'Información sin actualizar.' : loadingOrders ? 'Consultando...' : 'Sin pedidos en este estado.';
  const searchText = query.trim();
  const nothing = countsKnown && !stale && !loadingOrders && groups.ALL.count === 0
    ? searchText ? `Sin resultados para «${searchText}».` : scope === 'active' ? 'No hay pedidos activos en este momento.' : 'No hay pedidos para mostrar.' : '';
  // Actualización manual: remota o de los pedidos en vivo.
  const refresh = async () => {
    if (refreshRequest.current) return;
    const request = { controller: new AbortController() };
    refreshRequest.current = request;
    setRefreshFeedback({ path: queryPath, user, status: 'loading' });
    if (remote) { setRevision((value) => value + 1); return; }
    try {
      const accepted = await refreshOrders(request.controller.signal, true);
      if (refreshRequest.current === request) setRefreshFeedback(accepted === false ? null : { path: queryPath, user, status: 'done' });
    } catch {
      if (refreshRequest.current === request) setRefreshFeedback(null);
    } finally {
      if (refreshRequest.current === request) refreshRequest.current = null;
    }
  };
  const refreshing = refreshStatus === 'loading';
  // Registra el botón de cada tarjeta para devolverle el foco al cerrar el detalle.
  const registerOpener = useCallback((id, node) => {
    if (!node) return undefined;
    openers.current.set(id, node);
    return () => { if (openers.current.get(id) === node) openers.current.delete(id); };
  }, []);
  const closeDetail = () => { returnFocus.current = selected; setSelected(null); };
  // Al cerrar, el foco vuelve a la tarjeta; si ya no está a la vista (cambió de estado), al estado elegido.
  useEffect(() => {
    if (selected != null || returnFocus.current == null) return;
    const opener = openers.current.get(returnFocus.current);
    returnFocus.current = null;
    (todayOpener.current || opener || selectedState.current)?.focus();
    todayOpener.current = null;
  }, [selected]);
  const listProps = { known: countsKnown, emptyMessage, now, pending: orderOperationPending, onOpen: setSelected, registerOpener, onBackToStates: () => selectedState.current?.focus() };
  return <div className="space-y-4">
    {/* Encabezado con acceso al panel de reparto */}
    <div className="flex flex-wrap gap-3 justify-between items-start"><div><h1 className="text-2xl md:text-3xl font-extrabold font-heading text-monu-dark">Gestión de pedidos</h1><p className="text-monu-text/80">Operación, historial y correcciones sobre el mismo pedido.</p></div>{canVisit(user, '/delivery') && <Link to="/delivery" className={buttonClass}>Gestionar reparto</Link>}</div>
    {/* Bandeja de WhatsApp (comprobantes y atenciones) */}
    {can(user, 'whatsapp.ver') && <WhatsAppInbox section={params.get('bandeja')} requestKey={location.key} notificationTarget={params.get('aviso')} />}
    {/* Filtro activo por cliente */}
    {clientId && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-monu-bone p-3 text-sm"><p>Pedidos de <strong>{params.get('cliente') || `cliente #${clientId}`}</strong></p><Link to="/dashboard/orders" className={buttonClass}>Ver todos los clientes</Link></div>}
    {/* Búsqueda, vista y actualización */}
    <div className="flex flex-wrap gap-3 items-end">
      <label className="block basis-full sm:basis-auto flex-1 min-w-48 space-y-1 text-sm font-bold">Buscar por número de pedido, cliente o teléfono<input value={query} onChange={(event) => { const next = new URLSearchParams(params); next.delete('bandeja'); if (event.target.value) next.set('q', event.target.value); else next.delete('q'); setParams(next, { replace: true }); }} className={inputClass} /></label>
      <div className="flex flex-1 sm:flex-none min-w-0 gap-3 items-end">
        <label className="block flex-1 min-w-0 space-y-1 text-sm font-bold">Mostrar<select value={scope} onChange={(event) => { setResults(null); setScope(event.target.value); }} className={inputClass}><option value="active">Activos</option><option value="history">Cerrados / historial</option><option value="all">Todos los estados</option></select></label>
        <button type="button" onClick={refresh} disabled={loading || refreshing} aria-busy={refreshing} className={`${buttonClass} shrink-0`}>{refreshing ? 'Actualizando pedidos...' : 'Actualizar pedidos'}</button>
      </div>
    </div>
    {/* Errores, carga y barra de estados */}
    <DataError message={state.ordersError || error} retry={refresh} busy={loading || refreshing} />
    <p role="status" className="min-h-6 text-sm text-monu-text/80">{refreshing || loadingOrders ? 'Consultando pedidos...' : refreshStatus === 'done' && !stale ? 'Pedidos actualizados.' : ''}</p>
    <StatusBar options={options} groups={groups} known={countsKnown} current={current} onSelect={setFocus} controls="orders-board" selectedRef={selectedState} />
    {/* Tablero: todas las columnas o un único estado enfocado */}
    <div id="orders-board">
      {nothing ? <p className="rounded-2xl border border-monu-green/20 bg-monu-bone p-6 text-center text-monu-text/80">{nothing}</p> : current === 'ALL'
        ? <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] items-start">
          {states.map(([id, label]) => <OrderList key={id} id={id} label={label} group={groups[id]} layout="column" {...listProps} />)}
        </div>
        : <OrderList id={current} label={states.find(([id]) => id === current)[1]} group={groups[current]} layout="panel" {...listProps} />}
    </div>
    <TodayOrders clientId={clientId} pending={orderOperationPending} onOpen={(id, button) => { todayOpener.current = button; setSelected(id); }} />
    {/* Detalle del pedido abierto */}
    {selected && <OrderDetail key={selected} id={selected} onClose={closeDetail} />}
  </div>;
}
