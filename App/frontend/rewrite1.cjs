const fs = require('fs');
const path = require('path');

// 1. REWRITE DELIVERY PANEL
const dpPath = path.join(__dirname, 'src', 'fulfillment', 'DeliveryPanel.jsx');
const dpContent = `import { useData } from '../shared/store/DataContext';
import { MapPin, Phone, CheckCircle, Navigation } from 'lucide-react';

export default function DeliveryPanel() {
  const { state, dispatch } = useData();
  const { orders } = state;

  const activeOrders = orders.filter(o => o.status === 'en_camino' || o.status === 'listo');
  
  const markAsDelivered = (id) => {
    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: 'entregado' } });
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
            <div key={order.id} className={\`bg-white rounded-2xl shadow-sm overflow-hidden border-2 \${i === 0 ? 'border-monu-orange' : 'border-transparent'}\`}>
              <div className={\`p-4 text-white flex justify-between items-center \${i === 0 ? 'bg-monu-orange' : 'bg-monu-green/80'}\`}>
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
                    href={\`tel:\${order.phone?.replace(/\\D/g, '') || ''}\`}
                    className="flex-1 bg-yellow-50 hover:bg-yellow-100 text-yellow-700 font-bold py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition"
                  >
                    <Phone className="w-5 h-5" /> Llamar
                  </a>
                  <a 
                    href={\`https://maps.google.com/?q=\${encodeURIComponent(order.address + ', La Plata, Buenos Aires')}\`}
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
`;
fs.writeFileSync(dpPath, dpContent, 'utf-8');

