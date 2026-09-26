const fs = require("fs");
const code = `import { Plus } from 'lucide-react';
import { useData } from '../shared/store/DataContext';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';

const CATEGORIES = ['Todas', 'Nuestras Burgers', 'Monufusión', 'Opciones Individuales', 'Combos', 'Acompañamientos', 'Bebidas', 'Dips Extra'];

function ProductCard({ product, addToCart }) {
  const [selectedVariantIndex, setSelectedVariantIndex] = useState(0);

  const hasVariants = product.variants && product.variants.length > 0;
  const currentPrice = hasVariants ? product.variants[selectedVariantIndex].price : product.price;

  const handleAdd = () => {
    if (hasVariants) {
      const variant = product.variants[selectedVariantIndex];
      addToCart({
        ...product,
        id: \`\${product.id}-\${variant.name}\`,
        name: \`\${product.name} (\${variant.name})\`,
        price: variant.price,
      });
    } else {
      addToCart(product);
    }
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
           <span className="text-5xl opacity-40">🍔</span>
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
          <span className="font-extrabold text-monu-orange whitespace-nowrap">\${currentPrice}</span>
        </div>
        <p className="text-sm text-monu-text/70 mb-4 line-clamp-2 leading-relaxed">
          {product.description}
        </p>

        <div className="mt-auto">
          {hasVariants ? (
            <select 
              value={selectedVariantIndex}
              onChange={(e) => setSelectedVariantIndex(parseInt(e.target.value))}
              className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-3 py-2 text-sm font-bold text-monu-dark focus:outline-none focus:border-monu-green"
            >
              {product.variants.map((v, i) => (
                <option key={i} value={i}>{v.name} - \${v.price}</option>
              ))}
            </select>
          ) : (
            <div className="h-[38px]"></div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Menu() {
  const { state, dispatch } = useData();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentCategory = searchParams.get('categoria') || 'Todas';

  const PRODUCTS = state.catalog || [];

  const filteredProducts = currentCategory === 'Todas' 
    ? PRODUCTS 
    : PRODUCTS.filter(p => p.category === currentCategory);

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
            className={\`whitespace-nowrap px-6 py-2.5 rounded-full font-bold text-sm transition-all \${
              currentCategory === cat 
                ? 'bg-monu-dark text-white shadow-md' 
                : 'bg-white text-monu-text hover:bg-monu-cream'
            }\`}
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
`;
fs.writeFileSync("src/ordering/Menu.jsx", code, "utf-8");