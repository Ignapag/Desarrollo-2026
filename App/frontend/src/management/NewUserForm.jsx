import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';

const field = 'min-h-11 w-full rounded-xl border border-monu-green/30 bg-white px-3 py-2 focus-visible:outline-2 focus-visible:outline-monu-green';
const initial = { nombre: '', apellido: '', username: '', password: '', rol: 'EMPLEADO' };

export default function NewUserForm({ roles, onCreated, onPendingChange = () => {} }) {
  const [values, setValues] = useState(initial);
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const busy = useRef(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const change = (name) => (event) => {
    setValues((previous) => ({ ...previous, [name]: event.target.value }));
    setFeedback(null);
  };
  const save = async (event) => {
    event.preventDefault();
    if (busy.current) return;
    const body = { ...values, nombre: values.nombre.trim(), apellido: values.apellido.trim(), username: values.username.trim() };
    if (!body.nombre || !body.apellido || body.username.length < 4 || body.password.length < 8) {
      setFeedback({ error: true, text: 'Completá nombre y apellido, un usuario de al menos 4 caracteres y una contraseña de al menos 8.' });
      return;
    }
    busy.current = true; setPending(true); setFeedback(null); onPendingChange(true);
    try {
      const created = await apiFetch('/api/usuarios', { method: 'POST', body: JSON.stringify(body) });
      if (active.current) {
        setValues(initial);
        setFeedback({ error: false, text: `Cuenta creada: ${created.username}. Ya puede ingresar con sus credenciales.` });
        onCreated(created);
      }
    } catch (error) {
      if (active.current) setFeedback({ error: true, text: error.message });
    } finally {
      busy.current = false;
      if (active.current) { setPending(false); onPendingChange(false); }
    }
  };
  return <form onSubmit={save} className="rounded-2xl border border-monu-green/15 bg-white p-4 md:p-6 space-y-4" aria-labelledby="nueva-cuenta-titulo">
    <div><h3 id="nueva-cuenta-titulo" className="text-xl font-bold">Crear cuenta</h3><p className="mt-1 text-sm">Cada persona ingresa con su propio usuario y contraseña. La cuenta hereda los permisos del rol elegido.</p></div>
    <fieldset disabled={pending} className="grid gap-4 sm:grid-cols-2">
      <label className="space-y-1"><span className="font-bold">Nombre</span><input name="nombre" className={field} required autoComplete="given-name" value={values.nombre} onChange={change('nombre')} /></label>
      <label className="space-y-1"><span className="font-bold">Apellido</span><input name="apellido" className={field} required autoComplete="family-name" value={values.apellido} onChange={change('apellido')} /></label>
      <label className="space-y-1"><span className="font-bold">Nombre de usuario</span><input name="username" className={field} required minLength={4} autoComplete="off" autoCapitalize="none" spellCheck={false} value={values.username} onChange={change('username')} /><span className="block text-sm">Al menos 4 caracteres; debe ser único.</span></label>
      <label className="space-y-1"><span className="font-bold">Contraseña inicial</span><input name="password" type="password" className={field} required minLength={8} autoComplete="new-password" aria-describedby="nueva-cuenta-password-ayuda" value={values.password} onChange={change('password')} /><span id="nueva-cuenta-password-ayuda" className="block text-sm">Al menos 8 caracteres, sin espacios al inicio/final, no solo números ni igual al usuario.</span></label>
      <label className="space-y-1"><span className="font-bold">Rol de la nueva cuenta</span><select name="rol" className={field} value={values.rol} onChange={change('rol')}>{roles.map((role) => <option key={role.rol} value={role.rol}>{role.nombre}</option>)}</select></label>
    </fieldset>
    <button type="submit" disabled={pending} className="min-h-11 rounded-xl bg-monu-green px-4 py-2 font-bold text-white disabled:opacity-50 disabled:cursor-not-allowed">{pending ? 'Creando cuenta…' : 'Crear cuenta'}</button>
    {feedback && <p role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'text-red-700' : 'text-monu-green'}>{feedback.text}</p>}
  </form>;
}
