import { useRef, useState } from 'react';
import { apiFetch } from '../shared/api/http';
import { createPaymentAttempt, executePayment } from './orderCommands';
import { money } from './orderModel';
import { buttonClass, inputClass, Field, Reason, Confirmation } from './operationUi';

function readAttempt(key) {
  try { return JSON.parse(sessionStorage.getItem(key)) || null; } catch { return null; }
}
function saveAttempt(key, value) {
  try { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); } catch { /* El ref conserva el reintento mientras esta vista siga abierta. */ }
}

export default function OrderPayments({ order, userId, commands, run, busy }) {
  const key = `monu-payment:${userId}:${order.id}`;
  const [pending, setPending] = useState(() => readAttempt(key));
  const attempt = useRef(pending);
  const [kind, setKind] = useState('efectivo');
  const [amount, setAmount] = useState(String(order.saldo_pendiente));
  const [received, setReceived] = useState(String(order.saldo_pendiente));
  const [method, setMethod] = useState('EFECTIVO');
  const [reason, setReason] = useState('');
  const [verified, setVerified] = useState(false);
  const [checkedHistory, setCheckedHistory] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    if (!verified) return;
    if (!attempt.current) {
      const body = { pedido_id: order.id };
      if (kind === 'efectivo') Object.assign(body, { monto_recibido: received, monto_a_pagar: amount, conciliar_inmediato: true });
      else Object.assign(body, { monto: amount });
      if (kind === 'devolucion') Object.assign(body, { motivo: reason.trim(), metodo_pago: method });
      attempt.current = createPaymentAttempt(body, kind);
      saveAttempt(key, attempt.current);
      setPending(attempt.current);
    }
    await run(async () => {
      const result = await executePayment(apiFetch, attempt.current);
      attempt.current = null;
      saveAttempt(key, null);
      setPending(null);
      setVerified(false);
      return result;
    }, 'Movimiento financiero registrado. El estado físico del pedido se conserva.');
  };
  const discard = () => {
    if (!checkedHistory || busy) return;
    attempt.current = null;
    saveAttempt(key, null);
    setPending(null);
    setVerified(false);
  };
  return <section className="space-y-3">
    <h3 className="font-extrabold text-monu-dark">Cobros y devoluciones</h3>
    <p className="text-sm text-monu-text">Neto conciliado: <strong>{money(order.neto_cobrado)}</strong>. Saldo pendiente: <strong>{money(order.saldo_pendiente)}</strong>. Una imagen de transferencia no acredita dinero.</p>
    <ul className="space-y-2 text-sm">{order.pagos.map((payment) => <li key={payment.id} className="p-3 border border-monu-green/20 rounded-lg space-y-2"><p>{payment.tipo === 'DEVOLUCION' ? 'Devolución' : 'Cobro'} · {payment.metodo_pago} · {money(payment.monto)} · {payment.estado}</p>{payment.tipo === 'COBRO' && payment.estado === 'PENDIENTE' && <Reconcile payment={payment} commands={commands} run={run} busy={busy || pending} />}</li>)}</ul>
    {pending && <div className="rounded-lg bg-orange-50 p-3 text-sm text-orange-900 space-y-2"><p>Operación conservada para reintentar: {pending.kind}, {money(pending.body.monto ?? pending.body.monto_a_pagar)}. Se enviará el mismo contenido y la misma clave para evitar duplicados.</p><p>Si ya se registró por otra vía, actualizá y revisá el historial antes de liberar este intento.</p><Confirmation checked={checkedHistory} onChange={setCheckedHistory} disabled={busy}>Revisé el saldo y el historial actualizado; confirmé cómo se resolvió esta operación.</Confirmation><button type="button" disabled={busy || !checkedHistory} onClick={discard} className={buttonClass}>Dar por revisado este intento</button></div>}
    <form onSubmit={submit} className="space-y-3">
      {!pending && <>
        <Field label="Movimiento real"><select value={kind} onChange={(event) => { setKind(event.target.value); setVerified(false); }} disabled={busy} className={inputClass}><option value="efectivo">Registrar efectivo recibido</option><option value="transferencia">Registrar transferencia e ingreso verificado</option><option value="devolucion">Registrar devolución realizada</option></select></Field>
        <Field label={kind === 'devolucion' ? 'Importe devuelto (hasta el neto conciliado)' : 'Importe a cobrar (hasta el saldo pendiente)'}><input type="number" required min="0.01" step="0.01" max={kind === 'devolucion' ? order.neto_cobrado : order.saldo_pendiente} value={amount} onChange={(event) => setAmount(event.target.value)} disabled={busy} className={inputClass} /></Field>
        {kind === 'efectivo' && <Field label="Efectivo recibido del cliente"><input type="number" required min={amount || '0.01'} step="0.01" value={received} onChange={(event) => setReceived(event.target.value)} disabled={busy} className={inputClass} /></Field>}
        {kind === 'devolucion' && <><Field label="Método de devolución"><select value={method} disabled={busy} onChange={(event) => setMethod(event.target.value)} className={inputClass}><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select></Field><Reason value={reason} onChange={setReason} disabled={busy} /></>}
      </>}
      <Confirmation checked={verified} onChange={setVerified} disabled={busy}>{(pending ? pending.kind : kind) === 'transferencia' ? 'Verifiqué personalmente el ingreso real de la transferencia. Confirmo registrar y conciliar ese ingreso.' : 'Confirmo que el movimiento de dinero ocurrió realmente y verifiqué su importe.'}</Confirmation>
      <button disabled={busy || !verified} className={`${buttonClass} bg-monu-green text-white`}>{busy ? 'Registrando...' : pending ? 'Reintentar la misma operación' : 'Registrar movimiento verificado'}</button>
    </form>
  </section>;
}

function Reconcile({ payment, commands, run, busy }) {
  const [verified, setVerified] = useState(false);
  return <div className="space-y-2"><Confirmation checked={verified} onChange={setVerified} disabled={busy}>Verifiqué personalmente el ingreso real de {money(payment.monto)}.</Confirmation><button type="button" disabled={busy || !verified} onClick={() => { void run(() => commands.reconcile(payment.id), 'Ingreso conciliado por el personal.'); }} className={buttonClass}>Conciliar ingreso verificado</button></div>;
}
