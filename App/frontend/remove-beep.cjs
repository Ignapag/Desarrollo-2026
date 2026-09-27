const fs = require('fs');
const path = require('path');
const kitchenPath = path.join(__dirname, 'src', 'kitchen', 'Kitchen.jsx');
let kitchen = fs.readFileSync(kitchenPath, 'utf-8');

const audioEffect = `  useEffect(() => {
    const pendingOrders = orders.filter(o => o.status === 'pendiente' || o.status === 'en_preparacion').length;
    if (pendingOrders > 0) {
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
        gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.15);
      } catch (e) {}
    }
  }, [orders]);`;

kitchen = kitchen.replace(audioEffect, '');
fs.writeFileSync(kitchenPath, kitchen, 'utf-8');
console.log("Beep removed from Kitchen.jsx");