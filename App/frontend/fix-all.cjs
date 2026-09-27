const fs = require("fs");
const path = require("path");

// Fix Kitchen.jsx
const kitchenPath = path.join(__dirname, "src", "kitchen", "Kitchen.jsx");
let kitchen = fs.readFileSync(kitchenPath, "utf-8");

kitchen = kitchen.replace(/export default function Kitchen\(\) \{\s*\/\/ Efecto de sonido[\s\S]*?\}, \[orders\]\);/, `export default function Kitchen() {
  const { state, dispatch } = useData();
  const { orders } = state;

  // Efecto de sonido para nuevos pedidos
  useEffect(() => {
    const pendingOrders = orders.filter(o => o.status === 'pendiente' || o.status === 'en_preparacion').length;
    if (pendingOrders > 0) {
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
        gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.15);
      } catch (e) {}
    }
  }, [orders]);
`);

// Clean up duplicate declarations if any
kitchen = kitchen.replace(/  const \{ state, dispatch \} = useData\(\);\n  const \{ orders \} = state;\n\n  const kitchenOrders/g, "  const kitchenOrders");

fs.writeFileSync(kitchenPath, kitchen, "utf-8");

// Fix Inventory.jsx corrupted characters
const invPath = path.join(__dirname, "src", "inventory", "Inventory.jsx");
let inv = fs.readFileSync(invPath, "utf-8");
inv = inv.replace(/Categora/g, "Categoría");
inv = inv.replace(/Mnimo/g, "Mínimo");
inv = inv.replace(/Aadir/g, "Añadir");
inv = inv.replace(/Protenas/g, "Proteínas");
inv = inv.replace(/Panadera/g, "Panadería");
inv = inv.replace(/Lcteos/g, "Lácteos");
inv = inv.replace(/ptimo/g, "Óptimo");
fs.writeFileSync(invPath, inv, "utf-8");

// Fix emoji in Menu.jsx and Catalog.jsx
const menuPath = path.join(__dirname, "src", "ordering", "Menu.jsx");
let menu = fs.readFileSync(menuPath, "utf-8");
menu = menu.replace(/<span className="text-5xl opacity-40">🍔<\/span>/g, '<img src="/favicon.png" className="w-16 h-16 opacity-30 grayscale" alt="placeholder" />');
fs.writeFileSync(menuPath, menu, "utf-8");

const catPath = path.join(__dirname, "src", "management", "Catalog.jsx");
let cat = fs.readFileSync(catPath, "utf-8");
cat = cat.replace(/<div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center text-xl">🍔<\/div>/g, '<div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center p-2"><img src="/favicon.png" className="w-full h-full opacity-30 grayscale" alt="placeholder" /></div>');
fs.writeFileSync(catPath, cat, "utf-8");
