const fs = require('fs');
const path = require('path');

const dashPath = path.join(__dirname, 'src', 'management', 'DashboardLayout.jsx');
let dash = fs.readFileSync(dashPath, 'utf-8');

dash = dash.replace(
  "import { Outlet, NavLink } from 'react-router-dom';",
  "import { Outlet, NavLink, useSearchParams } from 'react-router-dom';"
);

dash = dash.replace(
  "const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);",
  "const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);\n  const [searchParams, setSearchParams] = useSearchParams();\n  const searchQuery = searchParams.get('q') || '';\n  \n  const handleSearch = (e) => {\n    if (e.target.value) {\n      setSearchParams({ q: e.target.value });\n    } else {\n      setSearchParams({});\n    }\n  };"
);

// Replace inputs
dash = dash.replace(
  `type="text" \n                placeholder="Buscar..." \n                className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-full py-2 pl-10 pr-4 text-sm font-bold focus:outline-none focus:border-monu-green transition-colors"`,
  `type="text" \n                value={searchQuery}\n                onChange={handleSearch}\n                placeholder="Buscar (Pedidos, Clientes, Menú)..." \n                className="w-full bg-monu-cream/50 border border-monu-green/10 rounded-full py-2 pl-10 pr-4 text-sm font-bold focus:outline-none focus:border-monu-green transition-colors"`
);

fs.writeFileSync(dashPath, dash, 'utf-8');


// Fix search in Orders.jsx
const ordersPath = path.join(__dirname, 'src', 'fulfillment', 'Orders.jsx');
let orders = fs.readFileSync(ordersPath, 'utf-8');
orders = orders.replace(
  "import { useData } from '../shared/store/DataContext';",
  "import { useData } from '../shared/store/DataContext';\nimport { useSearchParams } from 'react-router-dom';"
);
orders = orders.replace(
  "export default function Orders() {\n  const { state, dispatch } = useData();",
  "export default function Orders() {\n  const { state, dispatch } = useData();\n  const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
);
orders = orders.replace(
  "const updateStatus = (id, newStatus) => {",
  "const filteredOrders = state.orders.filter(o => \n    o.id.toString().includes(query) || \n    o.client.toLowerCase().includes(query) || \n    o.address.toLowerCase().includes(query)\n  );\n\n  const updateStatus = (id, newStatus) => {"
);
orders = orders.replace(
  `{state.orders.filter(o => o.status === col.id).map(order => (`,
  `{filteredOrders.filter(o => o.status === col.id).map(order => (`
);
fs.writeFileSync(ordersPath, orders, 'utf-8');


// Fix search in Catalog.jsx
const catalogPath = path.join(__dirname, 'src', 'management', 'Catalog.jsx');
let cat = fs.readFileSync(catalogPath, 'utf-8');
cat = cat.replace(
  "import { useState } from 'react';",
  "import { useState } from 'react';\nimport { useSearchParams } from 'react-router-dom';"
);
cat = cat.replace(
  "export default function Catalog() {",
  "export default function Catalog() {\n  const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
);
cat = cat.replace(
  "{state.catalog.map(product => (",
  "{state.catalog.filter(p => p.name.toLowerCase().includes(query) || p.category.toLowerCase().includes(query)).map(product => ("
);
fs.writeFileSync(catalogPath, cat, 'utf-8');


// Fix search in Inventory.jsx
const invPath = path.join(__dirname, 'src', 'inventory', 'Inventory.jsx');
let inv = fs.readFileSync(invPath, 'utf-8');
inv = inv.replace(
  "import { useData } from '../shared/store/DataContext';",
  "import { useData } from '../shared/store/DataContext';\nimport { useSearchParams } from 'react-router-dom';"
);
inv = inv.replace(
  "export default function Inventory() {",
  "export default function Inventory() {\n  const [searchParams] = useSearchParams();\n  const query = (searchParams.get('q') || '').toLowerCase();"
);
inv = inv.replace(
  "{state.inventory.map(item => (",
  "{state.inventory.filter(i => i.name.toLowerCase().includes(query) || i.category.toLowerCase().includes(query)).map(item => ("
);
fs.writeFileSync(invPath, inv, 'utf-8');

console.log("Admin Search fixed across all panels.");