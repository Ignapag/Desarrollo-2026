import { useData } from '../shared/store/DataContext';
import { MapPin, Phone, CheckCircle, Navigation } from 'lucide-react';
import { toast } from 'sonner';

export default function DeliveryPanel() {
  const { state, dispatch } = useData();
  const { orders } = state;

  const activeOrders = orders.filter(o => o.status === 'en_camino' || o.status === 'listo');
  
  const markAsDelivered = (id) => {
    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: 'entregado' } });
    toast.success(`¡Pedido #${id} entregado!`, { description: 'Buen trabajo' });
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Repartidor Activo</h1>
          <p className="text-monu-text/70">Tus pedidos asignados.</p>
        </div>
      </div>

      <div className="space-y-4">
        {activeOrders.length === 0 ? (
          <div className="py-20 text-center text-monu-text/50">
            <span className="text-5xl block mb-4">🛵</span>
            <p className="text-lg">No tenés pedidos asignados ahora mismo.</p>
          </div>
        ) : (
          activeOrders.map((order, i) => (
            <div key={order.id} className={`bg-white rounded-2xl shadow-sm overflow-hidden border-2 ${i === 0 ? 'border-monu-orange' : 'border-transparent'}`}>
              <div className={`p-4 text-white flex justify-between items-center ${i === 0 ? 'bg-monu-orange' : 'bg-monu-green/80'}`}>
                <div className="flex items-center gap-2 font-bold">
                  <span>{i === 0 ? '¡Urgente!' : 'Siguiente'}</span>
                </div>
                <span className="font-extrabold text-xl">#{order.id}</span>
              </div>
              
              <div className="p-5 space-y-5">
                <div className="flex items-start gap-3">
                  <MapPin className="w-5 h-5 text-monu-green shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm font-bold text-gray-500">Dirección de entrega</p>
                    <p className="font-extrabold text-xl text-monu-dark">{order.address}</p>
                    <p className="font-bold text-monu-dark/70">{order.client}</p>
                  </div>
                </div>

                <div className="flex gap-2 border-t border-gray-100 pt-5">
                  <a 
                    href={`tel:${order.phone?.replace(/\D/g, '') || ''}`}
                    className="flex-1 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 font-bold py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition"
                  >
                    <Phone className="w-5 h-5" /> Llamar
                  </a>
                  <a 
                    href={`https://maps.google.com/?q=${encodeURIComponent(order.address + ', La Plata, Buenos Aires')}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 bg-blue-50 hover:bg-blue-100 text-blue-600 font-bold py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition"
                  >
                    <Navigation className="w-5 h-5" /> Ruta GPS
                  </a>
                </div>

                <button 
                  onClick={() => markAsDelivered(order.id)}
                  className="w-full bg-monu-dark hover:bg-black text-white font-bold py-4 rounded-xl flex items-center justify-center gap-2 transition shadow-md"
                >
                  <CheckCircle className="w-5 h-5" />
                  Marcar Entregado
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}