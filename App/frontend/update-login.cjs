const fs = require('fs');
const path = require('path');

const authPath = path.join(__dirname, 'src', 'auth', 'AuthContext.jsx');
let auth = fs.readFileSync(authPath, 'utf-8');

// Change login and register to return errors instead of alerts
auth = auth.replace(
  `alert("Credenciales incorrectas o usuario no registrado.");`,
  `return { error: "Correo o contraseña incorrectos." };`
);
auth = auth.replace(
  `if (existingUser) {`,
  `if (existingUser) {`
);
// In login() need to make sure we return a success object or undefined when OK
auth = auth.replace(`navigate('/menu');
    } else {
      return { error: "Correo o contraseña incorrectos." };
    }`, 
    `navigate('/menu');
      return { success: true };
    } else {
      return { error: "Correo o contraseña incorrectos." };
    }`);

auth = auth.replace(`alert("El correo ya está registrado.");
      return;`, 
      `return { error: "Este correo ya está registrado." };`);
auth = auth.replace(`navigate('/menu');
  };`, 
  `navigate('/menu');
    return { success: true };
  };`);

fs.writeFileSync(authPath, auth, 'utf-8');

const loginPath = path.join(__dirname, 'src', 'auth', 'Login.jsx');
const loginContent = `import { useAuth } from './AuthContext';
import { Eye, EyeOff, ArrowRight, CheckCircle } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  
  const [showPassword, setShowPassword] = useState(false);
  const [mode, setMode] = useState('login'); // 'login', 'register', 'recover'
  
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (mode === 'recover') {
      if (!email) return setErrorMsg("Ingresá tu correo electrónico");
      
      // Simulación de envío de correo (Esto va en el Backend)
      setSuccessMsg("Si el correo existe, te enviamos un enlace para restablecer tu contraseña.");
      setTimeout(() => setMode('login'), 4000);
      return;
    }

    if (mode === 'register') {
      if (!name || !email || !password) return setErrorMsg("Completá todos los campos");
      if (password.length < 6) return setErrorMsg("La contraseña debe tener al menos 6 caracteres");
      
      const res = register(name, email, password);
      if (res?.error) setErrorMsg(res.error);
    } else {
      if (!email || !password) return setErrorMsg("Completá todos los campos");
      const res = login(email, password);
      if (res?.error) setErrorMsg(res.error);
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
            {mode === 'register' ? 'Creá tu cuenta' : mode === 'recover' ? 'Recuperar Clave' : 'Iniciar Sesión'}
          </h1>
          <p className="text-monu-text/70 text-sm mb-6 font-bold">
            {mode === 'register' ? 'Unite para hacer tus pedidos' : mode === 'recover' ? 'Te enviaremos un correo con las instrucciones' : 'Tus hamburguesas favoritas, a un clic.'}
          </p>

          {errorMsg && (
            <div className="bg-red-50 text-red-600 font-bold text-xs p-3 rounded-xl mb-4 border border-red-100">
              {errorMsg}
            </div>
          )}
          
          {successMsg && (
            <div className="bg-green-50 text-green-700 font-bold text-xs p-3 rounded-xl mb-4 border border-green-200 flex items-start gap-2">
              <CheckCircle className="w-4 h-4 shrink-0" />
              <p>{successMsg}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
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

            {mode !== 'recover' && (
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="block text-xs font-bold text-monu-dark">Contraseña</label>
                  {mode === 'login' && (
                    <button type="button" onClick={() => { setMode('recover'); setErrorMsg(''); setSuccessMsg(''); }} className="text-[10px] font-bold text-monu-green hover:underline focus:outline-none">
                      ¿Olvidaste tu clave?
                    </button>
                  )}
                </div>
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
            )}

            <button 
              type="submit" 
              className="w-full bg-monu-dark hover:bg-black text-white font-extrabold py-3.5 rounded-xl flex items-center justify-center gap-2 transition shadow-md mt-2"
            >
              {mode === 'register' ? 'Registrarme' : mode === 'recover' ? 'Enviar Enlace' : 'Ingresar'}
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          <div className="mt-6 text-center text-sm font-bold text-monu-text/70">
            {mode === 'register' ? '¿Ya tenés cuenta? ' : mode === 'recover' ? '¿Recordaste tu clave? ' : '¿No tenés cuenta? '}
            <button 
              onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setErrorMsg(''); setSuccessMsg(''); }}
              className="text-monu-green hover:underline focus:outline-none"
            >
              {mode === 'login' ? 'Registrate gratis' : 'Iniciá Sesión'}
            </button>
          </div>
          
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
console.log("Login updated successfully.");