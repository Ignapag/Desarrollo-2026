import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { useEffect, useRef, useState } from 'react';
import { DataError } from '../fulfillment/operationUi';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Trash2, Check, Image as ImageIcon } from 'lucide-react';
import RecipeEditor from './RecipeEditor';
import RecipeModal from './RecipeModal';
import { newRecipe, serializeRecipe } from './recipeModel';

export default function Catalog() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const query = (searchParams.get('q') || '').toLowerCase();
  const { state, createProduct, deactivateProduct, refreshCatalog, refreshInventory } = useData();
  useEffect(() => {
    const controller = new AbortController();
    Promise.resolve().then(() => { if (!controller.signal.aborted) return Promise.allSettled([refreshCatalog(controller.signal), refreshInventory(controller.signal)]); return undefined; });
    return () => controller.abort();
  }, [refreshCatalog, refreshInventory]);
  const [isAdding, setIsAdding] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const deleteBusy = useRef(false);
  const [deleting, setDeleting] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [recipe, setRecipe] = useState(newRecipe);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const imageReader = useRef(null);
  const mounted = useRef(true);
  const [imageLoading, setImageLoading] = useState(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; imageReader.current?.abort?.(); imageReader.current = null; }; }, []);
  const [createError, setCreateError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [showRecipeErrors, setShowRecipeErrors] = useState(false);
  const errorSummary = useRef(null);
  useEffect(() => { if (createError) errorSummary.current?.focus(); }, [createError]);
  const [newItem, setNewItem] = useState({ 
    name: '', category: '', price: '', description: '', image: null,
  });

  const categories = [...new Set(state.catalog.map(p => p.category))];
  const selectedCategory = categories.includes(newItem.category) ? newItem.category : '';

  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    imageReader.current?.abort?.();
    imageReader.current = null;
    setImageLoading(false);
    if (file) {
      if (!file.type.startsWith('image/')) { setCreateError('Seleccioná un archivo de imagen.'); return; }
      const reader = new FileReader();
      imageReader.current = reader;
      setImageLoading(true);
      reader.onload = () => {
        if (imageReader.current !== reader) return;
        setNewItem((item) => ({ ...item, image: reader.result }));
        setImageLoading(false);
      };
      reader.onerror = () => { if (imageReader.current === reader) { setImageLoading(false); setCreateError('No se pudo leer la imagen. Elegila nuevamente.'); } };
      reader.readAsDataURL(file);
    }
  };

  const handleAdd = async () => {
    if (savingRef.current || imageLoading || !can(user, 'productos.gestionar')) return;
    setCreateError('');
    setShowRecipeErrors(true);
    const category = state.catalog.find((product) => product.category === selectedCategory);
    const errors = {};
    if (!newItem.name.trim() || newItem.name.length > 120) errors.name = 'Ingresá un nombre de hasta 120 caracteres.';
    if (!category) errors.category = 'Seleccioná una categoría existente';
    const basePrice = newItem.price.trim().replace(',', '.');
    if (!recipe.variants.length && (!/^\d{1,10}(?:\.\d{1,2})?$/.test(basePrice) || Number(basePrice) <= 0)) errors.price = 'Ingresá un precio mayor que cero, con hasta 2 decimales.';
    setFieldErrors(errors);
    if (Object.keys(errors).length) return setCreateError(Object.values(errors).join(' '));
    try {
      if (recipe.ingredients.some((row) => !state.inventory.some((item) => String(item.id) === row.ingredientId))) throw Error('Seleccioná un ingrediente disponible en cada fila.');
      const ingredients = serializeRecipe(recipe, { includePrices: true });
      const price = ingredients.variantes[0]?.precio || basePrice;
      if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(price) || Number(price) <= 0) throw Error('Completá un precio válido.');
      savingRef.current = true;
      setSaving(true);
      await createProduct({
        ...newItem, name: newItem.name.trim(),
        ...ingredients,
        categoryId: category.categoryId,
        price,
      });
      if (!mounted.current) return;
      toast.success('Producto agregado', { description: newItem.name });
      setNewItem({
        name: '', category: categories[0] || '', price: '', description: '', image: null,
      });
      setRecipe(newRecipe());
      setShowRecipeErrors(false);
      setIsAdding(false);
    } catch (error) {
      if (mounted.current) setCreateError(error.message);
    } finally {
      savingRef.current = false;
      if (mounted.current) setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (deleteBusy.current || !can(user, 'productos.gestionar')) return;
    deleteBusy.current = true;
    setDeleting(true);
    try {
      await deactivateProduct(id);
      if (!mounted.current) return;
      toast.info('Producto desactivado');
      setDeletingId(null);
    } catch (error) {
      if (mounted.current) toast.error('No se pudo desactivar el producto', { description: error.message });
    } finally {
      deleteBusy.current = false;
      if (mounted.current) setDeleting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <DataError message={state.catalogError || state.inventoryError} retry={() => { void Promise.allSettled([refreshCatalog(undefined, true), refreshInventory(undefined, true)]); }} />
      {state.catalogStatus === 'loading' && <p role="status">Consultando catálogo...</p>}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Catálogo de Menú</h1>
          <p className="text-monu-text/70">Gestioná los productos que ven los clientes.</p>
        </div>
        <button disabled={!can(user, 'productos.gestionar')}
          onClick={() => {
            setNewItem((item) => ({ ...item, category: categories.includes(item.category) ? item.category : categories[0] || '' }));
            setIsAdding(true);
          }}
          className="bg-monu-dark text-white px-4 py-2 rounded-xl font-bold flex items-center gap-2 hover:bg-black transition shadow-md"
        >
          <Plus className="w-5 h-5" /> Nuevo Producto
        </button>
      </div>

      {isAdding && can(user, 'productos.gestionar') && (
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-monu-green/10 mb-6 flex flex-col gap-4">
          <h3 className="font-extrabold text-lg border-b pb-2">Agregar nuevo producto</h3>
          <fieldset disabled={saving} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label htmlFor="new-product-name" className="block text-xs font-bold text-gray-500 mb-1">Nombre</label>
              <input id="new-product-name" type="text" maxLength={120} aria-invalid={Boolean(fieldErrors.name)} aria-describedby="new-product-name-error" value={newItem.name} disabled={saving} onChange={e => setNewItem({...newItem, name: e.target.value})} className="min-h-11 w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green" placeholder="Ej: Super Burger" />
              <p id="new-product-name-error" className="text-sm text-red-700">{fieldErrors.name}</p>
            </div>
            <div>
              <label htmlFor="new-product-category" className="block text-xs font-bold text-gray-500 mb-1">Categoría</label>
              <select id="new-product-category" aria-invalid={Boolean(fieldErrors.category)} aria-describedby="new-product-category-error" value={selectedCategory} onChange={e => setNewItem({...newItem, category: e.target.value})} className="min-h-11 w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green">
                <option value="" disabled>Seleccioná una categoría</option>
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <p id="new-product-category-error" className="text-sm text-red-700">{fieldErrors.category}</p>
            </div>
            <div>
              <label htmlFor="new-product-price" className="block text-xs font-bold text-gray-500 mb-1">Precio base ($)</label>
              <input id="new-product-price" inputMode="decimal" aria-invalid={Boolean(fieldErrors.price)} aria-describedby="new-product-price-error" value={newItem.price} disabled={saving || recipe.variants.length > 0} onChange={e => setNewItem({...newItem, price: e.target.value})} className="min-h-11 w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green" placeholder="10000" />
              <p id="new-product-price-error" className="text-sm text-red-700">{fieldErrors.price}</p>
              {recipe.variants.length > 0 && <p className="mt-1 text-xs text-monu-text">Se usa el precio de la primera variante.</p>}
            </div>
            <div>
              <label htmlFor="new-product-image" className="block text-xs font-bold text-gray-500 mb-1">Foto</label>
              <div className="w-full border rounded-lg px-3 py-2 font-bold flex flex-wrap items-center gap-2 bg-gray-50">
                <ImageIcon className="w-4 h-4 text-monu-green" />
                <span className="text-sm truncate">{newItem.image ? 'Imagen cargada' : 'Subir archivo...'}</span>
                <input id="new-product-image" type="file" accept="image/*" onChange={handleImageUpload} className="min-h-11 w-full text-sm focus-visible:outline-2 focus-visible:outline-monu-green" />
              </div>
              {imageLoading && <p role="status" className="text-sm">Leyendo imagen…</p>}
            </div>
            <div className="md:col-span-2 lg:col-span-4">
              <label htmlFor="new-product-description" className="block text-xs font-bold text-gray-500 mb-1">Descripción del menú</label>
              <input id="new-product-description" type="text" value={newItem.description} onChange={e => setNewItem({...newItem, description: e.target.value})} className="min-h-11 w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green" placeholder="Ej: Carne, cheddar, bacon y salsa monu." />
            </div>
          </fieldset>
          <RecipeEditor value={recipe} onChange={setRecipe} inventory={state.inventory} disabled={saving} basePrice={newItem.price} showErrors={showRecipeErrors} />
          <div ref={errorSummary} tabIndex={-1}><DataError message={createError} /></div>
          <div className="flex justify-end gap-2 mt-2 border-t pt-4">
            <button disabled={saving} onClick={() => { imageReader.current?.abort?.(); imageReader.current = null; setImageLoading(false); setIsAdding(false); }} className="min-h-11 px-4 py-2 text-gray-500 font-bold hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button disabled={saving || imageLoading} aria-busy={saving} onClick={handleAdd} className="min-h-11 px-4 py-2 bg-monu-green text-white font-bold rounded-lg hover:bg-[#002b22] flex items-center gap-2 disabled:opacity-60">
              <Check className="w-4 h-4" /> Guardar Producto
            </button>
          </div>
        </div>
      )}

      <div role="region" aria-label="Catálogo de productos" tabIndex={0} className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-x-auto focus-visible:ring-2 focus-visible:ring-monu-green">
        <table className="w-full text-left">
          <thead className="bg-monu-cream/50 text-monu-dark">
            <tr>
              <th className="p-4 font-extrabold">Producto</th>
              <th className="p-4 font-extrabold hidden md:table-cell">Categoría</th>
              <th className="p-4 font-extrabold">Precio</th>
              <th className="p-4 font-extrabold text-right">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-monu-green/10">
            {state.catalog.filter(p => p.name.toLowerCase().includes(query) || p.category.toLowerCase().includes(query)).map(product => (
              <tr key={product.id} className="hover:bg-gray-50 transition">
                <td className="p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-lg bg-gray-100 flex items-center justify-center p-1 shrink-0 overflow-hidden">
                      {product.image ? (
                        <img src={product.image} className="w-full h-full object-cover rounded-md" alt={product.name} />
                      ) : (
                        <img src="/favicon.png" className="w-8 h-8 object-contain opacity-50" alt="Logo" />
                      )}
                    </div>
                    <div>
                      <p className="font-extrabold text-monu-dark">{product.name}</p>
                      {product.available === false && <p className="mt-1 text-sm font-medium text-monu-burnt">No disponible · Revisá la receta y el stock.</p>}
                      <p className="text-xs text-gray-500 truncate max-w-[200px] hidden sm:block">{product.description}</p>
                    </div>
                  </div>
                </td>
                <td className="p-4 font-bold text-gray-600 hidden md:table-cell">{product.category}</td>
                <td className="p-4 font-extrabold text-monu-green">
                  ${product.price ? product.price.toLocaleString('es-AR') : product.variants?.[0]?.price?.toLocaleString('es-AR')}
                </td>
                <td className="p-4 text-right">
                  <button disabled={!can(user, 'productos.ver_receta')} onClick={() => setEditingProduct(product)} className="min-h-11 rounded-lg border border-monu-green/20 px-3 py-2 font-bold text-monu-green hover:bg-monu-cream focus-visible:ring-2 focus-visible:ring-monu-green" aria-label={`Editar receta de ${product.name}`}>Receta</button>
                  {deletingId === product.id ? (
                    <div className="flex flex-col gap-1 items-end">
                      <span className="text-xs font-bold text-red-500">¿Seguro?</span>
                      <div className="flex gap-1">
                        <button disabled={deleting || !can(user, 'productos.gestionar')} aria-busy={deleting} onClick={() => handleDelete(product.id)} className="min-h-11 min-w-11 text-xs font-bold bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded transition">Sí</button>
                        <button disabled={deleting} onClick={() => setDeletingId(null)} className="min-h-11 min-w-11 text-xs font-bold bg-gray-200 hover:bg-gray-300 text-monu-dark px-2 py-1 rounded transition">No</button>
                      </div>
                    </div>
                  ) : (
                    <button disabled={deleting || !can(user, 'productos.gestionar')} onClick={() => setDeletingId(product.id)} className="min-h-11 min-w-11 p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition" aria-label={`Desactivar ${product.name}`} title="Eliminar">
                      <Trash2 className="w-5 h-5" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editingProduct && <RecipeModal key={editingProduct.id} product={editingProduct} onClose={() => setEditingProduct(null)} />}
    </div>
  );
}
