import { useEffect, useRef, useState } from 'react';
import { Info, LoaderCircle, MessageCircle, Paperclip, Send, X } from 'lucide-react';
import { chatMessageStatus, getChatConversation, getPendingChatSend, openChatSession, reconcileChatSend, sendChatReceipt, sendChatText } from './chatDemo';

const buttonClass = 'min-h-11 min-w-11 inline-flex items-center justify-center gap-2 rounded-xl px-3 font-bold active:opacity-75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

function messageText(value) {
  return value.split(/(\*[^*\n]+\*)/g).map((part, index) => part.startsWith('*') && part.endsWith('*') && part.length > 2
    ? <strong key={index}>{part.slice(1, -1)}</strong> : part);
}

export default function ChatDrawer({ isOpen, onClose }) {
  const [conversation, setConversation] = useState(null);
  const [checkedAt, setCheckedAt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const [sendError, setSendError] = useState(() => getPendingChatSend() ? 'Hay un envío sin confirmar. Recuperaremos el historial antes de continuar; podés reintentar el mismo contenido.' : '');
  const [text, setText] = useState(() => getPendingChatSend()?.text || '');
  const [retry, setRetry] = useState(getPendingChatSend);
  const [revision, setRevision] = useState(0);
  const [showInfo, setShowInfo] = useState(false);
  const [showAttachment, setShowAttachment] = useState(false);
  const [localMessage, setLocalMessage] = useState(null);
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const timelineRef = useRef(null);
  const epoch = useRef(0);
  const mutation = useRef(0);
  const busyRef = useRef(false);
  const refreshRef = useRef(null);
  const localMessageRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    const overflow = document.body.style.overflow;
    dialog.showModal();
    if (inputRef.current?.disabled) closeRef.current?.focus();
    else inputRef.current?.focus();
    document.body.style.overflow = 'hidden';
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && !loading && document.activeElement === closeRef.current) inputRef.current?.focus();
  }, [isOpen, loading]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const current = ++epoch.current;
    let polling = false;
    let initialized = false;
    let refreshRequested = false;
    let timer;
    let waiting = false;
    const refresh = async () => {
      window.clearTimeout(timer);
      if (document.hidden || epoch.current !== current) return;
      if (polling) { refreshRequested = true; return; }
      polling = true;
      let failed = false;
      const version = mutation.current;
      try {
        const data = initialized ? await getChatConversation() : await openChatSession();
        initialized = true;
        if (epoch.current === current && mutation.current === version) {
          const unresolved = getPendingChatSend();
          if (reconcileChatSend(data)) {
            setRetry(null);
            setSendError('');
            setText((value) => value === unresolved.text ? '' : value);
          }
          const local = localMessageRef.current;
          if (local?.id && data.mensajes.some((message) => message.id === local.id)) {
            localMessageRef.current = null;
            setLocalMessage(null);
          }
          waiting = data.mensajes.some((message) => message.direccion === 'cliente' && message.estado === 'PENDIENTE');
          setConversation(data);
          setCheckedAt(Date.now());
          setFetchError('');
        }
      } catch (failure) {
        failed = true;
        if (epoch.current === current) setFetchError((failure.message || 'No pudimos actualizar la conversación.') + ' El historial visible puede estar desactualizado.');
      } finally {
        polling = false;
        if (epoch.current === current) {
          setLoading(false);
          if (refreshRequested) { refreshRequested = false; void refresh(); }
          else if (!document.hidden) timer = window.setTimeout(refresh, !failed && (waiting || localMessageRef.current) ? 600 : 6000);
        }
      }
    };
    refreshRef.current = refresh;
    void refresh();
    document.addEventListener('visibilitychange', refresh);
    return () => { epoch.current += 1; refreshRef.current = null; window.clearTimeout(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [isOpen]);

  useEffect(() => {
    if (revision) void refreshRef.current?.();
  }, [revision]);

  const lastMessage = conversation?.mensajes?.at(-1);
  useEffect(() => {
    const timeline = timelineRef.current;
    if (timeline) timeline.scrollTop = timeline.scrollHeight;
  }, [lastMessage?.id, localMessage?.id, localMessage?.estado]);

  const send = async (operation) => {
    if (busyRef.current) return;
    busyRef.current = true;
    mutation.current += 1;
    setSending(true);
    setSendError('');
    const outgoing = { direccion: 'cliente', texto: operation.file ? `Comprobante: ${operation.file.name || 'archivo'}` : operation.text.trim(), estado: 'ENVIANDO_LOCAL', creado_en: new Date().toISOString(), tiene_archivo: !!operation.file };
    localMessageRef.current = outgoing;
    setLocalMessage(outgoing);
    if (!operation.file && !operation.preserveText) setText((value) => value === operation.text ? '' : value);
    try {
      const acknowledgement = operation.file ? await sendChatReceipt(operation.file) : await sendChatText(operation.text);
      const saved = { ...outgoing, ...acknowledgement };
      localMessageRef.current = saved;
      setLocalMessage(saved);
      if (fileRef.current) fileRef.current.value = '';
      setShowAttachment(false);
      setRetry(null);
      setRevision((value) => value + 1);
    } catch (failure) {
      localMessageRef.current = null;
      setLocalMessage(null);
      if (!operation.file && !operation.preserveText) setText((value) => value || operation.text);
      const unresolved = getPendingChatSend();
      setSendError((failure.message || 'No pudimos enviar.') + (unresolved ? ' No confirmamos el resultado; recuperá el mismo envío antes de continuar.' : ''));
      setRetry(unresolved ? { ...unresolved, preserveText: operation.preserveText || (unresolved.text && unresolved.text !== text) } : null);
    } finally {
      busyRef.current = false;
      setSending(false);
    }
  };

  if (!isOpen) return null;
  const savedMessages = conversation?.mensajes || [];
  const messages = localMessage && !savedMessages.some((message) => message.id === localMessage.id)
    ? [...savedMessages, localMessage] : savedMessages;
  const error = sendError || fetchError;
  const pending = messages.some((message) => message.direccion === 'cliente' && message.estado === 'PENDIENTE');
  const delayed = messages.some((message) => message.direccion === 'cliente' && message.estado === 'PENDIENTE' && checkedAt - Date.parse(message.creado_en) > 90000);
  const unavailable = !conversation || sending || !!retry || !!localMessage || pending || !!fetchError;
  return (
    <dialog ref={dialogRef} aria-labelledby="chat-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="fixed inset-0 m-auto h-[min(48rem,calc(100dvh_-_1rem))] w-[calc(100%_-_1rem)] max-w-xl overflow-hidden rounded-3xl border border-monu-green/10 bg-monu-bone p-0 text-monu-text shadow-monu-lg backdrop:bg-black/55 backdrop:backdrop-blur-sm">
      <div className="flex h-full min-h-0 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-monu-green/10 bg-white px-3 py-2 sm:px-4">
          <div className="min-w-0">
            <h2 id="chat-title" className="flex items-center gap-2 font-heading text-base font-extrabold text-monu-dark sm:text-lg"><MessageCircle aria-hidden="true" className="size-5 shrink-0 text-monu-green" />Chat Monu Burger</h2>
            <span className="ml-7 text-xs text-monu-text/80">Demo</span>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button type="button" onClick={() => { setShowInfo((value) => !value); setShowAttachment(false); }} aria-label="Información y opciones del chat" aria-expanded={showInfo} aria-controls="chat-info" className={buttonClass + ' text-monu-green hover:bg-monu-green/10'}><Info aria-hidden="true" className="size-5" /></button>
            <button ref={closeRef} type="button" onClick={onClose} aria-label="Cerrar chat" className={buttonClass + ' hover:bg-monu-green/10'}><X aria-hidden="true" className="size-5" /></button>
          </div>
        </header>
        {showInfo && <section id="chat-info" aria-label="Información y opciones del chat" className="max-h-[40%] shrink-0 overflow-y-auto border-b border-monu-green/10 bg-white px-4 py-3 text-sm">
          <p>Demostración: los mensajes no se envían por WhatsApp.</p>
          {conversation && <p className="mt-1 text-xs text-monu-text/80">{conversation.interpretador === 'real' ? conversation.gemini_configurado ? 'Interpretación con Gemini configurado' : 'Gemini sin configurar · podés pedir atención humana' : 'Interpretación simulada'}</p>}
          {(conversation?.borradores || []).map((draft, index) => {
            const expired = !draft.pedido_id && Date.parse(draft.expira_en) <= checkedAt;
            return <p key={draft.pedido_id || index} className="mt-2 text-xs">{draft.pedido_id
              ? `Pedido #${draft.numero || draft.pedido_id} · ${draft.estado_pedido || draft.estado}${draft.total != null ? ` · $${Number(draft.total).toLocaleString('es-AR')}` : ''}`
              : expired ? <>Borrador vencido · venció el <time dateTime={draft.expira_en}>{new Date(draft.expira_en).toLocaleString('es-AR')}</time></>
                : `Borrador ${draft.estado} · pendiente de completar`}</p>;
          })}
          <p id="chat-send-help" className="mt-2 text-xs text-monu-text/80">Enter envía; Mayús + Enter agrega una línea.</p>
          {conversation && <div className="mt-2 flex flex-wrap gap-2" aria-label="Acciones de la conversación">
            <button type="button" disabled={unavailable} onClick={() => { inputRef.current?.focus(); setShowInfo(false); void send({ text: 'ayuda', preserveText: true }); }} className={buttonClass + ' text-sm text-monu-green hover:bg-monu-green/10'}>Ver opciones</button>
            <button type="button" disabled={unavailable} onClick={() => { inputRef.current?.focus(); setShowInfo(false); void send({ text: 'resumen', preserveText: true }); }} className={buttonClass + ' text-sm text-monu-green hover:bg-monu-green/10'}>Consultar resumen</button>
            <button type="button" disabled={unavailable} onClick={() => { inputRef.current?.focus(); setShowInfo(false); void send({ text: 'empleado', preserveText: true }); }} className={buttonClass + ' text-sm text-monu-green hover:bg-monu-green/10'}>Pedir atención humana</button>
          </div>}
        </section>}
        {error && <div role="alert" className="max-h-[30%] shrink-0 overflow-y-auto border-b border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <p>{error}</p>
          {fetchError && sendError && <p className="mt-1">{fetchError}</p>}
          {retry?.fileName && !retry.file && <p className="mt-1 break-words">Volvé a elegir el mismo comprobante: {retry.fileName}. El archivo no se guarda en el navegador.</p>}
          <button type="button" disabled={sending} onClick={() => retry ? retry.fileName && !retry.file ? fileRef.current?.click() : void send(retry) : setRevision((value) => value + 1)} className={buttonClass + ' mt-1 underline'}>{retry ? retry.fileName && !retry.file ? 'Elegir el mismo comprobante' : 'Reintentar mismo envío' : 'Actualizar conversación'}</button>
        </div>}
        <div ref={timelineRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-4 sm:px-4">
          {loading && !conversation && <p role="status" className="py-4 text-sm">Recuperando conversación…</p>}
          {!loading && conversation && !messages.length && <p className="py-4 text-sm text-monu-text/80">¿En qué te ayudamos? Podés traer tu pedido desde el carrito.</p>}
          <ol role="log" aria-live="polite" aria-relevant="additions" aria-label="Mensajes de la conversación" className="space-y-3">
            {messages.map((message) => <li key={message.id || 'enviando-local'} aria-label={message.direccion === 'cliente' ? 'Vos' : 'Monu Burger'} className={'flex ' + (message.direccion === 'cliente' ? 'justify-end' : 'justify-start')}>
              <div className={'max-w-[90%] rounded-2xl px-3 py-2 sm:max-w-[85%] ' + (message.direccion === 'cliente' ? 'bg-monu-green/10' : 'border border-monu-green/10 bg-white')}>
                <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{message.direccion === 'cliente' ? message.texto : messageText(message.texto)}</p>
                {message.tiene_archivo && <p className="mt-1 flex items-center gap-1 text-xs"><Paperclip aria-hidden="true" className="size-3" />Comprobante · pendiente de revisión</p>}
                <p className="mt-1 flex flex-wrap justify-end gap-x-2 gap-y-1 text-xs text-monu-text/80"><time dateTime={message.creado_en}>{new Date(message.creado_en).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}</time>{message.estado === 'ENVIANDO_LOCAL' ? <span>Enviando…</span> : ['FALLIDO', 'INCIERTO'].includes(message.estado) ? <span>{chatMessageStatus(message)}</span> : null}</p>
              </div>
            </li>)}
          </ol>
        </div>
        {(pending || localMessage?.estado === 'PROCESADO') && <p role="status" className="flex shrink-0 items-center gap-2 px-4 pb-2 text-xs text-monu-text/80"><LoaderCircle aria-hidden="true" className="size-3 shrink-0 motion-safe:animate-spin" />{fetchError ? 'Sin conexión. Esperando recuperar el resultado.' : delayed ? 'Está demorando. Tu mensaje está guardado; no hace falta reenviarlo.' : 'Esperando respuesta…'}</p>}
        <form className="shrink-0 border-t border-monu-green/10 bg-white p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:px-3" onSubmit={(event) => { event.preventDefault(); if (!unavailable && text.trim()) void send({ text }); }}>
          {showAttachment && <div id="chat-attachment" className="mb-2 rounded-xl bg-monu-bone px-3 py-2 text-xs">
            <p>Comprobante ficticio: PDF, PNG o JPEG hasta 2 MiB. Adjuntarlo no acredita dinero.</p>
            <button type="button" disabled={unavailable} onClick={() => fileRef.current?.click()} className={buttonClass + ' mt-1 text-sm text-monu-green hover:bg-monu-green/10'}>Elegir comprobante</button>
          </div>}
          <div className="flex items-end gap-2">
            <button type="button" aria-label="Adjuntar comprobante" aria-expanded={showAttachment} aria-controls="chat-attachment" disabled={unavailable} onClick={() => { setShowAttachment((value) => !value); setShowInfo(false); }} className={buttonClass + ' shrink-0 text-monu-green hover:bg-monu-green/10'}><Paperclip aria-hidden="true" className="size-5" /></button>
            <label htmlFor="chat-text" className="sr-only">Tu mensaje</label>
            <textarea ref={inputRef} id="chat-text" placeholder="Escribí un mensaje…" value={text} onChange={(event) => setText(event.target.value)} maxLength={2000} rows={Math.min(2, text.split('\n').length)} disabled={!conversation || !!retry || !!fetchError} aria-describedby={showInfo ? 'chat-send-help' : undefined}
              onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!unavailable && text.trim()) void send({ text }); } }}
              className="max-h-28 min-h-11 min-w-0 flex-1 resize-y rounded-xl border border-monu-green/25 bg-monu-bone px-3 py-2 text-base leading-6 focus:outline-none focus:ring-2 focus:ring-monu-green disabled:opacity-50" />
            <input ref={fileRef} type="file" accept="application/pdf,image/png,image/jpeg" aria-label="Elegir comprobante ficticio" className="sr-only" tabIndex={-1} disabled={sending || (!retry?.fileName && unavailable)} onChange={(event) => { const file = event.target.files?.[0]; if (file) void send({ file }); event.target.value = ''; }} />
            <button type="submit" aria-label="Enviar mensaje" disabled={unavailable || !text.trim()} aria-busy={sending} className={buttonClass + ' shrink-0 bg-monu-green text-white hover:bg-monu-dark'}>{sending ? <LoaderCircle aria-hidden="true" className="size-5 motion-safe:animate-spin" /> : <Send aria-hidden="true" className="size-5" />}</button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
