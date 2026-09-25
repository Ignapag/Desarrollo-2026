import { Plus } from 'lucide-react';
import { useData } from '../shared/store/DataContext';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';

const PRODUCTS = [
  // NUESTRAS BURGERS
  { id: 1, name: 'Cheese', description: 'Ingredientes: Carne, cheddar, salsa monu.', variants: [{name: 'Simple', price: 11000}, {name: 'Doble', price: 13500}, {name: 'Triple', price: 15500}], category: 'Nuestras Burgers', image: '/menu/chesee burger.jpg' },
  { id: 2, name: 'Bacon', description: 'Ingredientes: Carne, cheddar, bacon, salsa monu.', variants: [{name: 'Simple', price: 12000}, {name: 'Doble', price: 14500}, {name: 'Triple', price: 16500}], category: 'Nuestras Burgers', image: '/menu/BaconBurger.jpg' },
  { id: 3, name: 'Crispy', description: 'Ingredientes: Carne, cheddar, bacon, cebolla crispy, alioli.', variants: [{name: 'Simple', price: 13000}, {name: 'Doble', price: 15500}, {name: 'Triple', price: 17500}], category: 'Nuestras Burgers', image: '/menu/CrispyBurger.jpg' },
  { id: 4, name: 'Monulibra', description: 'Ingredientes: Carne, cheddar, cebolla en cubos, ketchup, mostaza.', variants: [{name: 'Simple', price: 13000}, {name: 'Doble', price: 15500}, {name: 'Triple', price: 17500}], category: 'Nuestras Burgers', image: '/menu/MonuLibraBurgerjpg.jpg' },
  { id: 5, name: 'Monuburger', description: 'Ingredientes: Carne, cheddar, cebolla caramelizada, bacon, huevo, barbacoa.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Nuestras Burgers', image: '/menu/MonuBurger.jpg' },
  { id: 6, name: 'La Típica', description: 'Ingredientes: Carne, cheddar, lechuga, tomate, mayonesa.', variants: [{name: 'Simple', price: 12500}, {name: 'Doble', price: 15000}, {name: 'Triple', price: 17000}], category: 'Nuestras Burgers', image: '/menu/LaTipicaBurger.jpg' },
  { id: 7, name: 'Witcher', description: 'Ingredientes: Carne, cheddar, bacon, tomate, lechuga, cebolla, pepinillos, mayonesa, ketchup.', variants: [{name: 'Simple', price: 13500}, {name: 'Doble', price: 16000}, {name: 'Triple', price: 18000}], category: 'Nuestras Burgers', image: '/menu/WitcherBurger.jpg' },
  { id: 8, name: '18 Supermash', description: 'Ingredientes: Carne smasheada, cheddar, panceta, pepinillo, salsa smash.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Nuestras Burgers', image: '/menu/18supersmash.jpg' },
  { id: 9, name: 'Oklahoma', description: 'Ingredientes: Carne smasheada con cebolla cruda, cheddar, salsa monu.', variants: [{name: 'Simple', price: 13500}, {name: 'Doble', price: 16000}, {name: 'Triple', price: 18000}], category: 'Nuestras Burgers', image: '/menu/oklahomaBurger.jpg' },
  { id: 10, name: 'Provoteca', description: 'Ingredientes: Carne, provoleta, cebolla caramelizada, rúcula, alioli.', variants: [{name: 'Simple', price: 12500}, {name: 'Doble', price: 15000}, {name: 'Triple', price: 17000}], category: 'Nuestras Burgers', image: '/menu/ProvotecaBurger.jpg' },
  { id: 11, name: 'Big Monu', description: 'Ingredientes: Carne, cheddar, cebolla, lechuga, pepinillos, salsa monu.', variants: [{name: 'Simple', price: 13000}, {name: 'Doble', price: 15500}, {name: 'Triple', price: 17500}], category: 'Nuestras Burgers', image: '/menu/BigMonuBurger.jpg' },
  { id: 12, name: 'Not Monu', description: 'Ingredientes: Medallón NotCo, cheddar, mayonesa, tomate y lechuga.', variants: [{name: 'Simple', price: 13500}, {name: 'Doble', price: 16000}, {name: 'Triple', price: 18000}], category: 'Nuestras Burgers', image: '/menu/notMonu.jpg' },
  { id: 13, name: 'Nueva Jersey', description: 'Ingredientes: Carne, cheddar, bacon en cubos tiernizado y mayonesa ahumada.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Nuestras Burgers', image: null },

  // MONUFUSIÓN
  { id: 14, name: 'Baconhoma', description: 'Ingredientes: Carne smasheada con cebolla cruda, cheddar, bacon, salsa monu.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Monufusión', image: null },
  { id: 15, name: 'Tipiteca', description: 'Ingredientes: Carne, provoleta, tomate, rúcula, mayonesa.', variants: [{name: 'Simple', price: 12500}, {name: 'Doble', price: 15000}, {name: 'Triple', price: 17000}], category: 'Monufusión', image: null },

  // OPCIONES INDIVIDUALES
  { id: 16, name: 'Keco', description: 'Ingredientes: Una carne smasheada, cheddar, cebolla crispy y alioli. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },
  { id: 17, name: 'Cito', description: 'Ingredientes: Un medallón de carne, cheddar, cebolla en cubos, ketchup, mostaza, bacon. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },
  { id: 18, name: 'Tino Andino', description: 'Ingredientes: Un medallón de carne, provoleta en medallón, cheddar en pan y mayonesa. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },
  { id: 19, name: 'Santi', description: 'Ingredientes: Un medallón de carne, cheddar, cebolla crispy, lechuga y alioli. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },

  // COMBOS
  { id: 20, name: 'Combo: Típica + Bacon', description: 'La Típica doble + Bacon simple + 1 Porción de Papas', price: 23000, category: 'Combos', image: null },
  { id: 21, name: 'Combo: Bacon + Típica', description: 'Bacon doble + La Típica simple + 1 Porción de Papas', price: 23000, category: 'Combos', image: null },
  { id: 22, name: 'Combo: Nuggets + Papas', description: 'Nuggets + Papas Fritas', price: 15000, category: 'Combos', image: '/menu/nuggetsmonu.jpg' },

  // ACOMPAÑAMIENTOS
  { id: 23, name: 'Papas Fritas (Porción)', description: 'Porción de papas fritas.', price: 8000, category: 'Acompañamientos', image: '/menu/papasfritasMonu.jpg' },
  { id: 24, name: 'Nuggets', description: '10 unidades. Incluye 2 dips (salsa monu y barbacoa)', price: 11000, category: 'Acompañamientos', image: '/menu/nuggetsmonu.jpg' },

  // BEBIDAS
  { id: 25, name: 'Coca Cola', description: '500ml', price: 2200, category: 'Bebidas', image: '/menu/cocacolamonu.jpg' },
  { id: 26, name: 'Sprite', description: '500ml', price: 2200, category: 'Bebidas', image: '/menu/sprite.jpg' },
  { id: 27, name: 'Fanta', description: '500ml', price: 2200, category: 'Bebidas', image: '/menu/fantamonu.jpg' },

  // DIPS EXTRA
  { id: 28, name: 'Salsa Monu', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
  { id: 29, name: 'Alioli', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
  { id: 30, name: 'Barbacoa', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
  { id: 31, name: 'Mayonesa', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
  { id: 32, name: 'Ketchup', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
  { id: 33, name: 'Mostaza', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
];

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
        id: `${product.id}-${variant.name}`,
        name: `${product.name} (${variant.name})`,
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
      </div>
      <div className="px-2 flex flex-col flex-1">
        <h3 className="font-extrabold text-monu-dark text-lg leading-tight mb-1">{product.name}</h3>
        <p className="text-xs text-monu-text/70 mb-4 flex-1">{product.description}</p>
        
        {hasVariants && (
          <select 
            className="w-full bg-monu-bone border border-monu-green/20 rounded-lg px-2 py-1.5 text-sm font-bold text-monu-dark mb-3 focus:outline-none focus:border-monu-orange cursor-pointer"
            value={selectedVariantIndex}
            onChange={(e) => setSelectedVariantIndex(parseInt(e.target.value))}
          >
            {product.variants.map((v, i) => (
              <option key={i} value={i}>{v.name} - ${v.price.toLocaleString()}</option>
            ))}
          </select>
        )}

        <div className="flex items-center justify-between mt-auto">
          <span className="font-extrabold text-xl text-monu-burnt">
            ${currentPrice.toLocaleString()}
          </span>
          <button 
            onClick={handleAdd}
            className="bg-monu-cream text-monu-green hover:bg-monu-green hover:text-white p-3 rounded-xl transition shadow-sm"
            title="Agregar al carrito"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Menu() {
  const { dispatch } = useData();
  const [searchParams] = useSearchParams();
  const searchQuery = searchParams.get('q')?.toLowerCase() || '';
  const [activeCategory, setActiveCategory] = useState('Todas');

  const addToCart = (product) => {
    dispatch({ type: 'ADD_TO_CART', payload: { ...product, quantity: 1 } });
  };

  const filteredProducts = PRODUCTS.filter(product => {
    const matchesSearch = product.name.toLowerCase().includes(searchQuery) || product.description.toLowerCase().includes(searchQuery);
    const matchesCategory = activeCategory === 'Todas' || product.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="space-y-8">
      {/* Promo Banner */}
      <div className="bg-monu-green text-white rounded-3xl p-8 relative overflow-hidden shadow-monu-lg">
        <div className="relative z-10 max-w-lg">
          <span className="inline-block bg-monu-yellow text-monu-dark font-extrabold px-3 py-1 rounded-full text-sm mb-4">
            🔥 NUEVA PROMO
          </span>
          <h2 className="text-4xl md:text-5xl font-extrabold font-heading mb-4">Combo Monu XL</h2>
          <p className="text-lg opacity-90 mb-6 font-medium">Llevate una Doble Cheddar + Papas + Gaseosa grande a un precio increíble.</p>
          <button className="bg-white text-monu-green hover:bg-monu-cream px-6 py-3 rounded-xl font-bold transition">
            Pedir ahora $14.500
          </button>
        </div>
        <img 
          src="/menu/BigMonuBurger.jpg" 
          alt="Promo Burger" 
          className="absolute -right-20 top-1/2 -translate-y-1/2 w-96 h-96 object-cover rounded-full border-8 border-white/10 hidden md:block"
        />
      </div>

      {/* Categories */}
      <div className="flex gap-3 overflow-x-auto pb-4 no-scrollbar">
        {CATEGORIES.map((cat, i) => (
          <button 
            key={i} 
            onClick={() => setActiveCategory(cat)}
            className={`whitespace-nowrap px-6 py-2.5 rounded-full font-bold transition ${
              activeCategory === cat
                ? 'bg-monu-dark text-white shadow-md' 
                : 'bg-white text-monu-text hover:bg-monu-green/10 border border-monu-green/10'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Product Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {filteredProducts.length === 0 ? (
          <div className="col-span-full py-20 text-center text-monu-text/60">
             <span className="text-4xl mb-4 block">🧐</span>
             <p className="text-lg">No encontramos productos que coincidan con tu búsqueda.</p>
          </div>
        ) : (
          filteredProducts.map(product => (
            <ProductCard key={product.id} product={product} addToCart={addToCart} />
          ))
        )}
      </div>
    </div>
  );
}
