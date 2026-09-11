// src/services/pedidos.ts
import type { CarritoItem } from "../types/cart";
import type { DatosEntrega, MetodoPago, Pedido } from "../types/order";

interface RegistrarPedidoInput {
    items: CarritoItem[];
    total: number;
    entrega: DatosEntrega;
    metodoPago: MetodoPago;
}

let contadorPedidosMock = 1041;

// TODO backend: reemplazar el cuerpo de esta función por un POST a la API
// de FastAPI (ej. POST /pedidos) cuando esté disponible. La firma
// (parámetros de entrada y el Pedido que devuelve) ya sigue la forma de
// "Datos del pedido" de CU_PED_02, así que el resto de la app no debería
// necesitar cambios cuando se conecte el backend real.
export async function registrarPedido(input: RegistrarPedidoInput): Promise<Pedido> {
    await new Promise((resolve) => setTimeout(resolve, 700));

    contadorPedidosMock += 1;

    return {
    numeroPedido: contadorPedidosMock,
    fechaHora: new Date().toISOString(),
    estado: "Pendiente",
    ...input,
    };
}