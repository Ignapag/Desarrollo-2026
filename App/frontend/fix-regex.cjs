const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let content = fs.readFileSync(file, 'utf-8');

// Just aggressively replace any broken LaTipicaBurger.jpg string
content = content.replace(/LaT\uFFFDpicaBurger\.jpg/g, 'LaTipicaBurger.jpg');
content = content.replace(/LaT.picaBurger\.jpg/g, 'LaTipicaBurger.jpg');

fs.writeFileSync(file, content, 'utf-8');