// src/types/product.ts

export type CategoriaProducto =
  | "Hamburguesas"
  | "Acompañamientos"
  | "Postres"
  | "Bebidas";

export interface IngredienteBase {
  id: string;
  nombre: string;
  enStock: boolean;
}

export interface IngredienteOpcional {
  id: string;
  nombre: string;
  costoAdicional: number; // >= 0, puede ser 0
  activo: boolean;
  enStock: boolean;
}

export interface Producto {
  id: string;
  nombre: string;
  descripcion: string;
  precioBase: number;
  imagenRepresentativa: string;
  categoria: CategoriaProducto;
  ordenVisualizacion: number;
  ingredientesBase: IngredienteBase[];
  ingredientesOpcionales: IngredienteOpcional[];
  activo: boolean;
}

// Estado interno del hook para ingredientes opcionales
// Empiezan todos en false (no seleccionados)
export interface IngredienteOpcionalEstado {
  ingrediente: IngredienteOpcional;
  seleccionado: boolean;
}

// Estado interno del hook para ingredientes base
// Empiezan todos en true (incluidos); el usuario puede destildar para quitar
export interface IngredienteBaseEstado {
  ingrediente: IngredienteBase;
  incluido: boolean;
}

// Lo que se envía al backend al registrar el pedido (CU_PED_02)
export interface PersonalizacionPayload {
  // Ingredientes opcionales que el cliente agregó, con su costo
  opcionalesAgregados: { ingredienteId: string; costoAdicional: number }[];
  // IDs de ingredientes base que el cliente pidió quitar
  baseQuitados: string[];
}