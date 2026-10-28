// Formulario de alta de cuentas del personal (nombre, apellido, usuario, contraseña
// inicial y rol), con validaciones de contraseña previas al envío.
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';
import { UserFacingError, userErrorMessage } from '../shared/api/userErrors.js';
import { confirmsUser } from './userConfirmation';

// Estilo de campo y valores iniciales del formulario.
const field = 'min-h-11 w-full rounded-xl border border-monu-green/30 bg-white px-3 py-2 focus-visible:outline-2 focus-visible:outline-monu-green';
const initial = { nombre: '', apellido: '', username: '', password: '', rol: 'EMPLEADO' };

/**
 * Crea una cuenta vía /api/usuarios. `onCreated` recibe la cuenta confirmada y
 * `onPendingChange` informa si hay un alta en curso.
 */
export default function NewUserForm({ roles, onCreated, onPendingChange = () => {} }) {
  // Valores, envío en curso, aviso general y errores por campo.
  const [values, setValues] = useState(initial);
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [errors, setErrors] = useState({});
  const summary = useRef(null);
  // El resumen de errores recibe el foco cuando aparece.
  useEffect(() => { if (feedback?.error) summary.current?.focus(); }, [feedback]);
  const busy = useRef(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  // Actualiza un campo y limpia su error.
  const change = (name) => (event) => {
    setValues((previous) => ({ ...previous, [name]: event.target.value }));
    setFeedback(null);
    setErrors((previous) => ({ ...previous, [name]: '' }));
  };
  // Valida los campos, crea la cuenta y confirma que la respuesta corresponda al usuario y rol pedidos.
  const save = async (event) => {
    event.preventDefault();
    if (busy.current) return;
    const body = { ...values, nombre: values.nombre.trim(), apellido: values.apellido.trim(), username: values.username.trim() };
    const invalid = {};
    if (!body.nombre) invalid.nombre = 'Ingresá el nombre.';
    if (!body.apellido) invalid.apellido = 'Ingresá el apellido.';
    if (body.username.length < 4) invalid.username = 'Usá al menos 4 caracteres para el usuario.';
    if (body.password.length < 8) invalid.password = 'Usá una contraseña de al menos 8 caracteres.';
    else if (body.password.trim() !== body.password) invalid.password = 'La contraseña no puede empezar ni terminar con espacios.';
    else if (/^\p{Decimal_Number}+$/u.test(body.password)) invalid.password = 'La contraseña no puede contener solo números.';
    else if (body.password.toLowerCase() === body.username.toLowerCase()) invalid.password = 'La contraseña no puede ser igual al nombre de usuario.';
    if (!roles.some((role) => role.rol === body.rol)) invalid.rol = 'Seleccioná un rol disponible.';
    setErrors(invalid);
    if (Object.keys(invalid).length) {
      setFeedback({ error: true, text: 'Revisá los campos indicados antes de crear la cuenta.' });
      return;
    }
    busy.current = true; setPending(true); setFeedback(null); onPendingChange(true);
    try {
      const created = await apiFetch('/api/usuarios', { method: 'POST', body: JSON.stringify(body) });
      if (!confirmsUser(created, { username: body.username, role: body.rol })) throw new UserFacingError('No pudimos confirmar la creación de la cuenta. Consultá el listado antes de intentar crearla otra vez.');
      if (active.current) {
        setValues(initial);
        setErrors({});
        setFeedback({ error: false, text: `Cuenta creada: ${created.username}. Ya puede ingresar con sus credenciales.` });
        onCreated(created);
      }
    } catch (error) {
      if (active.current) setFeedback({ error: true, text: userErrorMessage(error, 'No pudimos crear la cuenta. Consultá el listado antes de repetir el alta.') });
    } finally {
      busy.current = false;
      if (active.current) { setPending(false); onPendingChange(false); }
    }
  };
  return <form noValidate onSubmit={save} className="rounded-2xl border border-monu-green/15 bg-white p-4 md:p-6 space-y-4" aria-labelledby="nueva-cuenta-titulo">
    {/* Título y explicación */}
    <div><h3 id="nueva-cuenta-titulo" className="text-xl font-bold">Crear cuenta</h3><p className="mt-1 text-sm">Cada persona ingresa con su propio usuario y contraseña. La cuenta hereda los permisos del rol elegido.</p></div>
    {/* Aviso del resultado y resumen de errores con enlaces a cada campo */}
    {feedback && <div ref={summary} tabIndex={-1} role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'text-red-700' : 'text-monu-green'}><p>{feedback.text}</p>
      {feedback.error && Object.values(errors).some(Boolean) && <ul className="mt-2 space-y-1 text-sm">{Object.entries(errors).filter(([, message]) => message).map(([name, message]) => <li key={name}><a href={`#nueva-cuenta-${name}`} className="underline">{message}</a></li>)}</ul>}
    </div>}
    {/* Campos de la cuenta */}
    <fieldset disabled={pending} className="grid gap-4 sm:grid-cols-2">
      <label className="space-y-1"><span className="font-bold">Nombre</span><input id="nueva-cuenta-nombre" name="nombre" className={field} required autoComplete="given-name" aria-invalid={Boolean(errors.nombre)} aria-describedby="nueva-cuenta-nombre-error" value={values.nombre} onChange={change('nombre')} /><span id="nueva-cuenta-nombre-error" className="block text-sm text-red-700">{errors.nombre}</span></label>
      <label className="space-y-1"><span className="font-bold">Apellido</span><input id="nueva-cuenta-apellido" name="apellido" className={field} required autoComplete="family-name" aria-invalid={Boolean(errors.apellido)} aria-describedby="nueva-cuenta-apellido-error" value={values.apellido} onChange={change('apellido')} /><span id="nueva-cuenta-apellido-error" className="block text-sm text-red-700">{errors.apellido}</span></label>
      <label className="space-y-1"><span className="font-bold">Nombre de usuario</span><input id="nueva-cuenta-username" name="username" className={field} required minLength={4} autoComplete="off" autoCapitalize="none" spellCheck={false} aria-invalid={Boolean(errors.username)} aria-describedby="nueva-cuenta-username-error" value={values.username} onChange={change('username')} /><span className="block text-sm">Al menos 4 caracteres; debe ser único.</span><span id="nueva-cuenta-username-error" className="block text-sm text-red-700">{errors.username}</span></label>
      <label className="space-y-1"><span className="font-bold">Contraseña inicial</span><input id="nueva-cuenta-password" name="password" type="password" className={field} required minLength={8} autoComplete="new-password" aria-invalid={Boolean(errors.password)} aria-describedby="nueva-cuenta-password-ayuda nueva-cuenta-password-error" value={values.password} onChange={change('password')} /><span id="nueva-cuenta-password-ayuda" className="block text-sm">Al menos 8 caracteres, sin espacios al inicio/final, no solo números ni igual al usuario.</span><span id="nueva-cuenta-password-error" className="block text-sm text-red-700">{errors.password}</span></label>
      <label className="space-y-1"><span className="font-bold">Rol de la nueva cuenta</span><select id="nueva-cuenta-rol" name="rol" className={field} aria-invalid={Boolean(errors.rol)} aria-describedby="nueva-cuenta-rol-error" value={roles.some((role) => role.rol === values.rol) ? values.rol : ''} onChange={change('rol')}><option value="" disabled>Seleccioná un rol</option>{roles.map((role) => <option key={role.rol} value={role.rol}>{role.nombre}</option>)}</select><span id="nueva-cuenta-rol-error" className="block text-sm text-red-700">{errors.rol}</span></label>
    </fieldset>
    <button type="submit" disabled={pending} className="min-h-11 rounded-xl bg-monu-green px-4 py-2 font-bold text-white disabled:opacity-50 disabled:cursor-not-allowed">{pending ? 'Creando cuenta…' : 'Crear cuenta'}</button>
  </form>;
}
