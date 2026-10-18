import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { useAuth } from './auth/AuthContext';
import { portal } from './shared/portal';
import { pageLoaders } from './shared/pageLoaders';

// Layouts
import ClientLayout from './ordering/ClientLayout';
import Menu from './ordering/Menu';
import OrderOperationFeedback from './fulfillment/OrderOperationFeedback';

const DashboardLayout = lazy(pageLoaders.layout);
const Login = lazy(pageLoaders['/login']);
const ControlPanel = lazy(pageLoaders['/dashboard']);
const Customers = lazy(pageLoaders['/dashboard/customers']);
const Analytics = lazy(pageLoaders['/dashboard/analytics']);
const AccessControl = lazy(pageLoaders['/dashboard/access']);

const Orders = lazy(pageLoaders['/dashboard/orders']);
const DeliveryPanel = lazy(pageLoaders['/delivery']);

const Kitchen = lazy(pageLoaders['/dashboard/kitchen']);
const Catalog = lazy(pageLoaders['/dashboard/catalog']);
const Inventory = lazy(pageLoaders['/dashboard/inventory']);

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
    <><OrderOperationFeedback /><Suspense fallback={<div role="status" className="min-h-screen bg-monu-cream p-6">Cargando...</div>}>
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
    </Suspense></>
  );
}

export default App;
