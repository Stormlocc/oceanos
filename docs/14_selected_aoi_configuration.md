# Perfil candidato del AOI

Este documento expresa configuración conceptual. No se crea todavía `project.yaml` ni archivos de settings ejecutables.

| Decisión del perfil | Valor acordado |
|---|---|
| AOI | `lapargera_v1` |
| Geometría | `W2C_South_AOI.kmz` |
| Objetivo | Calidad del agua |
| Sensor inicial | Sentinel-2 |
| Fechas iniciales | 2026-08-01 a 2026-08-20 inclusive |
| Filtro de nubosidad | Desactivado; configurable por AOI |
| Adquisiciones | Todas las válidas; distinguir revisiones y representaciones |
| Resolución final MVP | 10 m |
| Extent | Rectángulo derivado del AOI, alineado |
| EPSG, origen y shape | Pendientes del análisis espacial |
| Máscara | Oceánica; comportamiento pendiente de auditoría |
| Fuente preferida | Zarr remoto si compatible |
| Fallback | Automático informado tras reintentos |
| Temporales | Máximo 50 GB |
| Concurrencia | Una escena |

## Tabla de settings a completar con evidencia

Los nombres siguientes son candidatos del documento de requisitos. Ningún default se ha leído todavía en la instalación elegida.

| Setting candidato | Default general | Default sensor | Override AOI candidato | Razón | Fuente pendiente |
|---|---|---|---|---|---|
| `s2_target_res` | Por verificar | Por verificar | 10 si corresponde a la grilla requerida | Resolución MVP | Defaults y lector S2 |
| `merge_tiles` | Por verificar | Por verificar | False si se confirma single-tile | Evitar combinación innecesaria | Run y lector |
| `limit` | Por verificar | Por verificar | Bounds calculados | Recorte AOI | ROI y lector |
| `l2w_parameters` | Por verificar | Por verificar | Lista compatible de productos solicitados | Productos obligatorios | L2W |
| `reproject_before_ac` | Por verificar | Por verificar | False si procede | Reproyección final | Run/proyección |
| `reproject_outputs` | Por verificar | Por verificar | Pendiente de benchmark | Reducir duplicación | Run/proyección |
| `output_projection_epsg` | Por verificar | Por verificar | Pendiente AOI | CRS local | Proyección |
| `output_projection_resolution` | Por verificar | Por verificar | 10 m con sintaxis verificada | Coincidencia espacial | Proyección |
| `output_projection_xrange`, `output_projection_yrange` | Por verificar | Por verificar | Rangos alineados calculados | Grilla reproducible | Proyección |
| `delete_extracted_input` | Por verificar | Por verificar | Desactivar eliminación prematura si hace falta | Validar antes de limpiar | Run/extracción |
| `l1r_delete_netcdf`, `l2r_delete_netcdf`, `l2w_delete_netcdf` | Por verificar | Por verificar | Conservar durante benchmark | Evitar pérdida de evidencia | Run |

La configuración final contendrá solo overrides necesarios, con defaults y referencias del commit auditado. No inventar settings para los campos de nuestro perfil.

## Actualización después de fase 1

El análisis de `01_aoi_analysis.md` confirma cobertura completa con 19QGV y ausencia de cruce UTM. EPSG candidato: 32619. Grilla geométrica propuesta: xrange 701980–775320 m, yrange 1973040–1997350 m, 2431 filas × 7334 columnas a 10 m. Estas mediciones resuelven los pendientes espaciales anteriores; su traducción a settings ACOLITE sigue pendiente. Landsat 005/048 cubre nominalmente 99,886 %, no el AOI íntegro.
