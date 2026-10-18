import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileCheck2, Headset, ArrowRight } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { apiFetch } from '../shared/api/http';

const staffRoles = ['EMPLEADO', 'ADMINISTRADOR', 'DUENIO'];
const linkClass = 'min-h-11 inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-bold text-monu-green hover:bg-monu-green/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green';

export default function WhatsAppAttentionNotice() {
  const { user } = useAuth();
  const enabled = staffRoles.includes(user?.backendRole);
  const [snapshot, setSnapshot] = useState(null);
  const retryRef = useRef(null);

  useEffect(() => {
    if (!enabled) return undefined;
    let active = true;
    let pending = false;
    let controller;
    const refresh = async () => {
      if (!active || pending || document.hidden) return;
      pending = true;
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 15000);
      try {
        const data = await apiFetch('/api/whatsapp/avisos', { signal: controller.signal, cache: 'no-store' });
        if (!['comprobantes_pendientes', 'atenciones_pendientes'].every((key) => Number.isSafeInteger(data?.[key]) && data[key] >= 0)) throw Error('Resumen inválido');
        if (active) setSnapshot({ owner: user, data, error: false });
      } catch {
        if (active) setSnapshot((previous) => ({ owner: user, data: previous?.owner === user ? previous.data : null, error: true }));
      } finally {
        window.clearTimeout(timeout);
        pending = false;
      }
    };
    retryRef.current = refresh;
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 8000);
    const onVisible = () => { void refresh(); };
    window.addEventListener('focus', onVisible);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      active = false;
      retryRef.current = null;
      controller?.abort();
      window.clearInterval(timer);
      window.removeEventListener('focus', onVisible);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [enabled, user]);

  const current = enabled && snapshot?.owner === user ? snapshot : null;
  const receipts = current?.data?.comprobantes_pendientes || 0;
  const attention = current?.data?.atenciones_pendientes || 0;
  if (!receipts && !attention && !current?.error) return null;

  return (
    <section aria-label="Atención pendiente de WhatsApp" aria-live="polite" className="mb-5 space-y-2">
      <div className="grid gap-3 lg:grid-cols-2">
        {receipts > 0 && <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-monu-dark">
          <FileCheck2 aria-hidden="true" className="h-5 w-5 shrink-0 text-amber-800" />
          <div className="min-w-0 flex-1"><p className="font-extrabold">Comprobante por verificar</p><p className="text-sm">{receipts === 1 ? 'Hay un comprobante pendiente de revisión.' : `Hay ${receipts} comprobantes pendientes de revisión.`}</p></div>
          <Link to="/dashboard/orders?bandeja=comprobantes" className={linkClass}>Revisar <ArrowRight aria-hidden="true" className="h-4 w-4" /></Link>
        </div>}
        {attention > 0 && <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-monu-green/25 bg-monu-bone px-4 py-3 text-monu-dark">
          <Headset aria-hidden="true" className="h-5 w-5 shrink-0 text-monu-green" />
          <div className="min-w-0 flex-1"><p className="font-extrabold">Se necesita un empleado</p><p className="text-sm">{attention === 1 ? 'Hay una solicitud de atención pendiente.' : `Hay ${attention} solicitudes de atención pendientes.`}</p></div>
          <Link to="/dashboard/orders?bandeja=atenciones" className={linkClass}>Atender <ArrowRight aria-hidden="true" className="h-4 w-4" /></Link>
        </div>}
      </div>
      {current?.error && <div role="status" className="flex flex-wrap items-center gap-2 text-sm text-monu-dark"><p>No se pudieron actualizar los avisos.{current.data ? ' Se conserva la última consulta.' : ''}</p><button type="button" onClick={() => { void retryRef.current?.(); }} className={linkClass}>Reintentar</button></div>}
    </section>
  );
}
