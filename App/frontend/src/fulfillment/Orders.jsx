import { useData } from '../shared/store/DataContext';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Clock, CheckCircle, PackageCheck, AlertCircle } from 'lucide-react';

const STATUS_COLUMNS = [
  { id: 'pendiente', title: 'Nuevos', color: 'bg-red-50 text-red-700 border-red-200', icon: AlertCircle },
  { id: 'en_preparacion', title: 'En Preparación', color: 'bg-orange-50 text-orange-700 border-orange-200', icon: Clock },
  { id: 'listo', title: 'Listos para Envío', color: 'bg-green-50 text-green-700 border-green-200', icon: CheckCircle },
  { id: 'en_camino', title: 'En Camino', color: 'bg-blue-50 text-blue-700 border-blue-200', icon: PackageCheck },
];

export default function Orders() {
  const { state, dispatch } = useData();
  const { orders } = state;
  const [searchParams] = useSearchParams();
  const query = (searchParams.get('q') || '').toLowerCase();

  const filteredOrders = state.orders.filter(o => 
    o.id.toString().includes(query) || 
    (o.client?.toLowerCase() || '').includes(query) || 
    (o.address?.toLowerCase() || '').includes(query)
  );

  const updateStatus = (id, newStatus) => {
    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: newStatus } });
  };

  return (
    <div className="h-[calc(100vh-100px)] flex flex-col">
      <div className="mb-6">
        <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Gestión de Pedidos</h1>
        <p className="text-monu-text/70">Tablero Kanban para el flujo operativo.</p>
      </div>

      <div className="flex-1 flex gap-4 overflow-x-auto pb-4 px-2 snap-x snap-mandatory">
        {STATUS_COLUMNS.map(col => (
          <div key={col.id} className="flex-none w-[85vw] md:w-80 snap-center bg-monu-bone rounded-2xl flex flex-col max-h-full border border-monu-green/10 shadow-sm">
            <div className={`p-4 border-b rounded-t-2xl flex justify-between items-center ${col.color}`}>
              <div className="flex items-center gap-2 font-bold">
                <col.icon className="w-5 h-5" />
                {col.title}
              </div>
              <span className="bg-white/50 px-2.5 py-0.5 rounded-full text-sm">
                {orders.filter(o => o.status === col.id).length}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {orders.filter(o => o.status === col.id).map(order => (
                <div key={order.id} className="bg-white p-4 rounded-xl border border-monu-green/10 shadow-sm hover:shadow-md transition">
                  <div className="flex justify-between items-center mb-3">
                    <span className="font-extrabold text-monu-dark">#{order.id}</span>
                    <span className="text-xs font-bold text-monu-text/50">{new Date(order.date).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                  </div>
                  <h3 className="font-bold text-sm mb-1">{order.client}</h3>
                  <p className="text-xs text-monu-text/70 mb-3">{order.address}</p>
                  
                  <div className="space-y-1 mb-4">
                    {order.items.map((item, i) => (
                      <div key={i} className="text-xs flex gap-2">
                        <span className="font-bold text-monu-green">1x</span>
                        <span className="text-monu-text/80">{item.replace(/^\dx\s/, '')}</span>
                      </div>
                    ))}
                  </div>

                  <div className="flex gap-2">
                    {col.id === 'pendiente' && (
                      <button onClick={() => updateStatus(order.id, 'en_preparacion')} className="w-full bg-monu-dark text-white py-2 rounded-lg text-xs font-bold transition hover:bg-black">A Cocina</button>
                    )}
                    {col.id === 'en_preparacion' && (
                      <button onClick={() => updateStatus(order.id, 'listo')} className="w-full bg-monu-green text-white py-2 rounded-lg text-xs font-bold transition hover:bg-monu-green/80">Marcar Listo</button>
                    )}
                    {col.id === 'listo' && (
                      <button onClick={() => updateStatus(order.id, 'en_camino')} className="w-full bg-monu-orange text-white py-2 rounded-lg text-xs font-bold transition hover:bg-monu-burnt">Asignar Delivery</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
