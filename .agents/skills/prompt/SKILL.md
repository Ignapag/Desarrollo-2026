---
name: prompt
description: Convierte ideas o pedidos sobre Monu Burger en prompts chicos, medianos o grandes, listos para copiar. Usar cuando el usuario pida redactar, mejorar o dividir un prompt; no para ejecutar la tarea descrita.
---

# Crear prompts para Monu Burger

Transformá lo que el usuario quiere hacer en un pedido claro y verificable. Respondé en español rioplatense. Entregá el prompt listo para copiar; no implementes la tarea que el prompt describe.

## Elegir tamaño y alcance

- **Chico:** un problema localizado y de bajo riesgo, con comportamiento actual y esperado conocidos.
- **Mediano:** una funcionalidad acotada, varios archivos o casos normales y límite que necesitan criterios de aceptación.
- **Grande:** varios módulos, contratos, persistencia, seguridad, pagos, caja, stock o concurrencia. Clasificá por riesgo y dependencias, no por cantidad de palabras.
- Si el pedido reúne objetivos independientes con validaciones propias, recomendá dividirlo y entregá prompts separados en orden de dependencia. Si las partes forman un flujo inseparable, usá un solo prompt grande por etapas. Explicá la división en una frase.

En el prompt generado incluí siempre una instrucción explícita para seguir `AGENTS.md` y elegir las skills pertinentes. Si el prompt pide implementación, conservá la indicación de revisión independiente o delegación proporcional al riesgo. `AGENTS.md` decide modelos y agentes disponibles; no fijes nombres o modelos salvo que el usuario los pida. No inventes archivos, decisiones, pasos de reproducción ni criterios ausentes: usá un marcador breve entre corchetes cuando el dato sea imprescindible. Si la intención es investigar, diseñar o revisar, adaptá los verbos de la plantilla y respetá ese límite.

Si estás en el repositorio, consultá `AGENTS.md` y las referencias dirigidas que hagan falta para evitar contradicciones. No inspecciones ni modifiques código por el solo hecho de redactar un prompt. Conservá restricciones y terminología que dio el usuario.

## Plantillas base

Adaptá el contenido a la tarea concreta y quitá campos innecesarios. No entregues las tres plantillas si basta una.

### Prompt chico

```text
Corregí [problema concreto] en [pantalla o módulo].
Actualmente pasa [qué ocurre] al hacer [pasos para reproducirlo].
Debería pasar [resultado verificable].
Mantené [restricción importante]. Seguí AGENTS.md, elegí las skills pertinentes, implementá y verificá lo afectado.
```

### Prompt mediano

```text
Implementá [funcionalidad] en [pantalla o módulo].
Objetivo: [qué podrá hacer el usuario].
Criterios de aceptación:
- [caso normal y resultado esperado].
- [error o caso límite y resultado esperado].
Límites: [compatibilidad, diseño o áreas que deben conservarse].
Seguí AGENTS.md y elegí las skills pertinentes. Revisá el código existente, armá un plan breve, implementá y probá. Pedí una revisión independiente cuando el riesgo lo justifique.
Entregá cambios, validaciones y cualquier limitación pendiente.
```

### Prompt grande

```text
Quiero implementar [funcionalidad completa] en Monu Burger.
Problema y objetivo: [para quién y qué debe mejorar].
Alcance: [comportamientos incluidos y módulos afectados, si se conocen].
Fuera de alcance: [lo que queda para otra tarea].
Criterios de aceptación:
- [flujo principal completo].
- [errores, reintentos o concurrencia relevantes].
- [compatibilidad y restricciones de datos].
Referencias: [diseño, documentos o ejemplos concretos].
Seguí AGENTS.md y elegí las skills pertinentes. Primero contrastá el pedido con el código y prepará un plan por etapas. Después implementalo hasta cumplir los criterios. Delegá solo subtareas independientes, con archivos asignados y modelos proporcionales. Revisá la integración final.
Preguntame solo por decisiones bloqueantes; resolvé los detalles técnicos con las convenciones del proyecto. Actualizá documentación y changelog cuando corresponda.
```

Indicá fuera del bloque cuál tamaño elegiste. Cuando propongas varios prompts, numeralos y explicitá dependencias; cada bloque debe poder usarse por separado.
