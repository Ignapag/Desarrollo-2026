const fs = require('fs');
const path = require('path');

const catPath = path.join(__dirname, 'src', 'management', 'Catalog.jsx');
let cat = fs.readFileSync(catPath, 'utf-8');
cat = cat.replace(/<img src="\/favicon\.png" className=".*?" alt="Logo" \/>/g, '<img src="/favicon.png" className="w-full h-full object-contain" alt="Logo" />');
fs.writeFileSync(catPath, cat, 'utf-8');

const menuPath = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let menu = fs.readFileSync(menuPath, 'utf-8');
menu = menu.replace(/<img src="\/favicon\.png" className=".*?" alt="Logo" \/>/g, '<img src="/favicon.png" className="w-full h-full object-contain" alt="Logo" />');
fs.writeFileSync(menuPath, menu, 'utf-8');

console.log("Images enforced");