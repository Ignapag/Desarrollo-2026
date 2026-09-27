const fs = require('fs');
const path = require('path');

const authPath = path.join(__dirname, 'src', 'auth', 'AuthContext.jsx');
const authContent = `import { createContext, useContext, useState, useEffect } from 'react';
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
    } else {
      alert("Credenciales incorrectas o usuario no registrado.");
    }
  };

  const register = (name, email, password) => {
    const users = JSON.parse(localStorage.getItem('monu_users') || '[]');
    if (users.find(u => u.email === email)) {
      alert("El correo ya está registrado.");
      return;
    }
    users.push({ name, email, password });
    localStorage.setItem('monu_users', JSON.stringify(users));
    
    // Auto login
    const u = { email, role: 'cliente', name };
    setUser(u);
    localStorage.setItem('monu_session', JSON.stringify(u));
    navigate('/menu');
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
`;
fs.writeFileSync(authPath, authContent, 'utf-8');

const loginPath = path.join(__dirname, 'src', 'auth', 'Login.jsx');
const loginContent = `import { useAuth } from './AuthContext';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isRegistering) {
      if (!name || !email || !password) return alert("Completá todos los campos");
      register(name, email, password);
    } else {
      if (!email || !password) return alert("Completá todos los campos");
      login(email, password);
    }
  };

  return (
    <div className="min-h-screen bg-[#eadecd] flex items-center justify-center p-4">
      <div className="bg-white max-w-[348px] w-full rounded-3xl shadow-monu overflow-hidden">
        <div className="w-full relative bg-[#f4e6b1]">
          <img src="/login-header-final.png" alt="Monu Burger Header" className="w-full h-auto object-cover" />
        </div>
        <div className="p-8">
          <h1 className="text-2xl font-extrabold text-monu-dark mb-1 font-heading">
            {isRegistering ? 'Creá tu cuenta' : 'Iniciar Sesión'}
          </h1>
          <p className="text-monu-text/70 text-sm mb-6 font-bold">
            {isRegistering ? 'Unite para hacer tus pedidos' : 'Tus hamburguesas favoritas, a un clic.'}
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegistering && (
              <div>
                <label className="block text-xs font-bold text-monu-dark mb-1">Nombre y Apellido</label>
                <input 
                  type="text" 
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 font-bold text-sm text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                  placeholder="Ej: Juan Pérez"
                />
              </div>
            )}
            <div>
              <label className="block text-xs font-bold text-monu-dark mb-1">Correo Electrónico</label>
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 font-bold text-sm text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                placeholder="tu@email.com"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-monu-dark mb-1">Contraseña</label>
              <div className="relative">
                <input 
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 font-bold text-sm text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                  placeholder="••••••••"
                />
                <button 
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3 text-monu-text/50 hover:text-monu-green transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            <button 
              type="submit" 
              className="w-full bg-monu-dark hover:bg-black text-white font-extrabold py-3.5 rounded-xl flex items-center justify-center gap-2 transition shadow-md mt-2"
            >
              {isRegistering ? 'Registrarme' : 'Ingresar'}
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          <div className="mt-6 text-center text-sm font-bold text-monu-text/70">
            {isRegistering ? '¿Ya tenés cuenta? ' : '¿No tenés cuenta? '}
            <button 
              onClick={() => setIsRegistering(!isRegistering)}
              className="text-monu-green hover:underline focus:outline-none"
            >
              {isRegistering ? 'Iniciá Sesión' : 'Registrate gratis'}
            </button>
          </div>
          
          {/* Botón rápido para testear como invitado si quieren (opcional) */}
          <button onClick={() => navigate('/menu')} className="mt-4 w-full text-xs text-monu-text/40 hover:text-monu-text/60 underline">
            Ver menú sin registrarse
          </button>
        </div>
      </div>
    </div>
  );
}
`;
fs.writeFileSync(loginPath, loginContent, 'utf-8');

console.log("Auth and Login rewritten.");