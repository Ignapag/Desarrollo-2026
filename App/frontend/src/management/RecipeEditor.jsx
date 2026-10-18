import { useId, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { buttonClass, inputClass } from '../fulfillment/operationUi';
import { parseRecipeQuantity, recipeUnit } from './recipeModel';

function QuantityField({ id, label, value, unit, disabled, onChange }) {
  const [touched, setTouched] = useState(false);
  const parsed = parseRecipeQuantity(value);
  const error = touched && !parsed.valid;
  return <div className="min-w-0 space-y-1">
    <label htmlFor={id} className="block text-sm font-bold text-monu-dark">{label} <span className="font-normal text-monu-text">({unit})</span></label>
    <input id={id} type="text" inputMode="text" autoComplete="off" spellCheck={false} maxLength={32} value={value} disabled={disabled} onBlur={() => setTouched(true)} onChange={(event) => onChange(event.target.value)} aria-describedby={`${id}-help`} aria-invalid={error || undefined} className={`${inputClass} w-full bg-white`} placeholder="Ej.: 0,25 o 1/4" />
    <p id={`${id}-help`} className={`min-h-5 text-xs ${error ? 'text-red-800' : 'text-monu-text'}`} role={error ? 'alert' : undefined}>{parsed.valid ? `${parsed.approximate ? 'Aprox. ' : ''}${parsed.display} ${unit} por producto` : error ? parsed.error : 'Decimal o fracción, por ejemplo 0,25 o 1/4.'}</p>
  </div>;
}

export default function RecipeEditor({ value, onChange, inventory, disabled = false, lockVariants = false, basePrice = '' }) {
  const id = useId();
  const updateRow = (index, changes) => onChange({ ...value, ingredients: value.ingredients.map((row, i) => i === index ? { ...row, ...changes } : row) });
  const addVariant = () => onChange({ ...value, variants: [...value.variants, { name: value.variants.length ? '' : 'Simple', price: basePrice }], ingredients: value.ingredients.map((row) => ({ ...row, quantities: [...row.quantities, row.quantities[0] || row.quantity], variantBase: [...(row.variantBase || []), row.esBase !== false] })) });
  const removeVariant = (index) => onChange({ ...value, variants: value.variants.filter((_, i) => i !== index), ingredients: value.ingredients.map((row) => ({ ...row, quantity: row.quantities[0] || row.quantity, quantities: row.quantities.filter((_, i) => i !== index), variantBase: row.variantBase?.filter((_, i) => i !== index) })) });
  const updateVariant = (index, changes) => onChange({ ...value, variants: value.variants.map((variant, i) => i === index ? { ...variant, ...changes } : variant) });
  return <fieldset disabled={disabled} className="space-y-4 min-w-0">
    <legend className="mb-2 font-extrabold text-lg text-monu-dark">Receta e ingredientes</legend>
    <p className="text-sm text-monu-text">Indicá lo que se usa en un producto. Podés escribir 1/4, 1/8, 0,25 o la cantidad que necesites.</p>
    {value.variants.length > 0 && <div className="space-y-3 rounded-xl bg-monu-cream/40 p-3">
      <p className="text-sm font-bold">Cantidades por variante</p>
      {value.variants.map((variant, index) => <div key={index} className="flex flex-wrap items-end gap-3">
        <div className="min-w-36 flex-1"><label htmlFor={`${id}-variant-${index}`} className="block text-sm font-bold">Variante {index + 1}</label><input id={`${id}-variant-${index}`} value={variant.name} disabled={disabled || lockVariants} maxLength={60} onChange={(event) => updateVariant(index, { name: event.target.value })} className={`${inputClass} w-full`} placeholder="Ej.: Doble" /></div>
        {!lockVariants && <div className="min-w-32 flex-1"><label htmlFor={`${id}-price-${index}`} className="block text-sm font-bold">Precio ($)</label><input id={`${id}-price-${index}`} inputMode="decimal" value={variant.price} onChange={(event) => updateVariant(index, { price: event.target.value })} className={`${inputClass} w-full`} /></div>}
        {!lockVariants && <button type="button" aria-label={`Quitar variante ${variant.name || index + 1}`} onClick={() => removeVariant(index)} className={`${buttonClass} text-red-700`}><Trash2 aria-hidden="true" className="h-4 w-4" /></button>}
      </div>)}
      <p className="text-xs text-monu-text">Definí cada cantidad: una doble puede usar dos medallones y un solo pan. Las fracciones no exactas muestran su aproximación a 3 decimales.</p>
    </div>}
    <div className="space-y-3">
      {value.ingredients.map((row, index) => {
        const ingredient = inventory.find((item) => String(item.id) === row.ingredientId);
        const unit = recipeUnit(ingredient?.category);
        return <div key={row.key} className="space-y-3 rounded-xl border border-monu-green/20 bg-monu-bone p-3 sm:p-4">
          <div className="flex items-end gap-2">
            <div className="min-w-0 flex-1"><label htmlFor={`${id}-ingredient-${row.key}`} className="block text-sm font-bold text-monu-dark">Ingrediente {index + 1}</label><select id={`${id}-ingredient-${row.key}`} value={row.ingredientId} onChange={(event) => updateRow(index, { ingredientId: event.target.value })} className={`${inputClass} w-full bg-white`}><option value="">Seleccioná un ingrediente</option>{inventory.map((item) => <option key={item.id} value={item.id} disabled={value.ingredients.some((other, i) => i !== index && other.ingredientId === String(item.id))}>{item.name} · {recipeUnit(item.category)}</option>)}</select></div>
            <button type="button" aria-label={`Quitar ingrediente ${ingredient?.name || index + 1}`} onClick={() => onChange({ ...value, ingredients: value.ingredients.filter((_, i) => i !== index) })} className={`${buttonClass} text-red-700`}><Trash2 aria-hidden="true" className="h-4 w-4" /></button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {value.variants.length ? value.variants.map((variant, variantIndex) => <QuantityField key={variantIndex} id={`${id}-${row.key}-${variantIndex}`} label={variant.name || `Variante ${variantIndex + 1}`} value={row.quantities[variantIndex]} unit={unit} disabled={disabled} onChange={(quantity) => updateRow(index, { quantities: row.quantities.map((old, i) => i === variantIndex ? quantity : old) })} />) : <QuantityField id={`${id}-${row.key}-base`} label="Cantidad por producto" value={row.quantity} unit={unit} disabled={disabled} onChange={(quantity) => updateRow(index, { quantity })} />}
          </div>
          {ingredient && ingredient.category !== 'UNIDAD' && <p className="text-xs text-monu-text">Se descuenta en {unit}, como está registrado en inventario. Para un cuarto de pieza, el ingrediente debe medirse en unidades.</p>}
        </div>;
      })}
    </div>
    <div className="flex flex-wrap gap-2">
      <button type="button" onClick={() => onChange({ ...value, ingredients: [...value.ingredients, { key: crypto.randomUUID(), ingredientId: '', quantity: '1', quantities: value.variants.map(() => '1') }] })} className={buttonClass}><Plus aria-hidden="true" className="h-4 w-4 inline mr-2" />Agregar ingrediente</button>
      {!lockVariants && value.variants.length < 10 && <button type="button" onClick={addVariant} className={buttonClass}><Plus aria-hidden="true" className="h-4 w-4 inline mr-2" />{value.variants.length ? 'Agregar variante' : 'Usar variantes'}</button>}
    </div>
  </fieldset>;
}
