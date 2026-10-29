// Menú público: productos del catálogo filtrables por categoría y búsqueda, con
// variantes, personalización (quitar ingredientes) y botón para agregar al carrito.
import { Plus, LoaderCircle, RefreshCw } from 'lucide-react';
import { useData } from '../shared/store/DataContext';
import { useEffect, useRef, useState } from 'react';
import { Settings2 } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { buildCustomizedItem, extrasForVariant, portionLabel } from './ingredientExtras';

// Categorías del menú en el orden en que se muestran las pestañas.
const CATEGORIES = ['Todas', 'Nuestras Burgers', 'Monufusión', 'Opciones Individuales', 'Combos', 'Acompañamientos', 'Bebidas', 'Dips Extra'];

/**
 * Tarjeta de producto. Permite elegir variante y quitar ingredientes; `addToCart`
 * devuelve false si el carrito alcanzó sus límites.
 */
function ProductCard({ product, addToCart }) {
  // Variante elegida (la primera disponible) e ingredientes quitados por el cliente.
  const [selectedVariantName, setSelectedVariantName] = useState(() => product.variants?.find((variant) => variant.available !== false)?.name || '');
  const [removedIngredients, setRemovedIngredients] = useState([]);
  const [extraQuantities, setExtraQuantities] = useState({});
  const optionsRef = useRef(null);
  const isDip = product.category === 'Dips Extra';
  const removableIngredients = isDip ? [] : product.removableIngredients || [];
  const notes = removedIngredients.filter((name) => removableIngredients.includes(name))
    .map((name) => `Sin ${name}`).join(', ');

  // La captura de los dips no tiene resolución para un cuadro grande.
  const compact = isDip;
  const hasVariants = product.variants && product.variants.length > 0;
  const productAvailable = product.active === true && product.available === true;
  const selectedVariant = product.variants?.find((variant) => variant.name === selectedVariantName);
  const extraOptions = extrasForVariant(product, selectedVariantName);
  const changedExtras = Object.entries(extraQuantities).some(([id, quantity]) => quantity > 0 && !extraOptions.some((extra) => String(extra.ingrediente_id) === id && quantity <= extra.max_por_item));
  const changedOptions = !isDip && (removedIngredients.some((name) => !removableIngredients.includes(name)) || changedExtras);
  const canOrder = productAvailable && !changedOptions && (!hasVariants || (selectedVariant && selectedVariant.available !== false));
  const basePrice = hasVariants ? selectedVariant?.price : product.price;
  const extraCents = extraOptions.reduce((sum, extra) => sum + Math.round(Number(extra.precio) * 100) * (extraQuantities[extra.ingrediente_id] || 0), 0);
  const currentPrice = (Math.round(Number(basePrice || 0) * 100) + extraCents) / 100;
  const changeExtra = (extra, delta) => {
    setExtraQuantities((previous) => ({ ...previous, [extra.ingrediente_id]: Math.max(0, Math.min(extra.max_por_item, (previous[extra.ingrediente_id] || 0) + delta)) }));
    if (delta > 0) setRemovedIngredients((previous) => previous.filter((name) => name !== extra.nombre));
  };

  // Agrega el producto (con su variante y aclaraciones) al carrito y reinicia la personalización.
  const handleAdd = () => {
    if (!canOrder) return;
    const itemToAdd = buildCustomizedItem(product, selectedVariantName, removedIngredients, extraQuantities);
    
    if (addToCart(itemToAdd) === false) return;
    toast.success('Agregado al carrito', { description: itemToAdd.name });
    setRemovedIngredients([]);
    setExtraQuantities({});
    if (optionsRef.current) optionsRef.current.open = false;
  };

  // Botón de agregar, ubicado sobre la foto o junto al precio según el formato de la tarjeta.
  const addButton = (
    <button
      onClick={handleAdd}
      disabled={!canOrder}
      aria-label={`Agregar ${product.name} al carrito`}
      className={`${compact ? 'shrink-0 ' : 'absolute bottom-3 right-3 '}min-w-11 min-h-11 bg-white text-monu-dark p-2.5 rounded-xl shadow-md hover:bg-monu-dark hover:text-white transition-colors focus-visible:ring-2 focus-visible:ring-monu-green disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400 disabled:shadow-none`}
    >
      <Plus aria-hidden="true" className="w-5 h-5" />
    </button>
  );

  return (
    <div className={`bg-white rounded-[2rem] p-4 border border-monu-green/5 shadow-sm hover:shadow-monu-lg transition-all flex group ${compact ? 'flex-row gap-4 self-start' : 'flex-col h-full'}`}>
      {/* Foto del producto (o logo si no tiene) */}
      <div className={`relative overflow-hidden bg-monu-cream flex items-center justify-center ${compact ? 'aspect-[138/135] w-24 shrink-0 self-start rounded-xl' : 'aspect-[4/3] rounded-2xl mb-4'}`}>
        {product.image ? (
           <img 
             src={product.image} 
             alt={product.name}
             className={compact ? 'w-full h-full object-contain' : 'w-full h-full object-cover group-hover:scale-105 transition duration-500'}
           />
        ) : (
           <img src="/favicon.png" className="w-full h-full object-contain" alt="Logo" />
        )}
        {!compact && addButton}
        {!compact && !canOrder && <span className="absolute left-3 top-3 rounded-full bg-white px-3 py-1 text-sm font-bold text-monu-text">No disponible</span>}
      </div>

      {/* Nombre, precio y descripción */}
      <div className="min-w-0 flex-1 flex flex-col">
        <div className={compact ? 'mb-1' : 'flex justify-between items-start mb-2 gap-2'}>
          <h3 className={`font-heading font-black text-monu-dark leading-tight ${compact ? 'text-lg' : 'text-xl'}`}>{product.name}</h3>
          {!compact && <span className="font-extrabold text-monu-orange whitespace-nowrap">${currentPrice}</span>}
        </div>
        <p className={`text-sm text-monu-text/70 line-clamp-2 leading-relaxed ${compact ? 'mb-2' : 'mb-4'}`}>
          {product.description}
        </p>

        {/* Precio compacto, selector de variante y personalización */}
        <div className="mt-auto">
          {compact && (
            <>
              {!canOrder && <span className="mb-2 block text-sm font-bold text-monu-text">No disponible</span>}
              <div className="flex items-center justify-between gap-2">
                <span className="font-extrabold text-monu-orange whitespace-nowrap">${currentPrice}</span>
                {addButton}
              </div>
            </>
          )}
          <div className="flex gap-2">
            {hasVariants ? (
              <select 
                disabled={!productAvailable}
                value={selectedVariant?.name || ''}
                aria-label={`Variante de ${product.name}`}
                onChange={(e) => {
                  const name = e.target.value;
                  const valid = extrasForVariant(product, name);
                  setSelectedVariantName(name);
                  setExtraQuantities((previous) => Object.fromEntries(Object.entries(previous).filter(([id, quantity]) => valid.some((extra) => String(extra.ingrediente_id) === id && quantity <= extra.max_por_item))));
                }}
                className="min-h-11 min-w-0 flex-1 bg-monu-cream/50 border border-monu-green/10 rounded-xl px-3 py-2 text-sm font-bold text-monu-dark focus:outline-none focus:border-monu-green"
              >
                {!selectedVariant && <option value="" disabled>Elegí una variante vigente</option>}
                {product.variants.map((v) => (
                  <option key={v.name} value={v.name} disabled={v.available === false}>{v.name} - ${v.price}{v.available === false ? ' · Sin disponibilidad' : ''}</option>
                ))}
              </select>
            ) : null}
          </div>
          
          {/* Aviso si cambiaron los ingredientes removibles desde que se personalizó */}
          {changedOptions && <div role="alert" className="mt-3 text-sm text-red-800"><p>Las opciones cambiaron. Revisá la personalización antes de agregar.</p><button type="button" onClick={() => { setRemovedIngredients((previous) => previous.filter((name) => removableIngredients.includes(name))); setExtraQuantities({}); }} className="min-h-11 underline focus-visible:ring-2 focus-visible:ring-monu-green">Revisar opciones vigentes</button></div>}
          {/* Personalización: quitar ingredientes (otros cambios se piden por WhatsApp) */}
          {productAvailable && (removableIngredients.length > 0 || extraOptions.length > 0) && (
            <details ref={optionsRef} className="mt-3 rounded-xl border border-monu-green/10 bg-monu-cream/25">
              <summary aria-label={`Personalizar ${product.name}`} className="min-h-11 cursor-pointer rounded-xl px-3 py-3 text-sm font-bold text-monu-green focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green">
                <Settings2 aria-hidden="true" className="mr-2 inline size-4" />Personalizar
              </summary>
              <fieldset className="px-3 pb-3">
                <legend className="mb-2 text-sm font-bold text-monu-dark">Quitar ingredientes</legend>
                <div className="flex flex-wrap gap-2">
                  {removableIngredients.map((ingredient) => (
                    <label key={ingredient} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-monu-green/15 bg-white px-3 py-2 text-sm font-medium text-monu-dark hover:bg-monu-cream/50">
                      <input type="checkbox" className="size-4 accent-monu-green focus-visible:ring-2 focus-visible:ring-monu-green"
                        checked={removedIngredients.includes(ingredient)}
                        onChange={(event) => {
                          const checked = event.target.checked;
                          if (checked) setExtraQuantities((previous) => Object.fromEntries(Object.entries(previous).filter(([id]) => !extraOptions.some((extra) => String(extra.ingrediente_id) === id && extra.nombre === ingredient))));
                          setRemovedIngredients((previous) => checked
                            ? [...previous, ingredient]
                            : previous.filter((name) => name !== ingredient));
                        }} />
                      {`Sin ${ingredient}`}
                    </label>
                  ))}
                </div>
              </fieldset>
              {extraOptions.length > 0 && <fieldset className="space-y-3 px-3 pb-3">
                <legend className="mb-2 text-sm font-bold text-monu-dark">Agregar ingredientes</legend>
                {extraOptions.map((extra) => <div key={extra.ingrediente_id} className="rounded-lg bg-white p-2">
                  <p className="text-sm font-bold text-monu-dark">{extra.nombre}</p>
                  <p className="text-sm text-monu-text">{portionLabel(extra)} por extra · +${Number(extra.precio).toLocaleString('es-AR')} · Máx. {extra.max_por_item}</p>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <button type="button" aria-label={`Reducir extra ${extra.nombre}`} disabled={!extraQuantities[extra.ingrediente_id]} onClick={() => changeExtra(extra, -1)} className="size-11 rounded-lg border border-monu-green/20 text-lg font-bold focus-visible:ring-2 focus-visible:ring-monu-green disabled:opacity-40">−</button>
                      <output aria-label={`Cantidad extra de ${extra.nombre}`} className="min-w-6 text-center font-bold">{extraQuantities[extra.ingrediente_id] || 0}</output>
                      <button type="button" aria-label={`Sumar extra ${extra.nombre}`} disabled={(extraQuantities[extra.ingrediente_id] || 0) >= extra.max_por_item} onClick={() => changeExtra(extra, 1)} className="size-11 rounded-lg border border-monu-green/20 text-lg font-bold focus-visible:ring-2 focus-visible:ring-monu-green disabled:opacity-40">+</button>
                    </div>
                    <span className="text-sm font-bold">+${(Number(extra.precio) * (extraQuantities[extra.ingrediente_id] || 0)).toLocaleString('es-AR')}</span>
                  </div>
                </div>)}
              </fieldset>}
            </details>
          )}
          {(notes || extraCents > 0) && <div className="mt-3 space-y-1 text-sm text-monu-dark" aria-live="polite">
            {notes && <p>{notes}</p>}
            {extraOptions.filter((extra) => extraQuantities[extra.ingrediente_id] > 0).map((extra) => <p key={extra.ingrediente_id}>+{extraQuantities[extra.ingrediente_id]} × {extra.nombre} ({portionLabel(extra)} cada extra)</p>)}
            <p className="font-bold">Total por hamburguesa: ${currentPrice.toLocaleString('es-AR')}</p>
          </div>}
        </div>
      </div>
    </div>
  );
}

