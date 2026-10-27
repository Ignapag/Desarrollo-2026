import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch, invalidateApiSession, onUnauthorized } from '../shared/api/http';
import { aceptaSesion, portal } from '../shared/portal';
import { can as hasPermission, homeFor } from './permissions';

const AuthContext = createContext(null);
function mapUser(data) {
  return { id: data.id, username: data.username,
    role: ['ADMINISTRADOR', 'DUENIO', 'EMPLEADO'].includes(data.rol) ? 'admin' : data.rol.toLowerCase(),
    backendRole: data.rol, permisos: [...(data.permisos || [])].sort(),
    name: `${data.nombre} ${data.apellido}`.trim() };
}
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(portal.personal);
  const [sessionError, setSessionError] = useState('');
  const signedOut = useRef(false);
  const navigate = useNavigate();
  const epoch = useRef(0);
  const busy = useRef(false);
  const authQueue = useRef(Promise.resolve());
  const mutateAuth = (operation) => {
    const result = authQueue.current.then(operation, operation);
    authQueue.current = result.catch(() => undefined);
    return result;
  };
  const refreshRequest = useRef(null);
  const refreshSession = useCallback(async () => {
    if (!portal.personal || busy.current || signedOut.current) return;
    if (refreshRequest.current) return refreshRequest.current;
    const token = epoch.current;
    const request = apiFetch('/api/auth/me').then((data) => {
      if (token !== epoch.current || busy.current) return;
      const next = aceptaSesion(data.rol, portal.modo) ? mapUser(data) : null;
      setUser((previous) => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    }).catch((error) => {
      if (token === epoch.current && [401, 403].includes(error.status)) setUser(null);
    }).finally(() => {
      if (token === epoch.current) setLoading(false);
      if (refreshRequest.current === request) refreshRequest.current = null;
    });
    refreshRequest.current = request;
    return request;
  }, []);
  useEffect(() => onUnauthorized(() => {
    epoch.current += 1;
    invalidateApiSession();
    busy.current = false;
    refreshRequest.current = null;
    signedOut.current = true;
    setUser(null);
    setLoading(false);
    setSessionError('La sesión venció. Volvé a ingresar.');
  }), []);
  useEffect(() => {
    void refreshSession();
    const refreshVisible = () => { if (!document.hidden) void refreshSession(); };
    const timer = window.setInterval(refreshVisible, 15000);
    window.addEventListener('focus', refreshVisible);
    document.addEventListener('visibilitychange', refreshVisible);
    return () => {
      epoch.current += 1;
      refreshRequest.current = null;
      window.clearInterval(timer);
      window.removeEventListener('focus', refreshVisible);
      document.removeEventListener('visibilitychange', refreshVisible);
    };
  }, [refreshSession]);
  const login = async (username, password) => {
    const token = ++epoch.current;
    invalidateApiSession();
    signedOut.current = false;
    setSessionError('');
    busy.current = true;
    refreshRequest.current = null;
    setUser(null);
    try {
      const data = await mutateAuth(() => apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }));
      if (token !== epoch.current) return { error: 'La sesión cambió. Volvé a ingresar.' };
      if (!aceptaSesion(data.rol, portal.modo)) {
        await mutateAuth(() => apiFetch('/api/auth/logout', { method: 'POST' }));
        return { error: 'Este acceso es exclusivo para el personal de Monu Burger.' };
      }
      const authenticated = mapUser(data);
      setUser(authenticated);
      navigate(homeFor(authenticated));
      return { success: true };
    } catch (error) { return { error: error.message }; }
    finally { if (token === epoch.current) { busy.current = false; setLoading(false); } }
  };
  const logout = async () => {
    const token = ++epoch.current;
    invalidateApiSession();
    signedOut.current = true;
    setSessionError('');
    busy.current = true;
    refreshRequest.current = null;
    setUser(null);
    setLoading(false);
    navigate('/login');
    try { await mutateAuth(() => apiFetch('/api/auth/logout', { method: 'POST' })); }
    catch (error) {
      if (token === epoch.current) setSessionError(`No se pudo cerrar la sesión en el servidor. Reintentá el cierre. ${error.message}`);
      return { error: error.message };
    }
    finally { if (token === epoch.current) busy.current = false; }
  };
  return <AuthContext.Provider value={{ user, loading, sessionError, login, logout, refreshSession, can: (permission) => hasPermission(user, permission) }}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);
