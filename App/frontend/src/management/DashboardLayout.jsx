import { Outlet, NavLink, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { 
  LayoutDashboard, 
  ListOrdered, 
  ChefHat,
  Users, 
  Package, 
  BarChart2, 
  ShieldCheck,
  LogOut,
  Bell,
  Search,
  Menu as MenuIcon,
  Store
} from 'lucide-react';
import { useState } from 'react';

export default function DashboardLayout() {
  const { logout, user } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const searchQuery = searchParams.get('q') || '';
  
  const handleSearch = (e) => {
    if (e.target.value) {
      setSearchParams({ q: e.target.value });
    } else {
      setSearchParams({});
    }
  };

  const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Panel de Control', end: true },
    { to: '/dashboard/orders', icon: ListOrdered, label: 'Pedidos' },
    { to: '/dashboard/kitchen', icon: ChefHat, label: 'Cocina / KDS' },
    { to: '/dashboard/catalog', icon: Store, label: 'Menú / Catálogo' },
    { to: '/dashboard/customers', icon: Users, label: 'Clientes' },
    { to: '/dashboard/inventory', icon: Package, label: 'Inventario' },
    { to: '/dashboard/analytics', icon: BarChart2, label: 'Reportes' },
    { to: '/dashboard/access', icon: ShieldCheck, label: 'Control de Acceso' },
  ];

  return (
    <div className="min-h-screen bg-monu-cream font-sans flex text-monu-text">
      {/* Sidebar Desktop */}
      <aside className="hidden md:flex flex-col w-64 bg-monu-bone border-r border-monu-green/10 fixed h-full z-20">
        <div className="p-6 flex items-center gap-3">
          <img src="/favicon.png" className="w-8 h-8 object-contain" alt="Logo" />
          <span className="text-xl font-extrabold font-heading text-monu-dark">Monu Burger</span>
        </div>
        <nav className="flex-1 px-4 space-y-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl font-bold transition-colors ${
                  isActive 
                    ? 'bg-monu-green text-white shadow-md' 
                    : 'text-monu-text hover:bg-monu-cream'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-monu-green/10">
          <button 
            onClick={logout}
            className="flex items-center gap-3 px-4 py-3 w-full rounded-xl font-bold text-red-500 hover:bg-red-50 transition-colors"
          >
            <LogOut className="w-5 h-5" />
            Cerrar Sesión
          </button>
        </div>
      </aside>

      {/* Main Content Wrapper */}
      <div className="flex-1 flex flex-col md:ml-64 min-h-screen">
        {/* Header Mobile & Search */}
        <header className="bg-white border-b border-monu-green/10 h-16 flex items-center justify-between px-4 sticky top-0 z-10 shadow-sm">
          <div className="flex items-center gap-3 md:hidden">
            <button 
              onClick={() => setIsMobileMenuOpen(true)}
              className="p-2 -ml-2 text-monu-text hover:bg-monu-cream rounded-lg"
            >
              <MenuIcon className="w-6 h-6" />
            </button>
            <img src="/favicon.png" className="w-8 h-8 object-contain" alt="Logo" />
          </div>

          <div className="hidden md:flex items-center gap-2 flex-1 max-w-md">
            <div className="relative w-full">
              <input 
                type="text" 
                value={searchQuery}
                onChange={handleSearch}
                placeholder="Buscar (Pedidos, Clientes, Menú)..." 
                className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-full py-2 pl-10 pr-4 text-sm font-bold focus:outline-none focus:border-monu-green transition-colors"
              />
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-monu-text/50" />
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button className="relative p-2 text-monu-text hover:bg-monu-cream rounded-full transition-colors">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
            </button>
            <div className="flex items-center gap-3 pl-4 border-l border-monu-green/10">
              <div className="w-8 h-8 bg-monu-green text-white rounded-full flex items-center justify-center font-bold text-sm">
                A
              </div>
              <div className="hidden sm:block">
                <p className="text-sm font-bold text-monu-dark">{user?.name}</p>
                <p className="text-xs text-monu-text/60 capitalize">{user?.role}</p>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 p-4 md:p-8 bg-monu-cream/20">
          <Outlet />
        </main>
      </div>

      {/* Mobile Sidebar Overlay */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Sidebar */}
      <aside className={`fixed inset-y-0 left-0 w-64 bg-monu-bone shadow-2xl z-50 transform transition-transform duration-300 md:hidden flex flex-col ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/favicon.png" className="w-8 h-8 object-contain" alt="Logo" />
            <span className="text-lg font-extrabold font-heading text-monu-dark">Monu Burger</span>
          </div>
        </div>
        <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setIsMobileMenuOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl font-bold transition-colors ${
                  isActive 
                    ? 'bg-monu-green text-white shadow-md' 
                    : 'text-monu-text hover:bg-monu-cream'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-monu-green/10">
          <button 
            onClick={logout}
            className="flex items-center gap-3 px-4 py-3 w-full rounded-xl font-bold text-red-500 hover:bg-red-50 transition-colors"
          >
            <LogOut className="w-5 h-5" />
            Cerrar Sesión
          </button>
        </div>
      </aside>
    </div>
  );
}