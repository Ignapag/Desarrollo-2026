import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { apiFetch } from '../shared/api/http';
import { userErrorMessage } from '../shared/api/userErrors';
import { useData } from '../shared/store/DataContext';
import { buttonClass, inputClass } from '../fulfillment/operationUi';
import RecipeEditor from './RecipeEditor';
import { productEditFromApi, serializeProductEdit, validateProductImageFile } from './productEditorModel';

export default function ProductEditorModal({ product, onClose }) {
  const { user } = useAuth();
  const { state, updateProduct } = useData();
  const canRead = can(user, 'productos.ver_receta');
  const canEdit = can(user, 'productos.gestionar');
  const dialog = useRef(null), errorSummary = useRef(null), reader = useRef(null);
  const mounted = useRef(true), busy = useRef(false);
  const [data, setData] = useState(null), [fields, setFields] = useState(null), [recipe, setRecipe] = useState(null);
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [imageLoading, setImageLoading] = useState(false);
  const [error, setError] = useState(''), [reload, setReload] = useState(0), [showErrors, setShowErrors] = useState(false);
  const disabled = loading || saving || !canEdit || !canRead;
  const change = (key, value) => setFields((previous) => ({ ...previous, [key]: value }));
  useEffect(() => { if (error) errorSummary.current?.focus(); }, [error]);
  useEffect(() => {
    mounted.current = true; dialog.current?.showModal();
    return () => { mounted.current = false; reader.current?.abort(); reader.current = null; };
  }, []);
  useEffect(() => {
    if (!canRead) return undefined;
    const controller = new AbortController();
    apiFetch(`/api/productos/${product.id}`, { signal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return;
      const editor = productEditFromApi(result);
      setData(result); setFields(editor.fields); setRecipe(editor.recipe); setError(''); setShowErrors(false);
    }).catch((failure) => { if (!controller.signal.aborted) setError(userErrorMessage(failure, 'No pudimos cargar el producto. Intentá nuevamente.')); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [product.id, canRead, reload]);

  const uploadImage = (event) => {
    const file = event.target.files?.[0]; event.target.value = '';
    reader.current?.abort(); reader.current = null; setImageLoading(false);
    if (!file) return;
    const invalid = validateProductImageFile(file);
    if (invalid) { setError(invalid); return; }
    const current = new FileReader(); reader.current = current; setImageLoading(true); setError('');
    current.onload = () => {
      if (!mounted.current || reader.current !== current) return;
      change('image', current.result); setImageLoading(false); reader.current = null;
    };
    current.onerror = () => {
      if (!mounted.current || reader.current !== current) return;
      setError('No pudimos leer la imagen. Elegila nuevamente.'); setImageLoading(false); reader.current = null;
    };
    try { current.readAsDataURL(file); }
    catch { reader.current = null; setImageLoading(false); setError('No pudimos leer la imagen. Elegila nuevamente.'); }
  };
  const save = async () => {
    if (busy.current || disabled || imageLoading || !data) return;
    setShowErrors(true);
    let payload;
    try { payload = serializeProductEdit(fields, recipe, data); }
    catch (failure) { setError(userErrorMessage(failure, 'Revisá los datos del producto.')); return; }
    busy.current = true; setSaving(true); setError('');
    try {
      await updateProduct(product.id, payload);
      if (mounted.current) onClose();
    } catch (failure) {
      if (mounted.current) setError(userErrorMessage(failure, 'No pudimos guardar el producto. Consultá su estado antes de repetir el cambio.'));
    } finally { busy.current = false; if (mounted.current) setSaving(false); }
  };
  const inventory = [...state.inventory];
  for (const item of data?.ingredientes || []) {
    if (!inventory.some((candidate) => candidate.id === item.ingrediente_id)) inventory.push({ id: item.ingrediente_id, name: item.nombre, category: item.unidad_medida, active: false });
  }
  const selectedCategory = data?.categorias.find((category) => String(category.id) === fields?.categoryId);
  const nameError = showErrors && (!fields?.name.trim() || fields.name.length > 120);
  const priceError = showErrors && (!/^\d{1,10}(?:[.,]\d{1,2})?$/.test(fields?.price || '') || Number(fields?.price.replace(',', '.')) <= 0);
  return <dialog ref={dialog} aria-labelledby="product-editor-title" onCancel={(event) => { event.preventDefault(); if (!busy.current) onClose(); }} className="m-auto max-h-[90dvh] w-[min(58rem,calc(100%_-_2rem))] overflow-y-auto rounded-3xl border border-monu-green/15 bg-monu-bone p-0 text-monu-dark shadow-xl backdrop:bg-black/50">
    <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-monu-green/15 bg-monu-bone px-5 py-4">
      <h2 id="product-editor-title" className="min-w-0 break-words text-xl font-extrabold">Editar producto: {data?.nombre || product.name}</h2>
      <button type="button" aria-label="Cerrar edición de producto" disabled={saving} onClick={onClose} className={buttonClass}><X aria-hidden="true" className="size-5" /></button>
    </div>
    <div className="space-y-6 p-5">
      {error && <div className="space-y-2"><div ref={errorSummary} tabIndex={-1} role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div><button type="button" disabled={saving || loading} onClick={() => { reader.current?.abort(); reader.current = null; setImageLoading(false); setLoading(true); setReload((previous) => previous + 1); }} className={buttonClass}>Volver a cargar producto</button><p className="text-sm">Volver a cargar reemplaza tus cambios por los datos guardados.</p></div>}
      {!canRead ? <p role="alert">No tenés permiso para consultar este producto.</p> : loading && <p role="status">Consultando producto…</p>}
      {canRead && fields && <>
        <fieldset disabled={disabled} className="grid min-w-0 gap-4 sm:grid-cols-2">
          <legend className="mb-3 text-lg font-extrabold">Datos del producto</legend>
          <div className="space-y-1 sm:col-span-2"><label htmlFor="edit-product-name" className="block text-sm font-bold">Nombre</label><input id="edit-product-name" value={fields.name} maxLength={120} onChange={(event) => change('name', event.target.value)} aria-invalid={nameError || undefined} aria-describedby={nameError ? 'edit-product-name-error' : undefined} className={`${inputClass} w-full bg-white`} />{nameError && <p id="edit-product-name-error" className="text-sm text-red-800">Ingresá un nombre de hasta 120 caracteres.</p>}</div>
          <div className="space-y-1"><label htmlFor="edit-product-category" className="block text-sm font-bold">Categoría</label><select id="edit-product-category" value={selectedCategory ? fields.categoryId : ''} onChange={(event) => change('categoryId', event.target.value)} className={`${inputClass} w-full bg-white`}><option value="">Seleccioná una categoría</option>{data.categorias.map((category) => <option key={category.id} value={category.id}>{category.nombre}{!category.activa ? ' · Inactiva' : ''}</option>)}</select></div>
          <div className="space-y-1"><label htmlFor="edit-product-price" className="block text-sm font-bold">Precio base ($)</label><input id="edit-product-price" inputMode="decimal" value={fields.price} onChange={(event) => change('price', event.target.value)} aria-invalid={priceError || undefined} aria-describedby="edit-product-price-help" className={`${inputClass} w-full bg-white`} /><p id="edit-product-price-help" className={`text-sm ${priceError ? 'text-red-800' : 'text-monu-text'}`}>{priceError ? 'Ingresá un precio mayor que cero, con hasta 2 decimales.' : 'Precio sin variante. Cada variante tiene su propio precio más abajo.'}</p></div>
          <div className="space-y-1 sm:col-span-2"><label htmlFor="edit-product-description" className="block text-sm font-bold">Descripción</label><textarea id="edit-product-description" rows={3} value={fields.description} onChange={(event) => change('description', event.target.value)} className={`${inputClass} w-full bg-white`} /></div>
          <div className="space-y-1"><label htmlFor="edit-product-order" className="block text-sm font-bold">Orden en el menú</label><input id="edit-product-order" type="number" min="0" max="2147483647" step="1" value={fields.order} onChange={(event) => change('order', event.target.value)} className={`${inputClass} w-full bg-white`} /></div>
          <label className="flex min-h-11 items-center gap-3 self-center text-sm font-bold"><input type="checkbox" checked={fields.active} onChange={(event) => change('active', event.target.checked)} className="size-5 accent-monu-green focus-visible:ring-2 focus-visible:ring-monu-green" />Producto activo en el menú</label>
        </fieldset>
        <fieldset disabled={disabled} className="min-w-0 space-y-3 rounded-2xl border border-monu-green/15 p-4">
          <legend className="px-1 text-lg font-extrabold">Imagen del producto</legend>
          {fields.image && <img src={fields.image} alt="Vista previa del producto" className="max-h-48 w-full rounded-xl bg-monu-cream object-contain" />}
          <label htmlFor="edit-product-image" className="block space-y-1 text-sm font-bold"><span>URL o ruta de la imagen</span><input id="edit-product-image" type="text" value={fields.image.startsWith('data:') ? '' : fields.image} onChange={(event) => { reader.current?.abort(); reader.current = null; setImageLoading(false); change('image', event.target.value); }} placeholder={fields.image.startsWith('data:') ? 'Imagen cargada desde archivo' : 'https://… o /images/…'} className={`${inputClass} w-full bg-white`} /></label>
          <label htmlFor="edit-product-file" className="block space-y-1 text-sm font-bold"><span>Subir o reemplazar imagen</span><input id="edit-product-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/avif" onChange={uploadImage} className="block min-h-11 w-full min-w-0 rounded-lg border border-monu-green/20 bg-white p-2 text-sm focus-visible:ring-2 focus-visible:ring-monu-green" /></label>
          <p className="text-sm text-monu-text">PNG, JPEG, WebP, GIF o AVIF. Hasta 5 MiB.</p>
          <p className="text-sm text-monu-text">Al quitarla, se usa la imagen de respaldo del menú si existe.</p>
          {imageLoading && <p role="status" className="text-sm">Leyendo imagen…</p>}
          <button type="button" disabled={!fields.image && !imageLoading} aria-label="Quitar imagen del producto" onClick={() => { reader.current?.abort(); reader.current = null; setImageLoading(false); change('image', ''); }} className={buttonClass}>Quitar imagen</button>
        </fieldset>
        <RecipeEditor value={recipe} onChange={setRecipe} inventory={inventory} disabled={disabled} basePrice={fields.price} showErrors={showErrors} allowExtras={selectedCategory?.nombre !== 'Dips Extra'} />
        {selectedCategory?.nombre === 'Dips Extra' && <p className="text-sm text-monu-text">Dips Extra no admite agregados de ingredientes. Al guardar en esta categoría se deshabilitan los extras anteriores.</p>}
        <p className="text-sm text-monu-text">Los pedidos ya registrados conservan su nombre, precio y receta originales. Cambiar este producto no modifica el stock existente.</p>
      </>}
    </div>
    <div className="sticky bottom-0 z-10 flex flex-wrap justify-end gap-2 border-t border-monu-green/15 bg-monu-bone px-5 py-4">
      <button type="button" disabled={saving} onClick={onClose} className={buttonClass}>Cancelar</button>
      {canRead && canEdit && <button type="button" disabled={disabled || imageLoading || !fields} onClick={save} aria-busy={saving} className={`${buttonClass} bg-monu-green text-white disabled:opacity-60`}>Guardar producto</button>}
    </div>
  </dialog>;
}
