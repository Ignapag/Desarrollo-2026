import { useData } from '../../context/DataContext';
import { AlertTriangle, CheckCircle, Package, X } from 'lucide-react';
import { useState } from 'react';

export default function Inventory() {
  const { state, dispatch } = useData();
  const { inventory } = state;
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [newItem, setNewItem] = useState({
    name: '',
    category: 'Proteínas',
    stock: '',
    min: '',
  });

  const handleAddItem = (e) => {
    e.preventDefault();
    const stockVal = parseInt(newItem.stock) || 0;
    const minVal = parseInt(newItem.min) || 0;
    const status = stockVal <= minVal ? 'critico' : 'estable';

    dispatch({
      type: 'ADD_INVENTORY_ITEM',
      payload: { ...newItem, stock: stockVal, min: minVal, status }
    });

    setNewItem({ name: '', category: 'Proteínas', stock: '', min: '' });
    setIsModalOpen(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Inventario</h1>
          <p className="text-monu-text/70">Control de stock de ingredientes y materia prima.</p>
        </div>
        <button 
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
              {inventory.map((item) => (
                <tr key={item.id} className="border-b border-monu-green/5 hover:bg-monu-cream/30 transition">
                  <td className="p-4 font-bold text-monu-dark">{item.name}</td>
                  <td className="p-4 text-sm text-monu-text/80">{item.category}</td>
                  <td className="p-4 font-extrabold">{item.stock} u.</td>
                  <td className="p-4 text-sm text-monu-text/60">{item.min} u.</td>
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
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal Añadir Insumo (Simulador) */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full shadow-2xl relative animate-in fade-in zoom-in duration-200">
            <button 
              onClick={() => setIsModalOpen(false)}
              className="absolute top-4 right-4 p-2 text-gray-400 hover:text-gray-600 bg-gray-100 rounded-full"
            >
              <X className="w-5 h-5" />
            </button>
            <h2 className="text-xl font-extrabold text-monu-dark mb-4">Añadir Nuevo Insumo</h2>
            <p className="text-xs text-gray-500 mb-4">
              (Simulador UI. TODO BACKEND: Enviar POST a la BD al enviar).
            </p>

            <form onSubmit={handleAddItem} className="space-y-4">
              <div>
                <label className="block text-sm font-bold text-monu-dark mb-1">Nombre</label>
                <input 
                  required
                  type="text" 
                  value={newItem.name}
                  onChange={e => setNewItem({...newItem, name: e.target.value})}
                  className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none" 
                  placeholder="Ej: Tomate"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-monu-dark mb-1">Categoría</label>
                <select 
                  value={newItem.category}
                  onChange={e => setNewItem({...newItem, category: e.target.value})}
                  className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none"
                >
                  <option>Proteínas</option>
                  <option>Panadería</option>
                  <option>Lácteos</option>
                  <option>Verduras</option>
                  <option>Bebidas</option>
                  <option>Congelados</option>
                </select>
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-bold text-monu-dark mb-1">Stock Inicial</label>
                  <input 
                    required
                    type="number" 
                    value={newItem.stock}
                    onChange={e => setNewItem({...newItem, stock: e.target.value})}
                    className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none" 
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-sm font-bold text-monu-dark mb-1">Stock Mínimo</label>
                  <input 
                    required
                    type="number" 
                    value={newItem.min}
                    onChange={e => setNewItem({...newItem, min: e.target.value})}
                    className="w-full px-4 py-2 border rounded-xl focus:border-monu-green focus:outline-none" 
                  />
                </div>
              </div>
              <button 
                type="submit" 
                className="w-full bg-monu-green text-white font-bold py-3 rounded-xl hover:bg-[#002b22] transition mt-2"
              >
                Guardar Insumo
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}