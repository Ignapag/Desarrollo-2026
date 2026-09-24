import { useData } from '../../context/DataContext';
import { AlertTriangle, CheckCircle, Package } from 'lucide-react';

export default function Inventory() {
  const { state } = useData();
  const { inventory } = state;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Inventario</h1>
          <p className="text-monu-text/70">Control de stock de ingredientes y materia prima.</p>
        </div>
        <button className="bg-monu-dark hover:bg-black text-white px-4 py-2 rounded-xl font-bold transition flex items-center gap-2 text-sm">
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
    </div>
  );
}
