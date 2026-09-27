const fs = require('fs');
const path = require('path');

const menuPath = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let menu = fs.readFileSync(menuPath, 'utf-8');

menu = menu.replace(/Acompa.amientos/g, 'Acompañamientos');
menu = menu.replace(/Monufusi.n/g, 'Monufusión');

fs.writeFileSync(menuPath, menu, 'utf-8');
console.log("Fixed Menu encoding");