# Riesgos y decisiones pendientes

Estado sincronizado al 30 de septiembre de 2026, después de la implementación del wrapper y del reinicio autorizado de ensayos. Los resultados históricos permanecen en los informes de fases y en SQLite; no implican disponibilidad de los NetCDF eliminados.

## Resuelto técnicamente

- AOI single-tile Sentinel-2 19QGV confirmado. Grilla común verificada en cinco Sentinel-2 y tres Landsat: EPSG:32619, 2440×7335, 10 m, x 701980–775330 e y 1997360–1972960 m.
- ACOLITE fijado a `80da0c0c681d9597fd4b7737837d6a3e61907b33`, con parche de catálogo. Desde el 01-10-2026 se usa la instalación `/home/antho/acolite`, restaurada y actualizada a esa revisión; identidad del motor idéntica a la de los ensayos ([documento 34](34_acolite_installation.md)).
- Catálogo SQLite v2 y wrapper secuencial implementados, con snapshots, hashes, reintentos, supervisión y QA técnico. Suite de 27 pruebas.
- OC4 excluido; NDCI solo Sentinel-2. Landsat reproyecta L1R antes de AC; entregar a 10 m no aumenta su detalle original.
- Persistencia vigente: L1R/L2W y SQLite; L2R/RAW temporales tras QA técnico y registro. Regenerar desde L1R repite AC.
- El reinicio solicitado eliminó escenas de ensayo; los artefactos históricos figuran `DELETED`. Las cifras antiguas de disco no describen el inventario actual.

## Pendientes reales

| Riesgo o incertidumbre | Estado y acción pendiente |
|---|---|
| Productos acuáticos mayormente enmascarados | Validación científica abierta; investigar máscara/glint con un ensayo autorizado, sin relajar umbrales arbitrariamente |
| Falta de datos in situ | Incorporar observaciones coincidentes y controles de calidad antes de aceptar productos científicos |
| FAI/NDVI con tierra | La salida exclusivamente oceánica sigue pendiente; conservar la excepción de máscara documentada |
| Zarr remoto | Retirado del wrapper el 01-10-2026: el STAC EOPF solo publica 2025-04-18 para el AOI. Reincorporarlo exige cobertura, un ensayo real y equivalencia SAFE/Zarr ([documento 06](06_acolite_zarr_input.md#retirada-del-wrapper-01-10-2026)) |
| Completitud USGS | La API nativa no pagina explícitamente; el wrapper registra completitud desconocida |
| Fuente sin checksum comparable | Puede requerir descargar y verificar antes de omitir cálculo; hacerlo solo con autorización |
| RAW retenido tras `SKIPPED` | Fallo reproducido con adquisición simulada: se omite el procesamiento tras descargar, pero `cleanup` aplaza el borrado. Corrección pendiente |
| Recursos y repetibilidad | 50 GB supervisados por muestreo, sin cuota instantánea; RAM y tiempos dependen de escena y caché. No hay traza exhaustiva de auxiliares consumidos |
| `Retry-After` | El wrapper usa esperas fijas de 60/300 s; no implementa la recomendación histórica de interpretar ese encabezado |
| Respaldo externo | No hay backups por comando; destino y procedimiento externo pendientes de definir |
| Docker/Airflow y cubo Zarr | Fases 12/13 no iniciadas; requieren nueva orden |

## Condiciones de la continuación

No descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita. `run` y `derive` pueden acceder a la red incluso con archivos locales; esta restricción es operativa y no está implementada como bloqueo en el CLI.

El perfil Sentinel-2 actual usa [2026-08-01,2026-08-15) UTC y el Landsat [2026-08-01,2026-08-21). Las cinco escenas Sentinel-2 de los informes corresponden al intervalo histórico más amplio; no son una nueva consulta del perfil actual.

Referencias: [wrapper actual](32_phase11_wrapper.md), [conservación y reinicio](33_retention_and_reset.md), [validación científica](28_phase7_validation.md).
