import { useData } from '../shared/store/DataContext';
import { Clock, CheckCircle } from 'lucide-react';

export default function Kitchen() {
  const { state, dispatch } = useData();
  const { orders } = state;

  const kitchenOrders = orders.filter(o => o.status === 'en_preparacion');

  const markReady = (id) => {
    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: 'listo' } });
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-extrabold font-heading text-monu-dark mb-1">Panel de Empleado (KDS)</h1>
          <p className="text-monu-text/70">Comandas en tiempo real para cocina.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {kitchenOrders.length === 0 ? (
          <div className="col-span-full py-20 text-center text-monu-text/50">
            <span className="text-5xl block mb-4">🍳</span>
            <p className="text-lg">No hay tickets en cocina en este momento.</p>
          </div>
        ) : (
          kitchenOrders.map((order, i) => (
            <div key={order.id} className={`bg-white rounded-2xl shadow-monu overflow-hidden border-2 ${i === 0 ? 'border-red-500 animate-pulse' : 'border-transparent'}`}>
              <div className={`p-4 text-white flex justify-between items-center ${i === 0 ? 'bg-red-500' : 'bg-monu-dark'}`}>
                <div className="flex items-center gap-2 font-bold">
                  <Clock className="w-4 h-4" />
                  <span>{i === 0 ? '¡Demorado!' : '10:45 AM'}</span>
                </div>
                <span className="font-extrabold text-xl">#{order.id}</span>
              </div>
              
              <div className="p-5">
                <div className="space-y-4 mb-6">
                  {order.items.map((item, j) => (
                    <div key={j} className="flex gap-3 items-start border-b border-monu-green/10 pb-3 last:border-0 last:pb-0">
                      <span className="w-8 h-8 rounded-lg bg-monu-green/10 text-monu-green flex items-center justify-center font-bold text-lg shrink-0">
                        {item.match(/^\d+/)?.[0] || '1'}
                      </span>
                      <span className="font-bold text-monu-dark text-lg leading-tight">
                        {item.replace(/^\dx\s/, '')}
                      </span>
                    </div>
                  ))}
                </div>

                <button 
                  onClick={() => markReady(order.id)}
                  className="w-full bg-monu-green hover:bg-monu-green/80 text-white font-bold py-4 rounded-xl flex items-center justify-center gap-2 transition shadow-md active:scale-95"
                >
                  <CheckCircle className="w-5 h-5" />
                  Listo para Envío
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
