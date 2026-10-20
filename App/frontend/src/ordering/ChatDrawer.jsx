import { useEffect, useRef, useState } from 'react';
import { MessageCircle, Paperclip, Send, X } from 'lucide-react';
import { chatMessageStatus, getChatConversation, openChatSession, sendChatReceipt, sendChatText } from './chatDemo';

const buttonClass = 'min-h-11 min-w-11 inline-flex items-center justify-center gap-2 rounded-xl px-3 font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

export default function ChatDrawer({ isOpen, onClose }) {
  const [conversation, setConversation] = useState(null);
  const [checkedAt, setCheckedAt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const [sendError, setSendError] = useState('');
  const [text, setText] = useState('');
  const [retry, setRetry] = useState(null);
  const [revision, setRevision] = useState(0);
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const timelineRef = useRef(null);
  const epoch = useRef(0);
  const mutation = useRef(0);
  const busyRef = useRef(false);

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
    const refresh = async () => {
      if (document.hidden || polling) return;
      polling = true;
      const version = mutation.current;
      try {
        const data = initialized ? await getChatConversation() : await openChatSession();
        initialized = true;
        if (epoch.current === current && mutation.current === version) {
          setConversation(data);
          setCheckedAt(Date.now());
          setFetchError('');
        }
      } catch (failure) {
        if (epoch.current === current) setFetchError(failure.message || 'No pudimos actualizar la conversación.');
      } finally {
        polling = false;
        if (epoch.current === current) setLoading(false);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 2000);
    document.addEventListener('visibilitychange', refresh);
    return () => { epoch.current += 1; window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [isOpen, revision]);

  const lastMessage = conversation?.mensajes?.at(-1);
  useEffect(() => {
    const timeline = timelineRef.current;
    if (timeline) timeline.scrollTop = timeline.scrollHeight;
  }, [lastMessage?.id]);

  const send = async (operation) => {
    if (busyRef.current) return;
    busyRef.current = true;
    mutation.current += 1;
    setSending(true);
    setSendError('');
    setRetry(null);
    try {
      if (operation.file) await sendChatReceipt(operation.file);
      else await sendChatText(operation.text);
      if (!operation.file && !operation.preserveText) setText('');
      if (fileRef.current) fileRef.current.value = '';
      setRevision((value) => value + 1);
    } catch (failure) {
      setSendError(failure.message || 'No pudimos enviar. Reintentá con el mismo contenido.');
      setRetry(operation);
    } finally {
      busyRef.current = false;
      setSending(false);
    }
  };

  if (!isOpen) return null;
  const messages = conversation?.mensajes || [];
  const error = sendError || fetchError;
  const pending = messages.some((message) => message.direccion === 'cliente' && message.estado === 'PENDIENTE');
  const offerHuman = conversation && (!messages.length || (conversation.interpretador === 'real' && !conversation.gemini_configurado));
  return (
    <dialog ref={dialogRef} aria-labelledby="chat-title" aria-describedby="chat-demo-help"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="fixed inset-0 m-auto h-[min(48rem,calc(100dvh_-_1rem))] w-[calc(100%_-_1rem)] max-w-xl overflow-hidden rounded-3xl border border-monu-green/10 bg-monu-bone p-0 text-monu-text shadow-monu-lg backdrop:bg-black/55 backdrop:backdrop-blur-sm">
      <div className="flex h-full min-h-0 flex-col">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-monu-green/10 bg-white px-4 py-4 sm:px-6">
          <div>
            <h2 id="chat-title" className="flex items-center gap-2 font-heading text-xl font-extrabold text-monu-dark"><MessageCircle aria-hidden="true" className="size-5 text-monu-green" />Chat Monu Burger</h2>
            <p id="chat-demo-help" className="mt-1 text-xs leading-relaxed">Demostración: los mensajes no se envían por WhatsApp.</p>
            {conversation && <p className="mt-1 text-xs font-semibold text-monu-green">{conversation.interpretador === 'real' ? conversation.gemini_configurado ? 'Interpretación con Gemini configurado' : 'Gemini sin configurar · podés pedir atención humana' : 'Interpretación simulada'}</p>}
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Cerrar chat" className={buttonClass + ' hover:bg-monu-green/10'}><X aria-hidden="true" className="size-5" /></button>
        </header>
        {error && <div role="alert" className="shrink-0 border-b border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <p>{error}</p>
          <button type="button" disabled={sending} onClick={() => sendError && retry ? void send(retry) : setRevision((value) => value + 1)} className={buttonClass + ' mt-1 underline'}>{sendError && retry ? 'Reintentar mismo envío' : 'Actualizar conversación'}</button>
        </div>}
        <div ref={timelineRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
          {loading && !conversation && <p role="status" className="py-4 text-sm">Recuperando conversación…</p>}
          {!loading && conversation && !messages.length && <p className="rounded-2xl border border-monu-green/15 bg-white p-4 text-sm leading-relaxed">Armá tu pedido en el menú y elegí «Continuar en el chat» desde el carrito. También podés pedir atención humana acá.</p>}
          <ol role="log" aria-live="polite" aria-relevant="additions" aria-label="Mensajes de la conversación" className="space-y-4">
            {messages.map((message) => <li key={message.id} className={'flex ' + (message.direccion === 'cliente' ? 'justify-end' : 'justify-start')}>
              <div className={'max-w-[90%] rounded-2xl border px-4 py-3 sm:max-w-[85%] ' + (message.direccion === 'cliente' ? 'border-monu-green/15 bg-monu-green/10' : 'border-monu-green/10 bg-white')}>
                <p className="mb-1 text-xs font-bold text-monu-green">{message.direccion === 'cliente' ? 'Vos' : 'Monu Burger'}</p>
                <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{message.texto}</p>
                {message.tiene_archivo && <p className="mt-2 flex items-center gap-1 text-xs font-semibold"><Paperclip aria-hidden="true" className="size-3" />Comprobante adjunto · requiere revisión humana</p>}
                <p className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs text-monu-text/80"><time dateTime={message.creado_en}>{new Date(message.creado_en).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}</time><span>{chatMessageStatus(message)}</span></p>
              </div>
            </li>)}
          </ol>
        </div>
        <div className="max-h-[25%] shrink-0 overflow-y-auto border-t border-monu-green/10 bg-white px-4 text-xs leading-relaxed sm:px-6">
          {(conversation?.borradores || []).map((draft, index) => {
            const expired = !draft.pedido_id && Date.parse(draft.expira_en) <= checkedAt;
            return <p key={draft.pedido_id || index} className="py-2">{draft.pedido_id
              ? `Pedido #${draft.numero || draft.pedido_id} · ${draft.estado_pedido || draft.estado}${draft.total != null ? ` · $${Number(draft.total).toLocaleString('es-AR')}` : ''}`
              : expired ? <>Borrador vencido · venció el <time dateTime={draft.expira_en}>{new Date(draft.expira_en).toLocaleString('es-AR')}</time></>
                : `Borrador ${draft.estado} · pendiente de completar`}</p>;
          })}
          {pending && <p role="status" className="py-2">Hay mensajes pendientes. El procesamiento puede demorar; el chat se actualiza automáticamente.</p>}
          {offerHuman && <button type="button" disabled={sending} onClick={() => void send({ text: 'quiero hablar con una persona', preserveText: true })} className={buttonClass + ' my-2 text-monu-green underline hover:bg-monu-green/10'}>Pedir atención humana</button>}
        </div>
        <form className="shrink-0 space-y-2 border-t border-monu-green/10 bg-white px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:px-6" onSubmit={(event) => { event.preventDefault(); void send({ text }); }}>
          <label htmlFor="chat-text" className="text-sm font-bold text-monu-dark">Tu mensaje</label>
          <textarea ref={inputRef} id="chat-text" value={text} onChange={(event) => setText(event.target.value)} maxLength={2000} rows={2} disabled={!conversation || sending} aria-describedby="chat-send-help"
            onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (text.trim()) void send({ text }); } }}
            className="w-full resize-none rounded-xl border border-monu-green/25 bg-monu-bone px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-monu-green disabled:opacity-50" />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <input ref={fileRef} type="file" accept="application/pdf,image/png,image/jpeg" aria-label="Elegir comprobante ficticio" className="sr-only" tabIndex={-1} disabled={!conversation || sending} onChange={(event) => { const file = event.target.files?.[0]; if (file) void send({ file }); }} />
            <button type="button" disabled={!conversation || sending} onClick={() => fileRef.current?.click()} className={buttonClass + ' text-monu-green hover:bg-monu-green/10'}><Paperclip aria-hidden="true" className="size-4" />Comprobante</button>
            <button type="submit" disabled={!conversation || sending || !text.trim()} aria-busy={sending} className={buttonClass + ' bg-monu-green text-white hover:bg-monu-dark'}><Send aria-hidden="true" className="size-4" />{sending ? 'Enviando…' : 'Enviar'}</button>
          </div>
          <p id="chat-send-help" className="text-xs leading-relaxed text-monu-text/80">Enter envía; Mayús + Enter agrega una línea. Comprobante ficticio: PDF, PNG o JPEG hasta 2 MiB. Adjuntarlo no acredita dinero.</p>
        </form>
      </div>
    </dialog>
  );
}
