# Resultado de fase 3 — catálogo y provenance

> Informe histórico. Estado vigente al 30-09-2026: diseño implementado en fase 11, SQLite v2 con seis tablas. El parche CDSE y las pruebas ya existen. La descripción de lo no implementado se refiere exclusivamente al cierre de fase 3. Rige la [política L1R/L2W y reinicio](33_retention_and_reset.md); las cifras y decisiones originales no describen la disponibilidad actual de archivos.

Fecha: 25 de septiembre de 2026. Estado: **diseño documental completado**. No se creó la base de datos ni se implementaron clientes, SQL o pipeline. No se consultaron adquisiciones ni se descargaron escenas en esta fase.

## Decisiones

- SQLite será el único catálogo. Metadata seleccionada en campos JSON; archivos científicos y de ejecución fuera de la base, referenciados por ruta.
- Seis tablas: consultas, versiones_producto, observaciones, ejecuciones, artefactos y eventos.
- Cada intento de consulta queda registrado, incluso vacío, fallido o incompleto. Una consulta terminada no equivale a completitud demostrada.
- Separar adquisición física, producto publicado, representación de entrada y snapshot de metadata. No deduplicar por fecha ni exigir que SAFE y Zarr tengan hashes idénticos.
- Nueva baseline o contenido comparable cambiado implica reprocesar y conservar historial. Cambios administrativos no disparan ciencia por sí solos.
- Antes de adquirir nuevamente, buscar un L1R válido y compatible con las dependencias del producto nuevo; registrar derivación y padre.
- Usar una clave previa de trabajo y un hash posterior de provenance real; no fingir conocer de antemano auxiliares resueltos durante ejecución.
- Mantener estado de validación separado de limpieza. Un fallo limpiando no repite AC; un fallo procesando no se transforma en éxito por eliminar temporales.

## Límite de ACOLITE que requiere adaptación mínima

La API CDSE auditada recibe metadata que no devuelve. Se definió una extensión opcional y compatible del retorno con campos seleccionados y evidencia de estado/completitud. Se implementó después en fase 11 mediante parche con revisión/hash y tests, sin crear otro cliente CDSE. No se modificó ACOLITE durante fase 3.

## Revisión del diseño

Se revisaron documentalmente doce casos de aceptación: repetición, duplicados, revisiones, URL temporal, Zarr no equivalente, regeneración desde L1R, producto no soportado, consulta fallida/vacía, fronteras temporales, interrupción, archivo ausente y limpieza fallida. Durante fase 3 fueron casos de diseño, no tests ejecutados. La suite del wrapper posterior contiene 23 pruebas; ver fase 11.

[Diseño completo, campos y reglas](16_catalog_provenance.md).

## Continuación posterior

La fase 4 fijó el perfil y excluyó OC4; la fase 5 consultó disponibilidad y las fases 6/10 procesaron escenas. La fase 11 implementó el catálogo y el wrapper. Siguen pendientes la aceptación científica y la fase 12, no la creación de la base.
