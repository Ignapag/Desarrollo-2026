import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Users, ShieldCheck } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { apiFetch } from '../shared/api/http';
import NewUserForm from './NewUserForm';

const field = 'min-h-11 w-full rounded-xl border border-monu-green/30 bg-white px-3 py-2 focus-visible:outline-2 focus-visible:outline-monu-green';
const button = 'min-h-11 rounded-xl bg-monu-green px-4 py-2 font-bold text-white disabled:opacity-50 disabled:cursor-not-allowed';
function samePermissions(left, right) {
  return left.length === right.length && left.every((key) => right.includes(key));
}
export function UserRoleEditor({ person, roles, onSaved }) {
  const [selected, setSelected] = useState(person.rol);
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const save = async (event) => {
    event.preventDefault();
    if (pending || selected === person.rol) return;
    setPending(true); setFeedback(null);
    try {
      const updated = await apiFetch(`/api/usuarios/${person.id}/rol`, { method: 'POST', body: JSON.stringify({ rol: selected }) });
      if (active.current) { onSaved(updated); setFeedback({ text: 'Rol actualizado.', error: false }); }
    } catch (error) { if (active.current) setFeedback({ text: error.message, error: true }); }
    finally { if (active.current) setPending(false); }
  };
  return <form onSubmit={save} className="rounded-xl border border-monu-green/15 p-4 space-y-3">
    <div className="break-words"><h3 className="font-bold">{person.nombre} {person.apellido}</h3><p className="text-sm">{person.username} · {person.estado}</p></div>
    <label className="block space-y-1"><span className="text-sm font-bold">Rol de {person.username}</span><select className={field} value={selected} disabled={pending} onChange={(event) => { setSelected(event.target.value); setFeedback(null); }}>{roles.map((role) => <option key={role.rol} value={role.rol}>{role.nombre}</option>)}</select></label>
    <div className="flex flex-wrap gap-3 items-center"><button className={button} disabled={pending || selected === person.rol}>{pending ? 'Guardando…' : 'Guardar rol'}</button>{selected !== person.rol && <span className="text-sm">Cambio sin guardar</span>}</div>
    {feedback && <p role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'text-red-700' : 'text-monu-green'}>{feedback.text}</p>}
  </form>;
}
export function RolePermissionsEditor({ role, modules, onSaved, refreshRole }) {
  const [selected, setSelected] = useState(role.permisos);
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [conflicted, setConflicted] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const dirty = !samePermissions(selected, role.permisos);
  const reload = async () => {
    setPending(true);
    try { await refreshRole(role.rol); }
    catch (error) { if (active.current) setFeedback({ error: true, text: `No se pudo actualizar el rol. ${error.message}` }); }
    finally { if (active.current) setPending(false); }
  };
  const save = async (event) => {
    event.preventDefault();
    if (!role.editable || !dirty || pending || conflicted) return;
    setPending(true); setFeedback(null);
    try {
      const updated = await apiFetch(`/api/acceso/roles/${role.rol}`, { method: 'PUT', body: JSON.stringify({ permisos: selected, version: role.version }) });
      if (active.current) { onSaved(updated); setFeedback({ error: false, text: 'Permisos guardados.' }); }
    } catch (error) {
      if (active.current) {
        if (error.status === 409) { setConflicted(true); setFeedback({ error: true, text: 'Otro administrador modificó este rol. Actualizá sus permisos antes de volver a editar. Tus cambios no se guardaron.' }); }
        else setFeedback({ error: true, text: error.message });
      }
    } finally { if (active.current) setPending(false); }
  };
  return <form onSubmit={save} className="rounded-2xl border border-monu-green/15 bg-white p-4 md:p-6 space-y-4 min-w-0">
    <div><h3 className="text-xl font-bold">{role.nombre}</h3><p className="text-sm">{selected.length} permisos{role.editable ? ' · Editable' : ' · Protegido'}</p></div>
    {role.rol === 'REPARTIDOR' && <p className="text-sm">El repartidor opera únicamente sobre sus viajes y pedidos. Para otras funciones, asigná el rol Empleado.</p>}
    {!role.editable && <p className="text-sm">{role.rol === 'ADMINISTRADOR' ? 'El administrador conserva todos los permisos del sistema.' : 'El cliente conserva su acceso público y no tiene permisos administrativos.'}</p>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{modules.map((module) => <fieldset key={module.clave} disabled={!role.editable || pending || conflicted} className="rounded-xl border border-monu-green/15 p-3 min-w-0"><legend className="px-1 font-bold">{module.nombre}</legend>{module.acciones.map((action) => {
      const key = action.clave.includes('.') ? action.clave : `${module.clave}.${action.clave}`;
      return <label key={key} className="flex min-h-11 items-center gap-3 py-2 cursor-pointer"><input type="checkbox" disabled={!role.disponibles?.includes(key)} className="h-5 w-5 shrink-0 accent-monu-green" checked={selected.includes(key)} onChange={(event) => { setFeedback(null); setSelected(event.target.checked ? [...selected, key] : selected.filter((permission) => permission !== key)); }} /><span className="break-words">{action.nombre}{role.editable && !role.disponibles?.includes(key) && <span className="block text-xs">No disponible para este rol</span>}</span></label>;
    })}</fieldset>)}</div>
    {role.editable && <div className="flex flex-wrap items-center gap-3"><button className={button} disabled={pending || !dirty || conflicted}>{pending ? 'Guardando…' : 'Guardar permisos'}</button><button type="button" className="min-h-11 px-3 underline disabled:opacity-50" disabled={pending || !dirty || conflicted} onClick={() => { setSelected(role.permisos); setFeedback(null); }}>Descartar cambios</button>{dirty && <span className="text-sm">Cambios sin guardar</span>}</div>}
    {feedback && <p role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'text-red-700' : 'text-monu-green'}>{feedback.text}</p>}
    {conflicted && <button type="button" className={button} disabled={pending} onClick={reload}>Actualizar permisos del rol</button>}
  </form>;
}
export default function AccessControl() {
  const { user, refreshSession } = useAuth();
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [retry, setRetry] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const owner = useRef(user);
  useLayoutEffect(() => { owner.current = user; }, [user]);
  useEffect(() => {
    const controller = new AbortController();
    Promise.resolve().then(() => { if (!controller.signal.aborted) { setSnapshot(null); setError(null); } });
    Promise.all([apiFetch('/api/acceso', { signal: controller.signal }), apiFetch('/api/usuarios', { signal: controller.signal })]).then(([access, people]) => {
      if (!controller.signal.aborted && owner.current === user) setSnapshot({ owner: user, access, people });
    }).catch((failure) => { if (!controller.signal.aborted && owner.current === user) setError(failure.message); });
    return () => controller.abort();
  }, [user, retry]);
  if (user?.backendRole !== 'ADMINISTRADOR') return <p role="alert">El control de acceso está reservado al administrador.</p>;
  if (error) return <section className="space-y-4"><h1 className="text-3xl font-bold">Control de Acceso</h1><p role="alert">{error}</p><button className={button} onClick={() => setRetry((value) => value + 1)}>Reintentar</button></section>;
  if (!snapshot || snapshot.owner !== user) return <p role="status">Cargando usuarios y permisos…</p>;
  const { access, people } = snapshot;
  const updateRole = (updated) => {
    if (owner.current !== user) return;
    setSnapshot((previous) => ({ ...previous, access: { ...previous.access, roles: previous.access.roles.map((role) => role.rol === updated.rol ? updated : role) } }));
    void refreshSession();
  };
  const refreshRole = async (rol) => {
    const current = await apiFetch('/api/acceso');
    updateRole(current.roles.find((role) => role.rol === rol));
  };
  const normalized = query.trim().toLocaleLowerCase('es');
  const filtered = people.filter((person) => (!roleFilter || person.rol === roleFilter) && `${person.nombre} ${person.apellido} ${person.username}`.toLocaleLowerCase('es').includes(normalized));
  return <div className="space-y-6 min-w-0">
    <div><h1 className="text-3xl font-extrabold font-heading text-monu-dark">Control de Acceso</h1><p className="mt-2">Asigná roles a usuarios y configurá las acciones permitidas por módulo.</p></div>
    <div className="flex flex-wrap gap-4 rounded-2xl bg-white border border-monu-green/10 p-4"><p className="flex items-center gap-2"><Users aria-hidden="true" size={20} />{people.length} usuarios</p><p className="flex items-center gap-2"><ShieldCheck aria-hidden="true" size={20} />{access.roles.length} roles · {access.roles.filter((role) => role.editable).length} editables</p></div>
    <div><button type="button" className={button} disabled={creating} aria-expanded={showCreate} aria-controls="crear-cuenta" onClick={() => setShowCreate((value) => !value)}>{showCreate ? 'Cerrar formulario' : 'Crear cuenta'}</button></div>
    {showCreate && <section id="crear-cuenta"><NewUserForm roles={access.roles} onPendingChange={setCreating} onCreated={(created) => {
      if (owner.current !== user) return;
      setSnapshot((previous) => ({ ...previous, people: [created, ...previous.people.filter((person) => person.id !== created.id)] }));
      setQuery(''); setRoleFilter('');
    }} /></section>}
    <section className="space-y-4" aria-labelledby="usuarios-acceso"><h2 id="usuarios-acceso" className="text-2xl font-bold">Roles de usuarios</h2><div className="grid gap-3 sm:grid-cols-2"><label className="space-y-1"><span className="font-bold">Buscar usuario</span><input type="search" className={field} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nombre, apellido o usuario" /></label><label className="space-y-1"><span className="font-bold">Filtrar por rol</span><select className={field} value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}><option value="">Todos los roles</option>{access.roles.map((role) => <option key={role.rol} value={role.rol}>{role.nombre}</option>)}</select></label></div><p role="status">{filtered.length} de {people.length} usuarios</p><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{filtered.map((person) => <UserRoleEditor key={`${person.id}-${person.rol}`} person={person} roles={access.roles} onSaved={(updated) => {
      if (owner.current !== user) return;
      setSnapshot((previous) => ({ ...previous, people: previous.people.map((candidate) => candidate.id === updated.id ? updated : candidate) }));
      void refreshSession();
    }} />)}</div>{!filtered.length && <p>No hay usuarios que coincidan con la búsqueda.</p>}</section>
    <section className="space-y-4" aria-labelledby="permisos-acceso"><h2 id="permisos-acceso" className="text-2xl font-bold">Permisos por rol y módulo</h2><p>Los cambios se aplican al guardar cada rol. Las sesiones abiertas actualizan sus accesos automáticamente.</p>{access.roles.map((role) => <RolePermissionsEditor key={`${role.rol}-${role.version}-${retry}`} role={role} modules={access.modulos} onSaved={updateRole} refreshRole={refreshRole} />)}</section>
  </div>;
}
