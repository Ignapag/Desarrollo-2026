import { createContext, useContext, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../shared/api/http';

const AuthContext = createContext(null);

const ROLE_DESTINATION = {
  ADMINISTRADOR: '/dashboard',
  DUENIO: '/dashboard',
  EMPLEADO: '/dashboard',
  REPARTIDOR: '/delivery',
  CLIENTE: '/menu',
};

function mapUser(data) {
  const role = ['ADMINISTRADOR', 'DUENIO', 'EMPLEADO'].includes(data.rol)
    ? 'admin'
    : data.rol.toLowerCase();
  return {
    id: data.id,
    username: data.username,
    role,
    backendRole: data.rol,
    name: `${data.nombre} ${data.apellido}`.trim(),
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    apiFetch('/api/auth/me')
      .then((data) => {
        if (active) setUser(mapUser(data));
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = async (username, password) => {
    try {
      const data = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      const authenticated = mapUser(data);
      setUser(authenticated);
      navigate(ROLE_DESTINATION[data.rol] || '/menu');
      return { success: true };
    } catch (error) {
      return { error: error.message };
    }
  };

  const logout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } finally {
      setUser(null);
      navigate('/login');
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