/** Pantalla de menú del cliente. */
export default function Menu() {
  const { state, dispatch, refreshCatalog } = useData();
  // Carga el catálogo al montar.
  useEffect(() => {
    const controller = new AbortController();
    Promise.resolve().then(() => { if (!controller.signal.aborted) return refreshCatalog(controller.signal); }).catch(() => undefined);
    return () => controller.abort();
  }, [refreshCatalog]);
  // Filtros del menú: búsqueda (?q=) y categoría (?categoria=).
  const [searchParams, setSearchParams] = useSearchParams();
  const query = (searchParams.get('q') || '').toLowerCase();
  const currentCategory = searchParams.get('categoria') || 'Todas';

  const PRODUCTS = state.catalog || [];

  const filteredProducts = PRODUCTS.filter(p => {
    const matchCat = currentCategory === 'Todas' || p.category === currentCategory;
    const matchQuery = p.name.toLowerCase().includes(query) || (p.description && p.description.toLowerCase().includes(query));
    return matchCat && matchQuery;
  });

  // Agrega al carrito respetando los límites del pedido (50 productos y 50 unidades por ítem).
  const addToCart = (product) => {
    const existing = state.cart.find((item) => item.id === product.id);
    if ((existing?.quantity || 0) >= 50 || (!existing && state.cart.length >= 50)) {
      toast.error('Revisá el carrito', { description: 'El pedido admite hasta 50 productos y 50 unidades por ítem.' });
      return false;
    }
    dispatch({ type: 'ADD_TO_CART', payload: { ...product, quantity: 1 } });
    return true;
  };

  // Estados de carga y error del catálogo.
  if (state.catalogStatus === 'loading') {
    return (
      <div role="status" className="flex min-h-64 items-center justify-center gap-3 rounded-3xl border border-monu-green/10 bg-monu-bone p-6 text-monu-dark">
        <LoaderCircle aria-hidden="true" className="size-5 motion-safe:animate-spin" />
        <p className="font-bold">Cargando menú…</p>
      </div>
    );
  }

  if (state.catalogStatus === 'error') {
    return (
      <div className="flex min-h-64 flex-col items-center justify-center gap-4 rounded-3xl border border-monu-green/10 bg-monu-bone p-6 text-center">
        <p role="alert" className="font-bold text-monu-dark">{state.catalogError}</p>
        <button type="button" onClick={() => { void refreshCatalog(undefined, true).catch(() => undefined); }} className="flex min-h-11 items-center gap-2 rounded-xl bg-monu-green px-5 py-3 font-bold text-white hover:bg-monu-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2">
          <RefreshCw aria-hidden="true" className="size-4" />Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Pestañas de categorías */}
      <div className="flex overflow-x-auto hide-scrollbar gap-2 pb-2 -mx-4 px-4 sm:mx-0 sm:px-0">
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => setSearchParams(cat === 'Todas' ? {} : { categoria: cat })}
            className={`whitespace-nowrap px-6 py-2.5 rounded-full font-bold text-sm transition-all ${
              currentCategory === cat 
                ? 'bg-monu-dark text-white shadow-md' 
                : 'bg-white text-monu-text hover:bg-monu-cream'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Grilla de productos */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredProducts.map(product => (
          <ProductCard 
            key={product.id} 
            product={product} 
            addToCart={addToCart}
          />
        ))}
      </div>
      
      {/* Estado vacío */}
      {filteredProducts.length === 0 && (
        <div className="text-center py-20 bg-white rounded-3xl border border-dashed border-monu-green/20">
          <span className="text-6xl mb-4 block">🔍</span>
          <p className="text-monu-text/60 font-bold">No hay productos en esta categoría aún.</p>
        </div>
      )}
    </div>
  );
}
