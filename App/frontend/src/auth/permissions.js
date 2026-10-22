export const STAFF_ROLES = ['ADMINISTRADOR', 'DUENIO', 'EMPLEADO'];
export function can(user, permission) {
  return Boolean(user && (user.backendRole === 'ADMINISTRADOR' || user.permisos?.includes(permission)));
}
export const ROUTE_PERMISSIONS = {
  '/dashboard': 'reportes.ver',
  '/dashboard/orders': 'pedidos.ver',
  '/dashboard/kitchen': 'pedidos.ver',
  '/dashboard/catalog': 'productos.gestionar',
  '/dashboard/customers': 'clientes.ver',
  '/dashboard/inventory': 'stock.ver',
  '/dashboard/analytics': 'reportes.ver',
  '/delivery': 'delivery.ver',
};
export function canVisit(user, path) {
  if (path === '/dashboard/catalog') return can(user, 'productos.gestionar') || can(user, 'productos.ver_receta');
  if (path === '/dashboard/access') return user?.backendRole === 'ADMINISTRADOR';
  return can(user, ROUTE_PERMISSIONS[path]);
}
export function homeFor(user) {
  if (user?.backendRole === 'REPARTIDOR' && canVisit(user, '/delivery')) return '/delivery';
  if (user?.backendRole === 'CLIENTE') return '/menu';
  return Object.keys(ROUTE_PERMISSIONS).find((path) => canVisit(user, path)) || '/dashboard';
}
