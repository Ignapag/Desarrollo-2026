const fractions = { '¼': '1/4', '½': '1/2', '¾': '3/4', '⅓': '1/3', '⅔': '2/3', '⅛': '1/8' };
const invalid = (error) => ({ valid: false, error });

export function parseRecipeQuantity(value) {
  const raw = String(value ?? '').trim();
  const text = fractions[raw] || raw;
  let scaled;
  let approximate = false;
  const fraction = /^(\d{1,12})\s*\/\s*(\d{1,12})$/.exec(text);
  if (fraction) {
    const numerator = BigInt(fraction[1]) * 1000n;
    const denominator = BigInt(fraction[2]);
    if (!denominator) return invalid('El denominador debe ser mayor que cero.');
    approximate = numerator % denominator !== 0n;
    scaled = (numerator + denominator / 2n) / denominator;
  } else if (/^\d{1,12}(?:[.,]\d{1,3})?$/.test(text)) {
    const [integer, decimals = ''] = text.replace(',', '.').split('.');
    scaled = BigInt(integer) * 1000n + BigInt(decimals.padEnd(3, '0'));
  } else return invalid('Usá una cantidad como 0,25 o una fracción como 1/4. Máximo 3 decimales.');
  if (scaled < 1n) return invalid('La cantidad mínima es 0,001 en la unidad del ingrediente.');
  if (scaled > 999999999999n) return invalid('La cantidad supera el máximo permitido.');
  const decimal = String(scaled % 1000n).padStart(3, '0').replace(/0+$/, '');
  const amount = `${scaled / 1000n}${decimal ? `.${decimal}` : ''}`;
  return { valid: true, amount, display: amount.replace('.', ','), approximate, error: '' };
}

export function newRecipe() {
  return { ingredients: [{ key: crypto.randomUUID(), ingredientId: '', quantity: '1', quantities: [] }], variants: [] };
}

export function recipeFromApi(data) {
  return {
    ingredients: data.ingredientes.map((row) => ({
      key: `ingredient-${row.ingrediente_id}`, ingredientId: String(row.ingrediente_id),
      quantity: String(row.cantidad_requerida),
      esBase: row.es_base !== false,
      variantBase: data.variantes.map((variant) => variant.ingredientes.find((item) => item.ingrediente_id === row.ingrediente_id)?.es_base ?? (row.es_base !== false)),
      quantities: data.variantes.map((variant) => String(variant.ingredientes.find((item) => item.ingrediente_id === row.ingrediente_id)?.cantidad_requerida ?? row.cantidad_requerida)),
    })),
    variants: data.variantes.map((row) => ({ name: row.nombre, price: String(row.precio) })),
  };
}

export function serializeRecipe(recipe, { includePrices = false } = {}) {
  if (!recipe.ingredients.length) throw Error('Agregá al menos un ingrediente a la receta.');
  const ids = new Set();
  for (const row of recipe.ingredients) {
    const id = Number(row.ingredientId);
    if (!Number.isSafeInteger(id) || id <= 0) throw Error('Seleccioná un ingrediente en cada fila.');
    if (ids.has(id)) throw Error('No se puede repetir un ingrediente en la receta.');
    ids.add(id);
  }
  const rows = (variantIndex) => recipe.ingredients.map((row) => {
    const parsed = parseRecipeQuantity(variantIndex == null ? row.quantity : row.quantities[variantIndex]);
    if (!parsed.valid) throw Error(`Revisá la cantidad del ingrediente: ${parsed.error}`);
    return { ingrediente_id: Number(row.ingredientId), cantidad_requerida: parsed.amount, es_base: variantIndex == null ? row.esBase !== false : row.variantBase?.[variantIndex] ?? (row.esBase !== false) };
  });
  const names = new Set();
  const variants = recipe.variants.map((variant, index) => {
    const name = variant.name.trim();
    if (!name || name.length > 60 || names.has(name.toLocaleLowerCase('es'))) throw Error('Cada variante debe tener un nombre distinto, de hasta 60 caracteres.');
    names.add(name.toLocaleLowerCase('es'));
    const result = { nombre: name, ingredientes: rows(index) };
    if (includePrices) {
      const price = String(variant.price).trim().replace(',', '.');
      if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(price) || Number(price) <= 0) throw Error(`Completá un precio válido para ${name}.`);
      result.precio = price;
    }
    return result;
  });
  return { ingredientes: variants[0]?.ingredientes || rows(), variantes: variants };
}

export const recipeUnit = (unit) => ({ UNIDAD: 'unidad', GR: 'g', KG: 'kg', LT: 'l', ML: 'ml' })[unit] || unit || 'unidad';
