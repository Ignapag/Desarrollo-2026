const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'components', 'client', 'CartDrawer.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "import { useNavigate } from 'react-router-dom';",
  "import { useNavigate } from 'react-router-dom';\nimport { toast } from 'sonner';"
);

// Remove the `isSuccess` state completely.
content = content.replace(
  "const [isSuccess, setIsSuccess] = useState(false);",
  ""
);

// Replace the placeOrder logic
const oldPlace = `setIsSuccess(true);
      setTimeout(() => {
        setIsSuccess(false);
        onClose();
        navigate('/menu');
      }, 3000);`;
const newPlace = `toast.success('¡Pedido Confirmado!', { description: 'Tu pedido ya entró a la cocina. ¡Preparate para disfrutar!' });
      onClose();
      navigate('/menu');`;

content = content.replace(oldPlace, newPlace);

// Remove the bulky success UI
content = content.replace(
  /\{isSuccess \? \([\s\S]*?\) : cart\.length === 0 \? \(/,
  "{cart.length === 0 ? ("
);

// Update !isSuccess block at the bottom
content = content.replace(
  "{!isSuccess && cart.length > 0 && (",
  "{cart.length > 0 && ("
);

fs.writeFileSync(file, content, 'utf-8');