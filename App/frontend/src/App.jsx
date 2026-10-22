import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import ProtectedRoute from './auth/ProtectedRoute';
import { STAFF_ROLES } from './auth/permissions';
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

        {portal.personal && <Route element={<ProtectedRoute allowedRoles={[...STAFF_ROLES, 'REPARTIDOR']}><DashboardLayout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<ProtectedRoute path="/dashboard"><ControlPanel /></ProtectedRoute>} />
          <Route path="/dashboard/orders" element={<ProtectedRoute path="/dashboard/orders"><Orders /></ProtectedRoute>} />
          <Route path="/dashboard/kitchen" element={<ProtectedRoute path="/dashboard/kitchen"><Kitchen /></ProtectedRoute>} />
          <Route path="/dashboard/catalog" element={<ProtectedRoute path="/dashboard/catalog"><Catalog /></ProtectedRoute>} />
          <Route path="/dashboard/customers" element={<ProtectedRoute path="/dashboard/customers"><Customers /></ProtectedRoute>} />
          <Route path="/dashboard/inventory" element={<ProtectedRoute path="/dashboard/inventory"><Inventory /></ProtectedRoute>} />
          <Route path="/dashboard/analytics" element={<ProtectedRoute path="/dashboard/analytics"><Analytics /></ProtectedRoute>} />
          <Route path="/dashboard/access" element={<ProtectedRoute path="/dashboard/access"><AccessControl /></ProtectedRoute>} />
        </Route>}

        {portal.personal && <Route path="/delivery" element={
          <ProtectedRoute allowedRoles={['REPARTIDOR', ...STAFF_ROLES]} path="/delivery">
            <DeliveryPanel />
          </ProtectedRoute>
        } />}
        <Route path="*" element={<Navigate to={portal.inicio} replace />} />
      </Routes>
    </Suspense></>
  );
}

export default App;
