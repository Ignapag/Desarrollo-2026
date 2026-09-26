const fs = require("fs");
const path = require("path");

const file = path.join(__dirname, "src", "components", "client", "CartDrawer.jsx");
let content = fs.readFileSync(file, "utf-8");

content = content.replace("const [isSuccess, setIsSuccess] = useState(false);", "const [isSuccess, setIsSuccess] = useState(false);\n  const [isPayingMP, setIsPayingMP] = useState(false);");

const newPlaceOrder = `
  const placeOrder = () => {
    if (cart.length === 0) return;
    setIsPayingMP(true);
    
    // Simula el tiempo que tarda en abrir MercadoPago y cobrar
    setTimeout(() => {
      setIsPayingMP(false);
      dispatch({ 
        type: 'PLACE_ORDER', 
        payload: { 
          client: 'Cliente Monu', 
          address: 'Calle 50 #782', 
          total, 
          items: cart.map(i => \`\${i.quantity}x \${i.name}\`) 
        } 
      });
      setIsSuccess(true);
      setTimeout(() => {
        setIsSuccess(false);
        onClose();
      }, 3000);
    }, 2500);
  };
`;

content = content.replace(/const placeOrder = \(\) => \{[\s\S]*?onClose\(\);\n      \}, 3000\);\n    \}\n  \};/, newPlaceOrder.trim());

const newSuccess = `
          {isSuccess ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center animate-in fade-in zoom-in">
              <div className="w-20 h-20 bg-monu-green/10 rounded-full flex items-center justify-center mb-6">
                <CheckCircle className="w-10 h-10 text-monu-green" />
              </div>
              <h3 className="font-heading font-black text-2xl text-monu-dark mb-2">¡Pedido Pagado!</h3>
              <p className="text-monu-text/70 mb-4">Tu orden ya está en la cocina. Podés seguirla en la pantalla de pedidos.</p>
              <div className="p-4 bg-gray-50 rounded-xl w-full">
                <p className="text-sm font-bold text-gray-500">Transacción MercadoPago:</p>
                <p className="text-xs text-gray-400 font-mono">#MP-{Math.floor(Math.random() * 10000000)}</p>
              </div>
            </div>
          ) : isPayingMP ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center animate-in fade-in zoom-in">
               <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-6"></div>
               <h3 className="font-heading font-black text-xl text-blue-600 mb-2">Conectando con MercadoPago...</h3>
               <p className="text-sm text-gray-500">Por favor, no cierres esta ventana.</p>
            </div>
          ) : (`

content = content.replace(/\{isSuccess \? \([\s\S]*?\} \: \(/, newSuccess);

const oldButton = `
              <button 
                onClick={placeOrder}
                disabled={cart.length === 0}
                className="w-full bg-monu-green text-white font-black py-4 rounded-2xl hover:bg-[#002b22] transition-colors disabled:opacity-50 mt-4 text-lg"
              >
                Confirmar Pedido
              </button>
`;

const newButton = `
              <button 
                onClick={placeOrder}
                disabled={cart.length === 0 || isPayingMP}
                className="w-full bg-[#009EE3] text-white font-black py-4 rounded-2xl hover:bg-[#0080b7] transition-colors disabled:opacity-50 mt-4 text-lg flex items-center justify-center gap-2"
              >
                Pagar con MercadoPago
              </button>
`;

content = content.replace(oldButton, newButton);
fs.writeFileSync(file, content, "utf-8");