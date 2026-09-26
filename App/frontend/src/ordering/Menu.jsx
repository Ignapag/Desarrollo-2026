import { Plus } from 'lucide-react';
import { useData } from '../shared/store/DataContext';
import { useState } from 'react';
import { Settings2 } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

const CATEGORIES = ['Todas', 'Nuestras Burgers', 'Monufusión', 'Opciones Individuales', 'Combos', 'Acompañamientos', 'Bebidas', 'Dips Extra'];

function ProductCard({ product, addToCart }) {
  const [selectedVariantIndex, setSelectedVariantIndex] = useState(0);
  const [showOptions, setShowOptions] = useState(false);
  const [notes, setNotes] = useState('');

  const hasVariants = product.variants && product.variants.length > 0;
  const currentPrice = hasVariants ? product.variants[selectedVariantIndex].price : product.price;

  const handleAdd = () => {
    const itemToAdd = hasVariants ? {
      ...product,
      id: `${product.id}-${product.variants[selectedVariantIndex].name}`,
      name: `${product.name} (${product.variants[selectedVariantIndex].name})`,
      price: product.variants[selectedVariantIndex].price,
    } : { ...product };

    if (notes.trim()) {
      itemToAdd.notes = notes.trim();
      itemToAdd.id = `${itemToAdd.id}-${Date.now()}`; // Unique ID so it stacks separately in cart
    }
    
    addToCart(itemToAdd);
    toast.success('Agregado al carrito', { description: itemToAdd.name });
    setNotes('');
    setShowOptions(false);
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
          className="absolute bottom-3 right-3 bg-white text-monu-dark p-2.5 rounded-xl shadow-md hover:bg-monu-dark hover:text-white transition-colors"
        >
          <Plus className="w-5 h-5" />
        </button>
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
                value={selectedVariantIndex}
                onChange={(e) => setSelectedVariantIndex(parseInt(e.target.value))}
                className="flex-1 bg-monu-cream/50 border border-monu-green/10 rounded-xl px-3 py-2 text-sm font-bold text-monu-dark focus:outline-none focus:border-monu-green"
              >
                {product.variants.map((v, i) => (
                  <option key={i} value={i}>{v.name} - ${v.price}</option>
                ))}
              </select>
            ) : (
              <div className="flex-1 h-[38px]"></div>
            )}
            <button 
              onClick={() => setShowOptions(!showOptions)}
              className={`p-2 rounded-xl transition-colors ${showOptions ? 'bg-monu-green text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}
              title="Personalizar pedido"
            >
              <Settings2 className="w-5 h-5" />
            </button>
          </div>
          
          {showOptions && (
            <div className="mt-3 animate-in slide-in-from-top-2 bg-yellow-50 border border-yellow-200 rounded-xl p-3">
              <p className="text-xs font-bold text-yellow-800 mb-2">Sacar ingredientes:</p>
              <div className="flex flex-wrap gap-2 mb-3">
                {['Sin Cebolla', 'Sin Tomate', 'Sin Lechuga', 'Sin Pepinillos', 'Sin Bacon', 'Sin Cheddar'].map(ing => (
                  <label key={ing} className="flex items-center gap-1.5 text-xs font-bold text-yellow-900 bg-yellow-100/50 px-2 py-1 rounded-md cursor-pointer hover:bg-yellow-200 transition">
                    <input 
                      type="checkbox" 
                      className="accent-monu-orange"
                      checked={notes.includes(ing)}
                      onChange={(e) => {
                        if(e.target.checked) {
                          setNotes(notes ? notes + ', ' + ing : ing);
                        } else {
                          setNotes(notes.replace(ing + ', ', '').replace(', ' + ing, '').replace(ing, ''));
                        }
                      }}
                    />
                    {ing}
                  </label>
                ))}
              </div>
              <input 
                type="text" 
                placeholder="Otras notas / extras..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-white border border-yellow-300 rounded-lg px-3 py-2 text-sm text-monu-dark placeholder:text-gray-400 focus:outline-none focus:border-monu-orange"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Menu() {
  const { state, dispatch } = useData();
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
