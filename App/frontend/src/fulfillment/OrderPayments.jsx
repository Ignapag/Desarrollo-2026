// Sección de pagos del detalle del pedido: cobrar en efectivo (con cálculo de vuelto),
// confirmar transferencias, conciliar cobros pendientes y registrar devoluciones.
// Cada intento guarda su UUID en sessionStorage para reintentar sin duplicar el cobro.
import { UserFacingError } from '../shared/api/userErrors.js';
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';
import { createPaymentAttempt, executePayment } from './orderCommands';
import { paymentAmount } from './paymentValidation';
import { knownLabel, money, paymentMethodLabel } from './orderModel';
import { buttonClass, inputClass, Field, Reason } from './operationUi';

// Lee/guarda el intento de pago pendiente en sessionStorage (tolerando que no esté disponible).
function readAttempt(key) {
  try { return JSON.parse(sessionStorage.getItem(key)) || null; } catch { return null; }
}
function saveAttempt(key, value) {
  try { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); } catch { /* El ref conserva el reintento mientras esta vista siga abierta. */ }
}

// Operación y monto sugeridos: devolución si se canceló; si no, cobrar el saldo con el método acordado.
const defaultKind = (order) => order.estado === 'CANCELADO' ? 'devolucion' : order.metodo_pago_acordado === 'TRANSFERENCIA' ? 'transferencia' : 'efectivo';
const defaultAmount = (order) => String(order.estado === 'CANCELADO' ? order.neto_cobrado : order.saldo_pendiente);

/**
 * Pagos de un pedido. `userId` separa los intentos guardados por usuario, `run`
 * ejecuta la operación vía el detalle y `can` consulta los permisos de pagos.
 */
