# Control de entrega del paso 54

Esta tabla distingue documentos entregados de investigación completada. Los 23 puntos tienen ubicación documental, pero no todos cuentan aún con resultados técnicos.

| N.º | Entregable | Documento | Estado |
|---|---|---|---|
| 1 | Análisis AOI | 01 | Completado; costa estimada a escala cartográfica |
| 2 | Tiles y grids | 01, 12 | Tiles comprobados; grilla geométrica candidata calculada |
| 3 | Auditoría ACOLITE | 02–12, 23 | Completada estáticamente; escena real pendiente |
| 4 | Matriz ACOLITE/código propio | 02 | Capacidades y límites verificados en código |
| 5 | Estrategia de catálogo | 03, 16, 24 | Diseño terminado: SQLite único, sin implementar |
| 6 | Metadata/provenance | 16 | Seis entidades, campos, origen y ausencia definidos |
| 7 | Detección de cambios | 03, 16 | Reglas de cambios, hashes y reutilización definidas |
| 8 | SAFE frente a Zarr | 06 | Disponibilidad consultada en fase 5; rendimiento sin medir |
| 9 | Fallback | 04 | Política acordada; sin implementación |
| 10 | Configuración candidata | 14, 25 | YAML del perfil y TXT nativo preparados; OC4 excluido |
| 11 | Settings/defaults/razón/fuente | 14 | 81 settings auditados; overrides candidatos |
| 12 | Productos finales | 11 | Soporte auditado; OC4 excluido por el usuario |
| 13 | Conservación L1R/L2W | 10, 11, 25 | Conservar L1R/L2W; regenerar AC y eliminar L2R temporal tras QA técnico |
| 14 | Proyección | 12, 25 | Ensayo sin warp final; grilla nativa candidata calculada |
| 15 | Temporales | 17, 30 | Política aplicada: retención del ensayo no aceptado |
| 16 | Eliminación SAFE | 17, 30 | Borrado aplazado; integridad de fuente conservada |
| 17 | Estimación computacional | 13 | Una escena medida; análisis y límites en documento 29 |
| 18 | Benchmark | 13, 29 | Medición analizada; sin comparación Zarr ni escena científicamente aceptada |
| 19 | Validación | 15 | Plan técnico y tests; ciencia pendiente |
| 20 | Airflow | 18 | Arquitectura futura conceptual |
| 21 | Zarr | 19 | Arquitectura futura conceptual |
| 22 | Riesgos | 21 | Registro inicial |
| 23 | Decisiones pendientes | 21 | Registro inicial |

No declarar completo el paso 54 en su sentido técnico hasta resolver la investigación requerida. Esta entrega permite revisar el alcance y el diseño sin adelantar programación ni atribuir a ACOLITE capacidades no verificadas.

## Actualización de fase 10

Ocho adquisiciones completadas (cinco Sentinel-2 y tres Landsat), con grilla común y flags comprobados. Inventario final 27,84 GB; máximo RSS individual 6,57 GB. El acceso USGS y la alineación Landsat quedaron resueltos; la aceptación científica y el ensayo Zarr siguen pendientes. No se inició fase 11. Ver [informe y evidencias](31_phase10_multidate.md).

## Implementación en fase 11

El diseño histórico se materializó en el wrapper local y seis tablas SQLite, agrupando metadata en JSON. La aceptación técnica permite reutilización, pero no implica aprobación científica ni limpieza por éxito. Consultar [alcance, pruebas y límites](32_phase11_wrapper.md). No se inició fase 12.
