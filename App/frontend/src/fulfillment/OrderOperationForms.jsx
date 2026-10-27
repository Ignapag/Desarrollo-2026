import { useRef, useState } from 'react';
import { canEditOperation, stateCommands } from './orderModel';
import { buttonClass, inputClass, Field, Reason } from './operationUi';

export function EditOperation({ order, role, commands, run, busy, can = null }) {
  const [base, setBase] = useState(order);
  const [delivery, setDelivery] = useState(order.tipo_entrega);
  const [payment, setPayment] = useState(order.metodo_pago_acordado);
  const [address, setAddress] = useState(order.direccion || { calle: '', numero: '', localidad: '', referencia: '' });
  const [notes, setNotes] = useState(order.observaciones || '');
  const [reason, setReason] = useState('');
  const [invalidAddress, setInvalidAddress] = useState([]);
  const addressRefs = useRef({});
  const changes = {};
  if (delivery !== base.tipo_entrega) changes.tipo_entrega = delivery;
  if (payment !== base.metodo_pago_acordado) changes.metodo_pago_acordado = payment;
  if ((notes.trim() || null) !== (base.observaciones?.trim() || null)) changes.observaciones = notes.trim() || null;
  const addressFields = ['calle', 'numero', 'localidad', 'referencia'];
  const addressChanged = addressFields.some((key) => (address[key]?.trim() || '') !== (base.direccion?.[key]?.trim() || ''));
  if (delivery === 'DELIVERY' && (addressChanged || !base.direccion_id)) {
    changes.direccion_nueva = Object.fromEntries(addressFields.map((key) => [key, address[key]?.trim() || (key === 'referencia' ? null : '')]));
  }
  const hasChanges = Object.keys(changes).length > 0;
  const needsRebase = base.version !== order.version;
  const rebase = (discard = false) => {
    if (busy) return;
    if (discard || delivery === base.tipo_entrega) setDelivery(order.tipo_entrega);
    if (discard || payment === base.metodo_pago_acordado) setPayment(order.metodo_pago_acordado);
    if (discard || (notes.trim() || null) === (base.observaciones?.trim() || null)) setNotes(order.observaciones || '');
    setAddress(Object.fromEntries(addressFields.map((key) => [key, discard || (address[key]?.trim() || '') === (base.direccion?.[key]?.trim() || '') ? order.direccion?.[key] || '' : address[key]])));
    if (discard) setReason('');
    setBase(order);
  };
  if (!canEditOperation(order, role, can)) return null;
  const submit = (event) => {
    event.preventDefault();
    if (busy || needsRebase || !hasChanges) return;
    const invalid = changes.direccion_nueva ? addressFields.filter((key) => key !== 'referencia' && !address[key]?.trim()) : [];
    setInvalidAddress(invalid);
    if (invalid.length) { addressRefs.current[invalid[0]]?.focus(); return; }
    const changedLabels = { tipo_entrega: 'entrega', metodo_pago_acordado: 'forma de pago', direccion_nueva: 'dirección', observaciones: 'observaciones' };
    const annotation = reason.trim() || `Edición desde el panel: ${Object.keys(changes).map((key) => changedLabels[key]).join(', ')}.`;
    void run(() => commands.edit(order, changes, annotation), 'Cambios guardados.', { keepOpen: true, resetEdit: true });
  };
  return <details className="space-y-3"><summary className={`${buttonClass} cursor-pointer flex items-center`}>Editar dirección, entrega y pago</summary>
    <form onSubmit={submit} className="mt-3 space-y-3">
      {needsRebase && <div role="alert" className="rounded-xl border border-orange-200 bg-orange-50 p-3 space-y-2 text-sm text-orange-950"><p>El pedido cambió a la versión {order.version}. Conservamos tu borrador: comparalo con el detalle actualizado antes de guardar. Los campos que no editaste adoptarán los valores actuales.</p><button type="button" disabled={busy} onClick={() => rebase()} className={buttonClass}>Conservar borrador sobre la versión actual</button><button type="button" disabled={busy} onClick={() => rebase(true)} className={buttonClass}>Descartar borrador y usar datos actuales</button></div>}
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Modalidad"><select value={delivery} onChange={(event) => setDelivery(event.target.value)} disabled={busy} className={inputClass}><option value="DELIVERY">Delivery</option><option value="RETIRO">Retiro en local</option></select></Field>
        <Field label="Método de pago acordado"><select value={payment} onChange={(event) => setPayment(event.target.value)} disabled={busy} className={inputClass}><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select></Field>
      </div>
      {delivery === 'DELIVERY' && <details open={order.tipo_entrega !== 'DELIVERY' || invalidAddress.length > 0}><summary className="cursor-pointer min-h-11 flex items-center text-sm font-bold text-monu-green">Cambiar dirección</summary><div className="grid sm:grid-cols-2 gap-3">{[['calle', 'Calle', 160], ['numero', 'Número', 30], ['localidad', 'Localidad', 100], ['referencia', 'Referencia (opcional)', 300]].map(([key, label, max]) => <Field key={key} label={label}><input ref={(node) => { addressRefs.current[key] = node; }} required={Boolean(changes.direccion_nueva) && key !== 'referencia'} maxLength={max} value={address[key] || ''} onChange={(event) => { setAddress({ ...address, [key]: event.target.value }); setInvalidAddress((current) => current.filter((field) => field !== key)); }} disabled={busy} aria-invalid={invalidAddress.includes(key)} aria-describedby={invalidAddress.includes(key) ? `operation-address-${key}-error` : undefined} className={inputClass} />{invalidAddress.includes(key) && <span id={`operation-address-${key}-error`} role="alert" className="block text-sm text-red-800">Completá {label.toLowerCase()}.</span>}</Field>)}</div></details>}
      <Field label="Observaciones"><textarea value={notes} maxLength={500} onChange={(event) => setNotes(event.target.value)} disabled={busy} className={inputClass} /></Field>
      <Reason value={reason} onChange={setReason} disabled={busy} />
      <button disabled={busy || needsRebase || !hasChanges} className={`${buttonClass} bg-monu-green text-white`}>Guardar cambios</button>
    </form>
  </details>;
}

