// src/utils/zonas.ts
import type { ZonaResultado } from "../types/order";

// TODO backend: hoy esto es un match de texto simple. Cuando exista el
// módulo de Delivery/backend, reemplazar por la consulta real de zonas
// configuradas (CU_DEL_01), sin cambiar la firma de la función.
export function validarZonaCobertura(direccion: string): ZonaResultado {
    const normalizado = direccion.trim().toLowerCase();

    if (normalizado.length === 0) return "Fuera de zona";
    if (normalizado.includes("ensenada")) return "Ensenada";
    if (normalizado.includes("dique")) return "El Dique";
    if (normalizado.includes("punta lara")) return "Punta Lara";

    return "Fuera de zona";
}