const ROLES_PERSONAL = ['EMPLEADO', 'ADMINISTRADOR', 'DUENIO', 'REPARTIDOR'];

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

export function aceptaSesion(rol, modo) {
  if (modo === 'clientes') return false;
  return ROLES_PERSONAL.includes(rol) || (modo === 'completo' && rol === 'CLIENTE');
}

export const portal = resolverPortal(import.meta.env?.VITE_PORTAL || 'completo');
