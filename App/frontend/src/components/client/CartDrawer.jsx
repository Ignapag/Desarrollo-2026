import { X, Minus, Plus, Trash2, CheckCircle } from 'lucide-react';
import { useData } from '../../shared/store/DataContext';
import { useState } from 'react';

export default function CartDrawer({ isOpen, onClose }) {
  const { state, dispatch } = useData();
  const { cart } = state;
  const [isSuccess, setIsSuccess] = useState(false);

  const total = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);

  const placeOrder = () => {
    if (cart.length === 0) return;
    dispatch({ 
      type: 'PLACE_ORDER', 
      payload: { 
        client: 'Cliente Monu', 
        address: 'Calle 50 #782', 
        total, 
        items: cart.map(i => `${i.quantity}x ${i.name}`) 
      } 
    });
    setIsSuccess(true);
    setTimeout(() => {
      setIsSuccess(false);
      onClose();
    }, 3000);
  };

  return (
    <>
      {/* Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 transition-opacity"
          onClick={onClose}
        ></div>
      )}

      {/* Drawer */}
      <div className={`fixed top-0 right-0 h-full w-full sm:w-[400px] bg-monu-bone shadow-2xl z-50 transform transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'} flex flex-col`}>
        <div className="p-6 border-b border-monu-green/10 flex items-center justify-between bg-white">
          <h2 className="text-2xl font-extrabold font-heading text-monu-dark">El Carrito De Compras</h2>
          <button onClick={onClose} className="p-2 hover:bg-monu-cream rounded-full transition">
            <X className="w-6 h-6 text-monu-text" />
          </button>
        </div>

        {isSuccess ? (
          <div className="flex-1 flex flex-col items-center justify-center p-6 text-center animate-in fade-in zoom-in duration-300">
            <CheckCircle className="w-20 h-20 text-monu-green mb-4" />
            <h3 className="text-2xl font-extrabold text-monu-dark mb-2">¡Pedido Confirmado!</h3>
            <p className="text-monu-text/70 mb-6">Tu pedido ya está en cocina y pronto estará en camino.</p>
            <button 
              onClick={() => { setIsSuccess(false); onClose(); }}
              className="bg-monu-cream text-monu-dark font-bold px-6 py-3 rounded-xl hover:bg-monu-green hover:text-white transition"
            >
              Cerrar
            </button>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {cart.length === 0 ? (
                <div className="text-center text-monu-text/60 mt-20">
                  <span className="text-6xl mb-4 block">🛒</span>
                  <p>Tu carrito está vacío</p>
                  <button onClick={onClose} className="text-monu-orange font-bold mt-4">Volver al menú</button>
                </div>
              ) : (
                cart.map((item, index) => (
                  <div key={index} className="flex gap-4 p-4 bg-white rounded-2xl border border-monu-green/10 shadow-sm">
                    <img src={item.image} alt={item.name} className="w-20 h-20 object-cover rounded-xl" />
                    <div className="flex-1 flex flex-col justify-between">
                      <div className="flex justify-between items-start">
                        <h3 className="font-bold text-monu-dark leading-tight">{item.name}</h3>
                        <button 
                          onClick={() => dispatch({ type: 'REMOVE_FROM_CART', payload: index })}
                          className="text-red-400 hover:text-red-600 transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="flex justify-between items-center mt-2">
                        <div className="flex items-center gap-3 bg-monu-cream rounded-lg px-2 py-1">
                          <button 
                            onClick={() => dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { index, delta: -1 } })}
                            className="text-monu-text hover:text-monu-orange"
                          >
                            <Minus className="w-4 h-4" />
                          </button>
                          <span className="font-bold text-sm">{item.quantity}</span>
                          <button 
                            onClick={() => dispatch({ type: 'UPDATE_CART_QUANTITY', payload: { index, delta: 1 } })}
                            className="text-monu-text hover:text-monu-green"
                          >
                            <Plus className="w-4 h-4" />
                          </button>
                        </div>
                        <span className="font-bold text-monu-burnt">${(item.price * item.quantity).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {cart.length > 0 && (
              <div className="p-6 bg-white border-t border-monu-green/10 shadow-[0_-10px_20px_rgba(0,0,0,0.05)]">
                <div className="space-y-3 mb-6">
                  <div className="flex justify-between text-monu-text/80">
                    <span>Subtotal</span>
                    <span>${total.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-monu-text/80">
                    <span>Costo de envío</span>
                    <span>$1.500</span>
                  </div>
                  <div className="flex justify-between font-extrabold text-xl text-monu-dark pt-3 border-t border-monu-green/10">
                    <span>Total</span>
                    <span className="text-monu-burnt">${(total + 1500).toLocaleString()}</span>
                  </div>
                </div>
                <button 
                  onClick={placeOrder}
                  className="w-full bg-monu-orange hover:bg-monu-burnt text-white py-4 rounded-2xl font-bold text-lg shadow-[0_8px_16px_-4px_rgba(232,93,44,0.3)] transition-all active:scale-[0.98]"
                >
                  Confirmar Pedido
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
