import { Outlet, Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { ShoppingCart, Search, LogOut } from 'lucide-react';
import CartDrawer from '../components/client/CartDrawer';
import { useState } from 'react';

export default function ClientLayout() {
  const { logout, user } = useAuth();
  const { state } = useData();
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const searchQuery = searchParams.get('q') || '';

  const handleSearch = (e) => {
    if (e.target.value) {
      setSearchParams({ q: e.target.value });
    } else {
      setSearchParams({});
    }
  };

  return (
    <div className="min-h-screen bg-monu-cream font-sans text-monu-text">
      {/* Header */}
      <header className="bg-monu-dark text-white shadow-md p-4 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-3xl">🍔</span>
            <Link to="/menu" className="text-2xl font-extrabold tracking-tight font-heading">
              Monu Burger
            </Link>
          </div>
          <div className="flex items-center gap-3 w-full md:w-auto">
            <div className="relative flex-1 md:w-64">
              <input 
                type="text" 
                value={searchQuery}
                onChange={handleSearch}
                placeholder="Buscar hamburguesas..." 
                className="w-full pl-9 pr-3 py-2 rounded-xl text-sm text-monu-text bg-monu-bone placeholder-monu-text/50 focus:outline-none focus:ring-2 focus:ring-monu-orange"
              />
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-monu-text/50" />
            </div>
            <button 
              onClick={() => setIsCartOpen(true)}
              className="bg-monu-orange hover:bg-monu-burnt text-white px-4 py-2 rounded-xl font-bold text-sm flex items-center gap-2 transition shadow-sm"
            >
              <ShoppingCart className="w-4 h-4" />
              <span>Carrito</span>
              {state.cart.length > 0 && (
                <span className="bg-white text-monu-orange font-extrabold text-xs px-2 py-0.5 rounded-full">
                  {state.cart.length}
                </span>
              )}
            </button>
            <button onClick={logout} className="p-2 hover:bg-white/10 rounded-xl transition" title="Cerrar sesión">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-4 md:p-6">
        <Outlet />
      </main>

      {/* Cart Drawer */}
      <CartDrawer isOpen={isCartOpen} onClose={() => setIsCartOpen(false)} />
    </div>
  );
}
