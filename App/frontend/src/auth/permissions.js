// Reglas de permisos del frontend: qué permiso exige cada ruta del panel y cuál es
// la pantalla inicial de cada usuario. El servidor es quien autoriza de verdad;
// esto solo decide qué mostrar.
export const STAFF_ROLES = ['ADMINISTRADOR', 'DUENIO', 'EMPLEADO'];
// Indica si el usuario tiene el permiso; el administrador los tiene todos.
export function can(user, permission) {
  return Boolean(user && (user.backendRole === 'ADMINISTRADOR' || user.permisos?.includes(permission)));
}
// Permiso necesario para visitar cada ruta del panel (también define el orden de inicio).
export const ROUTE_PERMISSIONS = {
  '/dashboard': 'reportes.ver',
  '/dashboard/orders': 'pedidos.ver',
  '/dashboard/kitchen': 'pedidos.ver',
  '/dashboard/catalog': 'productos.gestionar',
  '/dashboard/customers': 'clientes.ver',
  '/dashboard/inventory': 'stock.ver',
  '/dashboard/caja': 'caja.ver',
  '/dashboard/analytics': 'reportes.ver',
  '/delivery': 'delivery.ver',
};
// Decide si el usuario puede entrar a una ruta, con excepciones para catálogo y accesos.
export function canVisit(user, path) {
  if (path === '/dashboard/catalog') return can(user, 'productos.gestionar') || can(user, 'productos.ver_receta');
  if (path === '/dashboard/access') return user?.backendRole === 'ADMINISTRADOR';
  return can(user, ROUTE_PERMISSIONS[path]);
}
// Pantalla de inicio tras el login: repartidores al delivery, clientes al menú y
// el resto a la primera sección del panel que puedan ver.
export function homeFor(user) {
  if (user?.backendRole === 'REPARTIDOR' && canVisit(user, '/delivery')) return '/delivery';
  if (user?.backendRole === 'CLIENTE') return '/menu';
  return Object.keys(ROUTE_PERMISSIONS).find((path) => canVisit(user, path)) || '/dashboard';
}
