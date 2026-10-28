// Configuración del portal desplegado (VITE_PORTAL): solo clientes (menú), solo
// personal (panel) o completo, y qué roles pueden iniciar sesión en cada uno.
const ROLES_PERSONAL = ['EMPLEADO', 'ADMINISTRADOR', 'DUENIO', 'REPARTIDOR'];

// Describe qué partes de la app están activas para el modo y cuál es la ruta de inicio.
export function resolverPortal(modo = 'completo') {
  if (!['clientes', 'personal', 'completo'].includes(modo)) {
    throw new Error(`Portal inválido: ${modo}. Usá clientes, personal o completo.`);
  }
  return {
    modo,
    clientes: modo !== 'personal',
    personal: modo !== 'clientes',
    inicio: modo === 'personal' ? '/dashboard' : '/menu',
  };
}

// Indica si un rol puede usar la sesión en este portal (el portal de clientes no admite sesiones).
export function aceptaSesion(rol, modo) {
  if (modo === 'clientes') return false;
  return ROLES_PERSONAL.includes(rol) || (modo === 'completo' && rol === 'CLIENTE');
}

// Portal activo según la variable de entorno.
export const portal = resolverPortal(import.meta.env?.VITE_PORTAL || 'completo');
