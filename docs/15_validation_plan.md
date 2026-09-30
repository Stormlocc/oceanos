# Validación y tests

## Criterio de simplicidad

Validar los límites del sistema y los resultados importantes, sin replicar el algoritmo de ACOLITE. No crear código de tests hasta la fase de implementación autorizada.

## Validación técnica mínima

Antes de procesar: perfil legible, AOI presente, configuración coherente y espacio temporal suficiente. Después: NetCDF requerido existente y legible, variables obligatorias disponibles, dimensiones y grilla esperadas, metadatos esenciales y reporte de proporción de datos válidos/flags.

Un archivo existente pero vacío o sin las variables requeridas no autoriza eliminación de la fuente. Un producto con todo el AOI enmascarado debe quedar registrado explícitamente; la política de aceptación científica se definirá antes de automatizar limpieza.

Conservar reporte simple de resultado, motivos de fallo y métricas. No imponer umbrales científicos arbitrarios.

## Tests futuros prioritarios

- Una salida ausente o ilegible impide marcar validación exitosa y activar limpieza por éxito.
- Un archivo fuera del directorio temporal de la ejecución nunca se elimina.
- Misma entrada y configuración no generan procesamiento duplicado; cambio científico sí genera nueva ejecución.
- Nuevos productos reutilizan L1R solo si conserva bandas/geometría y grilla compatibles; se repite AC y se elimina L2R tras QA técnico.
- Agotar reintentos Zarr activa fallback registrado y acotado.
- Las fechas incluyen íntegramente el día 20 y excluyen el siguiente según el contrato de la API.
- Productos comparables mantienen grilla y variables previstas en una pequeña prueba de integración.

Usar dobles sencillos para control de estados; reservar una escena real para integración y benchmark. No descargar escenas en cada test unitario ni exigir igualdad bit a bit entre entornos sin justificación.

## Validación científica

Pendiente de datos in situ. Recordar al usuario antes de fase 7: CTD, muestras, clorofila, turbidez, observaciones OCEANOS/CariCOOS y controles de calidad. La revisión de flags y plausibilidad no sustituye comparación científica independiente.

## Resultados de auditoría de fase 2

Se ejecutaron seis comprobaciones aisladas de funciones nativas: precedencia de defaults de sensor, precedencia de override, OC3 presente para S2A/B/C, OC4 ausente para S2A/B/C, URL STAC defectuosa sin bbox y límite final STAC a medianoche. Además dos aserciones reprodujeron la forma de grilla con alineación activada/desactivada. Resultados en evidence/phase2/comprobaciones.json y alineacion_reproducida.json. Las comprobaciones con fallo esperado demuestran una limitación; no certifican funcionamiento de producción.

Añadir a los tests futuros necesarios: detectar ausencia de cualquier producto requerido sin aceptar éxito parcial (OC4 está excluido); conservar l2_flags cuando exista reproyección; no aplicar automáticamente máscara acuática a FAI/NDVI; no tratar descarga parcial como existente válida; comprobar diferencias de fechas CDSE/STAC/EarthExplorer. Mantener pocos tests de contrato, sin replicar corrección atmosférica.

## Casos de aceptación de fase 3

El apartado 11 del [diseño del catálogo](16_catalog_provenance.md) define doce escenarios de comportamiento para futuras pruebas. Se revisaron como diseño, no se ejecutaron tests de una base aún no implementada. Priorizar idempotencia, cambios de contenido, regeneración desde L1R, completitud y separación validación/limpieza.


## Resultado de fase 6

El ensayo real generó los tres NetCDF y confirmó la grilla, pero dejó todos los productos acuáticos enmascarados. Recursos y evidencia están en [el informe de fase 6](27_phase6_first_scene.md). No hay aceptación científica ni limpieza autorizada. El diagnóstico corresponde a fase 7.


## Revisión de fase 7

Se confirmó que el SWIR TOA supera el umbral en todo el recorte; las pruebas de escala SAFE/L1R, continuidad TOA y geolocalización pasaron. El brillo solar es una hipótesis compatible con la geometría, no una causa única demostrada. No se cambiaron parámetros; los productos acuáticos siguen no aceptados. Ver [dictamen y evidencia](28_phase7_validation.md).

## Actualización de fase 10

Ocho adquisiciones completadas (cinco Sentinel-2 y tres Landsat), con grilla común y flags comprobados. Inventario final 27,84 GB; máximo RSS individual 6,57 GB. El acceso USGS y la alineación Landsat quedaron resueltos; la aceptación científica y el ensayo Zarr siguen pendientes. No se inició fase 11. Ver [informe y evidencias](31_phase10_multidate.md).
