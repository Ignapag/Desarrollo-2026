const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let lines = fs.readFileSync(file, 'utf-8').split('\n');
let newLines = [];
let queryCount = 0;
for(let line of lines) {
  if(line.includes('const query = ')) {
    queryCount++;
    if(queryCount > 1) continue;
  }
  newLines.push(line);
}
fs.writeFileSync(file, newLines.join('\n'), 'utf-8');