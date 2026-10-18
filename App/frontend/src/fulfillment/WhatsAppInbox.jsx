import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageCircle, ChevronDown, RefreshCw, Download, Phone, ExternalLink } from 'lucide-react';
import { apiFetch } from '../shared/api/http';
import { useData } from '../shared/store/DataContext';

const actionClass = 'min-h-11 px-4 py-2 rounded-xl text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

async function downloadReceipt(kind, id) {
  // El cliente JSON compartido no admite respuestas binarias.
  const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
  const response = await fetch(`${base}/api/whatsapp/${kind}/${id}/archivo`, { credentials: 'include' });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.mensaje || body?.detail;
    throw new Error(typeof message === 'string' ? message : 'No se pudo descargar el comprobante.');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `comprobante-${kind}-${id}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

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

function ReviewCard({ record, kind, onReviewed, onReviewFailed }) {
  const [reason, setReason] = useState('');
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  const [financialAccepted, setFinancialAccepted] = useState(false);
  const submittingRef = useRef(false);
  const reasonRef = useRef(null);
  const isReceipt = kind === 'comprobantes';
  const pending = isReceipt ? record.estado === 'PENDIENTE' : record.estado === 'PENDIENTE_EMPLEADO';
  const hasReceiptTotal = record.total != null && Number.isFinite(Number(record.total));
  const hasChangeTotal = record.posterior?.total != null && Number.isFinite(Number(record.posterior.total));
  const priceChanged = !isReceipt && record.anterior?.total != null && record.posterior?.total != null
    && Number(record.anterior.total) !== Number(record.posterior.total);
  const cardId = `whatsapp-${kind}-${record.id}`;
  const approvalBlocked = isReceipt
    ? !verified || !hasReceiptTotal
    : !hasChangeTotal || (priceChanged && !financialAccepted);

  const review = async (event) => {
    event.preventDefault();
    if (submittingRef.current) return;
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
      await onReviewed(`Revisión registrada para el pedido #${record.numero || record.pedido_id}: ${result.estado || 'procesada'}.`);
    } catch (failure) {
      const message = failure.message || 'No se pudo registrar la revisión. Volvé a intentarlo.';
      setError(message);
      await onReviewFailed?.(message);
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  };

  const download = async () => {
    if (downloading) return;
    setDownloading(true);
    setError('');
    try {
      await downloadReceipt('comprobantes', record.id);
    } catch (failure) {
      setError(failure.message || 'No se pudo descargar el comprobante.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <article className="p-4 bg-white border border-monu-green/20 rounded-xl space-y-3 min-w-0" aria-labelledby={`${cardId}-title`}>
      <h4 id={`${cardId}-title`} className="font-extrabold text-monu-dark">Pedido #{record.numero || record.pedido_id} · {isReceipt ? 'Comprobante' : 'Cambio'} #{record.id}</h4>
      <p className="text-sm text-monu-text">Estado: <strong>{record.estado}</strong>{!isReceipt && ` · Versión ${record.version}`}</p>
      {isReceipt ? (
        <>
          <p className="text-sm text-monu-dark font-bold">Total vigente a verificar: {hasReceiptTotal ? Number(record.total).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' }) : 'No disponible. Actualizá antes de aprobar.'}</p>
          <p className="text-sm text-monu-text">Forma de pago: {record.metodo_pago || 'No informada'}</p>
          <button type="button" disabled={downloading || busy} onClick={download} className={`${actionClass} flex gap-2 items-center border border-monu-green text-monu-green hover:bg-monu-green/10`}>
            <Download aria-hidden="true" className="w-4 h-4" />{downloading ? 'Descargando...' : 'Descargar comprobante'}
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-monu-text">Acción solicitada: {describeChangeAction(record.accion)}</p>
          <ChangeDetails anterior={record.anterior} posterior={record.posterior} />
          {priceChanged && <p className="text-sm text-orange-800">El cambio no acredita cobros: cualquier saldo adicional queda pendiente. Si hay dinero a devolver, registrá primero la devolución en pagos antes de aprobar. Coordiná el cambio con cocina y caja.</p>}
          <p className="text-sm text-monu-text">El servidor verificará que la versión siga vigente antes de aplicar la decisión.</p>
        </>
      )}
      {error && <p role="alert" id={`${cardId}-error`} className="p-3 rounded-lg bg-red-50 text-red-800 text-sm">{error}</p>}
      {pending ? (
        <form onSubmit={review} className="space-y-3">
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
            <button type="submit" value="rechazar" disabled={busy} className={`${actionClass} border border-red-300 text-red-800 hover:bg-red-50`}>Rechazar</button>
          </div>
        </form>
      ) : record.motivo && <p className="text-sm text-monu-text break-words">Motivo registrado: {record.motivo}</p>}
    </article>
  );
}

const reasonLabels = {
  COMPROBANTE: 'Comprobante sin pedido vinculado. Revisá la conversación antes de registrar un pago.',
  SOLICITUD: 'El cliente pidió atención o el bot no pudo clasificar el mensaje',
  PROVEEDOR: 'Falló el intérprete automático; no se aplicaron cambios',
};

const deliveryStates = {
  PENDIENTE: 'En cola: todavía no se envió. El worker la procesará.',
  ENVIANDO: 'Enviándose ahora.',
  SIMULADO: 'Modo simulado: no se envió a WhatsApp.',
  ACEPTADO: 'Aceptada por WhatsApp; todavía sin confirmación de entrega.',
  ENTREGADO: 'Entregada al cliente.',
  FALLIDO: 'No se envió. Fuera de las 24 horas requiere plantilla: contactá al cliente por teléfono.',
  INCIERTO: 'Sin confirmación del proveedor: verificá antes de volver a responder.',
};

function newRequestId() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function AttentionForm({ id, label, help, maxLength, submitLabel, busyLabel, onSubmit }) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const fieldRef = useRef(null);
  const submittingRef = useRef(false);

  const submit = async (event) => {
    event.preventDefault();
    if (submittingRef.current) return;
    if (!value.trim()) {
      setError('Completá este campo antes de continuar.');
      fieldRef.current?.focus();
      return;
    }
    submittingRef.current = true;
    setBusy(true);
    setError('');
    setResult('');
    try {
      setResult(await onSubmit(value.trim()));
      setValue('');
    } catch (failure) {
      setError(failure.message || 'No se pudo completar la operación. Volvé a intentarlo.');
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor={id} className="block text-sm font-bold text-monu-dark">{label}</label>
      <textarea id={id} ref={fieldRef} maxLength={maxLength} rows={3} disabled={busy} value={value} onChange={(event) => setValue(event.target.value)} aria-describedby={`${id}-help${error ? ` ${id}-error` : ''}`} aria-invalid={error ? 'true' : undefined} className="w-full px-3 py-2 text-base border border-monu-green/30 rounded-lg focus:outline-none focus:ring-2 focus:ring-monu-green" />
      <p id={`${id}-help`} className="text-xs text-monu-text">{help} {value.length}/{maxLength}</p>
      {error && <p id={`${id}-error`} role="alert" className="p-2 rounded-lg bg-red-50 text-red-800 text-sm">{error}</p>}
      {result && <p role="status" className="text-sm font-bold text-monu-green">{result}</p>}
      <button type="submit" disabled={busy} className={`${actionClass} bg-monu-green text-white hover:bg-monu-green/90`}>{busy ? busyLabel : submitLabel}</button>
    </form>
  );
}

function AttentionCard({ record, onChanged }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const requestIdRef = useRef(newRequestId());
  const cardId = `whatsapp-atencion-${record.id}`;
  const phone = /^[0-9]{11,15}$/.test(record.telefono || '') ? record.telefono : null;
  const title = record.pedido_id ? `Pedido #${record.numero || record.pedido_id}` : 'Conversación sin pedido registrado';

  const reply = async (text) => {
    // El mismo identificador en un reintento evita encolar la respuesta dos veces.
    const result = await apiFetch(`/api/whatsapp/atenciones/${record.id}/respuesta`, {
      method: 'POST',
      body: JSON.stringify({ texto: text, solicitud_id: requestIdRef.current }),
    });
    requestIdRef.current = newRequestId();
    const refreshed = await onChanged();
    const state = deliveryStates[result.estado] || result.estado;
    return `Respuesta #${result.id} registrada en la cola de salida. Estado: ${result.estado}. ${state}${refreshed ? '' : ' No se pudo actualizar la bandeja; actualizala para ver el envío.'}`;
  };

  const resolve = async (text) => {
    const result = await apiFetch(`/api/whatsapp/atenciones/${record.id}/resolucion`, {
      method: 'POST',
      body: JSON.stringify({ resolucion: text }),
    });
    const refreshed = await onChanged(`Atención de ${title.toLowerCase()} marcada como ${result.estado.toLowerCase()}.`);
    return refreshed ? 'Atención resuelta.' : 'Atención resuelta, pero no se pudo actualizar la bandeja. Actualizala.';
  };

  return (
    <article className="p-4 bg-white border border-orange-200 rounded-xl space-y-3 min-w-0" aria-labelledby={`${cardId}-title`}>
      <h4 id={`${cardId}-title`} className="font-extrabold text-monu-dark">{title} · Atención #{record.id}</h4>
      <p className="text-sm text-orange-900">{reasonLabels[record.motivo] || 'Requiere atención de personal'}</p>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
        <dt className="font-bold text-monu-dark">Cliente</dt><dd className="text-monu-text break-words">{record.cliente || 'Sin nombre registrado'}</dd>
        <dt className="font-bold text-monu-dark">Teléfono</dt><dd className="text-monu-text">{phone ? `+${phone}` : 'No disponible'}</dd>
        <dt className="font-bold text-monu-dark">Estado</dt><dd className="text-monu-text">{record.pedido_id ? `Pedido ${record.estado_pedido}` : record.estado_conversacion ? 'Borrador sin pedido operativo' : 'Consulta sin compra vinculada'}{record.total != null && ` · Total ${Number(record.total).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' })}`}</dd>
        <dt className="font-bold text-monu-dark">Entrega y pago</dt><dd className="text-monu-text">{record.tipo_entrega || 'Entrega sin definir'} · {record.metodo_pago || 'Pago sin definir'}</dd>
      </dl>
      {record.tiene_archivo && record.motivo === 'COMPROBANTE' && <button type="button" disabled={downloading} className={`${actionClass} inline-flex items-center gap-2 border border-monu-green text-monu-green hover:bg-monu-green/10`} onClick={async () => {
        if (downloading) return;
        setDownloading(true);
        setDownloadError('');
        try { await downloadReceipt('atenciones', record.id); } catch (failure) { setDownloadError(failure.message); } finally { setDownloading(false); }
      }}><Download aria-hidden="true" className="h-4 w-4" />{downloading ? 'Descargando...' : 'Descargar comprobante'}</button>}
      {downloadError && <p role="alert" className="text-sm text-red-800">{downloadError}</p>}
      {record.borrador_vencido && <p className="p-2 rounded-lg bg-orange-50 text-orange-900 text-sm">El borrador venció: el cliente debe prepararlo nuevamente desde la web. Sus datos siguen visibles aquí.</p>}
      {record.productos?.length > 0 && (
        <ul className="text-sm text-monu-dark list-disc pl-5">
          {record.productos.map((item, index) => <li key={index} className="break-words">{item.cantidad} × {item.nombre}{item.aclaraciones ? ` (${item.aclaraciones})` : ''}</li>)}
        </ul>
      )}
      <div className="space-y-1">
        <p className="text-sm font-bold text-monu-dark">Mensaje que originó la atención</p>
        <p className="p-3 rounded-lg bg-monu-cream/40 text-sm text-monu-dark whitespace-pre-wrap break-words max-h-48 overflow-y-auto">{record.mensaje || 'Mensaje sin texto'}</p>
      </div>
      {record.mensajes?.length > 0 && (
        <details className="text-sm">
          <summary className="min-h-11 flex items-center cursor-pointer font-bold text-monu-dark rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green">Últimos mensajes de la conversación ({record.mensajes.length})</summary>
          <ol className="mt-2 space-y-2">
            {record.mensajes.map((message, index) => (
              <li key={index} className="p-2 rounded-lg border border-monu-green/10 space-y-1 break-words">
                <p><strong>Cliente:</strong> <span className="whitespace-pre-wrap">{message.texto || 'Adjunto o mensaje sin texto'}</span></p>
                {message.respuesta && <p className="text-monu-text"><strong>Bot:</strong> <span className="whitespace-pre-wrap">{message.respuesta}</span></p>}
              </li>
            ))}
          </ol>
        </details>
      )}
      {phone && (
        <div className="flex flex-wrap gap-3">
          <a href={`https://wa.me/${phone}`} target="_blank" rel="noopener noreferrer" className={`${actionClass} inline-flex gap-2 items-center border border-monu-green text-monu-green hover:bg-monu-green/10`}>
            <ExternalLink aria-hidden="true" className="w-4 h-4" />Abrir chat en WhatsApp<span className="sr-only"> (se abre en otra pestaña)</span>
          </a>
          <a href={`tel:+${phone}`} className={`${actionClass} inline-flex gap-2 items-center border border-monu-green text-monu-green hover:bg-monu-green/10`}>
            <Phone aria-hidden="true" className="w-4 h-4" />Llamar
          </a>
        </div>
      )}
      <div className="space-y-2">
        <p className="text-sm font-bold text-monu-dark">Respuestas del personal</p>
        {record.respuestas?.length ? (
          <ul className="space-y-2">
            {record.respuestas.map((answer) => (
              <li key={answer.id} className="p-2 rounded-lg border border-monu-green/10 text-sm break-words space-y-1">
                <p className="whitespace-pre-wrap text-monu-dark">{answer.texto}</p>
                <p className="text-monu-text"><strong>{answer.estado}</strong> · {deliveryStates[answer.estado] || 'Estado desconocido.'}{answer.empleado ? ` · ${answer.empleado}` : ''}</p>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-monu-text">Todavía no se respondió desde la bandeja.</p>}
      </div>
      <AttentionForm id={`${cardId}-respuesta`} label="Responder por WhatsApp" help="Se agrega a la cola de salida; el estado de envío aparece en esta tarjeta al actualizar." maxLength={1000} submitLabel="Encolar respuesta" busyLabel="Encolando..." onSubmit={reply} />
      <AttentionForm id={`${cardId}-resolucion`} label="Cómo se resolvió (obligatorio para cerrar)" help="Registra tu decisión; no envía mensajes al cliente." maxLength={500} submitLabel="Marcar como resuelta" busyLabel="Guardando..." onSubmit={resolve} />
    </article>
  );
}

export default function WhatsAppInbox({ section, requestKey }) {
  const { refreshData } = useData();
  const [expansion, setExpansion] = useState({ requestKey: null, expanded: false });
  const requestedSection = ['comprobantes', 'atenciones'].includes(section);
  const expanded = requestedSection && expansion.requestKey !== requestKey ? true : expansion.expanded;
  const [inbox, setInbox] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const loadingRef = useRef(false);
  const receiptHeading = useRef(null);
  const attentionHeading = useRef(null);
  const focusRequested = useRef(false);

  const load = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    setError('');
    try {
      setInbox(await apiFetch('/api/whatsapp/bandeja'));
    } catch (failure) {
      setError(failure.message || 'No se pudo actualizar la bandeja. Intentá nuevamente.');
      throw failure;
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!['comprobantes', 'atenciones'].includes(section)) return;
    focusRequested.current = true;
    let active = true;
    void Promise.resolve().then(() => { if (active) return load(); return undefined; }).catch(() => undefined);
    return () => { active = false; };
  }, [section, requestKey, load]);

  useEffect(() => {
    if (!focusRequested.current || !expanded || !inbox || loading) return;
    const heading = section === 'comprobantes' ? receiptHeading.current : attentionHeading.current;
    heading?.focus();
    heading?.scrollIntoView?.({ block: 'nearest' });
    focusRequested.current = false;
  }, [expanded, inbox, loading, section]);

  const toggle = () => {
    setExpansion({ requestKey, expanded: !expanded });
    if (!expanded && !inbox) void load().catch(() => undefined);
  };

  const onReviewed = async (message) => {
    setFeedback(message);
    const results = await Promise.allSettled([load(), refreshData()]);
    if (results.some((result) => result.status === 'rejected')) {
      setError('La revisión se registró, pero no se pudieron actualizar todos los datos. Usá Actualizar bandeja y comprobá el pedido antes de otra decisión.');
    }
  };

  const onAttentionChanged = async (message) => {
    if (message) setFeedback(message);
    try {
      await load();
      return true;
    } catch {
      return false;
    }
  };

  const onReviewFailed = async (message) => {
    try {
      await load();
      setError(message);
    } catch {
      setError(`${message} No se pudo actualizar la bandeja; actualizala antes de volver a revisar.`);
    }
  };

  return (
    <section className="mb-5 shrink-0 rounded-2xl border border-monu-green/20 bg-monu-cream/30">
      <button type="button" onClick={toggle} aria-expanded={expanded} aria-controls="whatsapp-inbox-content" className="w-full p-4 flex items-center gap-3 text-left font-extrabold text-monu-dark rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green">
        <MessageCircle aria-hidden="true" className="w-5 h-5 shrink-0" />
        <span className="flex-1">Bandeja de WhatsApp</span>
        <ChevronDown aria-hidden="true" className={`w-5 h-5 shrink-0 ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && (
        <div id="whatsapp-inbox-content" className="px-4 pb-4 space-y-5 max-h-[65dvh] overflow-y-auto">
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
              <div className="space-y-3">
                <h3 ref={receiptHeading} tabIndex={-1} className="font-extrabold text-monu-dark">Comprobantes</h3>
                {inbox.comprobantes.length === 0 && !inbox.atenciones.some((record) => record.motivo === 'COMPROBANTE') && <p className="text-sm text-monu-text">No hay comprobantes recibidos.</p>}
                {inbox.comprobantes.map((record) => <ReviewCard key={`${record.id}:${record.estado}:${record.total}`} record={record} kind="comprobantes" onReviewed={onReviewed} onReviewFailed={onReviewFailed} />)}
                {inbox.atenciones.filter((record) => record.motivo === 'COMPROBANTE').map((record) => <AttentionCard key={record.id} record={record} onChanged={onAttentionChanged} />)}
              </div>
              <div className="space-y-3">
                <h3 className="font-extrabold text-monu-dark">Cambios pendientes de revisión</h3>
                {inbox.cambios.length === 0 && <p className="text-sm text-monu-text">No hay cambios pendientes.</p>}
                {inbox.cambios.map((record) => <ReviewCard key={`${record.id}:${record.version}:${record.posterior?.total}`} record={record} kind="cambios" onReviewed={onReviewed} onReviewFailed={onReviewFailed} />)}
              </div>
              <div className="space-y-3">
                <h3 ref={attentionHeading} tabIndex={-1} className="font-extrabold text-monu-dark">Conversaciones que requieren atención</h3>
                {!inbox.atenciones.some((record) => record.motivo !== 'COMPROBANTE') && <p className="text-sm text-monu-text">No hay conversaciones derivadas al personal.</p>}
                {inbox.atenciones.filter((record) => record.motivo !== 'COMPROBANTE').map((record) => <AttentionCard key={record.id} record={record} onChanged={onAttentionChanged} />)}
              </div>
              <div className="space-y-3">
                <h3 className="font-extrabold text-monu-dark">Estado de los mensajes de salida</h3>
                <p className="text-sm text-monu-text">SIMULADO: no se envió a WhatsApp. INCIERTO: no hay confirmación de envío; verificá antes de reenviar. ACEPTADO: recibido por el proveedor, todavía no confirma entrega al cliente.</p>
                {inbox.salidas.length === 0 && <p className="text-sm text-monu-text">No hay mensajes de salida.</p>}
                <ul className="space-y-2">
                  {inbox.salidas.map((record) => <li key={record.id} className="p-3 rounded-xl bg-white text-sm text-monu-dark border border-monu-green/10">Mensaje #{record.id} · <strong>{record.estado}</strong> · Intentos: {record.intentos}</li>)}
                </ul>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
