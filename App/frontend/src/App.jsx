import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';

// Layouts
import ClientLayout from './layouts/ClientLayout';
import DashboardLayout from './layouts/DashboardLayout';

// Pages
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import RecoverPassword from './pages/auth/RecoverPassword';
import Menu from './pages/client/Menu';
import ControlPanel from './pages/dashboard/ControlPanel';
import Orders from './pages/dashboard/Orders';
import Kitchen from './pages/dashboard/Kitchen';
import Customers from './pages/dashboard/Customers';
import Inventory from './pages/dashboard/Inventory';
import Analytics from './pages/dashboard/Analytics';
import AccessControl from './pages/dashboard/AccessControl';
import DeliveryPanel from './pages/delivery/DeliveryPanel';

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
