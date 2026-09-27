import { useData } from '../shared/store/DataContext';
import { Mail, Phone, Calendar, Star } from 'lucide-react';

export default function Customers() {
  const { state } = useData();
  const { customers } = state;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Directorio de Clientes</h1>
          <p className="text-monu-text/70">Gestiona y visualiza la actividad de tus clientes frecuentes.</p>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left min-w-[700px]">
            <thead className="bg-monu-cream border-b border-monu-green/10 text-sm">
              <tr>
                <th className="p-4 font-bold text-monu-dark">Cliente</th>
                <th className="p-4 font-bold text-monu-dark">Contacto</th>
                <th className="p-4 font-bold text-monu-dark">Zona Frecuente</th>
                <th className="p-4 font-bold text-monu-dark">Pedidos</th>
                <th className="p-4 font-bold text-monu-dark">Cliente desde</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id} className="border-b border-monu-green/5 hover:bg-monu-cream/30 transition">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-monu-green/10 text-monu-green flex items-center justify-center font-bold">
                        {c.name.charAt(0)}
                      </div>
                      <span className="font-bold text-monu-dark">{c.name}</span>
                    </div>
                  </td>
                  <td className="p-4 text-sm">
                    <div className="flex items-center gap-2 text-monu-text/80"><Phone className="w-4 h-4" /> {c.phone}</div>
                  </td>
                  <td className="p-4 text-sm text-monu-text/80">{c.zone}</td>
                  <td className="p-4">
                    <span className="bg-monu-yellow/20 text-monu-dark font-bold px-3 py-1 rounded-full text-xs flex items-center gap-1 w-max">
                      <Star className="w-3 h-3 text-monu-orange" fill="currentColor"/> {c.ordersCount} pedidos
                    </span>
                  </td>
                  <td className="p-4 text-sm text-monu-text/60">{c.since}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
