// Pantalla de inicio de sesión del personal: valida usuario y contraseña en el
// cliente, llama a `login` del contexto de sesión y muestra los errores accesibles.
import { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from './AuthContext';
import { Link } from 'react-router-dom';
import { portal } from '../shared/portal';
import { userErrorMessage } from '../shared/api/userErrors';

/** Formulario de ingreso con usuario/contraseña y opción de mostrar la contraseña. */
export default function Login() {
  const { login, logout, sessionError, logoutFailed } = useAuth();
  // Estado del formulario, del envío en curso y de los errores por campo o generales.
  const [showPassword, setShowPassword] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const pending = useRef(false);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState('');
  const usernameInput = useRef(null);
  const passwordInput = useRef(null);
  // Lleva el foco al primer campo con error para que el usuario lo corrija rápido.
  useEffect(() => {
    if (errors.username) usernameInput.current?.focus();
    else if (errors.password) passwordInput.current?.focus();
  }, [errors]);

  // Envía el formulario: valida campos vacíos, evita doble envío y traduce el resultado a mensajes.
  const handleSubmit = async (event) => {
    event.preventDefault();
    if (pending.current) return;
    const invalid = { ...(!username.trim() && { username: 'Ingresá tu usuario.' }), ...(!password && { password: 'Ingresá tu contraseña.' }) };
    setErrors(invalid);
    setSubmitError('');
    if (Object.keys(invalid).length) {
      return;
    }

    pending.current = true;
    setSubmitting(true);
    try {
      const result = await login(username.trim(), password);
      if (result?.error) setSubmitError(result.error);
      else if (result?.success) toast.success('¡Bienvenido!');
      else setSubmitError('No se pudo confirmar el inicio de sesión. Volvé a intentar.');
    } catch (error) {
      setSubmitError(userErrorMessage(error, 'No pudimos iniciar sesión. Intentá nuevamente más tarde.'));
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#eadecd] flex items-center justify-center p-4">
      <section className="bg-white max-w-[348px] w-full rounded-3xl shadow-monu overflow-hidden" aria-labelledby="login-title">
        {/* Encabezado con la imagen de marca */}
        <div className="w-full relative bg-[#f4e6b1]">
          <img src="/login-header-final.png" alt="Monu Burger" className="w-full h-auto object-cover" />
        </div>

        <div className="p-8">
          <h1 id="login-title" className="text-2xl font-extrabold text-monu-dark mb-1 font-heading">Iniciar sesión</h1>
          <p className="text-monu-text/70 text-sm mb-6 font-bold">
            Ingresá con la cuenta asignada por Monu Burger{portal.modo === 'personal' ? ' al personal' : ''}.
          </p>

          {/* Formulario: errores de sesión, campos de usuario y contraseña y botón de ingreso */}
          <form noValidate onSubmit={handleSubmit} className="space-y-4">
            {sessionError && <div role="alert" className="text-sm text-red-700"><p>{sessionError}</p>{logoutFailed && <button type="button" onClick={logout} className="min-h-11 underline">Reintentar cierre de sesión</button>}</div>}
            {submitError && <p role="alert" className="text-sm text-red-700">{submitError}</p>}
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
                aria-invalid={Boolean(errors.username)}
                aria-describedby={errors.username ? 'username-error' : undefined}
                ref={usernameInput}
                className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 font-bold text-sm text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                placeholder="Tu usuario"
              />
              {errors.username && <p id="username-error" role="alert" className="text-sm text-red-700">{errors.username}</p>}
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
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? 'password-error' : undefined}
                  ref={passwordInput}
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
              {errors.password && <p id="password-error" role="alert" className="text-sm text-red-700">{errors.password}</p>}
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

          {/* Pie: aclaración de altas y acceso al menú público si el portal de clientes está activo */}
          <p className="mt-6 text-center text-xs text-monu-text/60">
            Las altas y recuperaciones de acceso se gestionan con un administrador.
          </p>
          {portal.clientes && <Link to="/menu" className="mt-3 min-h-11 flex items-center justify-center rounded-xl text-sm font-bold text-monu-green hover:bg-monu-green/10 focus-visible:ring-2 focus-visible:ring-monu-green">
            Ver el menú y pedir sin cuenta
          </Link>}
        </div>
      </section>
    </main>
  );
}
