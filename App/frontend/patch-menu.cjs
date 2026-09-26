const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "import { useSearchParams } from 'react-router-dom';",
  "import { useSearchParams } from 'react-router-dom';\nimport { toast } from 'sonner';"
);

content = content.replace(
  "addToCart(itemToAdd);\n    setNotes('');\n    setShowOptions(false);",
  "addToCart(itemToAdd);\n    toast.success('Agregado al carrito', { description: itemToAdd.name });\n    setNotes('');\n    setShowOptions(false);"
);

fs.writeFileSync(file, content, 'utf-8');