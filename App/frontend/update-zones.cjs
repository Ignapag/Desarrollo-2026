const fs = require('fs');
const path = require('path');

const cartPath = path.join(__dirname, 'src', 'components', 'client', 'CartDrawer.jsx');
let cartContent = fs.readFileSync(cartPath, 'utf-8');

// Add zone state
cartContent = cartContent.replace("const [address, setAddress] = useState('');", "const [address, setAddress] = useState('');\n  const [zone, setZone] = useState('');");

// Modify inputs in CartDrawer
const oldInputs = `<div className="space-y-3 mb-4">
              <input 
                type="text" 
                placeholder="Tu dirección de entrega..."`;

const newInputs = `<div className="space-y-3 mb-4">
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
                placeholder="Calle y Número (Ej: Calle 43 #123)..."`;

cartContent = cartContent.replace(oldInputs, newInputs);

// Modify disabled state
cartContent = cartContent.replace("disabled={cart.length === 0 || isPayingMP || !address || !phone}", "disabled={cart.length === 0 || isPayingMP || !address || !phone || !zone}");

// Modify payload address
cartContent = cartContent.replace("address: address,", "address: `${address}, ${zone}`,");

fs.writeFileSync(cartPath, cartContent, 'utf-8');


// Modify ClientLayout for Business Hours
const layoutPath = path.join(__dirname, 'src', 'ordering', 'ClientLayout.jsx');
let layoutContent = fs.readFileSync(layoutPath, 'utf-8');

const oldLogo = `<Link to="/menu" className="text-2xl font-extrabold tracking-tight font-heading">
              Monu Burger
            </Link>`;

const newLogo = `<div className="flex flex-col">
              <Link to="/menu" className="text-2xl font-extrabold tracking-tight font-heading leading-none mb-1">
                Monu Burger
              </Link>
              <span className="text-[11px] font-bold text-white/80 flex items-center gap-1 bg-white/10 px-2 py-0.5 rounded-full w-max">
                🕒 Todos los días de 19:30 a 00:00
              </span>
            </div>`;

layoutContent = layoutContent.replace(oldLogo, newLogo);

fs.writeFileSync(layoutPath, layoutContent, 'utf-8');

console.log("CartDrawer and ClientLayout updated successfully.");