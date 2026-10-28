// Enrutador principal de la aplicación: define qué pantallas existen según el
// portal activo (clientes o personal) y protege las rutas del panel por rol y permiso.
// Las pantallas pesadas se cargan de forma diferida (lazy) para aligerar el primer render.
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

// Pantallas cargadas bajo demanda: cada una se descarga recién cuando se visita su ruta.
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
const Caja = lazy(pageLoaders['/dashboard/caja']);


/**
 * Componente raíz de rutas. Monta el aviso global de operaciones de pedidos y
 * resuelve las rutas públicas (menú), de acceso (login) y del panel del personal.
 */
function App() {
  return (
    <><OrderOperationFeedback /><Suspense fallback={<div role="status" className="min-h-screen bg-monu-cream p-6">Cargando...</div>}>
      {/* Mientras se descarga una pantalla diferida se muestra el estado "Cargando..." */}
      <Routes>
        {/* La raíz redirige a la pantalla de inicio que corresponde al portal (menú o login) */}
        <Route path="/" element={<Navigate to={portal.inicio} replace />} />
        {/* Acceso del personal: registro y recuperación no existen y redirigen al login */}
        {portal.personal && <>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Navigate to="/login" replace />} />
          <Route path="/recover-password" element={<Navigate to="/login" replace />} />
        </>}

        {/* Portal de clientes: menú y carrito dentro del layout público */}
        {portal.clientes && <Route element={<ClientLayout />}>
          <Route path="/menu" element={<Menu />} />
        </Route>}

        {/* Panel del personal: cada sección exige además el permiso de su ruta */}
        {portal.personal && <Route element={<ProtectedRoute allowedRoles={[...STAFF_ROLES, 'REPARTIDOR']}><DashboardLayout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<ProtectedRoute path="/dashboard"><ControlPanel /></ProtectedRoute>} />
          <Route path="/dashboard/orders" element={<ProtectedRoute path="/dashboard/orders"><Orders /></ProtectedRoute>} />
          <Route path="/dashboard/kitchen" element={<ProtectedRoute path="/dashboard/kitchen"><Kitchen /></ProtectedRoute>} />
          <Route path="/dashboard/catalog" element={<ProtectedRoute path="/dashboard/catalog"><Catalog /></ProtectedRoute>} />
          <Route path="/dashboard/customers" element={<ProtectedRoute path="/dashboard/customers"><Customers /></ProtectedRoute>} />
          <Route path="/dashboard/inventory" element={<ProtectedRoute path="/dashboard/inventory"><Inventory /></ProtectedRoute>} />
          <Route path="/dashboard/caja" element={<ProtectedRoute path="/dashboard/caja"><Caja /></ProtectedRoute>} />
          <Route path="/dashboard/analytics" element={<ProtectedRoute path="/dashboard/analytics"><Analytics /></ProtectedRoute>} />
          <Route path="/dashboard/access" element={<ProtectedRoute path="/dashboard/access"><AccessControl /></ProtectedRoute>} />
        </Route>}

        {/* Panel de reparto para repartidores (y personal con permiso de delivery) */}
        {portal.personal && <Route path="/delivery" element={
          <ProtectedRoute allowedRoles={['REPARTIDOR', ...STAFF_ROLES]} path="/delivery">
            <DeliveryPanel />
          </ProtectedRoute>
        } />}
        {/* Cualquier ruta desconocida vuelve al inicio del portal */}
        <Route path="*" element={<Navigate to={portal.inicio} replace />} />
      </Routes>
    </Suspense></>
  );
}

export default App;
