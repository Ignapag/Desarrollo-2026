import { useState } from 'react';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from './AuthContext';

export default function Login() {
  const { login } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!username || !password) {
      toast.error('Completá usuario y contraseña');
      return;
    }

    setSubmitting(true);
    try {
      const result = await login(username, password);
      if (result?.error) toast.error(result.error);
      else toast.success('¡Bienvenido!');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#eadecd] flex items-center justify-center p-4">
      <section className="bg-white max-w-[348px] w-full rounded-3xl shadow-monu overflow-hidden" aria-labelledby="login-title">
        <div className="w-full relative bg-[#f4e6b1]">
          <img src="/login-header-final.png" alt="Monu Burger" className="w-full h-auto object-cover" />
        </div>

        <div className="p-8">
          <h1 id="login-title" className="text-2xl font-extrabold text-monu-dark mb-1 font-heading">Iniciar sesión</h1>
          <p className="text-monu-text/70 text-sm mb-6 font-bold">
            Ingresá con la cuenta asignada por Monu Burger.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-xs font-bold text-monu-dark mb-1">Usuario</label>
              <input
                id="username"
                name="username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
                className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 font-bold text-sm text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                placeholder="Tu usuario"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-bold text-monu-dark mb-1">Contraseña</label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 pr-11 font-bold text-sm text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  className="absolute right-3 top-3 text-monu-text/50 hover:text-monu-green transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-monu-dark hover:bg-black disabled:cursor-wait disabled:opacity-70 text-white font-extrabold py-3.5 rounded-xl flex items-center justify-center gap-2 transition shadow-md mt-2"
            >
              {submitting ? 'Ingresando...' : 'Ingresar'}
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-monu-text/60">
            Las altas y recuperaciones de acceso se gestionan con un administrador.
          </p>
        </div>
      </section>
    </main>
  );
}
