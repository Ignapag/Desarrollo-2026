// Comprueba el acuse que consume la interfaz; los permisos siguen siendo del servidor.
export function confirmsUser(user, { id, username, role }) {
  return Number.isInteger(user?.id) && user.id > 0 && (id == null || user.id === id)
    && ['nombre', 'apellido', 'username', 'rol', 'estado'].every((key) => typeof user[key] === 'string')
    && (username == null || user.username === username) && user.rol === role;
}