export function StateOperation({ order, role, commands, run, busy, can = null }) {
  const options = stateCommands(order, role, can).filter(() => !can || (can('pedidos.cambiar_estado') && (!['ENTREGADO', 'CANCELADO'].includes(order.estado) || can('pedidos.recuperar'))));
  const [reason, setReason] = useState('');
  const [confirming, setConfirming] = useState(null);
  if (!options.length) return null;
  const next = { PENDIENTE: 'EN_PREPARACION', CONFIRMADO: 'EN_PREPARACION', EN_PREPARACION: 'LISTO', LISTO: order.tipo_entrega === 'RETIRO' ? 'ENTREGADO' : null }[order.estado];
  const primary = options.find((item) => item.estado === next);
  const others = options.filter((item) => item !== primary);
  const needsPayment = order.metodo_pago_acordado === 'TRANSFERENCIA' && Number(order.saldo_pendiente) > 0;
  const label = (item) => item.estado === 'CANCELADO' ? 'Cancelar pedido'
    : item.tratamiento_stock === 'RECONSUMIR' ? 'Reabrir pedido'
    : item.correccion ? ({ PENDIENTE: 'Volver a nuevos', CONFIRMADO: 'Volver a confirmados', EN_PREPARACION: 'Volver a cocina', LISTO: 'Volver a listo' })[item.estado] || item.label : item.label;
  const apply = (command) => {
    if (busy || (command.estado === 'EN_PREPARACION' && needsPayment)) return;
    void run(() => commands.state(order, command, reason.trim() || `Acción desde el panel: ${command.label}.`), 'Pedido actualizado.', { optimisticOrder: { ...order, estado: command.estado } });
  };
  return <section aria-label="Acciones del pedido" className="space-y-3">
    {primary && <button type="button" disabled={busy || (primary.estado === 'EN_PREPARACION' && needsPayment)} onClick={() => apply(primary)} className={`${buttonClass} w-full bg-monu-dark text-white`}>{label(primary)}</button>}
    {primary?.estado === 'EN_PREPARACION' && needsPayment && <p className="text-sm">Confirmá el ingreso de la transferencia para enviarlo a cocina.</p>}
    {others.length > 0 && <details><summary className="cursor-pointer min-h-11 flex items-center text-sm font-bold text-monu-green">Más acciones</summary><div className="space-y-3 pt-2">
      <div className="flex flex-wrap gap-2">{others.map((item) => <button key={item.estado} type="button" disabled={busy || (item.estado === 'EN_PREPARACION' && needsPayment)} onClick={() => {
        if (item.estado === 'CANCELADO' || item.tratamiento_stock === 'RECONSUMIR') setConfirming(item);
        else apply(item);
      }} className={`${buttonClass} ${item.estado === 'CANCELADO' ? 'text-red-800 border-red-200' : ''}`}>{label(item)}</button>)}</div>
      <Reason value={reason} onChange={setReason} disabled={busy} />
      {confirming && <div role="group" aria-label={`Confirmar acción sobre pedido #${order.numero}`} className="rounded-xl border border-orange-200 bg-orange-50 p-3 space-y-3 text-sm text-orange-950">
        <p className="font-bold">{confirming.estado === 'CANCELADO' ? `¿Cancelar el pedido #${order.numero}?` : `¿Volver a preparar el pedido #${order.numero}?`}</p>
        <p>{confirming.tratamiento_stock === 'RECONSUMIR' ? 'Se descontarán insumos nuevamente.' : confirming.tratamiento_stock === 'MERMA' ? 'Los insumos utilizados se registrarán como merma.' : 'La reserva de insumos se devolverá al inventario.'}{confirming.estado === 'CANCELADO' && Number(order.neto_cobrado) > 0 ? ' El dinero cobrado se devuelve por separado.' : ''}</p>
        <div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={() => { apply(confirming); setConfirming(null); }} className={`${buttonClass} bg-monu-dark text-white`}>{confirming.estado === 'CANCELADO' ? 'Confirmar cancelación' : 'Confirmar nueva preparación'}</button><button type="button" disabled={busy} onClick={() => setConfirming(null)} className={buttonClass}>Volver</button></div>
      </div>}
    </div></details>}
  </section>;
}
