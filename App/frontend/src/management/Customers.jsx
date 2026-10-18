import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Phone, RefreshCw, Search } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { buttonClass, inputClass, DataError } from '../fulfillment/operationUi';

const pageSize = 50;
const customerDate = (value) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleDateString('es-AR', { timeZone: 'America/Argentina/Buenos_Aires' }) : '—';

export default function Customers() {
  const { user } = useAuth();
  const { getCustomers, cachedCustomers } = useData();
  const [params, setParams] = useSearchParams();
  const query = params.get('q') || '';
  const requestedOffset = Number(params.get('desplazamiento') || 0);
  const offset = Number.isSafeInteger(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0;
  const path = `/api/reportes/clientes?${new URLSearchParams({ q: query.trim(), limite: String(pageSize), desplazamiento: String(offset) })}`;
  const [snapshot, setSnapshot] = useState(() => ({ owner: user, path, data: cachedCustomers(path) }));
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [revision, setRevision] = useState(0);
  const data = snapshot.owner === user && snapshot.path === path ? snapshot.data : cachedCustomers(path);
  const errorMessage = error?.path === path ? error.message : '';

  useEffect(() => {
    const controller = new AbortController();
    let reading = false;
    async function load(force = false) {
      if (controller.signal.aborted || reading || document.hidden) return;
      reading = true;
      setRefreshing(true);
      try {
        const result = await getCustomers(path, controller.signal, force);
        if (!controller.signal.aborted) { setSnapshot({ owner: user, path, data: result }); setError(null); }
      } catch (failure) {
        if (!controller.signal.aborted) setError({ path, message: `No se pudieron cargar los clientes. ${failure.message}` });
      } finally {
        reading = false;
        if (!controller.signal.aborted) setRefreshing(false);
      }
    }
    const debounce = query.trim() ? setTimeout(() => { void load(revision > 0); }, 250) : null;
    if (!debounce) void load(revision > 0);
    const refresh = () => { if (!document.hidden) void load(true); };
    const timer = setInterval(refresh, 15000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => { controller.abort(); clearTimeout(debounce); clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [path, query, user, getCustomers, cachedCustomers, revision]);

  const setOffset = (value) => { const next = new URLSearchParams(params); if (value) next.set('desplazamiento', String(value)); else next.delete('desplazamiento'); setParams(next); };
  return <div className="space-y-6">
    <div className="flex flex-wrap gap-3 justify-between items-end">
      <div><h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Directorio de Clientes</h1><p className="text-monu-text/70">Clientes y pedidos registrados en el sistema.</p></div>
      <button type="button" disabled={refreshing} onClick={() => setRevision((value) => value + 1)} className={`${buttonClass} inline-flex items-center gap-2`}><RefreshCw aria-hidden="true" className={`w-4 h-4 ${refreshing ? 'motion-safe:animate-spin' : ''}`} />{refreshing ? 'Actualizando...' : 'Actualizar clientes'}</button>
    </div>
    <label className="block max-w-lg text-sm font-bold text-monu-dark space-y-2"><span>Buscar cliente por nombre o teléfono</span><div className="relative"><Search aria-hidden="true" className="absolute left-3 top-3 h-5 w-5 text-monu-text/50" /><input className={`${inputClass} pl-10`} type="search" value={query} onChange={(event) => { const next = new URLSearchParams(params); if (event.target.value) next.set('q', event.target.value); else next.delete('q'); next.delete('desplazamiento'); setParams(next, { replace: true }); }} /></div></label>
    <DataError message={errorMessage} retry={() => setRevision((value) => value + 1)} busy={refreshing} />
    {!data && !errorMessage && <p role="status">Consultando clientes...</p>}
    <div className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-hidden">
      <div className="overflow-x-auto"><table className="w-full text-left min-w-[700px]">
        <thead className="bg-monu-cream border-b border-monu-green/10 text-sm"><tr>{['Cliente', 'Contacto', 'Entrega habitual', 'Pedidos', 'Primer pedido'].map((title) => <th key={title} scope="col" className="p-4 font-bold text-monu-dark">{title}</th>)}<th scope="col"><span className="sr-only">Ver pedidos del cliente</span></th></tr></thead>
        <tbody>{data?.clientes.map((customer) => <tr key={customer.id} className="border-b border-monu-green/5 hover:bg-monu-cream/30 focus-within:bg-monu-cream/30 transition-colors">
          <td className="p-4"><div className="flex items-center gap-3"><div aria-hidden="true" className="w-10 h-10 rounded-full bg-monu-green/10 text-monu-green flex items-center justify-center font-bold shrink-0">{customer.nombre.charAt(0).toUpperCase()}</div><span className="font-bold text-monu-dark">{customer.nombre}</span></div></td>
          <td className="p-4 text-sm">{customer.telefono ? <a href={`tel:${customer.telefono.replace(/[^+\d]/g, '')}`} className="inline-flex items-center gap-2 min-h-11 rounded-lg hover:text-monu-green hover:underline"><Phone aria-hidden="true" className="w-4 h-4" />{customer.telefono}</a> : 'Sin teléfono'}</td>
          <td className="p-4 text-sm">{customer.zona_frecuente || 'Sin entregas registradas'}</td>
          <td className="p-4"><span className="bg-monu-yellow/20 text-monu-dark font-bold px-3 py-1 rounded-full text-xs whitespace-nowrap">{customer.pedidos_count} {customer.pedidos_count === 1 ? 'pedido' : 'pedidos'}</span></td>
          <td className="p-4 text-sm">{customerDate(customer.primer_pedido_en)}</td>
          <td className="p-4"><Link to={`/dashboard/orders?${new URLSearchParams({ cliente_id: String(customer.id), cliente: customer.nombre })}`} className={`${buttonClass} inline-flex items-center whitespace-nowrap hover:bg-monu-green hover:text-white`}>Ver pedidos<span className="sr-only"> de {customer.nombre}</span></Link></td>
        </tr>)}{data?.clientes.length === 0 && <tr><td colSpan="6" className="p-8 text-center text-sm">{query.trim() ? 'No hay clientes que coincidan con tu búsqueda.' : 'No hay clientes registrados.'}</td></tr>}</tbody>
      </table></div>
    </div>
    {data && <div className="flex flex-wrap items-center justify-between gap-3 text-sm"><p>{data.total === 0 ? '0 clientes' : `${offset + 1}–${offset + data.clientes.length} de ${data.total} clientes`}</p><div className="flex gap-2"><button type="button" disabled={refreshing || offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))} className={buttonClass}>Anterior</button><button type="button" disabled={refreshing || offset + pageSize >= data.total} onClick={() => setOffset(offset + pageSize)} className={buttonClass}>Siguiente</button></div></div>}
  </div>;
}
