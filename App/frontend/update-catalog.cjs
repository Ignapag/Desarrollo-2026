const fs = require('fs');
const path = require('path');

const catPath = path.join(__dirname, 'src', 'management', 'Catalog.jsx');
const catContent = `import { useData } from '../shared/store/DataContext';
import { useState } from 'react';
import { Plus, Trash2, Edit2, Check, X, Image as ImageIcon } from 'lucide-react';

export default function Catalog() {
  const { state, dispatch } = useData();
  const [isAdding, setIsAdding] = useState(false);
  const [newItem, setNewItem] = useState({ 
    name: '', category: 'Nuestras Burgers', price: '', description: '', image: null 
  });

  const categories = [...new Set(state.catalog.map(p => p.category))];

  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setNewItem({ ...newItem, image: reader.result }); // Base64
      };
      reader.readAsDataURL(file);
    }
  };

  const handleAdd = () => {
    if (!newItem.name || !newItem.price) return;
    
    dispatch({ 
      type: 'ADD_CATALOG_ITEM', 
      payload: {
        name: newItem.name,
        description: newItem.description,
        category: newItem.category,
        price: Number(newItem.price),
        image: newItem.image
      }
    });
    setNewItem({ name: '', category: 'Nuestras Burgers', price: '', description: '', image: null });
    setIsAdding(false);
  };

  const handleDelete = (id) => {
    if(confirm('¿Eliminar producto?')) {
      dispatch({ type: 'DELETE_CATALOG_ITEM', payload: id });
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Catálogo de Menú</h1>
          <p className="text-monu-text/70">Gestioná los productos que ven los clientes.</p>
        </div>
        <button 
          onClick={() => setIsAdding(true)}
          className="bg-monu-dark text-white px-4 py-2 rounded-xl font-bold flex items-center gap-2 hover:bg-black transition shadow-md"
        >
          <Plus className="w-5 h-5" /> Nuevo Producto
        </button>
      </div>

      {isAdding && (
        <div className="bg-white p-5 rounded-2xl shadow-sm border border-monu-green/10 mb-6 flex flex-col gap-4">
          <h3 className="font-extrabold text-lg border-b pb-2">Agregar nuevo producto</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-bold text-gray-500 mb-1">Nombre</label>
              <input type="text" value={newItem.name} onChange={e => setNewItem({...newItem, name: e.target.value})} className="w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green" placeholder="Ej: Super Burger" />
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 mb-1">Categoría</label>
              <select value={newItem.category} onChange={e => setNewItem({...newItem, category: e.target.value})} className="w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green">
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 mb-1">Precio Base ($)</label>
              <input type="number" value={newItem.price} onChange={e => setNewItem({...newItem, price: e.target.value})} className="w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green" placeholder="10000" />
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 mb-1">Foto</label>
              <label className="w-full border rounded-lg px-3 py-2 font-bold flex items-center gap-2 cursor-pointer bg-gray-50 hover:bg-gray-100 transition">
                <ImageIcon className="w-4 h-4 text-monu-green" />
                <span className="text-sm truncate">{newItem.image ? 'Imagen cargada' : 'Subir archivo...'}</span>
                <input type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />
              </label>
            </div>
            <div className="md:col-span-2 lg:col-span-4">
              <label className="block text-xs font-bold text-gray-500 mb-1">Ingredientes / Descripción</label>
              <input type="text" value={newItem.description} onChange={e => setNewItem({...newItem, description: e.target.value})} className="w-full border rounded-lg px-3 py-2 font-bold focus:outline-monu-green" placeholder="Ej: Carne, cheddar, bacon y salsa monu." />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-2 border-t pt-4">
            <button onClick={() => setIsAdding(false)} className="px-4 py-2 text-gray-500 font-bold hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button onClick={handleAdd} className="px-4 py-2 bg-monu-green text-white font-bold rounded-lg hover:bg-[#002b22] flex items-center gap-2">
              <Check className="w-4 h-4" /> Guardar Producto
            </button>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-monu-cream/50 text-monu-dark">
            <tr>
              <th className="p-4 font-extrabold">Producto</th>
              <th className="p-4 font-extrabold hidden md:table-cell">Categoría</th>
              <th className="p-4 font-extrabold">Precio</th>
              <th className="p-4 font-extrabold text-right">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-monu-green/10">
            {state.catalog.map(product => (
              <tr key={product.id} className="hover:bg-gray-50 transition">
                <td className="p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-lg bg-gray-100 flex items-center justify-center p-1 shrink-0 overflow-hidden">
                      {product.image ? (
                        <img src={product.image} className="w-full h-full object-cover rounded-md" alt={product.name} />
                      ) : (
                        <img src="/favicon.png" className="w-8 h-8 object-contain opacity-50" alt="Logo" />
                      )}
                    </div>
                    <div>
                      <p className="font-extrabold text-monu-dark">{product.name}</p>
                      <p className="text-xs text-gray-500 truncate max-w-[200px] hidden sm:block">{product.description}</p>
                    </div>
                  </div>
                </td>
                <td className="p-4 font-bold text-gray-600 hidden md:table-cell">{product.category}</td>
                <td className="p-4 font-extrabold text-monu-green">
                  ${product.price ? product.price.toLocaleString('es-AR') : product.variants?.[0]?.price?.toLocaleString('es-AR')}
                </td>
                <td className="p-4 text-right">
                  <button onClick={() => handleDelete(product.id)} className="p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition" title="Eliminar">
                    <Trash2 className="w-5 h-5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
`;
fs.writeFileSync(catPath, catContent, 'utf-8');
console.log("Catalog updated.");