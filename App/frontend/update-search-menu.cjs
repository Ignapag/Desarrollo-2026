const fs = require('fs');
const path = require('path');

const menuPath = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let menuContent = fs.readFileSync(menuPath, 'utf-8');

// Add useSearchParams import
menuContent = menuContent.replace(
  "import { Settings2 } from 'lucide-react';",
  "import { Settings2 } from 'lucide-react';\nimport { useSearchParams } from 'react-router-dom';"
);

// Add searchParams logic inside Menu
menuContent = menuContent.replace(
  "export default function Menu() {",
  `export default function Menu() {
  const [searchParams] = useSearchParams();
  const query = (searchParams.get('q') || '').toLowerCase();`
);

// Filter catalog categories
const oldCategories = "const categories = [...new Set(state.catalog.map(p => p.category))];";
const newCategories = `
  const filteredCatalog = state.catalog.filter(p => 
    p.name.toLowerCase().includes(query) || 
    (p.description && p.description.toLowerCase().includes(query))
  );
  
  const categories = query 
    ? [...new Set(filteredCatalog.map(p => p.category))] 
    : [...new Set(state.catalog.map(p => p.category))];
`;
menuContent = menuContent.replace(oldCategories, newCategories);

// Replace state.catalog mapping with filteredCatalog mapping
menuContent = menuContent.replace(
  `{state.catalog.filter(p => p.category === category).map(product => (`,
  `{filteredCatalog.filter(p => p.category === category).map(product => (`
);

// Add empty state if search has no results
const emptyState = `
      {filteredCatalog.length === 0 && query && (
        <div className="py-20 text-center text-monu-text/50 col-span-full">
          <span className="text-5xl mb-4 block">🍔</span>
          <p className="text-xl font-bold">No encontramos ninguna hamburguesa con "{query}"</p>
          <p className="text-sm">Probá buscando otra cosa.</p>
        </div>
      )}
`;
menuContent = menuContent.replace(
  `{categories.map(category => (`,
  `${emptyState}\n      {categories.map(category => (`
);

fs.writeFileSync(menuPath, menuContent, 'utf-8');
console.log("Client Menu search updated.");