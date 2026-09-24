import { Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
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
  Menu as MenuIcon
} from 'lucide-react';
import { useState } from 'react';

export default function DashboardLayout() {
  const { logout, user } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Panel de Control', end: true },
    { to: '/dashboard/orders', icon: ListOrdered, label: 'Pedidos' },
    { to: '/dashboard/kitchen', icon: ChefHat, label: 'Cocina / KDS' },
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
          <span className="text-3xl">🍔</span>
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
            className="flex items-center gap-3 px-4 py-3 w-full rounded-xl text-monu-text font-bold hover:bg-red-50 hover:text-red-600 transition"
          >
            <LogOut className="w-5 h-5" />
            Cerrar Sesión
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 md:ml-64 flex flex-col min-h-screen">
        {/* Navbar */}
        <header className="bg-monu-cream/80 backdrop-blur-md sticky top-0 z-10 p-4 md:p-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button 
              className="md:hidden p-2 bg-monu-bone rounded-xl shadow-sm"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            >
              <MenuIcon className="w-6 h-6 text-monu-dark" />
            </button>
            <div className="hidden md:flex relative w-96">
              <input 
                type="text" 
                placeholder="Buscar..." 
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-monu-green/20 bg-monu-bone text-sm focus:outline-none focus:border-monu-green"
              />
              <Search className="absolute left-3 top-2.5 w-5 h-5 text-monu-text/50" />
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <button className="relative p-2 bg-monu-bone rounded-xl shadow-sm hover:bg-white transition">
              <Bell className="w-5 h-5 text-monu-dark" />
              <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-monu-orange rounded-full border-2 border-monu-bone"></span>
            </button>
            <div className="flex items-center gap-3 bg-monu-bone px-3 py-1.5 rounded-xl shadow-sm cursor-pointer hover:bg-white transition">
              <div className="w-8 h-8 rounded-full bg-monu-green text-white flex items-center justify-center font-bold text-sm">
                {user?.name?.charAt(0) || 'A'}
              </div>
              <div className="hidden md:block text-sm">
                <p className="font-bold text-monu-dark">{user?.name}</p>
                <p className="text-xs text-monu-text/70 capitalize">{user?.role}</p>
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>

      {/* Mobile Drawer */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 md:hidden" onClick={() => setIsMobileMenuOpen(false)}>
          <aside className="w-64 bg-monu-bone h-full shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="p-6 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-2xl">🍔</span>
                <span className="text-lg font-extrabold font-heading text-monu-dark">Monu Burger</span>
              </div>
              <button onClick={() => setIsMobileMenuOpen(false)} className="text-2xl font-bold p-2">×</button>
            </div>
            <nav className="flex-1 px-4 space-y-2 overflow-y-auto">
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
                className="flex items-center gap-3 px-4 py-3 w-full rounded-xl text-monu-text font-bold hover:bg-red-50 hover:text-red-600 transition"
              >
                <LogOut className="w-5 h-5" />
                Cerrar Sesión
              </button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
