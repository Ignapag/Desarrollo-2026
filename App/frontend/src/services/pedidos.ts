// src/services/pedidos.ts
import type { CarritoItem } from "../types/cart";
import type { DatosEntrega, MetodoPago, Pedido } from "../types/order";

interface RegistrarPedidoInput {
    items: CarritoItem[];
    total: number;
    entrega: DatosEntrega;
    metodoPago: MetodoPago;
}

export async function registrarPedido(input: RegistrarPedidoInput): Promise<Pedido> {
    const zona = input.entrega.zona === "Punta Lara hasta Hospital Municipal"
        ? "Punta Lara"
        : input.entrega.zona;
    const response = await fetch("/api/pedidos", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            tipo_entrega: "DELIVERY",
            direccion_nueva: {
                calle: input.entrega.direccionOriginal,
                numero: "S/N",
                localidad: zona,
                referencia: input.entrega.puntoEncuentro ?? null,
            },
            items: input.items.map((item) => ({
                producto_id: Number(item.producto.id),
                cantidad: item.cantidad,
            })),
        }),
    });
    if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.mensaje ?? "No se pudo registrar el pedido");
    }
    const creado: { numero: number; creado_en: string; estado: string } = await response.json();
    return {
        numeroPedido: creado.numero,
        fechaHora: creado.creado_en,
        estado: "PENDIENTE",
        historial: [{ estado: "PENDIENTE", fechaHora: creado.creado_en }],
        ...input,
    };
}
