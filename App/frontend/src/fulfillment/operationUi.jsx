export const buttonClass = 'min-h-11 px-4 py-2 rounded-xl text-sm font-bold border border-monu-green/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-monu-green disabled:opacity-50 disabled:cursor-not-allowed hover:bg-monu-green/10';
export const inputClass = 'w-full min-h-11 px-3 py-2 text-base font-normal border border-monu-green/30 rounded-lg bg-white focus:outline-2 focus:outline-monu-green disabled:opacity-60';

export function Field({ label, children }) {
  return <label className="block space-y-1 text-sm font-bold text-monu-dark"><span>{label}</span>{children}</label>;
}
export function Reason({ value, onChange, disabled }) {
  return <Field label="Motivo (obligatorio)"><textarea required maxLength={500} rows={2} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} className={inputClass} /></Field>;
}
export function Confirmation({ checked, onChange, children, disabled }) {
  return <label className="flex items-start gap-3 min-h-11 text-sm text-monu-dark"><input type="checkbox" required checked={checked} onChange={(event) => onChange(event.target.checked)} disabled={disabled} className="mt-1 w-5 h-5 shrink-0 accent-monu-green" /><span>{children}</span></label>;
}
export function DataError({ message, retry, busy = false }) {
  return message ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 space-y-2 text-sm text-red-900"><p>{message}</p>{retry && <button type="button" disabled={busy} onClick={retry} className={buttonClass}>Actualizar y revisar</button>}</div> : null;
}
