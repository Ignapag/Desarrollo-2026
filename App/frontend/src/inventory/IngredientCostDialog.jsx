import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { X } from 'lucide-react';
import { userErrorMessage } from '../shared/api/userErrors.js';
import { DataError } from '../fulfillment/operationUi';
import { costUnitLabel, parseUnitCost } from './ingredientCost';

export default function IngredientCostDialog({ item, onSave, onClose }) {
  const [value, setValue] = useState(item.cost > 0 ? String(item.cost).replace('.', ',') : '');
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const saving = useRef(false);
  const mounted = useRef(true);
  const dialog = useRef(null);
  useEffect(() => { mounted.current = true; dialog.current?.showModal(); return () => { mounted.current = false; }; }, []);
  const parsed = parseUnitCost(value);
  const close = () => { if (!saving.current) onClose(); };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (saving.current) return;
    if (!parsed.valid) { setError(parsed.error); return; }
    saving.current = true;
    setError('');
    setIsSaving(true);
    try {
      await onSave(item.id, parsed.amount);
      if (!mounted.current) return;
      toast.success('Costo actualizado');
      onClose();
    } catch (failure) {
      if (!mounted.current) return;
      const message = userErrorMessage(failure, 'No pudimos guardar el costo. Comprobá el inventario antes de reintentar.');
      setError(message);
      toast.error('No pudimos guardar el costo', { description: message });
    } finally {
      saving.current = false;
      if (mounted.current) setIsSaving(false);
    }
  };

  return (
    <dialog ref={dialog} aria-labelledby="ingredient-cost-title" onCancel={(event) => { event.preventDefault(); close(); }} className="m-auto max-h-[90dvh] overflow-y-auto rounded-3xl border-0 p-0 w-[min(28rem,calc(100%_-_2rem))] backdrop:bg-black/50">
      <div className="bg-white rounded-3xl p-6 w-full shadow-2xl relative">
        <button type="button" disabled={isSaving} onClick={close} aria-label="Cerrar formulario de costo"
          className="absolute top-4 right-4 p-2 text-gray-400 hover:text-gray-600 bg-gray-100 rounded-full">
          <X className="w-5 h-5" />
        </button>
        <h2 id="ingredient-cost-title" className="text-xl font-extrabold text-monu-dark mb-4 pr-8">Costo de {item.name}</h2>
        <form noValidate onSubmit={handleSubmit} className="space-y-4" aria-busy={isSaving}>
          <fieldset disabled={isSaving}>
            <label htmlFor="ingredient-cost" className="block text-sm font-bold text-monu-dark mb-1">Costo unitario ({costUnitLabel(item.category)})</label>
            <input id="ingredient-cost" autoFocus type="text" inputMode="decimal" value={value}
              onChange={(event) => setValue(event.target.value)}
              aria-invalid={Boolean(error)} aria-describedby="ingredient-cost-error ingredient-cost-help"
              className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none" placeholder="Ej.: 4,50" />
            <div id="ingredient-cost-error" className="mt-1"><DataError message={error} /></div>
            <p id="ingredient-cost-help" className="mt-1 text-xs text-monu-text">
              Costo actual de 1 {item.category}, hasta 2 decimales. Reportes lo aplica a todas las ventas del período consultado, también a las anteriores al cambio.
            </p>
          </fieldset>
          <button type="submit" disabled={isSaving}
            className="w-full bg-monu-green text-white font-bold py-3 rounded-xl hover:bg-[#002b22] transition disabled:cursor-wait disabled:opacity-70">
            {isSaving ? 'Guardando…' : 'Guardar costo'}
          </button>
        </form>
      </div>
    </dialog>
  );
}
