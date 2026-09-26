const fs = require('fs');
const path = require('path');

const cartPath = path.join(__dirname, 'src', 'components', 'client', 'CartDrawer.jsx');
let content = fs.readFileSync(cartPath, 'utf-8');

// Add useAuth import
content = content.replace("import { useState } from 'react';", "import { useState } from 'react';\nimport { useAuth } from '../../auth/AuthContext';");

// Inside CartDrawer, grab the user
content = content.replace("export default function CartDrawer({ isOpen, onClose }) {", "export default function CartDrawer({ isOpen, onClose }) {\n  const { user } = useAuth();");

// Replace the payload client name
content = content.replace("client: 'Cliente Monu',", "client: user?.name || 'Cliente sin cuenta',");

fs.writeFileSync(cartPath, content, 'utf-8');
console.log("CartDrawer updated with user name");