const fs = require('fs');
const path = require('path');

const menuPath = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let menuContent = fs.readFileSync(menuPath, 'utf-8');

// Replace the top imports
menuContent = menuContent.replace("import { useState } from 'react';", "import { useState } from 'react';\nimport { Settings2 } from 'lucide-react';");

// Inside ProductCard
menuContent = menuContent.replace("const [selectedVariantIndex, setSelectedVariantIndex] = useState(0);", `const [selectedVariantIndex, setSelectedVariantIndex] = useState(0);
  const [showOptions, setShowOptions] = useState(false);
  const [notes, setNotes] = useState('');`);

// In handleAdd
const oldHandleAdd = `    if (hasVariants) {
      const variant = product.variants[selectedVariantIndex];
      addToCart({
        ...product,
        id: \`\${product.id}-\${variant.name}\`,
        name: \`\${product.name} (\${variant.name})\`,
        price: variant.price,
      });
    } else {
      addToCart(product);
    }`;
const newHandleAdd = `    const itemToAdd = hasVariants ? {
      ...product,
      id: \`\${product.id}-\${product.variants[selectedVariantIndex].name}\`,
      name: \`\${product.name} (\${product.variants[selectedVariantIndex].name})\`,
      price: product.variants[selectedVariantIndex].price,
    } : { ...product };

    if (notes.trim()) {
      itemToAdd.notes = notes.trim();
      itemToAdd.id = \`\${itemToAdd.id}-\${Date.now()}\`; // Unique ID so it stacks separately in cart
    }
    
    addToCart(itemToAdd);
    setNotes('');
    setShowOptions(false);`;
menuContent = menuContent.replace(oldHandleAdd, newHandleAdd);

// Render options
const selectHtml = `          {hasVariants ? (
            <select 
              value={selectedVariantIndex}
              onChange={(e) => setSelectedVariantIndex(parseInt(e.target.value))}
              className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-xl px-3 py-2 text-sm font-bold text-monu-dark focus:outline-none focus:border-monu-green"
            >
              {product.variants.map((v, i) => (
                <option key={i} value={i}>{v.name} - \${v.price}</option>
              ))}
            </select>
          ) : (
            <div className="h-[38px]"></div>
          )}
        </div>`;

const newSelectHtml = `          <div className="flex gap-2">
            {hasVariants ? (
              <select 
                value={selectedVariantIndex}
                onChange={(e) => setSelectedVariantIndex(parseInt(e.target.value))}
                className="flex-1 bg-monu-cream/50 border border-monu-green/10 rounded-xl px-3 py-2 text-sm font-bold text-monu-dark focus:outline-none focus:border-monu-green"
              >
                {product.variants.map((v, i) => (
                  <option key={i} value={i}>{v.name} - \${v.price}</option>
                ))}
              </select>
            ) : (
              <div className="flex-1 h-[38px]"></div>
            )}
            <button 
              onClick={() => setShowOptions(!showOptions)}
              className={\`p-2 rounded-xl transition-colors \${showOptions ? 'bg-monu-green text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}\`}
              title="Personalizar pedido"
            >
              <Settings2 className="w-5 h-5" />
            </button>
          </div>
          
          {showOptions && (
            <div className="mt-3 animate-in slide-in-from-top-2">
              <input 
                type="text" 
                placeholder="Ej: Sin cebolla, extra cheddar..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-yellow-50 border border-yellow-200 rounded-xl px-3 py-2 text-sm text-monu-dark placeholder:text-yellow-600/50 focus:outline-none focus:border-yellow-400"
              />
            </div>
          )}
        </div>`;
menuContent = menuContent.replace(selectHtml, newSelectHtml);

fs.writeFileSync(menuPath, menuContent, 'utf-8');
console.log("Menu updated");