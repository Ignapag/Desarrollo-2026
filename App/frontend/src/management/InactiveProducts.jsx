// Las bajas se consultan localmente: nunca se agregan al catálogo público del store.
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';
import { UserFacingError, userErrorMessage } from '../shared/api/userErrors';
import { useData } from '../shared/store/DataContext';

export default function InactiveProducts({ revision, query = '' }) {
  const { reactivateProduct } = useData();
  const [expanded, setExpanded] = useState(false);
  const [records, setRecords] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(null);
  const [retry, setRetry] = useState(0);
  const [feedback, setFeedback] = useState(null);
  const busy = useRef(false);
  const request = useRef(null);
  const mounted = useRef(true);
  const toggle = useRef(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; request.current?.abort(); }; }, []);
  useEffect(() => { if (pending === null && feedback && !feedback.error) toggle.current?.focus(); }, [pending, feedback]);

  useEffect(() => {
    if (!expanded || busy.current) return undefined;
    const controller = new AbortController();
    request.current = controller;
    Promise.resolve().then(async () => {
      if (controller.signal.aborted || busy.current) return;
      setLoading(true);
      try {
        const products = await apiFetch('/api/productos?solo_activos=false', { signal: controller.signal });
        if (!Array.isArray(products) || products.some((product) => !Number.isInteger(product?.id) || typeof product.nombre !== 'string' || typeof product.activo !== 'boolean')) throw new UserFacingError('No pudimos confirmar la lista de productos inactivos.');
        if (!controller.signal.aborted) setRecords(products.filter((product) => !product.activo));
      } catch (error) {
        if (!controller.signal.aborted) setFeedback({ error: true, text: userErrorMessage(error, 'No pudimos consultar los productos inactivos. Intentá nuevamente.') });
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    });
    return () => controller.abort();
  }, [expanded, revision, retry]);

  const reactivate = async (product) => {
    if (busy.current) return;
    busy.current = true;
    request.current?.abort();
    setLoading(false); setPending(product.id); setFeedback(null);
    try {
      await reactivateProduct(product.id);
      if (!mounted.current) return;
      setRecords((previous) => previous?.filter((record) => record.id !== product.id) ?? []);
      setFeedback({ error: false, text: `${product.nombre} se reactivó. Su disponibilidad depende de la categoría, receta y stock.` });
    } catch (error) {
      if (mounted.current) setFeedback({ error: true, text: userErrorMessage(error, 'No pudimos reactivar el producto. Actualizá la lista antes de reintentar.') });
    } finally {
      busy.current = false;
      if (mounted.current) setPending(null);
    }
  };
  const visible = (records ?? []).filter((product) => `${product.nombre} ${product.categoria ?? ''}`.toLocaleLowerCase('es').includes(query));

  return <section className="rounded-2xl border border-monu-green/15 bg-white p-4 space-y-3" aria-labelledby="productos-inactivos-titulo">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="productos-inactivos-titulo"><button ref={toggle} type="button" aria-expanded={expanded} aria-controls="productos-inactivos-lista" disabled={pending !== null} onClick={() => setExpanded((value) => !value)} className="min-h-11 rounded-lg px-2 text-lg font-bold text-monu-dark underline focus-visible:ring-2 focus-visible:ring-monu-green disabled:opacity-50">Productos inactivos</button></h2>
      {expanded && <button type="button" disabled={loading || pending !== null} onClick={() => { setFeedback(null); setRetry((value) => value + 1); }} className="min-h-11 rounded-lg border border-monu-green/30 px-3 font-bold text-monu-green focus-visible:ring-2 focus-visible:ring-monu-green disabled:opacity-50">Actualizar lista</button>}
    </div>
    <p className="text-sm text-monu-text">Los productos desactivados conservan sus datos y se pueden volver a habilitar.</p>
    {feedback && <p role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'text-red-700' : 'text-monu-green'}>{feedback.text}</p>}
    <div id="productos-inactivos-lista" hidden={!expanded} aria-busy={loading || pending !== null}>
      {loading && <p role="status" className="py-2">Consultando productos inactivos…</p>}
      {!loading && records !== null && <>
        {!visible.length && <p className="py-2 text-sm">{records.length ? 'No hay productos inactivos que coincidan con la búsqueda.' : 'No hay productos inactivos.'}</p>}
        <ul className="divide-y divide-monu-green/10">{visible.map((product) => <li key={product.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0"><p className="font-bold break-words text-monu-dark">{product.nombre}</p><p className="text-sm text-monu-text">{product.categoria} · Inactivo</p></div>
          <button type="button" disabled={pending !== null} aria-busy={pending === product.id} aria-label={`Reactivar ${product.nombre}`} onClick={() => reactivate(product)} className="min-h-11 shrink-0 rounded-lg bg-monu-green px-4 py-2 font-bold text-white hover:bg-monu-dark focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2 disabled:opacity-50">{pending === product.id ? 'Reactivando…' : 'Reactivar'}</button>
        </li>)}</ul>
      </>}
    </div>
  </section>;
}
