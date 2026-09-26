const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "export default function Menu() {\n  const query = (searchParams.get('q') || '').toLowerCase();\n  const { state, dispatch } = useData();\n  const [searchParams, setSearchParams] = useSearchParams();",
  "export default function Menu() {\n  const { state, dispatch } = useData();\n  const [searchParams, setSearchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
);

fs.writeFileSync(file, content, 'utf-8');