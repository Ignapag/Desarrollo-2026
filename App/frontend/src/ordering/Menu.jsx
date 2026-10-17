import { Plus, LoaderCircle, RefreshCw } from 'lucide-react';
import { useData } from '../shared/store/DataContext';
import { useRef, useState } from 'react';
import { Settings2 } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

const CATEGORIES = ['Todas', 'Nuestras Burgers', 'Monufusión', 'Opciones Individuales', 'Combos', 'Acompañamientos', 'Bebidas', 'Dips Extra'];

function ProductCard({ product, addToCart }) {
  const [selectedVariantIndex, setSelectedVariantIndex] = useState(0);
  const [removedIngredients, setRemovedIngredients] = useState([]);
  const optionsRef = useRef(null);
  const removableIngredients = product.removableIngredients || [];
  const notes = removedIngredients.filter((name) => removableIngredients.includes(name))
    .map((name) => `Sin ${name}`).join(', ');

  const hasVariants = product.variants && product.variants.length > 0;
  const canOrder = product.active === true && product.available === true;
  const currentPrice = hasVariants ? product.variants[selectedVariantIndex].price : product.price;

  const handleAdd = () => {
    if (!canOrder) return;
    const itemToAdd = hasVariants ? {
      ...product,
      id: `${product.id}-${product.variants[selectedVariantIndex].name}`,
      name: `${product.name} (${product.variants[selectedVariantIndex].name})`,
      price: product.variants[selectedVariantIndex].price,
      variant: product.variants[selectedVariantIndex].name,
    } : { ...product };

    if (notes.trim()) {
      itemToAdd.notes = notes.trim();
      itemToAdd.id = `${itemToAdd.id}-${Date.now()}`; // Unique ID so it stacks separately in cart
    }
    
    addToCart(itemToAdd);
    toast.success('Agregado al carrito', { description: itemToAdd.name });
    setRemovedIngredients([]);
    if (optionsRef.current) optionsRef.current.open = false;
  };

  return (
    <div className="bg-white rounded-[2rem] p-4 border border-monu-green/5 shadow-sm hover:shadow-monu-lg transition-all flex flex-col h-full group">
      <div className="relative aspect-[4/3] rounded-2xl overflow-hidden mb-4 bg-monu-cream flex items-center justify-center">
        {product.image ? (
           <img 
             src={product.image} 
             alt={product.name}
             className="w-full h-full object-cover group-hover:scale-105 transition duration-500"
           />
        ) : (
           <img src="/favicon.png" className="w-full h-full object-contain" alt="Logo" />
        )}
        <button 
          onClick={handleAdd}
          disabled={!canOrder}
          aria-label={`Agregar ${product.name} al carrito`}
          className="absolute bottom-3 right-3 min-w-11 min-h-11 bg-white text-monu-dark p-2.5 rounded-xl shadow-md hover:bg-monu-dark hover:text-white transition-colors focus-visible:ring-2 focus-visible:ring-monu-green disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400 disabled:shadow-none"
        >
          <Plus className="w-5 h-5" />
        </button>
        {!canOrder && <span className="absolute left-3 top-3 rounded-full bg-white px-3 py-1 text-sm font-bold text-monu-text">No disponible</span>}
      </div>

      <div className="flex-1 flex flex-col">
        <div className="flex justify-between items-start mb-2 gap-2">
          <h3 className="font-heading font-black text-xl text-monu-dark leading-tight">{product.name}</h3>
          <span className="font-extrabold text-monu-orange whitespace-nowrap">${currentPrice}</span>
        </div>
        <p className="text-sm text-monu-text/70 mb-4 line-clamp-2 leading-relaxed">
          {product.description}
        </p>

        <div className="mt-auto">
          <div className="flex gap-2">
            {hasVariants ? (
              <select 
                disabled={!canOrder}
                value={selectedVariantIndex}
                aria-label={`Variante de ${product.name}`}
                onChange={(e) => setSelectedVariantIndex(parseInt(e.target.value))}
                className="flex-1 bg-monu-cream/50 border border-monu-green/10 rounded-xl px-3 py-2 text-sm font-bold text-monu-dark focus:outline-none focus:border-monu-green"
              >
                {product.variants.map((v, i) => (
                  <option key={i} value={i}>{v.name} - ${v.price}</option>
                ))}
              </select>
            ) : null}
          </div>
          
          {canOrder && removableIngredients.length > 0 && (
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
                          setRemovedIngredients((previous) => checked
                            ? [...previous, ingredient]
                            : previous.filter((name) => name !== ingredient));
                        }} />
                      {`Sin ${ingredient}`}
                    </label>
                  ))}
                </div>
                <p className="mt-3 text-xs text-monu-text/70">Otros cambios se consultan por WhatsApp.</p>
              </fieldset>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Menu() {
  const { state, dispatch, refreshData } = useData();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = (searchParams.get('q') || '').toLowerCase();
  const currentCategory = searchParams.get('categoria') || 'Todas';

  const PRODUCTS = state.catalog || [];

  const filteredProducts = PRODUCTS.filter(p => {
    const matchCat = currentCategory === 'Todas' || p.category === currentCategory;
    const matchQuery = p.name.toLowerCase().includes(query) || (p.description && p.description.toLowerCase().includes(query));
    return matchCat && matchQuery;
  });

  const addToCart = (product) => {
    dispatch({ type: 'ADD_TO_CART', payload: { ...product, quantity: 1 } });
  };

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
        <button type="button" onClick={() => { void refreshData().catch(() => undefined); }} className="flex min-h-11 items-center gap-2 rounded-xl bg-monu-green px-5 py-3 font-bold text-white hover:bg-monu-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2">
          <RefreshCw aria-hidden="true" className="size-4" />Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
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

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredProducts.map(product => (
          <ProductCard 
            key={product.id} 
            product={product} 
            addToCart={addToCart}
          />
        ))}
      </div>
      
      {filteredProducts.length === 0 && (
        <div className="text-center py-20 bg-white rounded-3xl border border-dashed border-monu-green/20">
          <span className="text-6xl mb-4 block">🔍</span>
          <p className="text-monu-text/60 font-bold">No hay productos en esta categoría aún.</p>
        </div>
      )}
    </div>
  );
}
