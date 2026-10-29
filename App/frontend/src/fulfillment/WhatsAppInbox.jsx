// Bandeja de WhatsApp del personal: revisión humana de comprobantes de pago y de
// cambios pedidos por el cliente desde el bot, atención de conversaciones derivadas
// (marcar como resueltas) y estado de los mensajes de salida.
import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageCircle, ChevronDown, RefreshCw, Download } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { can } from '../auth/permissions';
import { apiFetch } from '../shared/api/http';
import { apiResponseError, UserFacingError, userErrorMessage } from '../shared/api/userErrors.js';
import { useData } from '../shared/store/DataContext';
import { useNotificationInboxLoader } from '../notifications/notificationHooks';
import { knownLabel, paymentMethodLabel } from './orderModel';

// Clase base de los botones de acción de la bandeja.
const actionClass = 'min-h-11 px-4 py-2 rounded-xl text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

// Descarga el archivo de un comprobante (PDF o imagen) con la cookie de sesión y
// dispara la descarga en el navegador.
async function downloadReceipt(kind, id) {
  // El cliente JSON compartido no admite respuestas binarias.
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
  const response = await fetch(`${base}/api/whatsapp/${kind}/${id}/archivo`, { credentials: 'include' });
  if (!response.ok) {
    throw apiResponseError(response.status, null);
  }
  const file = await response.blob();
  if (!file.size || !['application/pdf', 'image/png', 'image/jpeg'].includes(file.type)) {
    throw new UserFacingError('No pudimos descargar el comprobante. Intentá nuevamente más tarde.');
  }
  const url = URL.createObjectURL(file);
  const link = document.createElement('a');
  link.href = url;
  link.download = `comprobante-${kind}-${id}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Describe en texto la acción de cambio pedida por el cliente (quitar ingrediente o cambiar cantidad).
function describeChangeAction(action) {
  const labels = { quitar_ingrediente: 'Quitar ingrediente', cantidad: 'Cambiar cantidad' };
  const name = typeof action?.accion === 'string' ? action.accion : '';
  const label = Object.hasOwn(labels, name) ? labels[name] : 'Cambio no identificado';
  const args = action?.argumentos;
  const details = [label];
  if (Number.isInteger(args?.item_indice) && args.item_indice >= 1) details.push(`Producto ${args.item_indice}`);
  if (name === 'quitar_ingrediente' && typeof args?.ingrediente === 'string' && args.ingrediente.trim()) {
    details.push(args.ingrediente.trim().slice(0, 100));
  }
  if (name === 'cantidad' && Number.isInteger(args?.cantidad) && args.cantidad >= 1 && args.cantidad <= 50) {
    details.push(`${args.cantidad} unidades`);
  }
  return details.join(' · ');
}

/** Tabla comparativa entre el pedido vigente y el cambio solicitado (cantidad, aclaraciones, total). */
function ChangeDetails({ anterior, posterior }) {
  const rows = [
    ['cantidad', 'Cantidad'],
    ['aclaraciones', 'Aclaraciones'],
    ['total', 'Total'],
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <caption className="sr-only">Comparación del pedido vigente y el cambio solicitado</caption>
        <thead><tr><th className="p-2">Dato</th><th className="p-2">Vigente</th><th className="p-2">Solicitado</th></tr></thead>
        <tbody>
          {rows.map(([key, label]) => (
            <tr key={key} className="border-t border-monu-green/10">
              <th scope="row" className="p-2 align-top">{label}</th>
              <td className="p-2 align-top break-words max-w-40">{String(anterior?.[key] ?? '—')}</td>
              <td className="p-2 align-top break-words max-w-40">{String(posterior?.[key] ?? '—')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Tarjeta de revisión de un comprobante o de un cambio de pedido. Exige motivo y,
 * para aprobar, verificación manual del pago o aceptación del nuevo total.
 * `onReviewed`/`onReviewFailed` refrescan la bandeja tras la decisión.
 */
function ReviewCard({ record, kind, onReviewed, onReviewFailed }) {
  const { user } = useAuth();
  const manage = can(user, 'whatsapp.gestionar');
  // Estado del formulario de revisión (motivo, verificaciones, envío y descarga).
  const [reason, setReason] = useState('');
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  const [financialAccepted, setFinancialAccepted] = useState(false);
  const submittingRef = useRef(false);
  const reasonRef = useRef(null);
  // Datos derivados: tipo de registro, si sigue pendiente, totales y si cambió el precio.
  const isReceipt = kind === 'comprobantes';
  const pending = isReceipt ? record.estado === 'PENDIENTE' : record.estado === 'PENDIENTE_EMPLEADO';
  const hasReceiptTotal = record.total != null && Number.isFinite(Number(record.total));
  const hasChangeTotal = record.posterior?.total != null && Number.isFinite(Number(record.posterior.total));
  const priceChanged = !isReceipt && record.anterior?.total != null && record.posterior?.total != null
    && Number(record.anterior.total) !== Number(record.posterior.total);
  const cardId = `whatsapp-${kind}-${record.id}`;
  // Aprobar requiere permisos de gestión y pagos/edición, y las verificaciones marcadas.
  const approvalBlocked = !manage || (isReceipt
    ? !can(user, 'pagos.registrar') || !can(user, 'pagos.conciliar') || !verified || !hasReceiptTotal
    : !can(user, 'pedidos.editar') || !hasChangeTotal || (priceChanged && !financialAccepted));

  // Envía la decisión (aprobar o rechazar según el botón usado) con el total verificado;
  // si el cambio sube el precio, la diferencia queda como cobro pendiente.
  const review = async (event) => {
    event.preventDefault();
    if (submittingRef.current || !manage) return;
    const decision = event.nativeEvent.submitter?.value;
    if (!['aprobar', 'rechazar'].includes(decision)) return;
    const approve = decision === 'aprobar';
    if (!reason.trim()) {
      setError('Registrá el motivo de la decisión y la verificación realizada.');
      reasonRef.current?.focus();
      return;
    }
    if (approve && approvalBlocked) return;
    submittingRef.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await apiFetch(`/api/whatsapp/${kind}/${record.id}/revision`, {
        method: 'POST',
        body: JSON.stringify({
          aprobar: approve,
          motivo: reason.trim(),
          ...(isReceipt ? { total_verificado: record.total } : {
            total_verificado: record.posterior?.total ?? null,
            resolucion_financiera: approve && priceChanged ? 'COBRO_PENDIENTE' : null,
          }),
        }),
      });
      if (!['APROBADO', 'APLICADO', 'RECHAZADO'].includes(result?.estado)) {
        throw new UserFacingError('No pudimos confirmar la revisión. Actualizá el pedido y comprobá su estado antes de repetirla.');
      }
      await onReviewed(`Revisión registrada para el pedido #${record.numero || record.pedido_id}. Actualizá el pedido para comprobar el resultado.`);
    } catch (failure) {
      const message = userErrorMessage(failure, 'No pudimos confirmar la revisión. Actualizá el pedido y comprobá su estado antes de repetirla.');
      setError(message);
      await onReviewFailed?.(message);
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  };

  // Descarga el comprobante de esta revisión.
  const download = async () => {
    if (downloading) return;
    setDownloading(true);
    setError('');
    try {
      await downloadReceipt('comprobantes', record.id);
    } catch (failure) {
      setError(userErrorMessage(failure, 'No pudimos descargar el comprobante. Intentá nuevamente.'));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <article id={cardId} tabIndex={-1} className="p-4 bg-white border border-monu-green/20 rounded-xl space-y-3 min-w-0" aria-labelledby={`${cardId}-title`}>
      {/* Encabezado y estado de la revisión */}
      <h4 id={`${cardId}-title`} className="font-extrabold text-monu-dark">Pedido #{record.numero || record.pedido_id} · {isReceipt ? 'Comprobante' : 'Cambio'} #{record.id}</h4>
      <p className="text-sm text-monu-text">Estado: <strong>{knownLabel({ PENDIENTE: 'Pendiente', PENDIENTE_EMPLEADO: 'Pendiente de revisión', APROBADO: 'Aprobado', APLICADO: 'Aplicado', RECHAZADO: 'Rechazado' }, record.estado)}</strong></p>
      {/* Datos del comprobante o comparación del cambio solicitado */}
      {isReceipt ? (
        <>
          <p className="text-sm text-monu-dark font-bold">Total vigente a verificar: {hasReceiptTotal ? Number(record.total).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' }) : 'No disponible. Actualizá antes de aprobar.'}</p>
          <p className="text-sm text-monu-text">Forma de pago: {paymentMethodLabel(record.metodo_pago)}</p>
          <button type="button" disabled={downloading || busy} onClick={download} className={`${actionClass} flex gap-2 items-center border border-monu-green text-monu-green hover:bg-monu-green/10`}>
            <Download aria-hidden="true" className="w-4 h-4" />{downloading ? 'Descargando...' : 'Descargar comprobante'}
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-monu-text">Acción solicitada: {describeChangeAction(record.accion)}</p>
          <ChangeDetails anterior={record.anterior} posterior={record.posterior} />
          {priceChanged && <p className="text-sm text-orange-800">El cambio no acredita cobros: cualquier saldo adicional queda pendiente. Si hay dinero a devolver, registrá primero la devolución en pagos antes de aprobar. Coordiná el cambio con cocina y caja.</p>}
          <p className="text-sm text-monu-text">Si el pedido cambió, actualizá sus datos antes de revisar la solicitud.</p>
        </>
      )}
      {error && <p role="alert" id={`${cardId}-error`} className="p-3 rounded-lg bg-red-50 text-red-800 text-sm">{error}</p>}
      {/* Formulario de revisión mientras está pendiente; si no, el motivo registrado */}
      {pending ? (
        <form noValidate onSubmit={review} className="space-y-3">
          <label className="block text-sm font-bold text-monu-dark space-y-1">
            <span>Motivo y verificación realizada (obligatorio)</span>
            <textarea ref={reasonRef} required maxLength={500} rows={3} disabled={busy} value={reason} onChange={(event) => setReason(event.target.value)} aria-describedby={error ? `${cardId}-error` : undefined} className="w-full px-3 py-2 text-base font-normal border border-monu-green/30 rounded-lg focus:outline-none focus:ring-2 focus:ring-monu-green" />
          </label>
          {isReceipt && (
            <label className="flex gap-3 items-start min-h-11 text-sm text-monu-dark">
              <input type="checkbox" checked={verified} disabled={busy} onChange={(event) => setVerified(event.target.checked)} className="mt-1 w-5 h-5 shrink-0 accent-monu-green" />
              <span>Verifiqué personalmente el importe y la acreditación de la transferencia. El comprobante por sí solo no demuestra el pago.</span>
            </label>
          )}
          {!isReceipt && priceChanged && (
            <label className="flex gap-3 items-start min-h-11 text-sm text-monu-dark">
              <input type="checkbox" checked={financialAccepted} disabled={busy} onChange={(event) => setFinancialAccepted(event.target.checked)} className="mt-1 w-5 h-5 shrink-0 accent-monu-green" />
              <span>Verifiqué y acepto el nuevo total de {hasChangeTotal ? Number(record.posterior.total).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' }) : 'importe no disponible'}. Coordinaré con cocina y caja; el cobro adicional queda pendiente y las devoluciones necesarias ya deben estar registradas.</span>
            </label>
          )}
          <div className="flex flex-wrap gap-3">
            <button type="submit" value="aprobar" disabled={busy || approvalBlocked} className={`${actionClass} bg-monu-green text-white hover:bg-monu-green/90`}>{busy ? 'Guardando revisión...' : 'Aprobar revisión'}</button>
            <button type="submit" value="rechazar" disabled={busy || !manage} className={`${actionClass} border border-red-300 text-red-800 hover:bg-red-50`}>Rechazar</button>
          </div>
        </form>
      ) : record.motivo && <p className="text-sm text-monu-text break-words">Motivo registrado: {record.motivo}</p>}
    </article>
  );
}

// Textos visibles del estado de envío de un mensaje de salida por WhatsApp.
const deliveryStates = {
  PENDIENTE: 'Pendiente de envío: todavía no llegó al cliente.',
  ENVIANDO: 'Enviándose ahora.',
  SIMULADO: 'Modo simulado: no se envió a WhatsApp.',
  ACEPTADO: 'Aceptada por WhatsApp; todavía sin confirmación de entrega.',
  ENTREGADO: 'Entregada al cliente.',
  FALLIDO: 'No se envió. Fuera de las 24 horas requiere plantilla: contactá al cliente por teléfono.',
  INCIERTO: 'Sin confirmación del proveedor: verificá antes de volver a responder.',
};

// La API exige registrar cómo se resolvió; el cierre desde la bandeja usa este texto fijo.
const RESOLUTION_TEXT = 'Resuelta por el personal desde la bandeja.';

/**
 * Tarjeta de una conversación que requiere atención del personal: pedido, cliente,
 * teléfono y cierre.
 */
function AttentionCard({ record, onChanged }) {
  const { user } = useAuth();
  const manage = can(user, 'whatsapp.gestionar');
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const submittingRef = useRef(false);
  const cardId = `whatsapp-atencion-${record.id}`;
  const phone = /^[0-9]{11,15}$/.test(record.telefono || '') ? record.telefono : null;
  const title = record.pedido_id ? `Pedido #${record.numero || record.pedido_id}` : 'Conversación sin pedido registrado';

  // Marca la atención como resuelta; evita doble envío y muestra el resultado o el error.
  const resolve = async () => {
    if (submittingRef.current || !manage) return;
    submittingRef.current = true;
    setBusy(true);
    setError('');
    setResult('');
    try {
      const response = await apiFetch(`/api/whatsapp/atenciones/${record.id}/resolucion`, {
        method: 'POST',
        body: JSON.stringify({ resolucion: RESOLUTION_TEXT }),
      });
      if (response?.id !== record.id || response.estado !== 'RESUELTA') throw new UserFacingError('No pudimos confirmar el cierre de la atención. Actualizá la bandeja y comprobá su estado antes de repetirlo.');
      const refreshed = await onChanged(`Atención de ${title.toLowerCase()} marcada como resuelta.`);
      setResult(refreshed ? 'Atención resuelta.' : 'Atención resuelta, pero no se pudo actualizar la bandeja. Actualizala.');
    } catch (failure) {
      setError(userErrorMessage(failure, 'No pudimos confirmar el cierre de la atención. Actualizá la bandeja y comprobá su estado antes de repetirlo.'));
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  };

  return (
    <article id={cardId} tabIndex={-1} className="p-4 bg-white border border-orange-200 rounded-xl space-y-3 min-w-0" aria-labelledby={`${cardId}-title`}>
      {/* Pedido y sus productos */}
      <h4 id={`${cardId}-title`} className="font-extrabold text-monu-dark">{title} · Atención #{record.id}</h4>
      {record.productos?.length > 0 && (
        <ul className="text-sm text-monu-dark list-disc pl-5">
          {record.productos.map((item, index) => <li key={index} className="break-words">{item.cantidad} × {item.nombre}{item.aclaraciones ? ` (${item.aclaraciones})` : ''}</li>)}
        </ul>
      )}
      {/* Datos del cliente */}
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
        <dt className="font-bold text-monu-dark">Cliente</dt><dd className="text-monu-text break-words">{record.cliente || 'Sin nombre registrado'}</dd>
        <dt className="font-bold text-monu-dark">Teléfono</dt><dd className="text-monu-text">{phone ? `+${phone}` : 'No disponible'}</dd>
      </dl>
      {/* Descarga del comprobante adjunto (si la atención es por un comprobante) */}
      {record.tiene_archivo && record.motivo === 'COMPROBANTE' && <button type="button" disabled={downloading} className={`${actionClass} inline-flex items-center gap-2 border border-monu-green text-monu-green hover:bg-monu-green/10`} onClick={async () => {
        if (downloading) return;
        setDownloading(true);
        setError('');
        try { await downloadReceipt('atenciones', record.id); } catch (failure) { setError(userErrorMessage(failure, 'No pudimos descargar el comprobante. Intentá nuevamente.')); } finally { setDownloading(false); }
      }}><Download aria-hidden="true" className="h-4 w-4" />{downloading ? 'Descargando...' : 'Descargar comprobante'}</button>}
      {error && <p role="alert" className="p-2 rounded-lg bg-red-50 text-red-800 text-sm">{error}</p>}
      {result && <p role="status" className="text-sm font-bold text-monu-green">{result}</p>}
      {/* Cierre de la atención */}
      {manage && <button type="button" disabled={busy} onClick={resolve} className={`${actionClass} bg-monu-green text-white hover:bg-monu-green/90`}>{busy ? 'Guardando...' : 'Marcar como resuelta'}</button>}
    </article>
  );
}

/**
 * Contenido de la bandeja (desplegable). `section` abre directamente comprobantes o
 * atenciones, `requestKey` identifica cada navegación y `notificationTarget` la tarjeta a enfocar.
 */
function InboxContent({ section, requestKey, notificationTarget }) {
  const refreshInbox = useNotificationInboxLoader();
  const { refreshData } = useData();
  // Expansión del panel: se abre sola cuando la URL pide una sección.
  const [expansion, setExpansion] = useState({ requestKey: null, expanded: false });
  const requestedSection = ['comprobantes', 'atenciones'].includes(section);
  const expanded = requestedSection && expansion.requestKey !== requestKey ? true : expansion.expanded;
  // Datos de la bandeja y estado de carga, errores y avisos.
  const [inbox, setInbox] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  // Refs: carga en curso, revisión vigente, encabezados para el foco y pedido de foco pendiente.
  const loadingRef = useRef(false);
  const loadRevision = useRef(0);
  const receiptHeading = useRef(null);
  const attentionHeading = useRef(null);
  const focusRequested = useRef(false);

  // Carga la bandeja (vía el centro de notificaciones si existe) y descarta respuestas viejas.
  const load = useCallback(async (afterWrite = false) => {
    if (loadingRef.current && !afterWrite) return;
    const revision = ++loadRevision.current;
    loadingRef.current = true;
    setLoading(true);
    setError('');
    try {
      const data = refreshInbox ? await refreshInbox(true, afterWrite) : await apiFetch('/api/whatsapp/bandeja');
      if (!['comprobantes', 'cambios', 'atenciones', 'salidas'].every((key) => Array.isArray(data?.[key]))) throw new UserFacingError('No pudimos cargar la bandeja. Intentá actualizarla nuevamente.');
      if (revision === loadRevision.current) setInbox(data);
    } catch (failure) {
      if (revision === loadRevision.current) setError(userErrorMessage(failure, 'No pudimos actualizar la bandeja. Intentá nuevamente.'));
      throw failure;
    } finally {
      if (revision === loadRevision.current) { loadingRef.current = false; setLoading(false); }
    }
  }, [refreshInbox]);

  // Al llegar desde un aviso con sección, carga la bandeja y pide mover el foco.
  useEffect(() => {
    if (!['comprobantes', 'atenciones'].includes(section)) return;
    focusRequested.current = true;
    let active = true;
    void Promise.resolve().then(() => { if (active) return load(); return undefined; }).catch(() => undefined);
    return () => { active = false; };
  }, [section, requestKey, load]);

  // Cuando la bandeja está lista, enfoca la tarjeta del aviso o el encabezado de la sección.
  useEffect(() => {
    if (!focusRequested.current || !expanded || !inbox || loading) return;
    const target = /^whatsapp-(comprobantes|atencion)-[1-9][0-9]*$/.test(notificationTarget || '') ? document.getElementById?.(notificationTarget) : null;
    const heading = target || (section === 'comprobantes' ? receiptHeading.current : attentionHeading.current);
    heading?.focus();
    heading?.scrollIntoView?.({ block: 'nearest' });
    focusRequested.current = false;
  }, [expanded, inbox, loading, section, notificationTarget]);

  // Abre/cierra la bandeja y la carga la primera vez que se abre.
  const toggle = () => {
    setExpansion({ requestKey, expanded: !expanded });
    if (!expanded && !inbox) void load().catch(() => undefined);
  };

  // Tras una revisión se actualizan la bandeja y los datos generales (pedidos, pagos).
  const onReviewed = async (message) => {
    setFeedback(message);
    const results = await Promise.allSettled([load(true), refreshData()]);
    if (results.some((result) => result.status === 'rejected')) {
      setError('La revisión se registró, pero no se pudieron actualizar todos los datos. Usá Actualizar bandeja y comprobá el pedido antes de otra decisión.');
    }
  };

  // Tras responder o resolver una atención, recarga la bandeja e informa si pudo hacerlo.
  const onAttentionChanged = async (message) => {
    if (message) setFeedback(message);
    try {
      await load(true);
      return true;
    } catch {
      return false;
    }
  };

  // Si la revisión falló, recarga para mostrar el estado real y conserva el error.
  const onReviewFailed = async (message) => {
    try {
      await load(true);
      setError(message);
    } catch {
      setError(`${message} No se pudo actualizar la bandeja; actualizala antes de volver a revisar.`);
    }
  };

  return (
    <section className="mb-5 shrink-0 rounded-2xl border border-monu-green/20 bg-monu-cream/30">
      {/* Botón que despliega la bandeja */}
      <button type="button" onClick={toggle} aria-expanded={expanded} aria-controls="whatsapp-inbox-content" className="w-full p-4 flex items-center gap-3 text-left font-extrabold text-monu-dark rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green">
        <MessageCircle aria-hidden="true" className="w-5 h-5 shrink-0" />
        <span className="flex-1">Bandeja de WhatsApp</span>
        <ChevronDown aria-hidden="true" className={`w-5 h-5 shrink-0 ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && (
        <div id="whatsapp-inbox-content" className="px-4 pb-4 space-y-5 max-h-[65dvh] overflow-y-auto">
          {/* Barra de actualización y avisos */}
          <div className="flex flex-wrap gap-3 justify-between items-center">
            <p className="text-sm text-monu-text">Revisión humana de comprobantes, cambios y conversaciones. Actualización manual.</p>
            <button type="button" disabled={loading} onClick={() => { void load().catch(() => undefined); }} className={`${actionClass} flex gap-2 items-center border border-monu-green text-monu-green hover:bg-monu-green/10`}>
              <RefreshCw aria-hidden="true" className="w-4 h-4" />{loading ? 'Actualizando...' : 'Actualizar bandeja'}
            </button>
          </div>
          {feedback && <p role="status" className="text-sm font-bold text-monu-green">{feedback}</p>}
          {error && <p role="alert" className="p-3 rounded-xl bg-red-50 text-red-800 text-sm">{error}</p>}
          {loading && <p role="status" className="text-sm text-monu-text">Consultando la bandeja...</p>}
          {inbox && (
            <>
              {/* Comprobantes (revisiones y atenciones por comprobante) */}
              <div className="space-y-3">
                <h3 ref={receiptHeading} tabIndex={-1} className="font-extrabold text-monu-dark">Comprobantes</h3>
                {inbox.comprobantes.length === 0 && !inbox.atenciones.some((record) => record.motivo === 'COMPROBANTE') && <p className="text-sm text-monu-text">No hay comprobantes recibidos.</p>}
                {inbox.comprobantes.map((record) => <ReviewCard key={`${record.id}:${record.estado}:${record.total}`} record={record} kind="comprobantes" onReviewed={onReviewed} onReviewFailed={onReviewFailed} />)}
                {inbox.atenciones.filter((record) => record.motivo === 'COMPROBANTE').map((record) => <AttentionCard key={record.id} record={record} onChanged={onAttentionChanged} />)}
              </div>
              {/* Cambios de pedido pedidos desde WhatsApp */}
              <div className="space-y-3">
                <h3 className="font-extrabold text-monu-dark">Cambios pendientes de revisión</h3>
                {inbox.cambios.length === 0 && <p className="text-sm text-monu-text">No hay cambios pendientes.</p>}
                {inbox.cambios.map((record) => <ReviewCard key={`${record.id}:${record.version}:${record.posterior?.total}`} record={record} kind="cambios" onReviewed={onReviewed} onReviewFailed={onReviewFailed} />)}
              </div>
              {/* Conversaciones derivadas al personal */}
              <div className="space-y-3">
                <h3 ref={attentionHeading} tabIndex={-1} className="font-extrabold text-monu-dark">Conversaciones que requieren atención</h3>
                {!inbox.atenciones.some((record) => record.motivo !== 'COMPROBANTE') && <p className="text-sm text-monu-text">No hay conversaciones derivadas al personal.</p>}
                {inbox.atenciones.filter((record) => record.motivo !== 'COMPROBANTE').map((record) => <AttentionCard key={record.id} record={record} onChanged={onAttentionChanged} />)}
              </div>
              {/* Estado de los mensajes de salida */}
              <div className="space-y-3">
                <h3 className="font-extrabold text-monu-dark">Estado de los mensajes de salida</h3>
                <p className="text-sm text-monu-text">SIMULADO: no se envió a WhatsApp. INCIERTO: no hay confirmación de envío; verificá antes de reenviar. ACEPTADO: recibido por el proveedor, todavía no confirma entrega al cliente.</p>
                {inbox.salidas.length === 0 && <p className="text-sm text-monu-text">No hay mensajes de salida.</p>}
                <ul className="space-y-2">
                  {inbox.salidas.map((record) => <li key={record.id} className="p-3 rounded-xl bg-white text-sm text-monu-dark border border-monu-green/10">Mensaje #{record.id} · <strong>{knownLabel(deliveryStates, record.estado, 'Estado de envío sin informar.')}</strong> · Intentos: {record.intentos}</li>)}
                </ul>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

/** Bandeja de WhatsApp: solo se muestra con el permiso whatsapp.ver. */
export default function WhatsAppInbox(props) {
  const { user } = useAuth();
  return can(user, 'whatsapp.ver') ? <InboxContent {...props} /> : null;
}
