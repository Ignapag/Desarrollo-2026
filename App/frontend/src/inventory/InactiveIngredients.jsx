// Recuperación de insumos: el listado histórico queda fuera del inventario activo compartido.
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';
import { UserFacingError, userErrorMessage } from '../shared/api/userErrors';
import { useData } from '../shared/store/DataContext';

export default function InactiveIngredients({ revision }) {
  const { reactivateIngredient } = useData();
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
        const ingredients = await apiFetch('/api/stock/ingredientes?activo=false', { signal: controller.signal });
        if (!Array.isArray(ingredients) || ingredients.some((ingredient) => !Number.isInteger(ingredient?.id) || typeof ingredient.nombre !== 'string' || typeof ingredient.activo !== 'boolean')) throw new UserFacingError('No pudimos confirmar la lista de ingredientes inactivos.');
        if (!controller.signal.aborted) setRecords(ingredients.filter((ingredient) => !ingredient.activo));
      } catch (error) {
        if (!controller.signal.aborted) setFeedback({ error: true, text: userErrorMessage(error, 'No pudimos consultar los ingredientes inactivos. Intentá nuevamente.') });
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    });
    return () => controller.abort();
  }, [expanded, revision, retry]);

  const reactivate = async (ingredient) => {
    if (busy.current) return;
    busy.current = true;
    request.current?.abort();
    setLoading(false); setPending(ingredient.id); setFeedback(null);
    try {
      await reactivateIngredient(ingredient.id);
      if (!mounted.current) return;
      setRecords((previous) => previous?.filter((record) => record.id !== ingredient.id) ?? []);
      setFeedback({ error: false, text: `${ingredient.nombre} se reactivó conservando su stock.` });
    } catch (error) {
      if (mounted.current) setFeedback({ error: true, text: userErrorMessage(error, 'No pudimos reactivar el ingrediente. Actualizá la lista antes de reintentar.') });
    } finally {
      busy.current = false;
      if (mounted.current) setPending(null);
    }
  };

  return <section className="rounded-2xl border border-monu-green/15 bg-white p-4 space-y-3" aria-labelledby="ingredientes-inactivos-titulo">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="ingredientes-inactivos-titulo"><button ref={toggle} type="button" aria-expanded={expanded} aria-controls="ingredientes-inactivos-lista" disabled={pending !== null} onClick={() => setExpanded((value) => !value)} className="min-h-11 rounded-lg px-2 text-lg font-bold text-monu-dark underline focus-visible:ring-2 focus-visible:ring-monu-green disabled:opacity-50">Ingredientes inactivos</button></h2>
      {expanded && <button type="button" disabled={loading || pending !== null} onClick={() => { setFeedback(null); setRetry((value) => value + 1); }} className="min-h-11 rounded-lg border border-monu-green/30 px-3 font-bold text-monu-green focus-visible:ring-2 focus-visible:ring-monu-green disabled:opacity-50">Actualizar lista</button>}
    </div>
    <p className="text-sm text-monu-text">Los ingredientes desactivados conservan sus existencias e historial.</p>
    {feedback && <p role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'text-red-700' : 'text-monu-green'}>{feedback.text}</p>}
    <div id="ingredientes-inactivos-lista" hidden={!expanded} aria-busy={loading || pending !== null}>
      {loading && <p role="status" className="py-2">Consultando ingredientes inactivos…</p>}
      {!loading && records !== null && <>
        {!records.length && <p className="py-2 text-sm">No hay ingredientes inactivos.</p>}
        <ul className="divide-y divide-monu-green/10">{records.map((ingredient) => <li key={ingredient.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0"><p className="font-bold break-words text-monu-dark">{ingredient.nombre}</p><p className="text-sm text-monu-text">Inactivo · Stock conservado: {ingredient.cantidad_actual} {ingredient.unidad_medida}</p></div>
          <button type="button" disabled={pending !== null} aria-busy={pending === ingredient.id} aria-label={`Reactivar ${ingredient.nombre}`} onClick={() => reactivate(ingredient)} className="min-h-11 shrink-0 rounded-lg bg-monu-green px-4 py-2 font-bold text-white hover:bg-monu-dark focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2 disabled:opacity-50">{pending === ingredient.id ? 'Reactivando…' : 'Reactivar'}</button>
        </li>)}</ul>
      </>}
    </div>
  </section>;
}
