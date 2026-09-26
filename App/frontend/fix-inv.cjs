const fs = require('fs');
const path = require('path');

const invPath = path.join(__dirname, 'src', 'inventory', 'Inventory.jsx');
let inv = fs.readFileSync(invPath, 'utf-8');

inv = inv.replace(/Categor.a/g, 'Categoría');
inv = inv.replace(/A.adir/g, 'Añadir');
inv = inv.replace(/Prote.nas/g, 'Proteínas');
inv = inv.replace(/M.nimo/g, 'Mínimo');
inv = inv.replace(/L.cteos/g, 'Lácteos');
inv = inv.replace(/Panader.a/g, 'Panadería');
inv = inv.replace(/ptimo/g, 'Óptimo');

fs.writeFileSync(invPath, inv, 'utf-8');
console.log("Forced encoding fixes with dot regex");