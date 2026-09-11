// src/types/order.ts
import type { CarritoItem } from "./cart";

export type MetodoPago = "Efectivo" | "Mercado Pago" | "Cuenta DNI" | "Naranja X";

export type ZonaResultado =
    | "Ensenada"
    | "El Dique"
    | "Punta Lara hasta Hospital Municipal"
    | "Fuera de zona";

// Secuencia de estados operativos según CU_PED_04 (Pendiente -> En preparación
// -> Listo son los que gestiona el módulo de Pedidos; En camino y Entregado
// los administra Delivery).
export type EstadoPedido = "Pendiente" | "En preparación" | "Listo" | "En camino" | "Entregado";

export interface HistorialEstado {
    estado: EstadoPedido;
    fechaHora: string;
}

export interface DatosEntrega {
    direccionOriginal: string;
    zona: ZonaResultado;
    puntoEncuentro?: string;
    direccionValidada: boolean;
}

export interface Pedido {
    numeroPedido: number;
    fechaHora: string;
    estado: EstadoPedido;
    historial: HistorialEstado[];
    items: CarritoItem[];
    total: number;
    entrega: DatosEntrega;
    metodoPago: MetodoPago;
}