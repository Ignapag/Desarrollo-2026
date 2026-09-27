const fs = require('fs');
const path = require('path');

function cleanMenu(file) {
  let lines = fs.readFileSync(file, 'utf-8').split('\n');
  let newLines = [];
  let importCount = 0;
  
  for(let i = 0; i < lines.length; i++) {
    let line = lines[i];
    
    if (line.includes('import { useSearchParams }')) {
      importCount++;
      if (importCount > 1) continue; // skip duplicates
    }
    
    if (line.includes('const [searchParams] = useSearchParams();')) {
      // If we are in Menu.jsx, we want to KEEP it only if it's the first time
      // But actually Menu.jsx has `const [searchParams, setSearchParams] = useSearchParams();` below it.
      // So we skip this one if it's EXACTLY `const [searchParams] = useSearchParams();`
      continue;
    }
    
    newLines.push(line);
  }
  
  let content = newLines.join('\n');
  
  // Wait, in Menu.jsx, if I removed `const [searchParams] = useSearchParams();`, I still need the query variable!
  // I'll add the query variable back after the real `const [searchParams, setSearchParams] = useSearchParams();`
  content = content.replace(
    "const [searchParams, setSearchParams] = useSearchParams();",
    "const [searchParams, setSearchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
  );
  
  fs.writeFileSync(file, content, 'utf-8');
}

function cleanInv(file) {
  let lines = fs.readFileSync(file, 'utf-8').split('\n');
  let newLines = [];
  let importCount = 0;
  let spCount = 0;
  
  for(let i = 0; i < lines.length; i++) {
    let line = lines[i];
    
    if (line.includes('import { useSearchParams }')) {
      importCount++;
      if (importCount > 1) continue;
    }
    
    if (line.includes('const [searchParams] = useSearchParams();')) {
      spCount++;
      if (spCount > 1) continue;
    }
    
    newLines.push(line);
  }
  
  let content = newLines.join('\n');
  
  // Make sure query is defined
  if (!content.includes('const query =')) {
    content = content.replace(
      "const [searchParams] = useSearchParams();",
      "const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
    );
  }
  
  fs.writeFileSync(file, content, 'utf-8');
}

cleanMenu(path.join(__dirname, 'src', 'ordering', 'Menu.jsx'));
cleanInv(path.join(__dirname, 'src', 'inventory', 'Inventory.jsx'));