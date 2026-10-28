import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';
import { Link } from 'react-router-dom';
import { FileCheck2, Headset, ArrowRight } from 'lucide-react';
import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { useNotifications } from '../notifications/notificationHooks';

const linkClass = 'min-h-11 inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold text-monu-green hover:bg-monu-green/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green';

export default function WhatsAppAttentionNotice() {
  const { user } = useAuth();
  const feed = useNotifications();
  // Reparto también usa este aviso fuera del layout del centro de notificaciones.
  // Sólo allí se conserva el resumen liviano existente, sin un segundo sondeo en el panel.
  const fallbackEnabled = !feed && can(user, 'whatsapp.ver');
  const [summary, setSummary] = useState(null);
  const retry = useRef(null);
  useEffect(() => {
    if (!fallbackEnabled) return undefined;
    let active = true;
    let pending = false;
    let controller;
    const update = async () => {
      if (!active || pending || document.hidden) return;
      pending = true;
      controller = new AbortController();
      try {
        const data = await apiFetch('/api/whatsapp/avisos', { signal: controller.signal, timeoutMs: 15000, cache: 'no-store' });
        if (!['comprobantes_pendientes', 'atenciones_pendientes'].every((key) => Number.isSafeInteger(data?.[key]) && data[key] >= 0)) throw Error('Resumen inválido');
        if (active) setSummary({ owner: user, data, error: false });
      } catch {
        if (active) setSummary((previous) => ({ owner: user, data: previous?.owner === user ? previous.data : null, error: true }));
      } finally { pending = false; }
    };
    retry.current = update;
    void update();
    const timer = window.setInterval(() => { void update(); }, 8000);
    window.addEventListener('focus', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      active = false; retry.current = null; controller?.abort(); window.clearInterval(timer);
      window.removeEventListener('focus', update); document.removeEventListener('visibilitychange', update);
    };
  }, [fallbackEnabled, user]);
  const current = fallbackEnabled && summary?.owner === user ? summary : null;
  if (!can(user, 'whatsapp.ver')) return null;
  const pending = feed?.items.filter((item) => item.pending) || [];
  const receipts = feed ? pending.filter((item) => item.kind === 'comprobante').length : current?.data?.comprobantes_pendientes || 0;
  const attention = feed ? pending.filter((item) => item.kind === 'atencion').length : current?.data?.atenciones_pendientes || 0;
  const error = feed ? feed.errors.find((message) => message.includes('WhatsApp')) : current?.error;
  if (!receipts && !attention && !error) return null;
  return <section aria-label="Atención pendiente de WhatsApp" className="mb-5 space-y-2">
    <div className="grid gap-3 lg:grid-cols-2">
      {receipts > 0 && <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-monu-dark">
        <FileCheck2 aria-hidden="true" className="h-5 w-5 shrink-0 text-amber-800" />
        <div className="min-w-0 flex-1"><p className="font-extrabold">Comprobante por verificar</p><p className="text-sm">{receipts === 1 ? 'Hay un comprobante pendiente de revisión.' : 'Hay ' + receipts + ' comprobantes pendientes de revisión.'}</p></div>
        {can(user, 'pedidos.ver') && <Link to="/dashboard/orders?bandeja=comprobantes" className={linkClass}>Revisar <ArrowRight aria-hidden="true" className="h-4 w-4" /></Link>}
      </div>}
      {attention > 0 && <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-monu-green/25 bg-monu-bone px-4 py-3 text-monu-dark">
        <Headset aria-hidden="true" className="h-5 w-5 shrink-0 text-monu-green" />
        <div className="min-w-0 flex-1"><p className="font-extrabold">Se necesita un empleado</p><p className="text-sm">{attention === 1 ? 'Hay una solicitud de atención pendiente.' : 'Hay ' + attention + ' solicitudes de atención pendientes.'}</p></div>
        {can(user, 'pedidos.ver') && <Link to="/dashboard/orders?bandeja=atenciones" className={linkClass}>Atender <ArrowRight aria-hidden="true" className="h-4 w-4" /></Link>}
      </div>}
    </div>
    {error && <div role="status" className="flex flex-wrap items-center gap-2 text-sm text-monu-dark"><p>No se pudieron actualizar los avisos.{(feed ? feed.whatsappAvailable : current?.data) ? ' Se conserva la última consulta; puede estar desactualizada.' : ''}</p><button type="button" onClick={() => { if (feed) void feed.refresh(); else void retry.current?.(); }} className={linkClass}>Reintentar</button></div>}
  </section>;
}
