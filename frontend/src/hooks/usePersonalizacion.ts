import { useState, useMemo } from "react";
import type { IngredienteBase, IngredienteOpcional, PersonalizacionPayload } from "../types/product";

export function usePersonalizacion(
  ingredientesBaseIniciales: IngredienteBase[],
  ingredientesOpcionalesIniciales: IngredienteOpcional[]
) {
  const [baseEstados, setBaseEstados] = useState(() =>
    ingredientesBaseIniciales.map((ingrediente) => ({
      ingrediente,
      incluido: true,
    }))
  );

  const [opcionalesEstados, setOpcionalesEstados] = useState(() =>
    ingredientesOpcionalesIniciales.map((ingrediente) => ({
      ingrediente,
      seleccionado: false,
    }))
  );

  const toggleBase = (id: string) => {
    setBaseEstados((prev) =>
      prev.map((item) =>
        item.ingrediente.id === id ? { ...item, incluido: !item.incluido } : item
      )
    );
  };

  const toggleOpcional = (id: string) => {
    setOpcionalesEstados((prev) =>
      prev.map((item) =>
        item.ingrediente.id === id ? { ...item, seleccionado: !item.seleccionado } : item
      )
    );
  };

  const costoExtra = useMemo(() => {
    return opcionalesEstados.reduce((acc, item) => {
      return item.seleccionado ? acc + item.ingrediente.costoAdicional : acc;
    }, 0);
  }, [opcionalesEstados]);

  const payload: PersonalizacionPayload = useMemo(() => {
    const ingredientesQuitados = baseEstados
      .filter((item) => !item.incluido)
      .map((item) => item.ingrediente.id);

    const agregadosSeleccionados = opcionalesEstados
      .filter((item) => item.seleccionado)
      .map((item) => item.ingrediente.id);

    return {
      ingredientesQuitados,
      agregadosSeleccionados,
    };
  }, [baseEstados, opcionalesEstados]);

  return {
    baseEstados,
    opcionalesEstados,
    toggleBase,
    toggleOpcional,
    costoExtra,
    payload,
  };
}
