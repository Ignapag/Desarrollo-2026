const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'management', 'Catalog.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "import { useSearchParams } from 'react-router-dom';",
  "import { useSearchParams } from 'react-router-dom';\nimport { toast } from 'sonner';"
);

content = content.replace(
  "dispatch({ \n      type: 'ADD_CATALOG_ITEM', \n      payload: {",
  "toast.success('Producto agregado', { description: newItem.name });\n    dispatch({ \n      type: 'ADD_CATALOG_ITEM', \n      payload: {"
);

content = content.replace(
  "dispatch({ type: 'DELETE_CATALOG_ITEM', payload: product.id })",
  "dispatch({ type: 'DELETE_CATALOG_ITEM', payload: product.id }); toast.info('Producto eliminado');"
);

fs.writeFileSync(file, content, 'utf-8');