const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'management', 'Catalog.jsx');
let content = fs.readFileSync(file, 'utf-8');

// Add deletingId state
content = content.replace(
  "const [isAdding, setIsAdding] = useState(false);",
  "const [isAdding, setIsAdding] = useState(false);\n  const [deletingId, setDeletingId] = useState(null);"
);

// Remove the old handleDelete function definition because we will inline it
content = content.replace(
  /const handleDelete = \(id\) => \{\s+if\(confirm\('¿Eliminar producto\?'\)\) \{\s+dispatch\(\{ type: 'DELETE_CATALOG_ITEM', payload: id \}\);\s+\}\s+\};\s+/,
  ""
);
content = content.replace( // Catch the garbled text version too
  /const handleDelete = \(id\) => \{\s+if\(confirm\('Eliminar producto\?'\)\) \{\s+dispatch\(\{ type: 'DELETE_CATALOG_ITEM', payload: id \}\);\s+\}\s+\};\s+/,
  ""
);

// Replace the Trash button with the inline confirmation UI
const oldButton = `<button onClick={() => handleDelete(product.id)} className="p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition" title="Eliminar">
                    <Trash2 className="w-5 h-5" />
                  </button>`;

const newButton = `{deletingId === product.id ? (
                    <div className="flex flex-col gap-1 items-end">
                      <span className="text-xs font-bold text-red-500">¿Seguro?</span>
                      <div className="flex gap-1">
                        <button onClick={() => dispatch({ type: 'DELETE_CATALOG_ITEM', payload: product.id })} className="text-xs font-bold bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded transition">Sí</button>
                        <button onClick={() => setDeletingId(null)} className="text-xs font-bold bg-gray-200 hover:bg-gray-300 text-monu-dark px-2 py-1 rounded transition">No</button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setDeletingId(product.id)} className="p-2 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition" title="Eliminar">
                      <Trash2 className="w-5 h-5" />
                    </button>
                  )}`;

content = content.replace(oldButton, newButton);

fs.writeFileSync(file, content, 'utf-8');