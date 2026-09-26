const fs = require('fs');
const path = require('path');

const ctxPath = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let content = fs.readFileSync(ctxPath, 'utf-8');

// Fix image for La Tipica
content = content.replace("name: 'La Típica', description: 'Ingredientes: Carne, cheddar, tomate, lechuga y mayonesa.', variants: [{name: 'Simple', price: 11000}, {name: 'Doble', price: 13500}, {name: 'Triple', price: 15500}], category: 'Nuestras Burgers', image: null", "name: 'La Típica', description: 'Ingredientes: Carne, cheddar, tomate, lechuga y mayonesa.', variants: [{name: 'Simple', price: 11000}, {name: 'Doble', price: 13500}, {name: 'Triple', price: 15500}], category: 'Nuestras Burgers', image: '/menu/LaTipicaBurger.jpg'");

fs.writeFileSync(ctxPath, content, 'utf-8');
console.log("Fixed La Tipica image in DataContext");