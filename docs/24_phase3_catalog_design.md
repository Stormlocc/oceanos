# Resultado de fase 3 — catálogo y provenance

Fecha: 25 de septiembre de 2026. Estado: **diseño documental completado**. No se creó la base de datos ni se implementaron clientes, SQL o pipeline. No se consultaron adquisiciones ni se descargaron escenas en esta fase.

## Decisiones

- SQLite será el único catálogo. Metadata seleccionada en campos JSON; archivos científicos y de ejecución fuera de la base, referenciados por ruta.
- Seis tablas: consultas, versiones_producto, observaciones, ejecuciones, artefactos y eventos.
- Cada intento de consulta queda registrado, incluso vacío, fallido o incompleto. Una consulta terminada no equivale a completitud demostrada.
- Separar adquisición física, producto publicado, representación de entrada y snapshot de metadata. No deduplicar por fecha ni exigir que SAFE y Zarr tengan hashes idénticos.
- Nueva baseline o contenido comparable cambiado implica reprocesar y conservar historial. Cambios administrativos no disparan ciencia por sí solos.
- Antes de adquirir nuevamente, buscar un L2R válido y compatible con las dependencias del producto nuevo; registrar derivación y padre.
- Usar una clave previa de trabajo y un hash posterior de provenance real; no fingir conocer de antemano auxiliares resueltos durante ejecución.
- Mantener estado de validación separado de limpieza. Un fallo limpiando no repite AC; un fallo procesando no se transforma en éxito por eliminar temporales.

## Límite de ACOLITE que requiere adaptación mínima

La API CDSE auditada recibe metadata que no devuelve. Se define para la futura implementación una extensión opcional y compatible de su retorno que exponga campos seleccionados y evidencia de estado/completitud; no un cliente CDSE nuevo. El parche, si se aplica, tendrá revisión/hash y tests. No se modificó ACOLITE en esta fase.

## Revisión del diseño

Se revisaron documentalmente doce casos de aceptación: repetición, duplicados, revisiones, URL temporal, Zarr no equivalente, derivación L2R, producto no soportado, consulta fallida/vacía, fronteras temporales, interrupción, archivo ausente y limpieza fallida. No son tests ejecutados: se implementarán cuando exista código autorizado.

[Diseño completo, campos y reglas](16_catalog_provenance.md).

## Siguiente fase

**Fase 4: configuración científica del AOI**, pendiente de orden explícita. Resolverá productos finales —incluido el requisito OC4 no soportado—, máscaras, revisión ACOLITE de ejecución y grilla/proyección. La selección de fuente definitiva sigue en fase 5 y el procesamiento real en fase 6.
