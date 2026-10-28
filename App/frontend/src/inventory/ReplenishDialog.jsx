// Diálogo de reposición manual de stock de un insumo: valida la cantidad, muestra el
// saldo resultante, pide confirmación en reposiciones grandes o ambiguas y, si un
// intento anterior quedó sin confirmar, obliga a revisar el stock actual antes de repetir.
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { userErrorMessage } from '../shared/api/userErrors.js';
import { DataError } from '../fulfillment/operationUi';
import { isUncertainReplenishment, quantityWithUnit, replenishmentPlan, replenishmentSummary, scaledWithUnit, unitLabel } from './replenishment';

// Mensaje de error por defecto si la reposición falla.
const FALLBACK = 'No pudimos reponer el stock. Comprobá el inventario antes de repetir la reposición.';

// uncertain: un intento anterior de este insumo no se pudo confirmar. Antes de repetir
// se vuelve a consultar el stock y se exige confirmar el resumen sobre ese saldo.
export default function ReplenishDialog({ item, busy, uncertain, initialValue = '', onSubmit, verify, onClose }) {
  // Estado del formulario, del resumen de confirmación y de la verificación del stock.
  const [value, setValue] = useState(initialValue);
  const [fieldError, setFieldError] = useState('');
  const [requestError, setRequestError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [verification, setVerification] = useState(uncertain ? 'pending' : 'idle');
  const [sentPlan, setSentPlan] = useState(null);
  // Refs: envío en curso, verificación vigente y elementos que reciben el foco.
  const sendingRef = useRef(false);
  const verifyRun = useRef(0);
  const dialog = useRef(null);
  const input = useRef(null);
  const confirmButton = useRef(null);
  const errorBox = useRef(null);

  // Consulta el stock actual (verify) y registra si se pudo comprobar.
  const checkStock = async () => {
    const run = ++verifyRun.current;
    try {
      await verify();
      if (run === verifyRun.current) setVerification('ok');
    } catch {
      if (run === verifyRun.current) setVerification('failed');
    }
  };
  const recheck = () => { setVerification('pending'); void checkStock(); };
  const startedUncertain = useRef(uncertain);
  const firstCheck = useRef(checkStock);
  // Abre el diálogo al montar, enfoca la cantidad y, si hubo un intento incierto, verifica el stock.
  useEffect(() => {
    dialog.current?.showModal();
    input.current?.focus();
    if (startedUncertain.current) void firstCheck.current();
  }, []);
  // Mueve el foco al botón de confirmación o al error cuando aparecen.
  useEffect(() => { if (confirming) confirmButton.current?.focus(); }, [confirming]);
  useEffect(() => { if (requestError) errorBox.current?.focus(); }, [requestError]);

  const sending = sentPlan !== null;
  // Mientras se envía, item.stock ya incluye el saldo optimista: se muestra el plan enviado.
  const plan = sentPlan || replenishmentPlan(item, value);
  const unit = unitLabel(item.category, 2n);
  const locked = sending || busy;
  const verified = !uncertain || verification === 'ok';
  const id = `replenish-${item.id}`;

  // Envía la reposición con el plan calculado; si el resultado es incierto, vuelve a verificar el stock.
  const send = async (current) => {
    if (sendingRef.current || busy || !verified) return;
    sendingRef.current = true;
    setSentPlan(current);
    setRequestError('');
    try {
      await onSubmit(current);
    } catch (error) {
      setConfirming(false);
      setRequestError(userErrorMessage(error, FALLBACK));
      if (isUncertainReplenishment(error)) recheck();
    } finally {
      sendingRef.current = false;
      setSentPlan(null);
    }
  };

  // Valida la cantidad y decide si enviar directo o pedir confirmación del resumen.
  const review = (event) => {
    event.preventDefault();
    if (sendingRef.current || busy) return;
    if (!plan.valid) { setFieldError(plan.error); input.current?.focus(); return; }
    setFieldError('');
    if (plan.large || plan.review || uncertain) setConfirming(true);
    else void send(plan);
  };

  // Cierra el diálogo salvo que haya un envío en curso.
  const close = () => { if (!sendingRef.current) onClose(); };

  return (
    <dialog ref={dialog} aria-labelledby={`${id}-title`} aria-describedby={`${id}-current`}
      onCancel={(event) => { event.preventDefault(); close(); }}
      // Chrome puede cerrar el diálogo con un segundo Escape aunque se cancele el evento.
      onClose={() => { if (sendingRef.current) dialog.current?.showModal(); else onClose(); }}
      className="m-auto max-h-[90dvh] overflow-y-auto rounded-3xl border-0 p-0 w-[min(28rem,calc(100%_-_2rem))] backdrop:bg-black/50">
      <div className="bg-white rounded-3xl p-6 w-full shadow-2xl relative">
        {/* Cierre, nombre del insumo y stock actual */}
        <button type="button" disabled={sending} onClick={close} aria-label="Cerrar reposición" className="absolute top-3 right-3 min-h-11 min-w-11 flex items-center justify-center text-gray-500 hover:text-gray-700 bg-gray-100 rounded-full">
          <X className="w-5 h-5" aria-hidden="true" />
        </button>
        <h2 id={`${id}-title`} className="text-xl font-extrabold text-monu-dark mb-1 pr-12">Reponer {item.name}</h2>
        <p id={`${id}-current`} className="text-sm text-monu-text mb-4">Stock actual: <strong className="tabular-nums">{quantityWithUnit(item.stock, item.category)}</strong></p>
        <form noValidate onSubmit={review} className="space-y-4" aria-busy={sending}>
          {/* Error de la solicitud y campo de cantidad con el saldo resultante */}
          <div ref={errorBox} tabIndex={-1}><DataError message={requestError} /></div>
          <fieldset disabled={locked || confirming} className="space-y-1">
            <label htmlFor={`${id}-quantity`} className="block text-sm font-bold text-monu-dark">Cantidad a reponer ({unit})</label>
            <div className="flex items-center rounded-xl border focus-within:border-monu-green focus-within:ring-2 focus-within:ring-monu-green/40">
              <input
                ref={input} id={`${id}-quantity`} type="text" inputMode="decimal" autoComplete="off" enterKeyHint="done"
                value={value} placeholder={item.category === 'UNIDAD' ? 'Ej: 12' : 'Ej: 2500 o 2,5'}
                aria-invalid={Boolean(fieldError)} aria-describedby={`${id}-quantity-error ${id}-quantity-help`}
                onChange={(event) => { setValue(event.target.value); setFieldError(''); }}
                className="min-w-0 flex-1 bg-transparent px-4 py-3 text-base tabular-nums focus:outline-none"
              />
              <span className="px-4 text-sm font-bold text-monu-text" aria-hidden="true">{unit}</span>
            </div>
            <p id={`${id}-quantity-error`} aria-live="polite" className="text-sm text-red-700">{fieldError}</p>
            <p id={`${id}-quantity-help`} className="text-xs text-monu-text">{plan.valid ? `Quedará en ${scaledWithUnit(plan.resulting, item.category)}.` : 'Mayor que cero, hasta 3 decimales, en la unidad del insumo.'}</p>
          </fieldset>
          {/* Aviso de intento anterior sin confirmar y estado de la verificación del stock */}
          {uncertain && (
            <div role="status" className="rounded-xl border border-monu-orange/40 bg-monu-cream/60 p-3 text-sm text-monu-burnt space-y-2">
              {verification === 'failed' ? <>
                <p className="font-bold">No pudimos consultar el stock actual. Actualizalo antes de repetir para no duplicar la reposición.</p>
                <button type="button" disabled={locked} onClick={recheck} className="min-h-11 px-4 rounded-xl border border-monu-green/30 font-bold text-monu-dark">Volver a consultar</button>
              </> : <p className="font-bold">{verification === 'ok'
                ? 'Un intento anterior no se pudo confirmar. El stock actual ya está consultado: revisá que no lo incluya antes de enviarlo de nuevo.'
                : 'Un intento anterior no se pudo confirmar. Consultando el stock actual…'}</p>}
            </div>
          )}
          {/* Resumen a confirmar o botón de reponer */}
          {confirming && plan.valid ? (
            <div role="group" aria-labelledby={`${id}-summary`} className="rounded-xl border border-monu-orange/40 bg-monu-cream/60 p-4 space-y-3">
              <p id={`${id}-summary`} className="font-bold text-monu-dark">{replenishmentSummary(item, plan)}</p>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button type="button" disabled={locked} onClick={() => { setConfirming(false); input.current?.focus(); }} className="min-h-11 px-4 rounded-xl border border-monu-green/30 font-bold text-monu-dark">Corregir cantidad</button>
                <button ref={confirmButton} type="button" disabled={locked || !verified} onClick={() => send(plan)} className="min-h-11 px-4 rounded-xl bg-monu-green text-white font-bold hover:bg-[#002b22] disabled:cursor-wait disabled:opacity-70">{sending ? 'Reponiendo…' : 'Confirmar reposición'}</button>
              </div>
            </div>
          ) : (
            <button type="submit" disabled={locked} className="w-full min-h-11 bg-monu-green text-white font-bold py-3 rounded-xl hover:bg-[#002b22] transition disabled:cursor-wait disabled:opacity-70">
              {sending ? 'Reponiendo…' : 'Reponer'}
            </button>
          )}
        </form>
      </div>
    </dialog>
  );
}
