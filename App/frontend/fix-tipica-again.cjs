const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let content = fs.readFileSync(file, 'utf-8');

// Fix the image path in the initialState array
content = content.replace(/\/menu\/LaTpicaBurger\.jpg/g, '/menu/LaTipicaBurger.jpg');
content = content.replace(/\/menu\/LaT..picaBurger\.jpg/g, '/menu/LaTipicaBurger.jpg'); // Regex fallback for weird chars
content = content.replace(/\/menu\/LaTipicaBurger\.jpg/g, '/menu/LaTipicaBurger.jpg'); 

// Fix the patch
content = content.replace(
  "cat = cat.map(p => p.name === 'La Tpica' && !p.image ? { ...p, image: '/menu/LaTipicaBurger.jpg' } : p);",
  "cat = cat.map(p => (p.name.includes('T') && p.name.includes('pica')) ? { ...p, image: '/menu/LaTipicaBurger.jpg' } : p);"
);

// Fallback if the above replace didn't find the exact broken string
content = content.replace(
  "cat = cat.map(p => p.name === 'La Típica' && !p.image ? { ...p, image: '/menu/LaTipicaBurger.jpg' } : p);",
  "cat = cat.map(p => (p.name.includes('T') && p.name.includes('pica')) ? { ...p, image: '/menu/LaTipicaBurger.jpg' } : p);"
);

fs.writeFileSync(file, content, 'utf-8');
console.log("Fixed La Tipica encoding and patch");