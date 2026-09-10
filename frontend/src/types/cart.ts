// src/types/cart.ts
import type { Producto, PersonalizacionPayload } from "./product";

export interface CarritoItem {
    id: string;
    producto: Producto;
    cantidad: number;
    personalizacion: PersonalizacionPayload;
    precioUnitario: number;
}
