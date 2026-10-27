// Las rutas y la precarga del menú comparten los mismos módulos.
export const pageLoaders = {
  layout: () => import('../management/DashboardLayout'),
  '/login': () => import('../auth/Login'),
  '/dashboard': () => import('../management/ControlPanel'),
  '/dashboard/customers': () => import('../management/Customers'),
  '/dashboard/analytics': () => import('../management/Analytics'),
  '/dashboard/access': () => import('../management/AccessControl'),
  '/dashboard/orders': () => import('../fulfillment/Orders'),
  '/delivery': () => import('../fulfillment/DeliveryPanel'),
  '/dashboard/kitchen': () => import('../kitchen/Kitchen'),
  '/dashboard/catalog': () => import('../management/Catalog'),
  '/dashboard/inventory': () => import('../inventory/Inventory'),
  '/dashboard/caja': () => import('../cash/Caja'),
};

export function preloadPage(path) {
  void pageLoaders[path]?.().catch(() => undefined);
}
