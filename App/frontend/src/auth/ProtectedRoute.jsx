import { Fragment } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { canVisit } from './permissions';
import { portal } from '../shared/portal';

export default function ProtectedRoute({ children, allowedRoles, path }) {
  const { user, loading, logout } = useAuth();
  if (loading) return <div className="min-h-screen bg-monu-cream" aria-busy="true" />;
  if (!user) return <Navigate to="/login" replace />;
  if ((allowedRoles && !allowedRoles.includes(user.backendRole)) || (path && !canVisit(user, path))) {
    return <section className="p-6 space-y-4" role="alert"><h1 className="text-2xl font-bold">Sin acceso a esta sección</h1><p>Tu rol no tiene el permiso necesario. Pedile al administrador que revise tus accesos.</p><div className="flex flex-wrap gap-4">{portal.clientes && <Link to="/menu">Ir al menú</Link>}<button onClick={logout} className="min-h-11 underline">Cerrar sesión</button></div></section>;
  }
  return <Fragment key={JSON.stringify(user)}>{children}</Fragment>;
}
