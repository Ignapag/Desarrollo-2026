import { createContext, useContext, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const navigate = useNavigate();

  const login = async (email, password) => {
    // ==========================================
    // TODO BACKEND (Tomás): 
    // 1. Reemplazar este simulador por un `fetch()` o `axios.post('/api/auth/login')`.
    // 2. Enviar email y password al backend.
    // 3. Recibir el JWT Token y la info del usuario (con su rol real de la DB).
    // 4. Setear el usuario en el estado y guardar el token (localStorage/cookies).
    // ==========================================
    
    // Simulador actual para el frontend:
    if (email.includes('admin') || email.includes('empleado') || email.includes('gerente')) {
      setUser({ email, role: 'admin', name: 'Administrador' });
      navigate('/dashboard');
    } else if (email.includes('repartidor')) {
      setUser({ email, role: 'repartidor', name: 'Repartidor Juan' });
      navigate('/delivery');
    } else {
      setUser({ email, role: 'cliente', name: 'Cliente Monu' });
      navigate('/menu');
    }
  };

  const register = async (name, email, password) => {
    // ==========================================
    // TODO BACKEND (Tomás): 
    // 1. Reemplazar este simulador por un `fetch('/api/auth/register')`.
    // 2. Si el registro en la DB es exitoso, iniciar sesión automáticamente o redirigir al login.
    // ==========================================
    
    // Simulador actual para el frontend:
    setUser({ email, role: 'cliente', name: name });
    navigate('/menu');
  };

  const logout = () => {
    // TODO BACKEND: Limpiar JWT Token de localStorage o cookies aquí
    setUser(null);
    navigate('/login');
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);