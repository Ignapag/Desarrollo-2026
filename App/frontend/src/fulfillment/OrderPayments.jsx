import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';
import { createPaymentAttempt, executePayment } from './orderCommands';
import { money } from './orderModel';
import { buttonClass, inputClass, Field, Reason } from './operationUi';

function readAttempt(key) {
  try { return JSON.parse(sessionStorage.getItem(key)) || null; } catch { return null; }
}
function saveAttempt(key, value) {
  try { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); } catch { /* El ref conserva el reintento mientras esta vista siga abierta. */ }
}

const defaultKind = (order) => order.estado === 'CANCELADO' ? 'devolucion' : order.metodo_pago_acordado === 'TRANSFERENCIA' ? 'transferencia' : 'efectivo';
const defaultAmount = (order) => String(order.estado === 'CANCELADO' ? order.neto_cobrado : order.saldo_pendiente);

export default function OrderPayments({ order, userId, commands, run, busy }) {
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
  useEffect(() => {
    if (attempt.current) return;
    setKind(startingKind);
    setAmount(startingAmount);
    setReceived('');
    setConfirmRefund(false);
  }, [order.id, startingKind, startingAmount]);
  const pendingPayments = order.pagos.filter((payment) => payment.tipo === 'COBRO' && payment.estado === 'PENDIENTE');
  const existingCollection = pendingPayments.some((payment) => payment.metodo_pago === ({ efectivo: 'EFECTIVO', transferencia: 'TRANSFERENCIA' })[kind]);
  const maximum = Number(kind === 'devolucion' ? order.neto_cobrado : order.estado === 'CANCELADO' ? 0 : order.saldo_pendiente);
  const validAmount = Number.isFinite(Number(amount)) && Number(amount) > 0 && Number(amount) <= maximum;
  const validReceived = !received || (Number.isFinite(Number(received)) && Number(received) >= Number(amount));
  const canSubmit = Boolean(pending) || (!existingCollection && validAmount && (kind !== 'efectivo' || validReceived));
  const paymentLabel = pending ? 'Reintentar operación guardada' : kind === 'devolucion' ? `Registrar devolución de ${money(amount)}` : kind === 'transferencia' ? `Confirmar ingreso de ${money(amount)}` : `Cobrar ${money(amount)} en efectivo`;
  const perform = async () => {
    if (busy || !canSubmit) return;
    if (!attempt.current) {
      const body = { pedido_id: order.id };
      if (kind === 'efectivo') Object.assign(body, { monto_recibido: received || amount, monto_a_pagar: amount, conciliar_inmediato: true });
      else Object.assign(body, { monto: amount });
      if (kind === 'devolucion') Object.assign(body, { motivo: reason.trim() || 'Devolución registrada desde el panel.', metodo_pago: method });
      attempt.current = createPaymentAttempt(body, kind);
      saveAttempt(key, attempt.current);
      setPending(attempt.current);
    }
    await run(async () => {
      const result = await executePayment(apiFetch, attempt.current, { operativa: true });
      attempt.current = null;
      saveAttempt(key, null);
      setPending(null);
      setConfirmRefund(false);
      return result;
    }, 'Pago actualizado.');
  };
  const submit = async (event) => {
    event.preventDefault();
    if (busy || !canSubmit) return;
    if (kind === 'devolucion' && !pending) setConfirmRefund(true);
    else await perform();
  };
  const discard = () => {
    if (!confirmDiscard || busy) return;
    attempt.current = null;
    saveAttempt(key, null);
    setPending(null);
    setConfirmDiscard(false);
  };
  return <section className="space-y-3">
    <div className="flex flex-wrap justify-between gap-2"><h3 className="font-extrabold text-monu-dark">Pago</h3><p className="text-sm font-bold">{order.estado === 'CANCELADO' ? `Cobrado: ${money(order.neto_cobrado)}` : Number(order.saldo_pendiente) > 0 ? `Pendiente: ${money(order.saldo_pendiente)}` : 'Pagado'}</p></div>
    {!pending && kind === 'transferencia' && Number(order.saldo_pendiente) > 0 && <p className="text-sm">Confirmá sólo cuando veas el dinero ingresado en la cuenta.</p>}
    {!pending && pendingPayments.length > 0 && <div className="space-y-2"><p className="text-sm">Cobros por verificar: confirmá sólo el dinero que ya recibiste.</p>{pendingPayments.map((payment) => <div key={payment.id} className="space-y-1"><p className="text-sm font-bold">{({ EFECTIVO: 'Efectivo', TRANSFERENCIA: 'Transferencia' })[payment.metodo_pago] || payment.metodo_pago}</p><Reconcile payment={payment} commands={commands} run={run} busy={busy} /></div>)}</div>}
    {pending && <div className="rounded-xl bg-orange-50 p-3 text-sm text-orange-950 space-y-2"><p>Hay un {pending.kind === 'devolucion' ? 'reintegro' : 'cobro'} de {money(pending.body.monto ?? pending.body.monto_a_pagar)} por verificar. Reintentá para conocer el resultado sin duplicarlo.</p><details><summary className="cursor-pointer min-h-11 flex items-center font-bold">Ya lo resolví por otra vía</summary>{confirmDiscard ? <div className="space-y-2"><p>¿Revisaste el historial y comprobaste cómo se resolvió? Liberar este intento permite registrar otra operación.</p><button type="button" disabled={busy} onClick={discard} className={buttonClass}>Sí, ya revisé el movimiento</button><button type="button" disabled={busy} onClick={() => setConfirmDiscard(false)} className={buttonClass}>Volver</button></div> : <button type="button" disabled={busy} onClick={() => setConfirmDiscard(true)} className={buttonClass}>Revisar y liberar intento</button>}</details></div>}
    <form onSubmit={submit} className="space-y-3">
      {!pending && <details><summary className="cursor-pointer min-h-11 flex items-center text-sm font-bold text-monu-green">Otros importes, medios de pago o devolución</summary><div className="space-y-3 pt-2">
        <Field label="Operación"><select value={kind} onChange={(event) => { const next = event.target.value; setKind(next); setAmount(String(next === 'devolucion' ? order.neto_cobrado : order.saldo_pendiente)); setReceived(''); setConfirmRefund(false); }} disabled={busy} className={inputClass}><option value="efectivo" disabled={order.estado === 'CANCELADO'}>Cobrar en efectivo</option><option value="transferencia" disabled={order.estado === 'CANCELADO'}>Confirmar transferencia</option><option value="devolucion" disabled={Number(order.neto_cobrado) <= 0}>Devolver dinero</option></select></Field>
        <Field label={kind === 'devolucion' ? 'Importe a devolver' : 'Importe a cobrar'}><input type="number" min="0.01" step="0.01" max={maximum} value={amount} onChange={(event) => { setAmount(event.target.value); setConfirmRefund(false); }} disabled={busy} className={inputClass} /></Field>
        {kind === 'efectivo' && <><Field label="Recibís (opcional, para calcular vuelto)"><input type="number" min={amount || '0.01'} step="0.01" value={received} onChange={(event) => setReceived(event.target.value)} disabled={busy} className={inputClass} /></Field>{received && validReceived && validAmount && <p className="text-sm">Vuelto: <strong>{money(Number(received) - Number(amount))}</strong></p>}</>}
        {kind === 'devolucion' && <><Field label="Método de devolución"><select value={method} disabled={busy} onChange={(event) => { setMethod(event.target.value); setConfirmRefund(false); }} className={inputClass}><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select></Field><Reason value={reason} onChange={setReason} disabled={busy} /></>}
      </div></details>}
      {confirmRefund && !pending ? <div className="rounded-xl bg-orange-50 p-3 text-sm text-orange-950 space-y-3"><p>¿Ya devolviste {money(amount)} al cliente?</p><div className="flex flex-wrap gap-2"><button type="button" disabled={busy || !canSubmit} onClick={() => { void perform(); }} className={`${buttonClass} bg-monu-green text-white`}>Sí, registrar devolución</button><button type="button" disabled={busy} onClick={() => setConfirmRefund(false)} className={buttonClass}>Volver</button></div></div>
        : (pending || (!existingCollection && maximum > 0)) && <button disabled={busy || !canSubmit} className={`${buttonClass} w-full bg-monu-green text-white`}>{paymentLabel}</button>}
    </form>
    {order.pagos.length > 0 && <details className="text-sm"><summary className="cursor-pointer min-h-11 flex items-center font-bold text-monu-green">Ver movimientos · Recibido: {money(order.neto_cobrado)}</summary><ul className="space-y-2">{order.pagos.map((payment) => <li key={payment.id} className="p-3 border border-monu-green/20 rounded-lg">{payment.tipo === 'DEVOLUCION' ? 'Devolución' : 'Cobro'} · {({ EFECTIVO: 'Efectivo', TRANSFERENCIA: 'Transferencia' })[payment.metodo_pago] || payment.metodo_pago} · {money(payment.monto)} · {({ PENDIENTE: 'Por verificar', CONCILIADO: 'Registrado', ANULADO: 'Anulado' })[payment.estado] || payment.estado}</li>)}</ul></details>}
  </section>;
}

function Reconcile({ payment, commands, run, busy }) {
  return <button type="button" disabled={busy} onClick={() => { if (!busy) void run(() => commands.reconcile(payment.id), 'Ingreso registrado.'); }} className={`${buttonClass} w-full bg-monu-green text-white`}>Confirmar ingreso de {money(payment.monto)}</button>;
}
