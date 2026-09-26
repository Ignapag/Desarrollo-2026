const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "const filteredProducts = currentCategory === 'Todas' \n    ? PRODUCTS \n    : PRODUCTS.filter(p => p.category === currentCategory);",
  "const filteredProducts = PRODUCTS.filter(p => {\n    const matchCat = currentCategory === 'Todas' || p.category === currentCategory;\n    const matchQuery = p.name.toLowerCase().includes(query) || (p.description && p.description.toLowerCase().includes(query));\n    return matchCat && matchQuery;\n  });"
);

fs.writeFileSync(file, content, 'utf-8');