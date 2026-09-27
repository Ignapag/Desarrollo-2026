import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';

// Layouts
import ClientLayout from './ordering/ClientLayout';
import DashboardLayout from './management/DashboardLayout';

// Features
import Login from './auth/Login';
import Register from './auth/Register';
import RecoverPassword from './auth/RecoverPassword';
import Menu from './ordering/Menu';

import ControlPanel from './management/ControlPanel';
import Customers from './management/Customers';
import Analytics from './management/Analytics';
import AccessControl from './management/AccessControl';

import Orders from './fulfillment/Orders';
import DeliveryPanel from './fulfillment/DeliveryPanel';

import Kitchen from './kitchen/Kitchen';
import Catalog from './management/Catalog';
import Inventory from './inventory/Inventory';

function ProtectedRoute({ children, allowedRoles }) {
  const { user } = useAuth();
  
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
    <Routes>
      {/* Public / Auth */}
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/recover-password" element={<RecoverPassword />} />

      {/* Client Routes */}
      <Route element={<ProtectedRoute allowedRoles={['cliente', 'admin']}><ClientLayout /></ProtectedRoute>}>
        <Route path="/menu" element={<Menu />} />
      </Route>

      {/* Dashboard Routes (Admin/Employee) */}
      <Route element={<ProtectedRoute allowedRoles={['admin']}><DashboardLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<ControlPanel />} />
        <Route path="/dashboard/orders" element={<Orders />} />
        <Route path="/dashboard/kitchen" element={<Kitchen />} />
        <Route path="/dashboard/catalog" element={<Catalog />} />
        <Route path="/dashboard/customers" element={<Customers />} />
        <Route path="/dashboard/inventory" element={<Inventory />} />
        <Route path="/dashboard/analytics" element={<Analytics />} />
        <Route path="/dashboard/access" element={<AccessControl />} />
      </Route>

      {/* Delivery Route */}
      <Route path="/delivery" element={
        <ProtectedRoute allowedRoles={['repartidor', 'admin']}>
          <DeliveryPanel />
        </ProtectedRoute>
      } />
    </Routes>
  );
}

export default App;
