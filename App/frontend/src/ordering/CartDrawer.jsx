import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { Trash2, CreditCard, ChevronRight, MessageCircle, ShoppingCart, MapPin } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { buildWhatsAppDraftPayload, createWhatsAppDraft } from './whatsapp';

const inputClass = 'w-full bg-white border border-monu-green/30 rounded-xl px-4 py-3 text-base text-monu-dark focus:outline-none focus:ring-2 focus:ring-monu-green';
const actionClass = 'min-h-11 rounded-xl font-extrabold px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-monu-green disabled:opacity-50 disabled:cursor-not-allowed';

export default function CartDrawer({ isOpen, onClose }) {
  const { user } = useAuth();
  const { state, dispatch, placeOrder, startDigitalPayment } = useData();
  const { cart } = state;
  const navigate = useNavigate();
  const [isPayingMP, setIsPayingMP] = useState(false);
  const [address, setAddress] = useState('');
  const [zone, setZone] = useState('');
  const [phone, setPhone] = useState('');
  const [channel, setChannel] = useState('MERCADO_PAGO');
  const [delivery, setDelivery] = useState('RETIRO');
  const [payment, setPayment] = useState('EFECTIVO');
  const [number, setNumber] = useState('');
  const [isPreparing, setIsPreparing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState('');
  const [phoneError, setPhoneError] = useState('');
  const [copied, setCopied] = useState(false);
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const errorRef = useRef(null);
  const phoneRef = useRef(null);
  const draftRef = useRef(null);
  const preparingRef = useRef(false);
  const isWhatsApp = channel === 'WHATSAPP';
  const needsAddress = !isWhatsApp || delivery === 'DELIVERY';
  const busy = isPreparing || isPayingMP;
  const payload = buildWhatsAppDraftPayload({ cart, phone, delivery, payment, address, number, zone });
  const payloadKey = `${user?.id}:${JSON.stringify(payload)}`;
  const currentDraft = draft?.key === payloadKey ? draft.data : null;
  const total = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);

  useEffect(() => {
    if (!isOpen) return undefined;
    const previousFocus = document.activeElement;
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [isOpen]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const handleDialogKeyDown = (event) => {
    if (event.key === 'Escape') onClose();
    if (event.key !== 'Tab') return;
    const controls = [...dialogRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea, a[href]')];
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  };

  const prepareWhatsApp = async () => {
    if (preparingRef.current) return;
    setError('');
    setCopied(false);
    if (!user || user.role !== 'cliente') {
      setError('Iniciá sesión como cliente para preparar el mensaje.');
      return;
    }
    if (!/^\+?[\d\s()-]+$/.test(phone) || !/^\d{11,15}$/.test(payload.telefono)) {
      setPhoneError('Ingresá entre 11 y 15 dígitos, incluidos país y área.');
      phoneRef.current?.focus();
      return;
    }
    setPhoneError('');
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

  const submitOrder = async () => {
    if (cart.length === 0 || !address || !phone) return;
    setIsPayingMP(true);
    try {
      if (!user || user.role !== 'cliente') {
        throw new Error('Iniciá sesión como cliente para confirmar el pedido');
      }
      const order = await placeOrder({ address, zone, items: cart });
      await startDigitalPayment(order);
      toast.success('¡Pedido registrado!', { description: 'El pago quedó pendiente en Mercado Pago.' });
      onClose();
      navigate('/menu');
    } catch (failure) {
      toast.error('No se pudo confirmar el pedido', { description: failure.message });
    } finally {
      setIsPayingMP(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (busy) return;
    if (isWhatsApp) void prepareWhatsApp();
    else void submitOrder();
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" onClick={onClose} aria-hidden="true" />
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="cart-title" onKeyDown={handleDialogKeyDown} className="fixed inset-y-0 right-0 w-full md:w-96 bg-white z-50 shadow-2xl flex flex-col">
        <div className="p-5 border-b flex justify-between items-center bg-monu-cream/30">
          <h2 id="cart-title" className="text-xl font-extrabold font-heading text-monu-dark">Tu Carrito</h2>
          <button ref={closeRef} onClick={onClose} aria-label="Cerrar carrito" className="min-w-11 min-h-11 p-2 hover:bg-gray-100 rounded-full focus-visible:ring-2 focus-visible:ring-monu-green">
            <ChevronRight aria-hidden="true" className="w-6 h-6" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="p-5">
            {cart.length === 0 ? (
              <div className="py-12 flex flex-col items-center justify-center text-monu-text/70">
                <ShoppingCart aria-hidden="true" className="w-12 h-12 mb-4" />
                <p className="font-bold">Tu carrito está vacío</p>
                <p className="text-sm">¡Agregá algo rico del menú!</p>
              </div>
            ) : (
              <div className="space-y-4">
                {cart.map((item, index) => (
                  <div key={index} className="flex gap-3 border-b border-monu-green/10 pb-4 last:border-0">
                    {item.image ? (
                      <img src={item.image} alt={item.name} className="w-16 h-16 shrink-0 object-cover rounded-xl shadow-sm" />
                    ) : (
                      <div className="w-16 h-16 shrink-0 bg-monu-cream rounded-xl flex items-center justify-center">
                        <img src="/favicon.png" className="w-10 h-10 object-contain" alt="" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-start">
                        <h3 className="font-extrabold text-monu-dark leading-tight break-words">{item.name}</h3>
                        <button disabled={busy} aria-label={`Quitar ${item.name}`} onClick={() => dispatch({ type: 'REMOVE_FROM_CART', payload: index })} className="min-w-11 min-h-11 flex items-center justify-center text-red-600 hover:text-red-800 disabled:opacity-50">
                          <Trash2 aria-hidden="true" className="w-4 h-4" />
                        </button>
                      </div>
                      {item.notes && <p className="text-sm text-monu-text mt-1 break-words">Nota: {item.notes}</p>}
                      <div className="flex flex-wrap gap-2 justify-between items-center mt-3">
                        <div className="flex items-center bg-monu-cream rounded-lg">
                          <button disabled={busy} aria-label={`Reducir cantidad de ${item.name}`} onClick={() => dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { index, delta: -1 } })} className="min-w-11 min-h-11 font-bold text-monu-green hover:bg-monu-green/10 rounded disabled:opacity-50">-</button>
                          <span className="font-bold w-6 text-center">{item.quantity}</span>
                          <button disabled={busy} aria-label={`Aumentar cantidad de ${item.name}`} onClick={() => dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { index, delta: 1 } })} className="min-w-11 min-h-11 font-bold text-monu-green hover:bg-monu-green/10 rounded disabled:opacity-50">+</button>
                        </div>
                        <span className="font-extrabold text-monu-green">${(item.price * item.quantity).toLocaleString('es-AR')}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          {cart.length > 0 && (
            <form onSubmit={handleSubmit} className="p-5 border-t bg-monu-cream/30 space-y-4">
              {error && <p ref={errorRef} tabIndex={-1} role="alert" className="p-3 border border-red-300 rounded-xl text-red-800 bg-red-50">{error}</p>}
              <fieldset disabled={busy} className="space-y-4">
                <legend className="font-extrabold text-monu-dark mb-3">Cómo continuar</legend>
                <label className="block text-sm font-bold text-monu-dark space-y-1">
                  <span>Canal del pedido</span>
                  <select value={channel} onChange={(event) => { setChannel(event.target.value); setError(''); }} className={inputClass}>
                    <option value="MERCADO_PAGO">Mercado Pago</option>
                    <option value="WHATSAPP">WhatsApp</option>
                  </select>
                </label>
                {isWhatsApp && (
                  <>
                    <p className="text-sm text-monu-text">Prepará el mensaje y envialo por WhatsApp para continuar el pedido.</p>
                    <label className="block text-sm font-bold text-monu-dark space-y-1">
                      <span>Entrega</span>
                      <select value={delivery} onChange={(event) => setDelivery(event.target.value)} className={inputClass}>
                        <option value="RETIRO">Retiro en el local</option>
                        <option value="DELIVERY">Delivery</option>
                      </select>
                    </label>
                    <label className="block text-sm font-bold text-monu-dark space-y-1">
                      <span>Forma de pago</span>
                      <select value={payment} onChange={(event) => setPayment(event.target.value)} className={inputClass}>
                        <option value="EFECTIVO">Efectivo</option>
                        <option value="TRANSFERENCIA">Transferencia</option>
                      </select>
                    </label>
                    {payment === 'TRANSFERENCIA' && <p className="text-sm text-monu-text">Un empleado deberá revisar y confirmar la transferencia. Enviar un comprobante no acredita el pago automáticamente.</p>}
                  </>
                )}
                {needsAddress && (
                  <>
                    <div className="bg-orange-50 border border-orange-200 text-orange-800 text-sm p-3 rounded-xl flex items-start gap-2">
                      <MapPin aria-hidden="true" className="w-5 h-5 shrink-0" />
                      <p>Delivery exclusivo para <strong>Ensenada</strong> y <strong>Punta Lara</strong>.</p>
                    </div>
                    <label className="block text-sm font-bold text-monu-dark space-y-1">
                      <span>Localidad</span>
                      <select required value={zone} onChange={(event) => setZone(event.target.value)} className={inputClass}>
                        <option value="">Seleccioná tu localidad</option>
                        <option value="Ensenada">Ensenada</option>
                        <option value="Punta Lara">Punta Lara</option>
                      </select>
                    </label>
                    <label className="block text-sm font-bold text-monu-dark space-y-1">
                      <span>{isWhatsApp ? 'Calle' : 'Calle y número'}</span>
                      <input required maxLength={200} autoComplete="address-line1" value={address} onChange={(event) => setAddress(event.target.value)} className={inputClass} />
                    </label>
                    {isWhatsApp && (
                      <label className="block text-sm font-bold text-monu-dark space-y-1">
                        <span>Número</span>
                        <input required maxLength={20} value={number} onChange={(event) => setNumber(event.target.value)} className={inputClass} />
                      </label>
                    )}
                  </>
                )}
                <label className="block text-sm font-bold text-monu-dark space-y-1">
                  <span>Tu número de WhatsApp</span>
                  <input ref={phoneRef} required type="tel" autoComplete="tel" value={phone} onChange={(event) => { setPhone(event.target.value); setPhoneError(''); }} aria-invalid={isWhatsApp && Boolean(phoneError)} aria-describedby={isWhatsApp ? `whatsapp-phone-hint${phoneError ? ' whatsapp-phone-error' : ''}` : undefined} className={inputClass} />
                </label>
                {isWhatsApp && <p id="whatsapp-phone-hint" className="text-sm text-monu-text">Incluí país y área: por ejemplo, +54 9 221 555 0000 (entre 11 y 15 dígitos).</p>}
                {isWhatsApp && phoneError && <p id="whatsapp-phone-error" role="alert" className="text-sm text-red-800">{phoneError}</p>}
              </fieldset>
              <div className="flex justify-between gap-3 font-extrabold text-xl text-monu-dark border-t border-monu-green/10 pt-3">
                <span>{isWhatsApp ? 'Subtotal estimado' : 'Total'}</span>
                <span>${total.toLocaleString('es-AR')}</span>
              </div>
              {isWhatsApp && <p className="text-sm text-monu-text">El local verificará precios, disponibilidad y entrega al recibir el mensaje.</p>}
              <button type="submit" disabled={busy} aria-busy={busy} className={`${actionClass} w-full flex items-center justify-center gap-2 text-white ${isWhatsApp ? 'bg-monu-green hover:bg-monu-green/90' : 'bg-[#009EE3] hover:bg-[#0088C4]'}`}>
                {isWhatsApp ? <MessageCircle aria-hidden="true" className="w-5 h-5 shrink-0" /> : <CreditCard aria-hidden="true" className="w-5 h-5 shrink-0" />}
                {isPreparing ? 'Preparando mensaje...' : isPayingMP ? 'Conectando con Mercado Pago...' : isWhatsApp ? 'Preparar mensaje de WhatsApp' : 'Pagar con Mercado Pago'}
              </button>
              {isWhatsApp && currentDraft && (
                <div className="space-y-3 border-t border-monu-green/20 pt-4">
                  <p role="status" className="text-sm font-bold text-monu-dark">Mensaje preparado. Todavía no se creó el pedido: tenés que enviarlo.</p>
                  <p className="text-sm text-monu-text break-words">Referencia: {currentDraft.referencia}</p>
                  <label className="block text-sm font-bold text-monu-dark space-y-1">
                    <span>Mensaje para enviar</span>
                    <textarea readOnly rows={6} value={currentDraft.mensaje} className={inputClass} />
                  </label>
                  <button type="button" onClick={copyMessage} className={`${actionClass} w-full border border-monu-green text-monu-green hover:bg-monu-green/10`}>Copiar mensaje</button>
                  {copied && <p role="status" className="text-sm text-monu-green">Mensaje copiado.</p>}
                  {currentDraft.url_whatsapp ? (
                    <a href={currentDraft.url_whatsapp} target="_blank" rel="noopener noreferrer" className={`${actionClass} flex justify-center bg-monu-green text-white hover:bg-monu-green/90`}>Abrir WhatsApp y enviar mensaje</a>
                  ) : (
                    <p className="text-sm text-monu-text">Modo simulado: WhatsApp todavía no está conectado. Podés copiar el mensaje, pero no se enviará automáticamente ni se creará un pedido desde esta pantalla.</p>
                  )}
                  <p className="text-sm text-monu-text">Tu carrito se conserva. El local continuará la conversación cuando reciba el mensaje.</p>
                </div>
              )}
            </form>
          )}
        </div>
      </div>
    </>
  );
}
