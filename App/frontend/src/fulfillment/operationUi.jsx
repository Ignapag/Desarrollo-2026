// Piezas de interfaz compartidas por las pantallas de operación de pedidos:
// clases de botones y campos, etiqueta de campo, nota opcional y aviso de error.
export const buttonClass = 'min-h-11 px-4 py-2 rounded-xl text-sm font-bold border border-monu-green/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green disabled:opacity-50 disabled:cursor-not-allowed hover:bg-monu-green/10';
export const inputClass = 'w-full min-h-11 px-3 py-2 text-base font-normal border border-monu-green/30 rounded-lg bg-white focus:outline-2 focus:outline-monu-green disabled:opacity-60';

/** Campo con etiqueta visible que envuelve al control recibido en `children`. */
export function Field({ label, children }) {
  return <label className="block space-y-1 text-sm font-bold text-monu-dark"><span>{label}</span>{children}</label>;
}
/** Nota opcional (motivo) desplegable, limitada a 500 caracteres, con error accesible. */
export function Reason({ value, onChange, disabled, error = '' }) {
  return <details className="text-sm"><summary className="cursor-pointer min-h-11 flex items-center font-bold text-monu-green">Agregar nota (opcional)</summary><Field label="Nota (opcional)"><textarea maxLength={500} rows={2} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} aria-invalid={Boolean(error)} aria-describedby={error ? 'payment-reason-error' : undefined} className={inputClass} />{error && <span id="payment-reason-error" role="alert" className="block text-sm text-red-800">{error}</span>}</Field></details>;
}
/** Aviso de error de datos con botón opcional "Actualizar y revisar"; no dibuja nada sin mensaje. */
export function DataError({ message, retry, busy = false }) {
  return message ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 space-y-2 text-sm text-red-900"><p>{message}</p>{retry && <button type="button" disabled={busy} onClick={retry} className={buttonClass}>Actualizar y revisar</button>}</div> : null;
}
