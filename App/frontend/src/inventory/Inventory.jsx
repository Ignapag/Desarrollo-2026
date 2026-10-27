import { can } from '../auth/permissions';
import { useAuth } from '../auth/AuthContext';
import { useData } from '../shared/store/DataContext';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle, Package, X, Plus } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { DataError } from '../fulfillment/operationUi';
import { parseRecipeQuantity, recipeUnit } from '../management/recipeModel';

function initialQuantity(value) {
  const text = value.trim();
  return /^0+(?:[.,]0{1,3})?$/.test(text) ? { valid: true, amount: '0', display: '0' } : parseRecipeQuantity(value);
}

export default function Inventory() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const { state, createIngredient, replenishIngredient, refreshInventory } = useData();
  const { inventory } = state;
  useEffect(() => {
    const controller = new AbortController();
    Promise.resolve().then(() => { if (!controller.signal.aborted) return refreshInventory(controller.signal); return undefined; }).catch(() => undefined);
    return () => controller.abort();
  }, [refreshInventory]);
  
  const searchQuery = searchParams.get('q')?.toLowerCase() || '';

  const filteredInventory = inventory.filter(item => 
    item.name.toLowerCase().includes(searchQuery) || 
    item.category.toLowerCase().includes(searchQuery)
  );

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const saving = useRef(false);
  const replenishing = useRef(new Set());
  const [pendingStock, setPendingStock] = useState([]);
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const errorSummary = useRef(null);
  useEffect(() => { if (formError) errorSummary.current?.focus(); }, [formError]);
  const dialog = useRef(null);
  useEffect(() => { if (isModalOpen) dialog.current?.showModal(); }, [isModalOpen]);

  const [newItem, setNewItem] = useState({
    name: '',
    unit: 'UNIDAD',
    stock: '',
    min: '',
  });
  const parsedStock = initialQuantity(newItem.stock);
  const parsedMinimum = parseRecipeQuantity(newItem.min);

  const handleAddItem = async (e) => {
    e.preventDefault();
    if (saving.current || !can(user, 'stock.gestionar')) return;
    const stock = parsedStock;
    const min = parsedMinimum;
    const errors = {};
    if (!newItem.name.trim()) errors.name = 'Ingresá el nombre del insumo.';
    if (!stock.valid) errors.stock = stock.error;
    if (!min.valid) errors.min = min.error;
    setFieldErrors(errors);
    if (Object.keys(errors).length) { setFormError('Revisá los campos indicados.'); return; }
    saving.current = true;
    setFormError('');
    setIsSaving(true);
    try {
      await createIngredient({ ...newItem, name: newItem.name.trim(), stock: stock.amount, min: min.amount });
      if (!mounted.current) return;
      toast.success('Insumo agregado');
      setNewItem({ name: '', unit: 'UNIDAD', stock: '', min: '' });
      setIsModalOpen(false);
    } catch (error) {
      if (!mounted.current) return;
      setFormError(error.message);
      toast.error('No se pudo agregar el insumo', { description: error.message });
    } finally {
      saving.current = false;
      if (mounted.current) setIsSaving(false);
    }
  };

  const updateStock = async (id) => {
    if (replenishing.current.has(id) || !can(user, 'stock.reponer')) return;
    replenishing.current.add(id);
    setPendingStock([...replenishing.current]);
    try {
      await replenishIngredient(id, 1);
      if (mounted.current) toast.success('Stock repuesto');
    } catch (error) {
      if (mounted.current) toast.error('No se pudo reponer stock', { description: error.message });
    } finally {
      replenishing.current.delete(id);
      if (mounted.current) setPendingStock([...replenishing.current]);
    }
  };

  return (
    <div className="space-y-6">
      <DataError message={state.inventoryError} retry={() => { void refreshInventory(undefined, true).catch(() => undefined); }} />
      {['idle', 'loading'].includes(state.inventoryStatus) && <p role="status">Consultando inventario...</p>}
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

      <div className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left min-w-[600px]">
            <thead className="bg-monu-cream border-b border-monu-green/10 text-sm">
              <tr>
                <th className="p-4 font-bold text-monu-dark">Insumo</th>
                <th className="p-4 font-bold text-monu-dark">Categoría</th>
                <th className="p-4 font-bold text-monu-dark">Stock Actual</th>
                <th className="p-4 font-bold text-monu-dark">Stock Mínimo</th>
                <th className="p-4 font-bold text-monu-dark">Estado</th>
              </tr>
            </thead>
            <tbody>
              {filteredInventory.length === 0 ? (
                <tr>
                  <td colSpan="5" className="p-8 text-center text-monu-text/50">
                    {state.inventoryStatus === 'error' ? 'No se pudo consultar el inventario.' : state.inventoryStatus === 'ready' ? 'No se encontraron insumos que coincidan con tu búsqueda.' : 'Consultando insumos...'}
                  </td>
                </tr>
              ) : (
                filteredInventory.map((item) => (
                  <tr key={item.id} className="border-b border-monu-green/5 hover:bg-monu-cream/30 transition">
                    <td className="p-4 font-bold text-monu-dark">{item.name}</td>
                    <td className="p-4 text-sm text-monu-text/80">{item.category}</td>
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        <span className="font-extrabold min-w-[30px] text-center">{item.stock}</span>
                        <button disabled={!can(user, 'stock.reponer') || pendingStock.includes(item.id)}
                          onClick={() => updateStock(item.id)}
                          className="min-h-11 min-w-11 p-1 bg-green-50 text-green-700 rounded-md hover:bg-green-100 transition disabled:opacity-50"
                          title="Sumar 1"
                          aria-label={item.category === 'UNIDAD' ? `Reponer una unidad de ${item.name}` : `Reponer 1 ${recipeUnit(item.category)} de ${item.name}`}
                        >
                          <Plus className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                    <td className="p-4 text-sm text-monu-text/60">{item.min} {recipeUnit(item.category)}</td>
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
            <form onSubmit={handleAddItem} className="space-y-4" aria-busy={isSaving}>
              <div ref={errorSummary} tabIndex={-1}><DataError message={formError} /></div>
              <fieldset disabled={isSaving} className="space-y-4">
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
