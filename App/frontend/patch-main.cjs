const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'main.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "import App from './App.jsx'",
  "import App from './App.jsx'\nimport { Toaster } from 'sonner';"
);

content = content.replace(
  "<App />",
  "<Toaster richColors position=\"bottom-center\" />\n          <App />"
);

fs.writeFileSync(file, content, 'utf-8');