const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let content = fs.readFileSync(file, 'utf-8');

// Replace the naive loading with the healed loading
content = content.replace(
  "if (savedCatalog) st.catalog = JSON.parse(savedCatalog);",
  "if (savedCatalog) {\n        let cat = JSON.parse(savedCatalog);\n        cat = cat.map(p => p.name === 'La Típica' && !p.image ? { ...p, image: '/menu/LaTipicaBurger.jpg' } : p);\n        st.catalog = cat;\n      }"
);

fs.writeFileSync(file, content, 'utf-8');
console.log("Patched DataContext to heal La Tipica image in localStorage");