// 2. REWRITE CART DRAWER
const cartPath = path.join(__dirname, 'src', 'components', 'client', 'CartDrawer.jsx');
const cartContent = `import { useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { useData } from '../../shared/store/DataContext';
import { Trash2, CreditCard, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function CartDrawer({ isOpen, onClose }) {
  const { user } = useAuth();
  const { state, dispatch } = useData();
  const { cart } = state;
  const navigate = useNavigate();
  
  const [isSuccess, setIsSuccess] = useState(false);
  const [isPayingMP, setIsPayingMP] = useState(false);
  
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');

  const updateQuantity = (index, delta) => {
    dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { index, delta } });
  };

  const removeFromCart = (index) => {
    dispatch({ type: 'REMOVE_FROM_CART', payload: index });
  };

  const total = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);

  const placeOrder = () => {
    if (cart.length === 0 || !address || !phone) return;
    setIsPayingMP(true);
    
    setTimeout(() => {
      dispatch({ 
        type: 'PLACE_ORDER', 
        payload: { 
          client: user?.name || 'Cliente sin cuenta', 
          address: address, 
          phone: phone,
          total, 
          items: cart.map(i => \`\${i.quantity}x \${i.name} \${i.notes ? '(' + i.notes + ')' : ''}\`) 
        } 
      });
      setIsPayingMP(false);
      setIsSuccess(true);
      setTimeout(() => {
        setIsSuccess(false);
        onClose();
        navigate('/menu');
      }, 3000);
    }, 2000); // MP sim
  };

  return (
    <>
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 transition-opacity"
          onClick={onClose}
        />
      )}
      
      <div className={\`fixed inset-y-0 right-0 w-full md:w-96 bg-white z-50 shadow-2xl transform transition-transform duration-300 flex flex-col \${isOpen ? 'translate-x-0' : 'translate-x-full'}\`}>
        <div className="p-5 border-b flex justify-between items-center bg-monu-cream/30">
          <h2 className="text-xl font-extrabold font-heading text-monu-dark">Tu Carrito</h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <ChevronRight className="w-6 h-6" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {isSuccess ? (
            <div className="h-full flex flex-col items-center justify-center text-center space-y-4 animate-in fade-in zoom-in duration-500">
              <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center text-green-500 mb-4">
                <CheckCircle className="w-10 h-10" />
              </div>
              <h3 className="text-2xl font-extrabold text-monu-dark">¡Pedido Confirmado!</h3>
              <p className="text-monu-text/70">Tu pedido ya entró a la cocina. Podés pasar a retirarlo o esperar al repartidor en 30 minutos.</p>
            </div>
          ) : cart.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-monu-text/50">
              <span className="text-5xl mb-4">🛒</span>
              <p className="font-bold">Tu carrito está vacío</p>
              <p className="text-sm">¡Agregá algo rico del menú!</p>
            </div>
          ) : (
            <div className="space-y-4">
              {cart.map((item, index) => (
                <div key={index} className="flex gap-4 border-b border-monu-green/10 pb-4 last:border-0">
                  {item.image ? (
                    <img src={item.image} alt={item.name} className="w-20 h-20 object-cover rounded-xl shadow-sm" />
                  ) : (
                    <div className="w-20 h-20 bg-monu-cream rounded-xl flex items-center justify-center">
                      <img src="/favicon.png" className="w-10 h-10 object-contain" alt="Logo" />
                    </div>
                  )}
                  <div className="flex-1">
                    <div className="flex justify-between items-start">
                      <h4 className="font-extrabold text-monu-dark leading-tight">{item.name}</h4>
                      <button onClick={() => removeFromCart(index)} className="text-red-400 hover:text-red-600 transition-colors">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    {item.notes && <p className="text-xs font-bold text-monu-orange mt-1">Nota: {item.notes}</p>}
                    <div className="flex justify-between items-end mt-3">
                      <div className="flex items-center gap-3 bg-monu-cream rounded-lg px-2 py-1">
                        <button onClick={() => updateQuantity(index, -1)} className="w-6 h-6 flex items-center justify-center font-bold text-monu-green hover:bg-monu-green/10 rounded">-</button>
                        <span className="font-bold w-4 text-center">{item.quantity}</span>
                        <button onClick={() => updateQuantity(index, 1)} className="w-6 h-6 flex items-center justify-center font-bold text-monu-green hover:bg-monu-green/10 rounded">+</button>
                      </div>
                      <span className="font-extrabold text-monu-green">
                        ${(item.price * item.quantity).toLocaleString('es-AR')}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {!isSuccess && cart.length > 0 && (
          <div className="p-5 border-t bg-monu-cream/30">
            <div className="space-y-3 mb-4">
              <input 
                type="text" 
                placeholder="Tu dirección de entrega..." 
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="w-full bg-white border border-monu-green/20 rounded-xl px-4 py-3 font-bold text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
              />
              <input 
                type="tel" 
                placeholder="Tu WhatsApp (ej: 2215550000)" 
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full bg-white border border-monu-green/20 rounded-xl px-4 py-3 font-bold text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
              />
            </div>
            
            <div className="space-y-3 mb-6">
              <div className="flex justify-between text-monu-text/70 font-bold">
                <span>Subtotal</span>
                <span>${total.toLocaleString('es-AR')}</span>
              </div>
              <div className="flex justify-between font-extrabold text-xl text-monu-dark border-t border-monu-green/10 pt-3">
                <span>Total</span>
                <span>${total.toLocaleString('es-AR')}</span>
              </div>
            </div>

            <button 
              onClick={placeOrder}
              disabled={cart.length === 0 || isPayingMP || !address || !phone}
              className="w-full bg-[#009EE3] hover:bg-[#0088C4] disabled:opacity-50 disabled:cursor-not-allowed text-white font-extrabold py-4 rounded-xl flex items-center justify-center gap-2 transition-all shadow-lg active:scale-95"
            >
              {isPayingMP ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Conectando con MercadoPago...
                </>
              ) : (
                <>
                  <CreditCard className="w-5 h-5" />
                  Pagar con MercadoPago
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
`;
fs.writeFileSync(cartPath, cartContent, 'utf-8');

console.log("Rewrote DeliveryPanel and CartDrawer.");