const fs = require("fs");
const path = require("path");

const kitchenPath = path.join(__dirname, "src", "kitchen", "Kitchen.jsx");
let content = fs.readFileSync(kitchenPath, "utf-8");

if (!content.includes("AudioContext")) {
  const useEffectAudio = `
  // Efecto de sonido para nuevos pedidos
  useEffect(() => {
    const pendingOrders = orders.filter(o => o.status === 'pendiente' || o.status === 'en_preparacion').length;
    // Guardamos el length anterior en un ref o similar, pero simplificado: si hay ordenes, beep
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
      } catch (e) {
        // Ignorar si el navegador bloquea el autoplay
      }
    }
  }, [orders]);
`;
  content = content.replace("export default function Kitchen() {", "export default function Kitchen() {\n" + useEffectAudio);
  content = content.replace("import { useState } from 'react';", "import { useState, useEffect } from 'react';");
  fs.writeFileSync(kitchenPath, content, "utf-8");
}