export default function OrderPayments({ order, userId, commands, run, busy, can = () => true }) {
  // Intento pendiente (persistido) y valores del formulario de cobro o devolución.
  const key = `monu-payment:${userId}:${order.id}`;
  const startingKind = defaultKind(order);
  const startingAmount = defaultAmount(order);
  const [pending, setPending] = useState(() => readAttempt(key));
  const attempt = useRef(pending);
  const [kind, setKind] = useState(startingKind);
  const [amount, setAmount] = useState(startingAmount);
  const [received, setReceived] = useState('');
  const [method, setMethod] = useState('EFECTIVO');
  const [reason, setReason] = useState('');
  const [confirmRefund, setConfirmRefund] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  // Al cambiar de pedido o de saldo, reinicia el formulario si no hay un intento pendiente.
  useEffect(() => {
    if (attempt.current) return;
    setKind(startingKind);
    setAmount(startingAmount);
    setReceived('');
    setConfirmRefund(false);
  }, [order.id, startingKind, startingAmount]);
  // Validaciones del formulario: importe dentro del máximo, recibido suficiente y nota de devolución.
  const pendingPayments = order.pagos.filter((payment) => payment.tipo === 'COBRO' && payment.estado === 'PENDIENTE');
  const existingCollection = pendingPayments.some((payment) => payment.metodo_pago === ({ efectivo: 'EFECTIVO', transferencia: 'TRANSFERENCIA' })[kind]);
  const maximum = Number(kind === 'devolucion' ? order.neto_cobrado : order.estado === 'CANCELADO' ? 0 : order.saldo_pendiente);
  const canonicalAmount = paymentAmount(amount);
  const canonicalReceived = received.trim() ? paymentAmount(received) : canonicalAmount;
  const validAmount = canonicalAmount !== null && Number(canonicalAmount) <= maximum;
  const validReceived = canonicalReceived !== null && Number(canonicalReceived) >= Number(canonicalAmount);
  const validReason = kind !== 'devolucion' || !reason.trim() || reason.trim().length >= 3;
  const amountError = !validAmount ? `Ingresá un importe mayor a cero, con hasta dos decimales, hasta ${money(maximum)} (máximo 10 dígitos enteros).` : '';
  const receivedError = received.trim() && !validReceived ? 'Ingresá un importe recibido con hasta dos decimales, igual o mayor al importe a cobrar.' : '';
  const reasonError = !validReason ? 'Escribí al menos 3 caracteres para la nota de devolución, o dejala vacía.' : '';
  // Permisos de la operación y texto del botón principal.
  const operationKind = pending?.kind || kind;
  const allowed = can(operationKind === 'devolucion' ? 'pagos.corregir' : 'pagos.registrar') && (operationKind === 'devolucion' || can('pagos.conciliar'));
  const canSubmit = allowed && (Boolean(pending) || (!existingCollection && validAmount && validReason && (kind !== 'efectivo' || validReceived)));
  const paymentLabel = pending ? 'Reintentar operación guardada' : kind === 'devolucion' ? `Registrar devolución de ${money(canonicalAmount)}` : kind === 'transferencia' ? `Confirmar ingreso de ${money(canonicalAmount)}` : `Cobrar ${money(canonicalAmount)} en efectivo`;
  // Ejecuta el pago: crea y guarda el intento (con clave de operación) antes de enviarlo
  // y solo lo libera si la respuesta pertenece a la misma sesión que lo inició.
  const perform = async () => {
    if (busy || !canSubmit) return;
    if (!attempt.current) {
      const body = { pedido_id: order.id };
      if (kind === 'efectivo') Object.assign(body, { monto_recibido: canonicalReceived, monto_a_pagar: canonicalAmount, conciliar_inmediato: true });
      else Object.assign(body, { monto: canonicalAmount });
      if (kind === 'devolucion') Object.assign(body, { motivo: reason.trim() || 'Devolución registrada desde el panel.', metodo_pago: method });
      attempt.current = createPaymentAttempt(body, kind);
      saveAttempt(key, attempt.current);
      setPending(attempt.current);
    }
    await run(async (isCurrentSession = () => true) => {
      const currentSessionFetch = (path, options) => {
        if (!isCurrentSession()) throw new UserFacingError('La sesión cambió; revisá el cobro con la cuenta que lo inició.');
        return apiFetch(path, options);
      };
      const result = await executePayment(currentSessionFetch, attempt.current, { operativa: true });
      if (!isCurrentSession()) return result;
      attempt.current = null;
      saveAttempt(key, null);
      setPending(null);
      setConfirmRefund(false);
      return result;
    }, 'Pago actualizado.', { keepOpen: attempt.current.kind === 'transferencia' });
  };
  // Las devoluciones piden confirmación antes de registrarse.
  const submit = async (event) => {
    event.preventDefault();
    if (busy || !canSubmit) return;
    if (kind === 'devolucion' && !pending) setConfirmRefund(true);
    else await perform();
  };
  // Libera un intento pendiente que el usuario confirmó haber resuelto por otra vía.
  const discard = () => {
    if (!confirmDiscard || busy) return;
    attempt.current = null;
    saveAttempt(key, null);
    setPending(null);
    setConfirmDiscard(false);
  };
  return <section className="space-y-3">
    {/* Encabezado con saldo pendiente o importe cobrado */}
    <div className="flex flex-wrap justify-between gap-2"><h3 className="font-extrabold text-monu-dark">Pago</h3><p className="text-sm font-bold">{order.estado === 'CANCELADO' ? `Cobrado: ${money(order.neto_cobrado)}` : Number(order.saldo_pendiente) > 0 ? `Pendiente: ${money(order.saldo_pendiente)}` : 'Pagado'}</p></div>
    {!pending && kind === 'transferencia' && Number(order.saldo_pendiente) > 0 && <p className="text-sm">Confirmá sólo cuando veas el dinero ingresado en la cuenta.</p>}
    {/* Cobros pendientes de verificar (conciliación manual) */}
    {!pending && can('pagos.conciliar') && pendingPayments.length > 0 && <div className="space-y-2"><p className="text-sm">Cobros por verificar: confirmá sólo el dinero que ya recibiste.</p>{pendingPayments.map((payment) => <div key={payment.id} className="space-y-1"><p className="text-sm font-bold">{paymentMethodLabel(payment.metodo_pago)}</p><Reconcile payment={payment} commands={commands} run={run} busy={busy} /></div>)}</div>}
    {/* Intento guardado sin confirmar: reintentar o liberarlo */}
    {pending && <div className="rounded-xl bg-orange-50 p-3 text-sm text-orange-950 space-y-2"><p>Hay un {pending.kind === 'devolucion' ? 'reintegro' : 'cobro'} de {money(pending.body.monto ?? pending.body.monto_a_pagar)} por verificar. Reintentá para conocer el resultado sin duplicarlo.</p><details><summary className="cursor-pointer min-h-11 flex items-center font-bold">Ya lo resolví por otra vía</summary>{confirmDiscard ? <div className="space-y-2"><p>¿Revisaste el historial y comprobaste cómo se resolvió? Liberar este intento permite registrar otra operación.</p><button type="button" disabled={busy} onClick={discard} className={buttonClass}>Sí, ya revisé el movimiento</button><button type="button" disabled={busy} onClick={() => setConfirmDiscard(false)} className={buttonClass}>Volver</button></div> : <button type="button" disabled={busy} onClick={() => setConfirmDiscard(true)} className={buttonClass}>Revisar y liberar intento</button>}</details></div>}
    {/* Formulario de cobro o devolución */}
    {(can('pagos.registrar') || can('pagos.corregir')) && <form onSubmit={submit} className="space-y-3">
      {!pending && <details><summary className="cursor-pointer min-h-11 flex items-center text-sm font-bold text-monu-green">Otros importes, medios de pago o devolución</summary><div className="space-y-3 pt-2">
        <Field label="Operación"><select value={kind} onChange={(event) => { const next = event.target.value; setKind(next); setAmount(String(next === 'devolucion' ? order.neto_cobrado : order.saldo_pendiente)); setReceived(''); setConfirmRefund(false); }} disabled={busy} className={inputClass}><option value="efectivo" disabled={order.estado === 'CANCELADO' || !can('pagos.registrar')}>Cobrar en efectivo</option><option value="transferencia" disabled={order.estado === 'CANCELADO' || !can('pagos.registrar')}>Confirmar transferencia</option><option value="devolucion" disabled={Number(order.neto_cobrado) <= 0 || !can('pagos.corregir')}>Devolver dinero</option></select></Field>
        <Field label={kind === 'devolucion' ? 'Importe a devolver' : 'Importe a cobrar'}><input type="text" inputMode="decimal" max={maximum} value={amount} onChange={(event) => { setAmount(event.target.value); setConfirmRefund(false); }} disabled={busy} aria-invalid={!validAmount} aria-describedby={amountError ? 'payment-amount-error' : 'payment-amount-help'} className={inputClass} /><span id="payment-amount-help" className="text-sm font-normal">Hasta dos decimales, con coma o punto, sin separadores de miles.</span>{amountError && <span id="payment-amount-error" role="alert" className="block text-sm text-red-800">{amountError}</span>}</Field>
        {kind === 'efectivo' && <><Field label="Recibís (opcional, para calcular vuelto)"><input type="text" inputMode="decimal" value={received} onChange={(event) => setReceived(event.target.value)} disabled={busy} aria-invalid={Boolean(receivedError)} aria-describedby={receivedError ? 'payment-received-error' : undefined} className={inputClass} />{receivedError && <span id="payment-received-error" role="alert" className="block text-sm text-red-800">{receivedError}</span>}</Field>{received.trim() && validReceived && validAmount && <p className="text-sm">Vuelto: <strong>{money(Number(canonicalReceived) - Number(canonicalAmount))}</strong></p>}</>}
        {kind === 'devolucion' && <><Field label="Método de devolución"><select value={method} disabled={busy} onChange={(event) => { setMethod(event.target.value); setConfirmRefund(false); }} className={inputClass}><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select></Field><Reason value={reason} onChange={setReason} disabled={busy} error={reasonError} /></>}
      </div></details>}
      {confirmRefund && !pending ? <div className="rounded-xl bg-orange-50 p-3 text-sm text-orange-950 space-y-3"><p>¿Ya devolviste {money(canonicalAmount)} al cliente?</p><div className="flex flex-wrap gap-2"><button type="button" disabled={busy || !canSubmit} onClick={() => { void perform(); }} className={`${buttonClass} bg-monu-green text-white`}>Sí, registrar devolución</button><button type="button" disabled={busy} onClick={() => setConfirmRefund(false)} className={buttonClass}>Volver</button></div></div>
        : (pending || (!existingCollection && maximum > 0)) && <button disabled={busy || !canSubmit} className={`${buttonClass} w-full bg-monu-green text-white`}>{paymentLabel}</button>}
    </form>}
    {/* Movimientos de pago registrados */}
    {order.pagos.length > 0 && <details className="text-sm"><summary className="cursor-pointer min-h-11 flex items-center font-bold text-monu-green">Ver movimientos · Recibido: {money(order.neto_cobrado)}</summary><ul className="space-y-2">{order.pagos.map((payment) => <li key={payment.id} className="p-3 border border-monu-green/20 rounded-lg">{knownLabel({ DEVOLUCION: 'Devolución', COBRO: 'Cobro' }, payment.tipo)} · {paymentMethodLabel(payment.metodo_pago)} · {money(payment.monto)} · {knownLabel({ PENDIENTE: 'Por verificar', CONCILIADO: 'Registrado', ANULADO: 'Anulado' }, payment.estado)}</li>)}</ul></details>}
  </section>;
}

/** Botón para conciliar (confirmar el ingreso de) un cobro pendiente. */
function Reconcile({ payment, commands, run, busy }) {
  return <button type="button" disabled={busy} onClick={() => { if (!busy) void run(() => commands.reconcile(payment.id), 'Ingreso registrado.', { keepOpen: payment.metodo_pago === 'TRANSFERENCIA' }); }} className={`${buttonClass} w-full bg-monu-green text-white`}>Confirmar ingreso de {money(payment.monto)}</button>;
}
