const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'fulfillment', 'Orders.jsx');
let content = fs.readFileSync(file, 'utf-8');

// Use regex to avoid \r\n issues
content = content.replace(/export default function Orders\(\) \{[\s\S]*?const { orders } = state;/, 
  "export default function Orders() {\n  const { state, dispatch } = useData();\n  const { orders } = state;\n  const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
);

fs.writeFileSync(file, content, 'utf-8');