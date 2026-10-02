# Control de entrega del paso 54

Estado sincronizado al 30 de septiembre de 2026. La tabla distingue implementación técnica, evidencia histórica y aceptación científica pendiente.

| N.º | Entregable | Documento | Estado vigente |
|---|---|---|---|
| 1 | Análisis AOI | 01 | Completado; costa estimada a escala cartográfica |
| 2 | Tiles y grids | 01, 12, 31 | 19QGV confirmado; grilla 2440×7335, EPSG:32619, verificada en ocho adquisiciones |
| 3 | Auditoría ACOLITE | 02–12, 23 | Completada; ensayos técnicos posteriores realizados |
| 4 | Matriz ACOLITE/código propio | 02, 32 | Responsabilidades auditadas y wrapper implementado |
| 5 | Estrategia de catálogo | 03, 16, 24, 32 | SQLite v2 implementado, seis tablas |
| 6 | Metadata/provenance | 16, 32 | Snapshots, hashes y resúmenes en SQLite; sin traza exhaustiva de auxiliares consumidos |
| 7 | Detección de cambios | 03, 16, 32 | Implementada y probada; sin checksum comparable puede requerir nueva adquisición autorizada |
| 8 | SAFE frente a Zarr | 06, 31 | SAFE ensayado y operativo; Zarr remoto retirado el 01-10-2026 por falta de cobertura |
| 9 | Fallback | 04, 06 | Retirado junto con Zarr; quedan reintentos de consulta y adquisición |
| 10 | Configuración candidata | 14, 25, 31 | S2/Landsat ensayados técnicamente; ciencia pendiente |
| 11 | Settings/defaults/razón/fuente | 14 | 81 settings auditados; decisiones sincronizadas con perfiles actuales |
| 12 | Productos finales | 11, 31 | Variables/flags verificados; OC4 excluido, NDCI solo S2; ciencia pendiente |
| 13 | Conservación L1R/L2W | 10, 17, 33 | Implementada; regeneración repite AC y usa L2R temporal |
| 14 | Proyección | 12, 31 | S2 sin warp final; Landsat proyecta L1R antes de AC; grilla común verificada |
| 15 | Temporales | 17, 32 | Limpieza tras QA técnico; fallo pendiente en intentos `SKIPPED` después de descargar |
| 16 | Eliminación SAFE | 17, 30, 33 | Reinicio autorizado ejecutado; nuevas ejecuciones según política técnica |
| 17 | Estimación computacional | 13, 29, 31 | Mediciones históricas; RSS individual máximo registrado 6,57 GB |
| 18 | Benchmark | 13, 29 | Analizado; sin comparación Zarr ni escena científicamente aceptada |
| 19 | Validación | 15, 32 | 27 pruebas del wrapper; ensayos históricos; aceptación científica pendiente |
| 20 | Airflow | 18 | Fase 12 no iniciada; requiere orden |
| 21 | Zarr | 19 | Cubo propio futuro, fase 13 no iniciada |
| 22 | Riesgos | 21 | Actualizados: ciencia, red, completitud, recursos y limpieza |
| 23 | Decisiones pendientes | 21 | Separadas de hitos ya resueltos |

El wrapper implementado no cierra la validación científica ni demuestra equivalencia SAFE/Zarr. Los NetCDF de ensayo se retiraron en el reinicio; las cifras de 27,84/30,65 GB son históricas. Los resultados y hashes útiles permanecen en SQLite.

No descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita. La sincronización documental no inicia otra fase. Ver [estado operativo](32_phase11_wrapper.md) y [conservación](33_retention_and_reset.md).
