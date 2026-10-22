import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { apiFetch } from '../shared/api/http';
import { useData } from '../shared/store/DataContext';
import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { buttonClass, DataError } from '../fulfillment/operationUi';
import RecipeEditor from './RecipeEditor';
import { recipeFromApi, serializeRecipe } from './recipeModel';

export default function RecipeModal({ product, onClose }) {
  const { state, updateRecipe } = useData();
  const { user } = useAuth();
  const canEdit = can(user, 'productos.gestionar');
  const dialog = useRef(null);
  const busy = useRef(false);
  const mounted = useRef(true);
  const [data, setData] = useState(null);
  const [recipe, setRecipe] = useState(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    mounted.current = true;
    dialog.current?.showModal();
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch(`/api/productos/${product.id}/receta`, { signal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return;
      setData(result);
      setRecipe(recipeFromApi(result));
      setError('');
    }).catch((failure) => { if (!controller.signal.aborted) setError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [product.id, reload]);
  const save = async () => {
    if (busy.current || loading || !data || !canEdit) return;
    let payload;
    try { payload = { ...serializeRecipe(recipe), actualizado_en_esperado: data.actualizado_en }; }
    catch (failure) { setError(failure.message); return; }
    busy.current = true;
    setSaving(true);
    setError('');
    try {
      await updateRecipe(product.id, payload);
      if (mounted.current) onClose();
    } catch (failure) {
      if (mounted.current) setError(failure.message);
    } finally {
      busy.current = false;
      if (mounted.current) setSaving(false);
    }
  };
  // Mantener las unidades de ingredientes históricos aunque ya no estén en la lista activa.
  const inventory = [...state.inventory];
  for (const item of data?.ingredientes || []) {
    if (!inventory.some((candidate) => candidate.id === item.ingrediente_id)) inventory.push({ id: item.ingrediente_id, name: item.nombre, category: item.unidad_medida });
  }
  return <dialog ref={dialog} onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }} aria-labelledby="recipe-title" className="m-auto max-h-[90dvh] w-[min(56rem,calc(100%_-_2rem))] overflow-y-auto rounded-3xl border border-monu-green/15 bg-monu-bone p-0 text-monu-dark shadow-xl backdrop:bg-black/50">
    <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-monu-green/15 bg-monu-bone px-5 py-4">
      <h2 id="recipe-title" className="text-xl font-extrabold">Receta de {product.name}</h2>
      <button type="button" onClick={onClose} disabled={saving} aria-label="Cerrar receta" className={buttonClass}><X className="h-5 w-5" aria-hidden="true" /></button>
    </div>
    <div className="space-y-4 p-5">
      {error && <><DataError message={error} /><button type="button" disabled={saving || loading} onClick={() => { setLoading(true); setReload((old) => old + 1); }} className={buttonClass}>Volver a cargar receta</button><p className="text-xs">Volver a cargar reemplaza tus cambios por la receta guardada.</p></>}
      {loading && <p role="status">Consultando receta…</p>}
      {recipe && <RecipeEditor value={recipe} onChange={setRecipe} inventory={inventory} lockVariants disabled={saving || loading || !canEdit} />}
      {recipe && <p className="text-sm text-monu-text">Los pedidos ya registrados conservan sus cantidades originales.</p>}
    </div>
    <div className="sticky bottom-0 flex justify-end gap-2 border-t border-monu-green/15 bg-monu-bone px-5 py-4">
      <button type="button" onClick={onClose} disabled={saving} className={buttonClass}>Cancelar</button>
      {canEdit && <button type="button" onClick={save} disabled={saving || loading || !recipe} aria-busy={saving} className={`${buttonClass} bg-monu-green text-white disabled:opacity-60`}>Guardar receta</button>}
    </div>
  </dialog>;
}
