import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { useAuth } from './auth/AuthContext';
import { portal } from './shared/portal';

// Layouts
import ClientLayout from './ordering/ClientLayout';
import Menu from './ordering/Menu';

const DashboardLayout = lazy(() => import('./management/DashboardLayout'));
const Login = lazy(() => import('./auth/Login'));
const ControlPanel = lazy(() => import('./management/ControlPanel'));
const Customers = lazy(() => import('./management/Customers'));
const Analytics = lazy(() => import('./management/Analytics'));
const AccessControl = lazy(() => import('./management/AccessControl'));

const Orders = lazy(() => import('./fulfillment/Orders'));
const DeliveryPanel = lazy(() => import('./fulfillment/DeliveryPanel'));

const Kitchen = lazy(() => import('./kitchen/Kitchen'));
const Catalog = lazy(() => import('./management/Catalog'));
const Inventory = lazy(() => import('./inventory/Inventory'));

function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen bg-monu-cream" aria-busy="true" />;
  
  if (!user) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    // If not authorized, send them to their role's default page
    if (user.role === 'admin') return <Navigate to="/dashboard" replace />;
    if (user.role === 'repartidor') return <Navigate to="/delivery" replace />;
    return <Navigate to="/menu" replace />;
  }
  
  return children;
}

function App() {
  return (
    <Suspense fallback={<div role="status" className="min-h-screen bg-monu-cream p-6">Cargando...</div>}>
      <Routes>
        <Route path="/" element={<Navigate to={portal.inicio} replace />} />
        {portal.personal && <>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Navigate to="/login" replace />} />
          <Route path="/recover-password" element={<Navigate to="/login" replace />} />
        </>}

        {portal.clientes && <Route element={<ClientLayout />}>
          <Route path="/menu" element={<Menu />} />
        </Route>}

        {portal.personal && <Route element={<ProtectedRoute allowedRoles={['admin']}><DashboardLayout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<ControlPanel />} />
          <Route path="/dashboard/orders" element={<Orders />} />
          <Route path="/dashboard/kitchen" element={<Kitchen />} />
          <Route path="/dashboard/catalog" element={<Catalog />} />
          <Route path="/dashboard/customers" element={<Customers />} />
          <Route path="/dashboard/inventory" element={<Inventory />} />
          <Route path="/dashboard/analytics" element={<Analytics />} />
          <Route path="/dashboard/access" element={<AccessControl />} />
        </Route>}

        {portal.personal && <Route path="/delivery" element={
          <ProtectedRoute allowedRoles={['repartidor', 'admin']}>
            <DeliveryPanel />
          </ProtectedRoute>
        } />}
        <Route path="*" element={<Navigate to={portal.inicio} replace />} />
      </Routes>
    </Suspense>
  );
}

export default App;
