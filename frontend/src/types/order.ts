// src/types/order.ts
import type { CarritoItem } from "./cart";

export type MetodoPago = "Efectivo" | "Mercado Pago" | "Cuenta DNI" | "Naranja X";

export type ZonaResultado =
    | "Ensenada"
    | "El Dique"
    | "Punta Lara hasta Hospital Municipal"
    | "Fuera de zona";

export interface DatosEntrega {
    direccionOriginal: string;
    zona: ZonaResultado;
    puntoEncuentro?: string;
    direccionValidada: boolean;
}

export interface Pedido {
    numeroPedido: number;
    fechaHora: string;
    estado: "Pendiente";
    items: CarritoItem[];
    total: number;
    entrega: DatosEntrega;
    metodoPago: MetodoPago;
}