import { useState } from 'react';
import { canEditOperation, stateCommands, stateLabel } from './orderModel';
import { buttonClass, inputClass, Field, Reason, Confirmation } from './operationUi';

export function EditOperation({ order, role, commands, run, busy }) {
  const [delivery, setDelivery] = useState(order.tipo_entrega);
  const [payment, setPayment] = useState(order.metodo_pago_acordado);
  const [address, setAddress] = useState(order.direccion || { calle: '', numero: '', localidad: '', referencia: '' });
  const [notes, setNotes] = useState(order.observaciones || '');
  const [reason, setReason] = useState('');
  const changes = {};
  if (delivery !== order.tipo_entrega) changes.tipo_entrega = delivery;
  if (payment !== order.metodo_pago_acordado) changes.metodo_pago_acordado = payment;
  if ((notes.trim() || null) !== (order.observaciones?.trim() || null)) changes.observaciones = notes.trim() || null;
  const addressFields = ['calle', 'numero', 'localidad', 'referencia'];
  const addressChanged = addressFields.some((key) => (address[key]?.trim() || '') !== (order.direccion?.[key]?.trim() || ''));
  if (delivery === 'DELIVERY' && (addressChanged || !order.direccion_id)) {
    changes.direccion_nueva = Object.fromEntries(addressFields.map((key) => [key, address[key]?.trim() || (key === 'referencia' ? null : '')]));
  }
  const hasChanges = Object.keys(changes).length > 0;
  if (!canEditOperation(order, role)) return <p className="text-sm text-monu-text">Para editar dirección, modalidad o pago, el pedido debe estar abierto y sin repartidor asignado. Resolvé primero la asignación o el regreso real.</p>;
  const submit = (event) => {
    event.preventDefault();
    if (!reason.trim() || !hasChanges) return;
    void run(() => commands.edit(order, changes, reason.trim()), 'Datos operativos actualizados.');
  };
  return <details className="space-y-3"><summary className={`${buttonClass} cursor-pointer flex items-center`}>Editar dirección, entrega y pago</summary>
    <form onSubmit={submit} className="mt-3 space-y-3">
      <p className="text-sm text-monu-text">Se conserva el mismo pedido. La API valida cobertura y recalcula envío, total y saldo; los cobros anteriores se conservan.</p>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Modalidad"><select value={delivery} onChange={(event) => setDelivery(event.target.value)} disabled={busy} className={inputClass}><option value="DELIVERY">Delivery</option><option value="RETIRO">Retiro en local</option></select></Field>
        <Field label="Método de pago acordado"><select value={payment} onChange={(event) => setPayment(event.target.value)} disabled={busy} className={inputClass}><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select></Field>
      </div>
      {delivery === 'DELIVERY' && <div className="grid sm:grid-cols-2 gap-3">{[['calle', 'Calle', 160], ['numero', 'Número', 30], ['localidad', 'Localidad', 100], ['referencia', 'Referencia (opcional)', 300]].map(([key, label, max]) => <Field key={key} label={label}><input required={key !== 'referencia'} maxLength={max} value={address[key] || ''} onChange={(event) => setAddress({ ...address, [key]: event.target.value })} disabled={busy} className={inputClass} /></Field>)}</div>}
      <Field label="Observaciones"><textarea value={notes} maxLength={500} onChange={(event) => setNotes(event.target.value)} disabled={busy} className={inputClass} /></Field>
      <Reason value={reason} onChange={setReason} disabled={busy} />
      <button disabled={busy || !hasChanges} className={`${buttonClass} bg-monu-green text-white`}>Guardar cambios</button>
    </form>
  </details>;
}

export function StateOperation({ order, role, commands, run, busy }) {
  const options = stateCommands(order, role);
  const [selected, setSelected] = useState('');
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const command = options.find((item) => item.estado === selected);
  if (!options.length) return null;
  const stock = command?.tratamiento_stock;
  const submit = (event) => {
    event.preventDefault();
    if (!command || !reason.trim() || !confirmed) return;
    void run(() => commands.state(order, command, reason.trim()), 'Estado registrado.');
  };
  return <form onSubmit={submit} className="space-y-3">
    <h3 className="font-extrabold text-monu-dark">Estado y correcciones</h3>
    <Field label={`Acción desde ${stateLabel(order.estado)}`}><select required value={selected} onChange={(event) => { setSelected(event.target.value); setConfirmed(false); }} disabled={busy} className={inputClass}><option value="">Elegir acción</option>{options.map((item) => <option key={item.estado} value={item.estado}>{item.label}</option>)}</select></Field>
    {stock && <p className="text-sm text-orange-900">{stock === 'MERMA' ? 'Los insumos utilizados se declaran como merma: no vuelven a estar disponibles.' : stock === 'RECONSUMIR' ? 'La reapertura consumirá insumos nuevamente. Los movimientos y cobros anteriores se conservan.' : 'Se conserva el consumo de insumos existente; no se devuelve stock.'}</p>}
    {command?.estado === 'CANCELADO' && !stock && <p className="text-sm text-monu-text">La reserva se devuelve únicamente si todavía no comenzó la preparación. Cancelar no devuelve dinero: registrá el reintegro correspondiente en pagos.</p>}
    <Reason value={reason} onChange={setReason} disabled={busy} />
    <Confirmation checked={confirmed} onChange={setConfirmed} disabled={busy}>Verifiqué la situación real y confirmo esta acción sobre el pedido #{order.numero}.</Confirmation>
    <button disabled={busy || !command || !confirmed} className={`${buttonClass} bg-monu-dark text-white`}>{busy ? 'Registrando...' : 'Registrar acción'}</button>
  </form>;
}
