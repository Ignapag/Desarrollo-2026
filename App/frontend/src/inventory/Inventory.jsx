// Pantalla de Inventario: tabla de insumos con stock actual, mínimo, costo y estado,
// reposición rápida (+1) o por cantidad, edición de costos y alta de insumos nuevos.
// Los datos y mutaciones de stock pasan por DataContext contra la API.
import { UserFacingError, userErrorMessage } from '../shared/api/userErrors.js';
import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { useLocation, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle, CircleAlert, Package, Pencil, X, Plus } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { DataError } from '../fulfillment/operationUi';
import { parseRecipeQuantity, recipeUnit } from '../management/recipeModel';
import { costUnitLabel, formatUnitCost, parseUnitCost } from './ingredientCost';
import IngredientCostDialog from './IngredientCostDialog';
import ReplenishDialog from './ReplenishDialog';
import { isUncertainReplenishment, quantityWithUnit } from './replenishment';

// Stock inicial del alta: acepta cero explícito; el resto se valida como cantidad de receta.
function initialQuantity(value) {
  const text = value.trim();
  return /^0+(?:[.,]0{1,3})?$/.test(text) ? { valid: true, amount: '0', display: '0' } : parseRecipeQuantity(value);
}

/** Pantalla de inventario de insumos (stock) del personal. */
export default function Inventory() {
  const { user } = useAuth();
  // El parámetro ?ingrediente=ID permite llegar enfocado a un insumo (p. ej. desde una notificación).
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const ingredientId = searchParams.get('ingrediente');
  const targetIngredient = useRef(null);
  const focusedRequest = useRef(null);
  const { state, createIngredient, updateIngredientCost, replenishIngredient, refreshInventory } = useData();
  const { inventory } = state;
  // Enfoca y desplaza hasta el insumo pedido en la URL una vez por navegación.
  useEffect(() => {
    if (state.inventoryStatus !== 'ready' || !targetIngredient.current || focusedRequest.current === location.key) return;
    targetIngredient.current.focus();
    targetIngredient.current.scrollIntoView?.({ block: 'center' });
    focusedRequest.current = location.key;
  }, [state.inventoryStatus, inventory, ingredientId, location.key]);
  // Carga el inventario al montar.
  useEffect(() => {
    const controller = new AbortController();
    Promise.resolve().then(() => { if (!controller.signal.aborted) return refreshInventory(controller.signal); return undefined; }).catch(() => undefined);
    return () => controller.abort();
  }, [refreshInventory]);
  
  // Filtro de búsqueda (?q=) por nombre o unidad del insumo.
  const searchQuery = searchParams.get('q')?.toLowerCase() || '';

  const filteredInventory = inventory.filter(item => 
    item.name.toLowerCase().includes(searchQuery) || 
    item.category.toLowerCase().includes(searchQuery)
  );

  // Cantidad de insumos sin costo cargado (afectan la rentabilidad estimada de Reportes).
  const missingCost = inventory.filter((item) => !(item.cost > 0)).length;
  const canManage = can(user, 'stock.gestionar');

  // Estado de los diálogos de alta y de edición de costo.
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCost, setEditingCost] = useState(null);
  const costTrigger = useRef(null);
  const costItem = editingCost === null || !canManage ? null : inventory.find((item) => item.id === editingCost);
  // Al cerrar el diálogo de costo el foco vuelve al botón que lo abrió.
  useEffect(() => { if (!costItem) { costTrigger.current?.focus(); costTrigger.current = null; } }, [costItem]);
  const [isSaving, setIsSaving] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  // Estado de reposición: insumos con envío en curso, diálogo abierto, último resultado
  // e insumos cuyo último intento quedó incierto.
  const saving = useRef(false);
  const replenishing = useRef(new Set());
  const [pendingStock, setPendingStock] = useState([]);
  const [replenishTarget, setReplenishTarget] = useState(null);
  const [lastReplenishment, setLastReplenishment] = useState(null);
  const [uncertainStock, setUncertainStock] = useState([]);
  const [replenishValue, setReplenishValue] = useState('');
  const replenishTrigger = useRef(null);
  const canReplenish = can(user, 'stock.reponer');
  const replenishItem = replenishTarget === null || !canReplenish ? null : inventory.find((item) => item.id === replenishTarget);
  // Al cerrar el diálogo el foco vuelve al botón que lo abrió.
  useEffect(() => { if (!replenishItem) { replenishTrigger.current?.focus(); replenishTrigger.current = null; } }, [replenishItem]);
  // Errores del formulario de alta; el resumen recibe el foco al aparecer.
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const errorSummary = useRef(null);
  useEffect(() => { if (formError) errorSummary.current?.focus(); }, [formError]);
  const dialog = useRef(null);
  useEffect(() => { if (isModalOpen) dialog.current?.showModal(); }, [isModalOpen]);

  // Borrador del insumo nuevo y sus valores ya interpretados.
  const [newItem, setNewItem] = useState({
    name: '',
    unit: 'UNIDAD',
    stock: '',
    min: '',
    cost: '',
  });
  const parsedStock = initialQuantity(newItem.stock);
  const parsedMinimum = parseRecipeQuantity(newItem.min);
  const parsedCost = parseUnitCost(newItem.cost);

  // Da de alta el insumo: valida todos los campos, lo crea vía API y cierra el diálogo.
  const handleAddItem = async (e) => {
    e.preventDefault();
    if (saving.current || !can(user, 'stock.gestionar')) return;
    const stock = parsedStock;
    const min = parsedMinimum;
    const errors = {};
    if (!newItem.name.trim()) errors.name = 'Ingresá el nombre del insumo.';
    if (!stock.valid) errors.stock = stock.error;
    if (!min.valid) errors.min = min.error;
    if (!parsedCost.valid) errors.cost = parsedCost.error;
    setFieldErrors(errors);
    if (Object.keys(errors).length) { setFormError('Revisá los campos indicados.'); return; }
    saving.current = true;
    setFormError('');
    setIsSaving(true);
    try {
      await createIngredient({ ...newItem, name: newItem.name.trim(), stock: stock.amount, min: min.amount, cost: parsedCost.amount });
      if (!mounted.current) return;
      toast.success('Insumo agregado');
      setNewItem({ name: '', unit: 'UNIDAD', stock: '', min: '', cost: '' });
      setIsModalOpen(false);
    } catch (error) {
      if (!mounted.current) return;
      const message = userErrorMessage(error, 'No pudimos agregar el insumo. Comprobá el inventario antes de repetir el alta.');
      setFormError(message);
      toast.error('No pudimos agregar el insumo', { description: message });
    } finally {
      saving.current = false;
      if (mounted.current) setIsSaving(false);
    }
  };

  // Un único envío por insumo, compartido por el +1 y el diálogo. Sin reintentos automáticos.
  const replenish = async (item, quantity) => {
    if (replenishing.current.has(item.id) || !can(user, 'stock.reponer')) return null;
    replenishing.current.add(item.id);
    setPendingStock([...replenishing.current]);
    setLastReplenishment(null);
    try {
      const result = await replenishIngredient(item.id, quantity);
      if (mounted.current) {
        const description = result ? `${item.name} quedó en ${quantityWithUnit(result.stock, item.category)}. Movimiento #${result.movementId} registrado en el historial.` : undefined;
        if (result) setLastReplenishment(description);
        setUncertainStock((ids) => ids.filter((id) => id !== item.id));
        toast.success('Stock repuesto', { description });
      }
      return result;
    } catch (error) {
      if (mounted.current && isUncertainReplenishment(error)) setUncertainStock((ids) => ids.includes(item.id) ? ids : [...ids, item.id]);
      throw error;
    } finally {
      replenishing.current.delete(item.id);
      if (mounted.current) setPendingStock([...replenishing.current]);
    }
  };

  // Abre el diálogo de reposición recordando el botón que lo abrió para devolverle el foco.
  const openReplenish = (item, event, value = '') => {
    replenishTrigger.current = event?.currentTarget ?? null;
    setReplenishValue(value);
    setReplenishTarget(item.id);
  };

  // Reposición rápida de 1 unidad desde la tabla.
  const updateStock = async (item, event) => {
    // Tras un +1 incierto, repetirlo pasa por el diálogo: consulta el stock y pide confirmar.
    if (uncertainStock.includes(item.id)) { openReplenish(item, event, '1'); return; }
    try {
      await replenish(item, 1);
    } catch (error) {
      if (mounted.current) toast.error('No pudimos reponer stock', { description: userErrorMessage(error, 'No pudimos reponer el stock. Comprobá el inventario antes de repetir la reposición.') });
    }
  };

  // Envía la reposición confirmada desde el diálogo y lo cierra al terminar.
  const submitReplenishment = async (item, plan) => {
    const result = await replenish(item, plan.amount);
    if (result === null) throw new UserFacingError('Ya hay una reposición en curso para este insumo. Esperá su resultado antes de enviar otra.');
    if (mounted.current) setReplenishTarget(null);
  };

  return (
    <div className="space-y-6">
      {/* Estado de la carga y resultado de la última reposición (anunciado a lectores de pantalla) */}
      <DataError message={state.inventoryError} retry={() => { void refreshInventory(undefined, true).catch(() => undefined); }} />
      {['idle', 'loading'].includes(state.inventoryStatus) && <p role="status">Consultando inventario...</p>}
      <p role="status" className={lastReplenishment ? 'rounded-xl border border-green-200 bg-green-50 p-3 text-sm font-bold text-green-900' : 'sr-only'}>{lastReplenishment}</p>
      {/* Encabezado y botón para añadir insumos */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Inventario</h1>
          <p className="text-monu-text/70">Control de stock de ingredientes y materia prima.</p>
        </div>
        <button disabled={!can(user, 'stock.gestionar')}
          onClick={() => setIsModalOpen(true)}
          className="bg-monu-dark hover:bg-black text-white px-4 py-2 rounded-xl font-bold transition flex items-center gap-2 text-sm"
        >
          <Package className="w-4 h-4"/> Añadir Insumo
        </button>
      </div>

      {/* Aviso de insumos sin costo cargado */}
      {state.inventoryStatus === 'ready' && missingCost > 0 && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 flex items-start gap-2">
          <CircleAlert className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span><strong>{missingCost === 1 ? '1 insumo sin costo cargado.' : `${missingCost} insumos sin costo cargado.`}</strong> Si forman parte de una receta, la rentabilidad estimada de Reportes los cuenta como $ 0.</span>
        </p>
      )}

      {/* Tabla de insumos */}
      <div className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left min-w-[820px]">
            <thead className="bg-monu-cream border-b border-monu-green/10 text-sm">
              <tr>
                <th className="p-4 font-bold text-monu-dark">Insumo</th>
                <th className="p-4 font-bold text-monu-dark">Categoría</th>
                <th className="p-4 font-bold text-monu-dark">Stock Actual</th>
                <th className="p-4 font-bold text-monu-dark">Stock Mínimo</th>
                <th className="p-4 font-bold text-monu-dark">Costo unitario</th>
                <th className="p-4 font-bold text-monu-dark">Estado</th>
              </tr>
            </thead>
            <tbody>
              {filteredInventory.length === 0 ? (
                <tr>
                  <td colSpan="6" className="p-8 text-center text-monu-text/50">
                    {state.inventoryStatus === 'error' ? 'No se pudo consultar el inventario.' : state.inventoryStatus === 'ready' ? 'No se encontraron insumos que coincidan con tu búsqueda.' : 'Consultando insumos...'}
                  </td>
                </tr>
              ) : (
                filteredInventory.map((item) => (
                  <tr key={item.id} id={`ingrediente-${item.id}`} ref={String(item.id) === ingredientId ? targetIngredient : undefined} tabIndex={String(item.id) === ingredientId ? -1 : undefined} className="border-b border-monu-green/5 hover:bg-monu-cream/30 transition focus:outline-2 focus:outline-monu-green">
                    <td className="p-4 font-bold text-monu-dark">{item.name}</td>
                    <td className="p-4 text-sm text-monu-text/80">{item.category}</td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <span className="font-extrabold min-w-[30px] tabular-nums whitespace-nowrap">{quantityWithUnit(item.stock, item.category)}</span>
                        {canReplenish && <>
                          <button type="button" disabled={pendingStock.includes(item.id)}
                            onClick={(event) => updateStock(item, event)}
                            className="min-h-11 min-w-11 flex items-center justify-center bg-green-50 text-green-700 rounded-md hover:bg-green-100 transition disabled:opacity-50"
                            title="Sumar 1"
                            aria-label={item.category === 'UNIDAD' ? `Reponer una unidad de ${item.name}` : `Reponer 1 ${recipeUnit(item.category)} de ${item.name}`}
                          >
                            <Plus className="w-4 h-4" aria-hidden="true" />
                          </button>
                          <button type="button" disabled={pendingStock.includes(item.id)}
                            onClick={(event) => openReplenish(item, event)}
                            className="min-h-11 px-3 rounded-md border border-monu-green/30 text-sm font-bold text-monu-dark hover:bg-monu-cream transition disabled:opacity-50"
                            aria-label={`Reponer una cantidad de ${item.name}`}
                          >
                            Reponer…
                          </button>
                        </>}
                      </div>
                    </td>
                    <td className="p-4 text-sm text-monu-text/60">{item.min} {recipeUnit(item.category)}</td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        {item.cost > 0 ? (
                          <span className="text-sm font-bold text-monu-dark tabular-nums whitespace-nowrap">{formatUnitCost(item.cost, item.category)}</span>
                        ) : (
                          <span className="bg-amber-50 text-amber-900 font-bold px-3 py-1 rounded-full text-xs flex items-center gap-1 w-max whitespace-nowrap border border-amber-200">
                            <CircleAlert className="w-3 h-3" aria-hidden="true" /> Sin costo cargado
                          </span>
                        )}
                        {canManage && (
                          <button type="button"
                            onClick={(event) => { costTrigger.current = event?.currentTarget ?? null; setEditingCost(item.id); }}
                            className="min-h-11 min-w-11 flex items-center justify-center rounded-md border border-monu-green/30 text-monu-dark hover:bg-monu-cream transition"
                            title="Editar costo"
                            aria-label={`Editar costo de ${item.name}`}
                          >
                            <Pencil className="w-4 h-4" aria-hidden="true" />
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="p-4">
                      {item.status === 'critico' ? (
                        <span className="bg-red-50 text-red-600 font-bold px-3 py-1 rounded-full text-xs flex items-center gap-1 w-max border border-red-100">
                          <AlertTriangle className="w-3 h-3" /> Bajo Stock
                        </span>
                      ) : (
                        <span className="bg-green-50 text-green-700 font-bold px-3 py-1 rounded-full text-xs flex items-center gap-1 w-max border border-green-100">
                          <CheckCircle className="w-3 h-3" /> Óptimo
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Diálogos de reposición y de costo */}
      {replenishItem && (
        <ReplenishDialog key={replenishItem.id} item={replenishItem} busy={pendingStock.includes(replenishItem.id)}
          uncertain={uncertainStock.includes(replenishItem.id)} initialValue={replenishValue}
          verify={() => refreshInventory(undefined, true)}
          onSubmit={(plan) => submitReplenishment(replenishItem, plan)}
          onClose={() => setReplenishTarget(null)} />
      )}

      {costItem && (
        <IngredientCostDialog key={costItem.id} item={costItem} onSave={updateIngredientCost}
          onClose={() => setEditingCost(null)} />
      )}

      {/* Modal Añadir Insumo */}
      {isModalOpen && can(user, 'stock.gestionar') && (
        <dialog ref={dialog} aria-labelledby="new-ingredient-title" onCancel={(event) => { event.preventDefault(); if (!saving.current) setIsModalOpen(false); }} className="m-auto max-h-[90dvh] overflow-y-auto rounded-3xl border-0 p-0 w-[min(28rem,calc(100%_-_2rem))] backdrop:bg-black/50">
          <div className="bg-white rounded-3xl p-6 w-full shadow-2xl relative">
            <button 
              disabled={isSaving}
              onClick={() => setIsModalOpen(false)}
              aria-label="Cerrar formulario de insumo"
              className="absolute top-4 right-4 p-2 text-gray-400 hover:text-gray-600 bg-gray-100 rounded-full"
            >
              <X className="w-5 h-5" />
            </button>
            <h2 id="new-ingredient-title" className="text-xl font-extrabold text-monu-dark mb-4 pr-8">Añadir Nuevo Insumo</h2>
            <form noValidate onSubmit={handleAddItem} className="space-y-4" aria-busy={isSaving}>
              {/* Resumen de errores con enlaces a cada campo */}
              <div ref={errorSummary} tabIndex={-1}><DataError message={formError} />
                {formError && Object.keys(fieldErrors).length > 0 && <ul className="mt-2 space-y-1 text-sm text-red-800">{Object.entries(fieldErrors).map(([field, message]) => <li key={field}><a href={`#new-ingredient-${field}`} className="underline">{message}</a></li>)}</ul>}
              </div>
              <fieldset disabled={isSaving} className="space-y-4">
              {/* Campos del insumo: nombre, unidad, stock inicial, mínimo y costo */}
              <div>
                <label htmlFor="new-ingredient-name" className="block text-sm font-bold text-monu-dark mb-1">Nombre</label>
                <input 
                  id="new-ingredient-name" autoFocus aria-invalid={Boolean(fieldErrors.name)} aria-describedby="new-ingredient-name-error"
                  required
                  type="text" 
                  value={newItem.name}
                  onChange={e => setNewItem({...newItem, name: e.target.value})}
                  className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none" 
                  placeholder="Ej: Tomate"
                />
                <p id="new-ingredient-name-error" className="text-sm text-red-700">{fieldErrors.name}</p>
              </div>
              <div>
                <label htmlFor="new-ingredient-unit" className="block text-sm font-bold text-monu-dark mb-1">Unidad de medida</label>
                <select 
                  id="new-ingredient-unit"
                  value={newItem.unit}
                  onChange={e => setNewItem({...newItem, unit: e.target.value})}
                  className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none"
                >
                  <option value="UNIDAD">Unidad</option>
                  <option value="KG">Kilogramo</option>
                  <option value="GR">Gramo</option>
                  <option value="LT">Litro</option>
                  <option value="ML">Mililitro</option>
                </select>
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label htmlFor="new-ingredient-stock" className="block text-sm font-bold text-monu-dark mb-1">Stock Inicial</label>
                  <input 
                    id="new-ingredient-stock" aria-invalid={Boolean(fieldErrors.stock)} aria-describedby="new-ingredient-stock-error new-ingredient-stock-help"
                    required
                    type="text" inputMode="decimal"
                    value={newItem.stock}
                    onChange={e => setNewItem({...newItem, stock: e.target.value})}
                    className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none" 
                  />
                  <p id="new-ingredient-stock-error" className="text-sm text-red-700">{fieldErrors.stock}</p>
                  <p id="new-ingredient-stock-help" className="text-xs text-monu-text">{parsedStock.valid ? `${parsedStock.approximate ? 'Aprox. ' : ''}${parsedStock.display} ${recipeUnit(newItem.unit)}` : 'Cero, decimal o fracción; hasta 3 decimales.'}</p>
                </div>
                <div className="flex-1">
                  <label htmlFor="new-ingredient-min" className="block text-sm font-bold text-monu-dark mb-1">Stock Mínimo</label>
                  <input 
                    id="new-ingredient-min" aria-invalid={Boolean(fieldErrors.min)} aria-describedby="new-ingredient-min-error new-ingredient-min-help"
                    required
                    type="text" inputMode="decimal"
                    value={newItem.min}
                    onChange={e => setNewItem({...newItem, min: e.target.value})}
                    className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none" 
                  />
                  <p id="new-ingredient-min-error" className="text-sm text-red-700">{fieldErrors.min}</p>
                  <p id="new-ingredient-min-help" className="text-xs text-monu-text">{parsedMinimum.valid ? `${parsedMinimum.approximate ? 'Aprox. ' : ''}${parsedMinimum.display} ${recipeUnit(newItem.unit)}` : 'Mayor que cero; decimal o fracción.'}</p>
                </div>
              </div>
              <div>
                <label htmlFor="new-ingredient-cost" className="block text-sm font-bold text-monu-dark mb-1">Costo unitario ({costUnitLabel(newItem.unit)})</label>
                <input
                  id="new-ingredient-cost" aria-invalid={Boolean(fieldErrors.cost)} aria-describedby="new-ingredient-cost-error new-ingredient-cost-help"
                  required
                  type="text" inputMode="decimal"
                  value={newItem.cost}
                  onChange={e => setNewItem({...newItem, cost: e.target.value})}
                  className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none"
                  placeholder="Ej.: 4,50"
                />
                <p id="new-ingredient-cost-error" className="text-sm text-red-700">{fieldErrors.cost}</p>
                <p id="new-ingredient-cost-help" className="text-xs text-monu-text">Costo actual de 1 {newItem.unit}, hasta 2 decimales. Usá 0 si todavía no lo conocés: quedará marcado como sin costo cargado.</p>
              </div>
              </fieldset>
              <button 
                type="submit" 
                disabled={isSaving}
                className="w-full bg-monu-green text-white font-bold py-3 rounded-xl hover:bg-[#002b22] transition mt-2 disabled:cursor-wait disabled:opacity-70"
              >
                {isSaving ? 'Guardando…' : 'Guardar Insumo'}
              </button>
            </form>
          </div>
        </dialog>
      )}
    </div>
  );
}
