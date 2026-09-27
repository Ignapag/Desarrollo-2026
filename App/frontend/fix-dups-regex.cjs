const fs = require('fs');
const path = require('path');

function removeDups(file) {
  let content = fs.readFileSync(file, 'utf-8');
  
  // Remove all duplicate imports
  content = content.replace("import { useSearchParams } from 'react-router-dom';\nimport { useState } from 'react';\nimport { Settings2 } from 'lucide-react';\nimport { useSearchParams } from 'react-router-dom';", "import { useState } from 'react';\nimport { Settings2 } from 'lucide-react';\nimport { useSearchParams } from 'react-router-dom';");
  
  // Inventory imports
  content = content.replace("import { useSearchParams } from 'react-router-dom';\nimport { useState } from 'react';\nimport { Plus, AlertTriangle, TrendingUp, Package } from 'lucide-react';\nimport { useSearchParams } from 'react-router-dom';", "import { useState } from 'react';\nimport { Plus, AlertTriangle, TrendingUp, Package } from 'lucide-react';\nimport { useSearchParams } from 'react-router-dom';");

  // Fix inside Menu component
  content = content.replace("const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();\n  const [searchParams, setSearchParams] = useSearchParams();\n  const activeCategory = searchParams.get('category') || 'Todas';", "const [searchParams, setSearchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();\n  const activeCategory = searchParams.get('category') || 'Todas';");

  // Fix inside Inventory component
  content = content.replace("const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();\n  const [searchParams] = useSearchParams();\n  const activeCategory = searchParams.get('category') || 'Todos';", "const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();\n  const activeCategory = searchParams.get('category') || 'Todos';");

  fs.writeFileSync(file, content, 'utf-8');
}

removeDups(path.join(__dirname, 'src', 'ordering', 'Menu.jsx'));
removeDups(path.join(__dirname, 'src', 'inventory', 'Inventory.jsx'));