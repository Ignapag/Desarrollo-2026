const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'auth', 'Login.jsx');
let content = fs.readFileSync(file, 'utf-8');

content = content.replace(
  "import { useNavigate } from 'react-router-dom';",
  "import { useNavigate } from 'react-router-dom';\nimport { toast } from 'sonner';"
);

// Remove local error state UI
content = content.replace(/\{errorMsg && \([\s\S]*?\}\)/, '');
content = content.replace(/\{successMsg && \([\s\S]*?\}\)/, '');

// Replace logic
content = content.replace(
  /if \(!email\) return setErrorMsg\("Ingresá tu correo electrónico"\);/g,
  "if (!email) return toast.error('Ingresá tu correo electrónico');"
);
content = content.replace(
  /setSuccessMsg\("Si el correo existe, te enviamos un enlace para restablecer tu contraseña."\);/g,
  "toast.success('Correo enviado', { description: 'Revisá tu bandeja de entrada o spam.' });"
);
content = content.replace(
  /if \(!name \|\| !email \|\| !password\) return setErrorMsg\("Completá todos los campos"\);/g,
  "if (!name || !email || !password) return toast.error('Completá todos los campos');"
);
content = content.replace(
  /if \(password\.length < 6\) return setErrorMsg\("La contraseña debe tener al menos 6 caracteres"\);/g,
  "if (password.length < 6) return toast.error('La contraseña debe tener al menos 6 caracteres');"
);
content = content.replace(
  /if \(res\?\.error\) setErrorMsg\(res\.error\);/g,
  "if (res?.error) toast.error(res.error); else toast.success('¡Bienvenido!');"
);
content = content.replace(
  /if \(!email \|\| !password\) return setErrorMsg\("Completá todos los campos"\);/g,
  "if (!email || !password) return toast.error('Completá todos los campos');"
);

fs.writeFileSync(file, content, 'utf-8');