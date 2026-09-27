import { useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { useData } from '../../shared/store/DataContext';
import { Trash2, CreditCard, ChevronRight, CheckCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

export default function CartDrawer({ isOpen, onClose }) {
  const { user } = useAuth();
  const { state, dispatch } = useData();
  const { cart } = state;
  const navigate = useNavigate();
  
  
  const [isPayingMP, setIsPayingMP] = useState(false);
  
  const [address, setAddress] = useState('');
  const [zone, setZone] = useState('');
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
          address: `${address}, ${zone}`, 
          phone: phone,
          total, 
          items: cart.map(i => `${i.quantity}x ${i.name} ${i.notes ? '(' + i.notes + ')' : ''}`) 
        } 
      });
      setIsPayingMP(false);
      toast.success('¡Pedido Confirmado!', { description: 'Tu pedido ya entró a la cocina. ¡Preparate para disfrutar!' });
      onClose();
      navigate('/menu');
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
      
      <div className={`fixed inset-y-0 right-0 w-full md:w-96 bg-white z-50 shadow-2xl transform transition-transform duration-300 flex flex-col ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}>
        <div className="p-5 border-b flex justify-between items-center bg-monu-cream/30">
          <h2 className="text-xl font-extrabold font-heading text-monu-dark">Tu Carrito</h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <ChevronRight className="w-6 h-6" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {cart.length === 0 ? (
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

        {cart.length > 0 && (
          <div className="p-5 border-t bg-monu-cream/30">
            <div className="space-y-3 mb-4">
              <div className="bg-orange-50 border border-orange-200 text-orange-800 text-xs font-bold p-3 rounded-xl mb-2 flex items-start gap-2">
                <span className="text-lg leading-none">📍</span>
                <p>Delivery exclusivo para <strong>Ensenada</strong> y <strong>Punta Lara</strong>.</p>
              </div>
              <select
                value={zone}
                onChange={(e) => setZone(e.target.value)}
                className="w-full bg-white border border-monu-green/20 rounded-xl px-4 py-3 font-bold text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
              >
                <option value="">Seleccioná tu localidad...</option>
                <option value="Ensenada">Ensenada</option>
                <option value="Punta Lara">Punta Lara</option>
              </select>
              <input 
                type="text" 
                placeholder="Calle y Número (Ej: Calle 43 #123)..." 
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
              disabled={cart.length === 0 || isPayingMP || !address || !phone || !zone}
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