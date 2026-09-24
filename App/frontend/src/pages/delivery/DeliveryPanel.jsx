import { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useData } from '../../context/DataContext';
import { MapPin, Phone, CheckCircle, Navigation, Clock, LogOut } from 'lucide-react';

export default function DeliveryPanel() {
  const { user, logout } = useAuth();
  const { state, dispatch } = useData();
  const [activeTab, setActiveTab] = useState('pendientes');

  // Filter orders that are either ready to be picked up or currently being delivered
  const deliveryOrders = state.orders.filter(o => ['listo', 'en_camino'].includes(o.status));

  const historyOrders = state.orders.filter(o => o.status === 'entregado');

  const updateStatus = (id, status) => {
    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status } });
  };

  return (
    <div className="min-h-screen bg-monu-cream font-sans pb-20">
      {/* Header */}
      <header className="bg-monu-dark text-white p-4 sticky top-0 z-20 shadow-md">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-monu-green rounded-xl flex items-center justify-center font-bold">
              {user?.name?.charAt(0) || 'R'}
            </div>
            <div>
              <h2 className="font-bold">{user?.name}</h2>
              <p className="text-xs text-white/70">Repartidor activo</p>
            </div>
          </div>
          <button onClick={logout} className="p-2 hover:bg-white/10 rounded-lg">
            <LogOut className="w-5 h-5" />
          </button>
        </div>

        <div className="flex bg-white/10 rounded-xl p-1">
          <button 
            onClick={() => setActiveTab('pendientes')}
            className={`flex-1 py-2 font-bold text-sm rounded-lg transition ${activeTab === 'pendientes' ? 'bg-white text-monu-dark shadow' : 'text-white/80'}`}
          >
            Nuevos Pedidos
          </button>
          <button 
            onClick={() => setActiveTab('historial')}
            className={`flex-1 py-2 font-bold text-sm rounded-lg transition ${activeTab === 'historial' ? 'bg-white text-monu-dark shadow' : 'text-white/80'}`}
          >
            Entregados
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="p-4 space-y-4">
        {activeTab === 'pendientes' ? (
          deliveryOrders.length === 0 ? (
            <div className="text-center text-monu-text/60 mt-10">
              <span className="text-4xl mb-2 block">🛵</span>
              <p>No hay pedidos pendientes.</p>
            </div>
          ) : (
            deliveryOrders.map(order => (
              <div key={order.id} className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-hidden">
                <div className={`p-4 text-white flex justify-between items-center ${order.status === 'listo' ? 'bg-monu-yellow text-monu-dark' : 'bg-monu-orange'}`}>
                  <div className="flex items-center gap-2 font-bold">
                    <Clock className="w-4 h-4" />
                    <span>Hace 10 min</span>
                  </div>
                  <span className="font-extrabold text-lg">#{order.id}</span>
                </div>

                <div className="p-4 space-y-4">
                  <div className="flex items-start gap-3">
                    <MapPin className="w-5 h-5 text-monu-green mt-0.5" />
                    <div>
                      <p className="font-bold text-monu-dark">{order.address}</p>
                      <p className="text-sm text-monu-text/70">{order.client}</p>
                    </div>
                  </div>
                  
                  <div className="flex gap-2">
                    <button className="flex-1 bg-monu-cream text-monu-dark font-bold py-2.5 rounded-xl text-sm flex items-center justify-center gap-2">
                      <Phone className="w-4 h-4" />
                      Llamar
                    </button>
                    <button className="flex-1 bg-monu-cream text-monu-dark font-bold py-2.5 rounded-xl text-sm flex items-center justify-center gap-2">
                      <Navigation className="w-4 h-4" />
                      Ruta
                    </button>
                  </div>

                  {order.status === 'listo' ? (
                    <button 
                      onClick={() => updateStatus(order.id, 'en_camino')}
                      className="w-full bg-monu-green text-white font-bold py-3.5 rounded-xl flex items-center justify-center gap-2 shadow-md"
                    >
                      Tomar Pedido
                    </button>
                  ) : (
                    <button 
                      onClick={() => updateStatus(order.id, 'entregado')}
                      className="w-full bg-monu-dark text-white font-bold py-3.5 rounded-xl flex items-center justify-center gap-2 shadow-md"
                    >
                      <CheckCircle className="w-5 h-5" />
                      Marcar Entregado
                    </button>
                  )}
                </div>
              </div>
            ))
          )
        ) : (
          historyOrders.length === 0 ? (
            <div className="text-center text-monu-text/60 mt-10">
              <p>Historial de entregas vacío hoy.</p>
            </div>
          ) : (
            historyOrders.map(order => (
              <div key={order.id} className="bg-white rounded-2xl shadow-sm border border-monu-green/10 overflow-hidden opacity-75">
                <div className="p-4 bg-monu-cream flex justify-between items-center text-monu-text">
                  <div className="flex items-center gap-2 font-bold">
                    <CheckCircle className="w-4 h-4 text-monu-green" />
                    <span>Entregado</span>
                  </div>
                  <span className="font-extrabold text-lg">#{order.id}</span>
                </div>
                <div className="p-4 flex items-start gap-3">
                  <MapPin className="w-5 h-5 text-monu-text/40 mt-0.5" />
                  <div>
                    <p className="font-bold text-monu-dark line-through decoration-monu-text/30">{order.address}</p>
                    <p className="text-sm text-monu-text/70">{order.client}</p>
                  </div>
                </div>
              </div>
            ))
          )
        )}
      </main>
    </div>
  );
}
