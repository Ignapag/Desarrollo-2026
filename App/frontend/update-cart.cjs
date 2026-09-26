const fs = require('fs');
const path = require('path');

const cartPath = path.join(__dirname, 'src', 'components', 'client', 'CartDrawer.jsx');
let cartContent = fs.readFileSync(cartPath, 'utf-8');

// Add states for address and phone
cartContent = cartContent.replace('const [isPayingMP, setIsPayingMP] = useState(false);', `const [isPayingMP, setIsPayingMP] = useState(false);
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');`);

// Update PLACE_ORDER payload
const oldPayload = `payload: { 
          client: 'Cliente Monu', 
          address: 'Calle 50 #782', 
          total, 
          items: cart.map(i => \`\${i.quantity}x \${i.name}\`) 
        }`;
const newPayload = `payload: { 
          client: 'Cliente Monu', 
          address: address || 'Retira por local', 
          phone: phone,
          total, 
          items: cart.map(i => \`\${i.quantity}x \${i.name} \${i.notes ? '(' + i.notes + ')' : ''}\`) 
        }`;
cartContent = cartContent.replace(oldPayload, newPayload);

// Add the input fields before the subtotal section
const oldSubtotal = `<div className="space-y-3 mb-6">`;
const newInputs = `<div className="space-y-3 mb-4">
                  <input 
                    type="text" 
                    placeholder="Tu dirección de entrega..." 
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 font-bold text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                  />
                  <input 
                    type="tel" 
                    placeholder="Tu WhatsApp (ej: 2215550000)" 
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-4 py-3 font-bold text-monu-dark focus:outline-none focus:border-monu-green transition-colors"
                  />
                </div>
                <div className="space-y-3 mb-6">`;
cartContent = cartContent.replace(oldSubtotal, newInputs);

// Disable button if inputs are empty
cartContent = cartContent.replace('disabled={cart.length === 0 || isPayingMP}', 'disabled={cart.length === 0 || isPayingMP || !address || !phone}');

fs.writeFileSync(cartPath, cartContent, 'utf-8');
console.log("CartDrawer updated");