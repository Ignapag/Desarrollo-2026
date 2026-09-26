const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'management', 'Catalog.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "onClick={() => dispatch({ type: 'DELETE_CATALOG_ITEM', payload: product.id }); toast.info('Producto eliminado');}",
  "onClick={() => { dispatch({ type: 'DELETE_CATALOG_ITEM', payload: product.id }); toast.info('Producto eliminado'); }}"
);

fs.writeFileSync(file, content, 'utf-8');