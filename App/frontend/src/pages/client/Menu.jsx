import { Plus } from 'lucide-react';
import { useData } from '../../context/DataContext';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';

const PRODUCTS = [
  {
    id: 1,
    name: 'Monu Clásica',
    description: 'Medallón 180g, cheddar, lechuga, tomate y salsa especial.',
    price: 8500,
    category: 'Hamburguesas',
    image: 'https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&q=80&w=800'
  },
  {
    id: 2,
    name: 'Doble Cheddar & Bacon',
    description: 'Doble medallón, cuádruple cheddar, bacon crujiente y cebolla crispy.',
    price: 11200,
    category: 'Hamburguesas',
    image: 'https://images.unsplash.com/photo-1553979459-d2229ba7433b?auto=format&fit=crop&q=80&w=800'
  },
  {
    id: 3,
    name: 'Smash Onion',
    description: 'Doble smash, cebolla planchada, queso emmental y mayo provenzal.',
    price: 9800,
    category: 'Hamburguesas',
    image: 'https://images.unsplash.com/photo-1625813506062-0aeb1d7a094b?auto=format&fit=crop&q=80&w=800'
  },
  {
    id: 4,
    name: 'Veggie Monu',
    description: 'Medallón NotCo, queso vegano, rúcula y tomate confitado.',
    price: 9000,
    category: 'Vegetariano',
    image: 'https://images.unsplash.com/photo-1520072959219-c595dc870360?auto=format&fit=crop&q=80&w=800'
  },
  {
    id: 5,
    name: 'Papas Monu',
    description: 'Papas fritas con cheddar fundido, bacon y verdeo.',
    price: 4500,
    category: 'Acompañamientos',
    image: 'https://images.unsplash.com/photo-1576107232684-1279f390859f?auto=format&fit=crop&q=80&w=800'
  }
];

const CATEGORIES = ['Todas', 'Promos', 'Hamburguesas', 'Acompañamientos', 'Bebidas', 'Vegetariano'];

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
          src="https://images.unsplash.com/photo-1550547660-d9450f859349?auto=format&fit=crop&q=80&w=800" 
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
             <span className="text-4xl mb-4 block">🔍</span>
             <p className="text-lg">No encontramos productos que coincidan con tu búsqueda.</p>
          </div>
        ) : (
          filteredProducts.map(product => (
          <div key={product.id} className="bg-white rounded-[2rem] p-4 border border-monu-green/5 shadow-sm hover:shadow-monu-lg transition-all group">
            <div className="relative aspect-[4/3] rounded-2xl overflow-hidden mb-4">
              <img 
                src={product.image} 
                alt={product.name}
                className="w-full h-full object-cover group-hover:scale-105 transition duration-500"
              />
            </div>
            <div className="px-2">
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-extrabold text-monu-dark text-lg leading-tight">{product.name}</h3>
              </div>
              <p className="text-sm text-monu-text/70 mb-4 line-clamp-2 min-h-[40px]">{product.description}</p>
              <div className="flex items-center justify-between mt-auto">
                <span className="font-extrabold text-xl text-monu-burnt">${product.price.toLocaleString()}</span>
                <button 
                  onClick={() => addToCart(product)}
                  className="bg-monu-cream text-monu-green hover:bg-monu-green hover:text-white p-3 rounded-xl transition shadow-sm"
                  title="Agregar al carrito"
                >
                  <Plus className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
          ))
        )}
      </div>
    </div>
  );
}
