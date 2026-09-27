const fs = require('fs');
const path = require('path');

const ctxPath = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let ctx = fs.readFileSync(ctxPath, 'utf-8');

ctx = ctx.replace(/Categor.a/g, 'Categoría');
ctx = ctx.replace(/Prote.nas/g, 'Proteínas');
ctx = ctx.replace(/L.cteos/g, 'Lácteos');
ctx = ctx.replace(/Panader.a/g, 'Panadería');
ctx = ctx.replace(/Acompa.amientos/g, 'Acompañamientos');
ctx = ctx.replace(/Monufusi.n/g, 'Monufusión');
ctx = ctx.replace(/T.pica/g, 'Típica');
ctx = ctx.replace(/R.cula/g, 'Rúcula');
ctx = ctx.replace(/Medall.n/g, 'Medallón');
ctx = ctx.replace(/Porci.n/g, 'Porción');

fs.writeFileSync(ctxPath, ctx, 'utf-8');
console.log("Fixed DataContext encoding");