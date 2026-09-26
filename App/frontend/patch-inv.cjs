const fs = require('fs');
const path = require('path');

// Inventory
let invFile = path.join(__dirname, 'src', 'inventory', 'Inventory.jsx');
let inv = fs.readFileSync(invFile, 'utf-8');
inv = inv.replace(
  "import { useSearchParams } from 'react-router-dom';",
  "import { useSearchParams } from 'react-router-dom';\nimport { toast } from 'sonner';"
);
inv = inv.replace(
  "setIsModalOpen(false);\n  };",
  "setIsModalOpen(false);\n    toast.success('Insumo guardado', { description: newItem.name });\n  };"
);
fs.writeFileSync(invFile, inv, 'utf-8');

// Orders
let ordFile = path.join(__dirname, 'src', 'fulfillment', 'Orders.jsx');
let ord = fs.readFileSync(ordFile, 'utf-8');
ord = ord.replace(
  "import { useSearchParams } from 'react-router-dom';",
  "import { useSearchParams } from 'react-router-dom';\nimport { toast } from 'sonner';"
);
ord = ord.replace(
  "const updateStatus = (id, newStatus) => {\n    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: newStatus } });\n  };",
  "const updateStatus = (id, newStatus) => {\n    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: newStatus } });\n    toast.success(`Pedido #${id} actualizado a ${newStatus.replace('_', ' ')}`);\n  };"
);
fs.writeFileSync(ordFile, ord, 'utf-8');

// DeliveryPanel
let dpFile = path.join(__dirname, 'src', 'fulfillment', 'DeliveryPanel.jsx');
let dp = fs.readFileSync(dpFile, 'utf-8');
dp = dp.replace(
  "import { MapPin, Phone, CheckCircle, Navigation } from 'lucide-react';",
  "import { MapPin, Phone, CheckCircle, Navigation } from 'lucide-react';\nimport { toast } from 'sonner';"
);
dp = dp.replace(
  "const markAsDelivered = (id) => {\n    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: 'entregado' } });\n  };",
  "const markAsDelivered = (id) => {\n    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: 'entregado' } });\n    toast.success(`¡Pedido #${id} entregado!`, { description: 'Buen trabajo' });\n  };"
);
fs.writeFileSync(dpFile, dp, 'utf-8');
