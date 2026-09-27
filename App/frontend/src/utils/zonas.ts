// src/utils/zonas.ts
import type { ZonaResultado } from "../types/order";

export interface ZonaCobertura {
    nombre: ZonaResultado;
  // Palabras que, si aparecen en la dirección, la ubican en esta zona.
    palabrasClave: string[];
}

// Zonas de cobertura vigentes según CU_DEL_01. Para sumar una zona nueva
// (por ejemplo si el dueño amplía la cobertura), alcanza con agregar un
// objeto acá — no hace falta tocar la lógica de validarZonaCobertura.
//
// TODO backend/Delivery: cuando exista el módulo real, esta lista debería
// venir del backend (configurable por el Dueño/Supervisor) en vez de estar
// hardcodeada acá. La forma de ZonaCobertura ya está pensada para eso.
export const ZONAS_COBERTURA: ZonaCobertura[] = [
    { nombre: "Ensenada", palabrasClave: ["ensenada"] },
    { nombre: "El Dique", palabrasClave: ["dique", "el dique"] },
    {
    nombre: "Punta Lara hasta Hospital Municipal",
    palabrasClave: ["punta lara", "hospital municipal"],
    },
];

// CU_DEL_01, paso 2-3: normaliza el texto y determina la zona.
export function validarZonaCobertura(direccion: string): ZonaResultado {
    const normalizado = direccion.trim().toLowerCase();

    if (normalizado.length === 0) return "Fuera de zona";

    const zonaEncontrada = ZONAS_COBERTURA.find((zona) =>
    zona.palabrasClave.some((palabra) => normalizado.includes(palabra))
    );

    return zonaEncontrada ? zonaEncontrada.nombre : "Fuera de zona";
}