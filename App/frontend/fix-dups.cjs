const fs = require('fs');
const path = require('path');

function deduplicate(file) {
  let content = fs.readFileSync(file, 'utf-8');
  content = content.replace(/import { useSearchParams } from "react-router-dom";\nimport { useSearchParams } from "react-router-dom";/g, 'import { useSearchParams } from "react-router-dom";');
  content = content.replace(/import { useSearchParams } from 'react-router-dom';\nimport { useSearchParams } from 'react-router-dom';/g, "import { useSearchParams } from 'react-router-dom';");
  
  content = content.replace(/const \[searchParams\] = useSearchParams\(\);\n  const query = \(searchParams.get\('q'\) \|\| ''\)\.toLowerCase\(\);\n  const \[searchParams, setSearchParams\] = useSearchParams\(\);/, "const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();");
  
  content = content.replace(/const \[searchParams\] = useSearchParams\(\);\n  const query = \(searchParams.get\('q'\) \|\| ''\)\.toLowerCase\(\);\n  const \[searchParams\] = useSearchParams\(\);/, "const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();");

  // Fix multiple declarations by just doing a crude unique split
  // Or just rewrite the files properly
  fs.writeFileSync(file, content, 'utf-8');
}

const menuPath = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
const invPath = path.join(__dirname, 'src', 'inventory', 'Inventory.jsx');

deduplicate(menuPath);
deduplicate(invPath);

// Wait, the build error says:
// Menu.jsx:142  `const [searchParams] = useSearchParams();`
// Menu.jsx:145  `const [searchParams, setSearchParams] = useSearchParams();`
// This means Menu.jsx ALREADY had `useSearchParams` before my script!