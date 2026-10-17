import { useEffect, useRef, useState } from 'react';
import { useData } from '../shared/store/DataContext';
import { Trash2, X, MessageCircle, ShoppingCart, ArrowRight, Check, LoaderCircle } from 'lucide-react';
import { buildWhatsAppDraftPayload, createWhatsAppDraft } from './whatsapp';

const inputClass = 'w-full min-h-11 bg-white border border-monu-green/20 rounded-xl px-3 py-2.5 text-base font-medium text-monu-dark placeholder:text-monu-text/50 focus:outline-none focus:ring-2 focus:ring-monu-green disabled:opacity-60';
const actionClass = 'min-h-11 rounded-xl font-extrabold px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-monu-green disabled:opacity-50 disabled:cursor-not-allowed';
const labelClass = 'block space-y-1.5 text-sm font-bold text-monu-dark';
const iconButtonClass = 'flex min-w-11 min-h-11 items-center justify-center rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-monu-green disabled:opacity-50';

export default function CartDrawer({ isOpen, onClose }) {
  const { state, dispatch } = useData();
  const { cart } = state;
  const [address, setAddress] = useState('');
  const [zone, setZone] = useState('');
  const [delivery, setDelivery] = useState('RETIRO');
  const [payment, setPayment] = useState('EFECTIVO');
  const [number, setNumber] = useState('');
  const [contact, setContact] = useState({ nombre: '', apellido: '', telefono: '' });
  const [isPreparing, setIsPreparing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState('');
  const [expiredReference, setExpiredReference] = useState(null);
  const [copied, setCopied] = useState(false);
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const errorRef = useRef(null);
  const draftRef = useRef(null);
  const preparingRef = useRef(false);
  const readyRef = useRef(null);
  const needsAddress = delivery === 'DELIVERY';
  const busy = isPreparing;
  const payload = buildWhatsAppDraftPayload({ cart, delivery, payment, address, number, zone, contact });
  const payloadKey = JSON.stringify(payload);
  const currentDraft = draft?.key === payloadKey && draft.data.referencia !== expiredReference ? draft.data : null;
  const total = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);

  useEffect(() => {
    if (!isOpen) return undefined;
    const previousFocus = document.activeElement;
    const dialog = dialogRef.current;
    dialog.showModal();
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && currentDraft) readyRef.current?.focus();
  }, [isOpen, currentDraft]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    if (!draft) return undefined;
    const timer = window.setTimeout(() => setExpiredReference(draft.data.referencia), Math.max(0, Date.parse(draft.data.expira_en) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [draft]);

  const updateContact = (event) => {
    event.target.setCustomValidity('');
    const { name, value } = event.target;
    setContact((previous) => ({ ...previous, [name]: value }));
  };

  const prepareWhatsApp = async () => {
    if (preparingRef.current) return;
    setError('');
    setCopied(false);
    if (cart.length === 0) return;
    preparingRef.current = true;
    setIsPreparing(true);
    try {
      const cached = draftRef.current;
      if (cached?.key === payloadKey && Date.parse(cached.data.expira_en) > Date.now()) {
        setDraft(cached);
        return;
      }
      const data = await createWhatsAppDraft(payload);
      const prepared = { key: payloadKey, data };
      draftRef.current = prepared;
      setDraft(prepared);
    } catch (failure) {
      setError(failure.message || 'No se pudo preparar el mensaje. Intentá nuevamente.');
    } finally {
      preparingRef.current = false;
      setIsPreparing(false);
    }
  };

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(currentDraft.mensaje);
      setCopied(true);
    } catch {
      setError('No se pudo copiar. Seleccioná el mensaje y copialo manualmente.');
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (busy) return;
    for (const field of ['nombre', 'apellido', 'telefono']) {
      const input = event.currentTarget.elements.namedItem(field);
      const valid = field === 'telefono' ? /^[0-9]{11,15}$/.test(payload.contacto.telefono) : Boolean(contact[field].trim());
      input.setCustomValidity(valid ? '' : field === 'telefono' ? 'Ingresá entre 11 y 15 dígitos, con código de país.' : 'Completá este campo.');
      if (!valid) { input.reportValidity(); return; }
    }
    void prepareWhatsApp();
  };

  if (!isOpen) return null;

  return (
    <dialog ref={dialogRef} aria-labelledby="cart-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="fixed inset-0 m-auto w-[calc(100%_-_2rem)] max-w-4xl max-h-[calc(100dvh_-_2rem)] overflow-hidden rounded-3xl border border-monu-green/10 bg-monu-bone p-0 text-monu-text shadow-monu-lg backdrop:bg-black/55 backdrop:backdrop-blur-sm">
      <div className="flex max-h-[calc(100dvh_-_2rem)] flex-col">
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-monu-green/10 px-5 py-4 sm:px-7">
          <div>
            <h2 id="cart-title" className="font-heading text-2xl font-extrabold tracking-tight text-monu-dark">Tu pedido</h2>
            <p className="mt-1 text-sm text-monu-text/70">A un paso de algo rico.</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Cerrar carrito" className={iconButtonClass + ' bg-monu-green/5 text-monu-dark hover:bg-monu-green/10'}><X aria-hidden="true" className="size-5" /></button>
        </header>
        {cart.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
            <span className="flex size-16 items-center justify-center rounded-2xl bg-monu-cream text-monu-green"><ShoppingCart aria-hidden="true" className="size-7" /></span>
            <p className="text-lg font-extrabold text-monu-dark">Tu carrito está vacío</p>
            <button type="button" onClick={onClose} className={actionClass + ' mt-2 bg-monu-green text-white hover:bg-monu-dark'}>Volver al menú</button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex min-h-0 flex-col">
            <div className="min-h-0 overflow-y-auto overscroll-contain">
              <div className="grid md:grid-cols-2">
                <section aria-labelledby="cart-products" className="bg-monu-cream/25 p-5 sm:p-7">
                  <div className="mb-5 flex items-center justify-between gap-3">
                    <h3 id="cart-products" className="font-heading text-lg font-extrabold text-monu-dark">Lo que elegiste</h3>
                    <span className="rounded-full bg-white px-3 py-1 text-sm font-bold text-monu-green">{cart.reduce((sum, item) => sum + item.quantity, 0)} uds.</span>
                  </div>
                  <ul className="space-y-5">
                    {cart.map((item, index) => (
                      <li key={index} className="flex gap-3 border-b border-monu-green/10 pb-5 last:border-0 last:pb-0">
                        <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-monu-cream sm:size-20">
                          <img src={item.image || '/favicon.png'} alt="" className={item.image ? 'size-full object-cover' : 'size-10 object-contain'} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-1">
                            <h4 className="pt-2 font-extrabold leading-snug text-monu-dark break-words">{item.name}</h4>
                            <button type="button" disabled={busy} aria-label={'Quitar ' + item.name} onClick={() => dispatch({ type: 'REMOVE_FROM_CART', payload: index })} className={iconButtonClass + ' -mt-1 text-monu-text/60 hover:bg-red-50 hover:text-red-700'}><Trash2 aria-hidden="true" className="size-4" /></button>
                          </div>
                          {item.notes && <p className="mb-2 text-sm text-monu-text/70 break-words">{item.notes}</p>}
                          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center rounded-xl border border-monu-green/15 bg-white">
                              <button type="button" disabled={busy} aria-label={'Reducir cantidad de ' + item.name} onClick={() => dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { index, delta: -1 } })} className={iconButtonClass + ' font-bold text-monu-green hover:bg-monu-green/5'}>−</button>
                              <span className="w-5 text-center text-sm font-extrabold">{item.quantity}</span>
                              <button type="button" disabled={busy} aria-label={'Aumentar cantidad de ' + item.name} onClick={() => dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { index, delta: 1 } })} className={iconButtonClass + ' font-bold text-monu-green hover:bg-monu-green/5'}>+</button>
                            </div>
                            <span className="font-extrabold text-monu-dark">{'$' + (item.price * item.quantity).toLocaleString('es-AR')}</span>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
                <section aria-labelledby="checkout-contact" className="space-y-5 p-5 sm:p-7 md:border-l md:border-monu-green/10">
                  {error && <p ref={errorRef} tabIndex={-1} role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
                  <fieldset disabled={busy} className="space-y-4">
                    <legend id="checkout-contact" className="mb-4 font-heading text-lg font-extrabold text-monu-dark">Tus datos</legend>
                    <div className="grid grid-cols-2 gap-3">
                      <label htmlFor="checkout-first-name" className={labelClass}><span>Nombre</span>
                        <input id="checkout-first-name" name="nombre" required maxLength={80} autoComplete="given-name" value={contact.nombre} onChange={updateContact} className={inputClass} />
                      </label>
                      <label htmlFor="checkout-last-name" className={labelClass}><span>Apellido</span>
                        <input id="checkout-last-name" name="apellido" required maxLength={80} autoComplete="family-name" value={contact.apellido} onChange={updateContact} className={inputClass} />
                      </label>
                    </div>
                    <label htmlFor="checkout-phone" className={labelClass}><span>Teléfono</span>
                      <input id="checkout-phone" name="telefono" type="tel" inputMode="tel" required maxLength={25} pattern="[+0-9\(\) .\-]+" autoComplete="tel" aria-describedby="checkout-phone-help" placeholder="+54 9 11 1234 5678" value={contact.telefono} onChange={updateContact} className={inputClass} />
                    </label>
                    <p id="checkout-phone-help" className="!mt-1.5 text-xs text-monu-text/70">Con código de país, sin 0 ni 15.</p>
                  </fieldset>
                  <fieldset disabled={busy} className="space-y-4 border-t border-monu-green/10 pt-5">
                    <legend className="sr-only">Entrega y pago</legend>
                    <div className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-2 md:grid-cols-1 lg:grid-cols-2">
                      <label htmlFor="checkout-delivery" className={labelClass}><span>Entrega</span>
                        <select id="checkout-delivery" value={delivery} onChange={(event) => setDelivery(event.target.value)} className={inputClass}><option value="RETIRO">Retiro en el local</option><option value="DELIVERY">Delivery</option></select>
                      </label>
                      <label htmlFor="checkout-payment" className={labelClass}><span>Forma de pago</span>
                        <select id="checkout-payment" value={payment} onChange={(event) => setPayment(event.target.value)} className={inputClass}><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select>
                      </label>
                    </div>
                    {needsAddress && (
                      <div className="space-y-3">
                        <label htmlFor="checkout-zone" className={labelClass}><span>Localidad</span>
                          <select id="checkout-zone" required autoComplete="address-level2" value={zone} onChange={(event) => setZone(event.target.value)} className={inputClass}><option value="">Seleccioná tu localidad</option><option value="Ensenada">Ensenada</option><option value="Punta Lara">Punta Lara</option></select>
                        </label>
                        <div className="grid grid-cols-[minmax(0,1fr)_6rem] gap-3">
                          <label htmlFor="checkout-street" className={labelClass}><span>Calle</span>
                            <input id="checkout-street" required maxLength={200} autoComplete="address-line1" value={address} onChange={(event) => setAddress(event.target.value)} className={inputClass} />
                          </label>
                          <label htmlFor="checkout-number" className={labelClass}><span>Número</span>
                            <input id="checkout-number" required maxLength={20} value={number} onChange={(event) => setNumber(event.target.value)} className={inputClass} />
                          </label>
                        </div>
                      </div>
                    )}
                    {payment === 'TRANSFERENCIA' && <p className="text-xs leading-relaxed text-monu-text/70">Te pediremos el comprobante por WhatsApp para que lo revise el local.</p>}
                  </fieldset>
                  {currentDraft && (
                    <div className="rounded-2xl border border-monu-green/15 bg-monu-green/5 p-4">
                      <p role="status" className="flex items-center gap-2 text-sm font-bold text-monu-dark"><Check aria-hidden="true" className="size-4 shrink-0" />Listo para enviar por WhatsApp</p>
                      <details className="mt-2 text-sm">
                        <summary className="cursor-pointer py-2 font-semibold text-monu-green focus-visible:outline-monu-green">Ver o copiar mensaje</summary>
                        <label htmlFor="checkout-message" className="sr-only">Mensaje para enviar</label>
                        <textarea id="checkout-message" readOnly rows={3} value={currentDraft.mensaje} className={inputClass + ' mt-2'} />
                        <button type="button" onClick={copyMessage} className={actionClass + ' mt-2 border border-monu-green/20 text-monu-green hover:bg-white'}>{copied ? 'Copiado' : 'Copiar mensaje'}</button>
                        <p role="status" className="sr-only">{copied ? 'Mensaje copiado.' : ''}</p>
                        <p className="mt-3 text-xs leading-relaxed text-monu-text/70">Reenviar este mensaje conserva el mismo pedido.</p>
                        <button type="button" disabled={busy} onClick={() => { draftRef.current = null; void prepareWhatsApp(); }} className={actionClass + ' mt-1 text-left text-monu-green hover:bg-white'}>Preparar otro pedido igual</button>
                      </details>
                      {!currentDraft.url_whatsapp && <p className="mt-2 text-sm">WhatsApp no está conectado. Copiá el mensaje para usar el simulador.</p>}
                    </div>
                  )}
                  {draft?.key === payloadKey && draft.data.referencia === expiredReference && <p role="status" className="text-sm text-monu-text/70">El mensaje venció. Prepará uno nuevo para continuar.</p>}
                </section>
              </div>
            </div>
            <footer className="shrink-0 border-t border-monu-green/10 bg-white px-5 py-4 sm:px-7">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-baseline justify-between gap-4 sm:block">
                  <p className="text-sm font-medium text-monu-text/70">Subtotal estimado</p>
                  <p className="font-heading text-2xl font-extrabold tracking-tight text-monu-dark">{'$' + total.toLocaleString('es-AR')}</p>
                </div>
                {currentDraft?.url_whatsapp ? (
                  <a ref={readyRef} href={currentDraft.url_whatsapp} target="_blank" rel="noopener noreferrer" className={actionClass + ' flex items-center justify-center gap-2 bg-monu-green text-white hover:bg-monu-dark'}><MessageCircle aria-hidden="true" className="size-5 shrink-0" />Abrir WhatsApp<ArrowRight aria-hidden="true" className="size-4" /></a>
                ) : (
                  <button type="submit" disabled={busy} aria-busy={busy} className={actionClass + ' flex items-center justify-center gap-2 bg-monu-green text-white hover:bg-monu-dark'}>
                    {busy ? <LoaderCircle aria-hidden="true" className="size-5 motion-safe:animate-spin" /> : <MessageCircle aria-hidden="true" className="size-5 shrink-0" />}
                    {busy ? 'Preparando…' : 'Continuar por WhatsApp'}
                  </button>
                )}
              </div>
              <p className="mt-3 text-center text-xs leading-relaxed text-monu-text/70 sm:text-right">{currentDraft ? 'Enviá el mensaje para registrar tu pedido.' : 'Confirmamos tu pedido y el total por WhatsApp.'}</p>
            </footer>
          </form>
        )}
      </div>
    </dialog>
  );
}
