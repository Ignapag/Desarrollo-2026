// Campanita del centro de notificaciones del personal: contador de no leídas y
// diálogo con pestañas por categoría (stock y clientes/WhatsApp), filtro de pendientes
// y acciones para abrir el aviso o marcarlo como leído.
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, Check, FileCheck2, Headset, Package, RefreshCw, X } from 'lucide-react';
import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { useNotifications } from './notificationHooks';
import { categoryUnreadCount, elapsedTime, NOTIFICATION_CATEGORIES, notificationCategory } from './notificationModel';

// Estilo de botones e íconos por tipo de aviso.
const buttonClass = 'min-h-11 min-w-11 rounded-xl px-3 py-2 text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2 disabled:opacity-50';
const icons = { comprobante: FileCheck2, atencion: Headset, stock: Package };

/** Botón de notificaciones y su diálogo; no se muestra si el usuario no tiene avisos habilitados. */
export default function NotificationBell() {
  const { user } = useAuth();
  const feed = useNotifications();
  // Diálogo abierto, filtro (pendientes/todas) y categoría elegida.
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('pending');
  const [category, setCategory] = useState('clientes');
  const categoryButtons = useRef({});
  const trigger = useRef(null);
  const dialog = useRef(null);
  // Abre el <dialog> nativo cuando se activa.
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
  }, [open]);
  if (!feed?.enabled) return null;
  // Cierra el diálogo y devuelve el foco a la campanita.
  const close = () => { if (dialog.current?.open) dialog.current.close(); setOpen(false); trigger.current?.focus(); };
  // Mantiene el foco con Tab dentro del diálogo.
  const trapFocus = (event) => {
    if (event.key !== 'Tab') return;
    const controls = [...dialog.current.querySelectorAll('button:not([disabled]):not([tabindex="-1"]), a[href], [tabindex="0"]')];
    const first = controls[0];
    const last = controls.at(-1);
    if ((event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  };
  // Categorías visibles según permisos y avisos de la categoría activa.
  const categories = NOTIFICATION_CATEGORIES.filter((item) => can(user, item.permission));
  const active = categories.some((item) => item.id === category) ? category : categories[0]?.id;
  const activeLabel = categories.find((item) => item.id === active)?.label;
  const categoryItems = feed.items.filter((item) => notificationCategory(item) === active);
  const items = categoryItems.filter((item) => tab === 'all' || item.pending);
  const unread = categoryUnreadCount(feed.items, active);
  const status = feed.categoryStatus?.[active];
  const loading = status ? status.loading : feed.loading;
  const errors = status ? status.error ? [status.error] : [] : feed.errors;
  // Navegación por teclado entre pestañas de categoría (flechas, Inicio y Fin).
  const changeCategory = (event) => {
    const index = categories.findIndex((item) => item.id === active);
    const nextIndex = { ArrowRight: (index + 1) % categories.length,
      ArrowLeft: (index + categories.length - 1) % categories.length, Home: 0, End: categories.length - 1 }[event.key];
    if (nextIndex === undefined) return;
    event.preventDefault();
    const next = categories[nextIndex].id;
    setCategory(next);
    categoryButtons.current[next]?.focus();
  };
  const label = feed.unreadCount ? 'Notificaciones: ' + feed.unreadCount + ' sin leer' : 'Notificaciones';
  return <>
    <button ref={trigger} type="button" aria-label={label} aria-expanded={open} aria-haspopup="dialog" aria-controls={open ? 'notifications-dialog' : undefined}
      onClick={() => { if (open) close(); else { setOpen(true); void feed.refresh(); } }}
      className="relative min-h-11 min-w-11 inline-flex items-center justify-center text-monu-text hover:bg-monu-cream rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green">
      <Bell aria-hidden="true" className="w-5 h-5" />
      {feed.unreadCount > 0 && <span aria-hidden="true" className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full bg-monu-green text-white text-xs font-extrabold flex items-center justify-center">{feed.unreadCount > 99 ? '99+' : feed.unreadCount}</span>}
    </button>
    {/* Estado de la consulta anunciado a lectores de pantalla */}
    <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">{loading ? 'Consultando notificaciones.' : errors.length ? 'No se pudieron actualizar todas las notificaciones.' : feed.unreadCount + ' avisos sin leer.'}</span>
    {open && <dialog ref={dialog} id="notifications-dialog" aria-labelledby="notifications-title" onCancel={(event) => { event.preventDefault(); close(); }} onClose={close} onKeyDown={trapFocus}
      onClick={(event) => { if (event.target === event.currentTarget) close(); }}
      className="fixed inset-auto top-20 right-4 m-0 w-[calc(100%_-_2rem)] max-w-md max-h-[calc(100dvh_-_6rem)] overflow-y-auto rounded-2xl border border-monu-green/20 p-0 bg-monu-bone text-monu-text shadow-2xl backdrop:bg-monu-dark/20">
      <div className="min-w-0">
        {/* Encabezado fijo: título, pestañas de categoría y filtro de estado */}
        <div className="sticky top-0 z-10 bg-monu-bone border-b border-monu-green/10 p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 id="notifications-title" className="text-xl font-extrabold font-heading text-monu-dark">Notificaciones</h2>
            <button type="button" aria-label="Cerrar notificaciones" onClick={close} className={buttonClass}><X aria-hidden="true" className="h-5 w-5" /></button>
          </div>
          <div role="tablist" aria-label="Categorías de notificaciones" className="mt-3 flex gap-2">
            {categories.map((item) => <button key={item.id} ref={(node) => { categoryButtons.current[item.id] = node; }}
              id={'notifications-tab-' + item.id} type="button" role="tab" aria-selected={active === item.id}
              aria-controls="notifications-content" aria-label={item.label + ': ' + categoryUnreadCount(feed.items, item.id) + ' sin leer'}
              tabIndex={active === item.id ? 0 : -1} onKeyDown={changeCategory} onClick={() => setCategory(item.id)}
              className={buttonClass + ' flex-1 inline-flex items-center justify-center gap-2 border ' + (active === item.id ? 'bg-monu-green text-white border-monu-green' : 'border-monu-green/20 hover:bg-monu-cream')}>
              {item.label}<span aria-hidden="true" className="rounded-full bg-black/10 px-2 text-xs tabular-nums">{categoryUnreadCount(feed.items, item.id)}</span>
            </button>)}
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-2" role="group" aria-label="Estado de las notificaciones">
            <button type="button" aria-pressed={tab === 'pending'} onClick={() => setTab('pending')} className={buttonClass + (tab === 'pending' ? ' bg-monu-green text-white' : ' hover:bg-monu-cream')}>Pendientes</button>
            <button type="button" aria-pressed={tab === 'all'} onClick={() => setTab('all')} className={buttonClass + (tab === 'all' ? ' bg-monu-green text-white' : ' hover:bg-monu-cream')}>Todas</button>
            <button type="button" aria-label="Actualizar notificaciones" disabled={feed.refreshing} onClick={() => { void feed.refresh(); }} className={buttonClass + ' ml-auto'}><RefreshCw aria-hidden="true" className="h-4 w-4" /></button>
          </div>
          <p className="text-xs mt-3">Leer un aviso no resuelve su pendiente.</p>
        </div>
        <div id="notifications-content" role="tabpanel" aria-labelledby={'notifications-tab-' + active} className="p-4 space-y-3">
          {/* Errores, estado de carga y acción de marcar todo como leído */}
          {errors.length > 0 && <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
            {errors.map((error) => <p key={error}>{error}</p>)}
            <p>La información disponible puede estar desactualizada.</p>
            <button type="button" onClick={() => { void feed.refresh(); }} className={buttonClass + ' underline'}>Reintentar</button>
          </div>}
          {feed.storageError && <p role="status" className="text-sm">Las marcas de lectura se conservan solo durante esta sesión porque no se pudieron guardar en este navegador.</p>}
          {loading && <p role="status" className="text-sm">Consultando notificaciones...</p>}
          {unread > 0 && <button type="button" onClick={() => feed.markRead(categoryItems.map((item) => item.key))} className={buttonClass + ' w-full border border-monu-green/20 text-monu-green'}>Marcar {activeLabel} como leídas</button>}
          {!loading && !errors.length && items.length === 0 && <p className="py-6 text-center text-sm">{tab === 'pending' ? 'No tenés notificaciones pendientes.' : 'No hay notificaciones disponibles.'}</p>}
          {/* Lista de avisos de la categoría */}
          <ul className="space-y-3">
            {items.map((item) => {
              const Icon = icons[item.kind];
              const time = elapsedTime(item.date);
              const canOpen = item.kind === 'stock' ? can(user, 'stock.ver') : can(user, 'pedidos.ver');
              return <li key={item.key} className="min-w-0 rounded-xl border border-monu-green/15 bg-white p-4 space-y-2">
                <div className="flex items-start gap-3"><Icon aria-hidden="true" className="h-5 w-5 shrink-0 mt-0.5 text-monu-green" /><div className="min-w-0 flex-1">
                  <h3 className="font-extrabold text-monu-dark break-words">{item.title}</h3>
                  <p className="text-sm font-bold break-words">{item.reference}</p>
                </div></div>
                <p className="text-sm">{item.description}</p>
                {time && <time dateTime={item.date} title={new Date(item.date).toLocaleString('es-AR')} className="block text-xs">{time}</time>}
                <p className="text-xs font-bold">{item.pending ? 'Pendiente de atención' : 'Revisión finalizada'} · {item.read ? 'Leída' : 'Sin leer'}</p>
                <div className="flex flex-wrap items-center gap-2">
                  {canOpen && <Link to={item.href} onClick={() => { feed.markRead([item.key]); close(); }} className={buttonClass + ' inline-flex items-center bg-monu-green text-white'}>{item.action}</Link>}
                  {!item.read && <button type="button" onClick={() => feed.markRead([item.key])} className={buttonClass + ' inline-flex items-center gap-2 border border-monu-green/20'}><Check aria-hidden="true" className="h-4 w-4" />Marcar leída</button>}
                </div>
              </li>;
            })}
          </ul>
          {tab === 'all' && <p className="text-xs">Avisos disponibles, incluidos los leídos. Las marcas de lectura se guardan por usuario en este navegador.</p>}
        </div>
      </div>
    </dialog>}
  </>;
}
