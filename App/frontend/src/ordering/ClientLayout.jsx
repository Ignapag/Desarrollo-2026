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
            <img src="/favicon.png" className="w-8 h-8 object-contain" alt="Logo" />
            <div className="flex flex-col">
              <Link to="/menu" className="text-2xl font-extrabold tracking-tight font-heading leading-none mb-1">
                Monu Burger
              </Link>
              <span className="text-[11px] font-bold text-white/80 flex items-center gap-1 bg-white/10 px-2 py-0.5 rounded-full w-max">
                🕒 Todos los días de 19:30 a 00:00
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3 w-full md:w-auto">
            <div className="relative flex-1 md:w-64">
              <input 
                type="text" 
                value={searchQuery}
                onChange={handleSearch}
                placeholder="Buscar hamburguesas..." 
                className="w-full bg-white/10 border border-white/20 rounded-full py-2 pl-10 pr-4 text-white placeholder:text-white/50 focus:outline-none focus:border-monu-green transition-colors"
              />
              <Search className="w-5 h-5 absolute left-3 top-2.5 text-white/50" />
            </div>
            
            <button 
              onClick={() => setIsCartOpen(true)}
              className="relative p-2 hover:bg-white/10 rounded-full transition-colors flex-shrink-0"
            >
              <ShoppingCart className="w-6 h-6" />
              {state.cart.length > 0 && (
                <span className="absolute -top-1 -right-1 bg-monu-orange text-white text-xs font-bold w-5 h-5 flex items-center justify-center rounded-full">
                  {state.cart.length}
                </span>
              )}
            </button>

            {user && (
              <div className="flex items-center gap-3 pl-3 border-l border-white/20 ml-1">
                <span className="hidden sm:inline text-sm font-bold opacity-80">{user.name}</span>
                <button onClick={logout} className="p-2 hover:bg-white/10 rounded-full transition-colors text-red-400" title="Cerrar sesión">
                  <LogOut className="w-5 h-5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-4 py-8">
        <Outlet />
      </main>

      <CartDrawer isOpen={isCartOpen} onClose={() => setIsCartOpen(false)} />
    </div>
  );
}