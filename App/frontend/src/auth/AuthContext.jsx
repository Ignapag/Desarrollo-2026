import { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const navigate = useNavigate();

  // Cargar sesión guardada si existe
  useEffect(() => {
    const savedUser = localStorage.getItem('monu_session');
    if (savedUser) setUser(JSON.parse(savedUser));
  }, []);

  const login = (email, password) => {
    // Si es admin o repartidor
    if (email.includes('admin') || email.includes('empleado')) {
      const u = { email, role: 'admin', name: 'Administrador' };
      setUser(u);
      localStorage.setItem('monu_session', JSON.stringify(u));
      navigate('/dashboard');
      return;
    } 
    if (email.includes('repartidor')) {
      const u = { email, role: 'repartidor', name: 'Repartidor Juan' };
      setUser(u);
      localStorage.setItem('monu_session', JSON.stringify(u));
      navigate('/delivery');
      return;
    }

    // Si es cliente, buscar en la BD local de clientes
    const users = JSON.parse(localStorage.getItem('monu_users') || '[]');
    const existingUser = users.find(u => u.email === email && u.password === password);
    
    if (existingUser) {
      const u = { email, role: 'cliente', name: existingUser.name };
      setUser(u);
      localStorage.setItem('monu_session', JSON.stringify(u));
      navigate('/menu');
      return { success: true };
    } else {
      return { error: "Correo o contraseña incorrectos." };
    }
  };

  const register = (name, email, password) => {
    const users = JSON.parse(localStorage.getItem('monu_users') || '[]');
    if (users.find(u => u.email === email)) {
      return { error: "Este correo ya está registrado." };
    }
    users.push({ name, email, password });
    localStorage.setItem('monu_users', JSON.stringify(users));
    
    // Auto login
    const u = { email, role: 'cliente', name };
    setUser(u);
    localStorage.setItem('monu_session', JSON.stringify(u));
    navigate('/menu');
    return { success: true };
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('monu_session');
    navigate('/login');
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
