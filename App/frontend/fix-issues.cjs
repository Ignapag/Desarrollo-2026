const fs = require('fs');
const path = require('path');

// 1. FIX ENCODING IN INVENTORY
const invPath = path.join(__dirname, 'src', 'inventory', 'Inventory.jsx');
let inv = fs.readFileSync(invPath, 'utf-8');
// Reemplazar el caracter de error (\uFFFD)
inv = inv.replace(/A\uFFFDadir/g, 'Añadir');
inv = inv.replace(/Categor\uFFFDa/g, 'Categoría');
inv = inv.replace(/M\uFFFDnimo/g, 'Mínimo');
inv = inv.replace(/Prote\uFFFDnas/g, 'Proteínas');
inv = inv.replace(/L\uFFFDcteos/g, 'Lácteos');
inv = inv.replace(/Panader\uFFFDa/g, 'Panadería');
inv = inv.replace(/\uFFFD/g, ''); // Remove any lingering broken characters
fs.writeFileSync(invPath, inv, 'utf-8');

// 2. FIX LOGO IN MENU AND CATALOG
const menuPath = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let menu = fs.readFileSync(menuPath, 'utf-8');
menu = menu.replace(/<img src="\/favicon.png" className="w-16 h-16 opacity-30 grayscale" alt="placeholder" \/>/g, '<img src="/favicon.png" className="w-16 h-16 object-contain" alt="Logo" />');
fs.writeFileSync(menuPath, menu, 'utf-8');

const catPath = path.join(__dirname, 'src', 'management', 'Catalog.jsx');
let cat = fs.readFileSync(catPath, 'utf-8');
cat = cat.replace(/<img src="\/favicon.png" className="w-full h-full opacity-30 grayscale" alt="placeholder" \/>/g, '<img src="/favicon.png" className="w-full h-full object-contain p-1" alt="Logo" />');
fs.writeFileSync(catPath, cat, 'utf-8');

console.log("Encoding and Logo fixed!");