const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'fulfillment', 'Orders.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "export default function Orders() {\n  const { state, dispatch } = useData();\n  const { orders } = state;",
  "export default function Orders() {\n  const { state, dispatch } = useData();\n  const { orders } = state;\n  const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
);

content = content.replace(
  "o.client.toLowerCase().includes(query) || \n    o.address.toLowerCase().includes(query)",
  "(o.client?.toLowerCase() || '').includes(query) || \n    (o.address?.toLowerCase() || '').includes(query)"
);

fs.writeFileSync(file, content, 'utf-8');