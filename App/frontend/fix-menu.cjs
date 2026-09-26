const fs = require("fs");
const path = require("path");

const menuPath = path.join(__dirname, "src", "ordering", "Menu.jsx");
let content = fs.readFileSync(menuPath, "utf-8");

content = content.replace(/id: \$\{product\.id\}-\$\{variant\.name\},/g, "id: `${product.id}-${variant.name}`,");
content = content.replace(/name: \$\{product\.name\} \(\),/g, "name: `${product.name} (${variant.name})`,");

fs.writeFileSync(menuPath, content, "utf-8");