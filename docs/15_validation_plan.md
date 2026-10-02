# Validación y tests

## Criterio de simplicidad

Validar los límites del sistema y los resultados importantes, sin replicar el algoritmo de ACOLITE. La implementación autorizada de fase 11 cuenta con 27 pruebas en `tests/test_wrapper.py`.

## Validación técnica mínima

Antes de procesar: perfil legible, AOI presente, configuración coherente y espacio temporal suficiente. Después: NetCDF requerido existente y legible, variables obligatorias disponibles, dimensiones y grilla esperadas, metadatos esenciales y reporte de proporción de datos válidos/flags.

Un archivo existente pero vacío o sin las variables requeridas no autoriza eliminación de la fuente. Un producto con todo el AOI enmascarado debe quedar registrado explícitamente; la aceptación científica permanece pendiente y separada de la limpieza, que exige L1R/L2W técnicamente íntegros y registrados.

Conservar reporte simple de resultado, motivos de fallo y métricas dentro de SQLite. No imponer umbrales científicos arbitrarios.

## Contratos de prueba y cobertura actual

- Una salida ausente o ilegible impide marcar validación exitosa y activar limpieza por éxito.
- Un archivo fuera del directorio temporal de la ejecución nunca se elimina.
- Misma entrada y configuración no generan procesamiento duplicado; cambio científico sí genera nueva ejecución.
- Nuevos productos reutilizan L1R solo si conserva bandas/geometría y grilla compatibles; se repite AC y se elimina L2R tras QA técnico.
- Agotar los reintentos de consulta queda registrado y detiene la búsqueda con error.
- Las fechas incluyen el inicio UTC y excluyen el final configurado. Sentinel-2 termina actualmente el 15; Landsat el 21. La prueba existente cubre el inicio y fechas fuera del intervalo, sin cubrir cada frontera de cada API.
- Productos comparables mantienen grilla y variables previstas en una pequeña prueba de integración.

Usar dobles sencillos para control de estados; reservar una escena real para integración y benchmark. No descargar escenas en cada test unitario ni exigir igualdad bit a bit entre entornos sin justificación.

## Validación científica

Pendiente de datos in situ. Incorporar antes de declarar aceptación científica: CTD, muestras, clorofila, turbidez, observaciones OCEANOS/CariCOOS y controles de calidad. La revisión de flags y plausibilidad no sustituye comparación científica independiente.

## Resultados de auditoría de fase 2

Se ejecutaron seis comprobaciones aisladas de funciones nativas: precedencia de defaults de sensor, precedencia de override, OC3 presente para S2A/B/C, OC4 ausente para S2A/B/C, URL STAC defectuosa sin bbox y límite final STAC a medianoche. Además dos aserciones reprodujeron la forma de grilla con alineación activada/desactivada. Los JSON originales de esas comprobaciones se retiraron al consolidar el historial. Las comprobaciones con fallo esperado demuestran una limitación; no certifican funcionamiento de producción.

Contratos identificados en fase 2 para revisar en la cobertura actual: detectar ausencia de cualquier producto requerido sin aceptar éxito parcial (OC4 está excluido); conservar l2_flags cuando exista reproyección; no aplicar automáticamente máscara acuática a FAI/NDVI; no tratar descarga parcial como existente válida; comprobar diferencias de fechas CDSE/STAC/EarthExplorer. Mantener pocos tests de contrato, sin replicar corrección atmosférica.

## Casos de aceptación de fase 3

El [informe de fase 3](24_phase3_catalog_design.md) enumera doce escenarios revisados entonces como diseño. La base y las pruebas se implementaron después en fase 11; el [catálogo vigente](16_catalog_provenance.md) describe el comportamiento actual. Priorizar idempotencia, cambios de contenido, regeneración desde L1R, completitud y separación validación/limpieza.


## Resultado de fase 6

El ensayo real generó los tres NetCDF y confirmó la grilla, pero dejó todos los productos acuáticos enmascarados. Recursos y evidencia están en [el informe de fase 6](27_phase6_first_scene.md). No hubo aceptación científica; el diagnóstico se completó en fase 7. La conservación se rige ahora por el QA técnico y el reinicio del documento 33.


## Revisión de fase 7

Se confirmó que el SWIR TOA supera el umbral en todo el recorte; las pruebas de escala SAFE/L1R, continuidad TOA y geolocalización pasaron. El brillo solar es una hipótesis compatible con la geometría, no una causa única demostrada. No se cambiaron parámetros; los productos acuáticos siguen no aceptados. Ver [dictamen y evidencia](28_phase7_validation.md).

## Actualización de fase 10

Ocho adquisiciones completadas (cinco Sentinel-2 y tres Landsat), con grilla común y flags comprobados. Inventario histórico 27,84 GB; máximo RSS individual 6,57 GB. Los archivos de ensayo se retiraron después. El acceso USGS y la alineación Landsat quedaron resueltos; la aceptación científica y el ensayo Zarr siguen pendientes. La fase 11 posterior implementó wrapper, catálogo y pruebas. Ver [informe y evidencias](31_phase10_multidate.md).
