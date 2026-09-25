# Arquitectura y matriz ACOLITE / código propio

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

## Revisiones y alcance

Instalación local `/home/antho/acolite`: `f73cbe73887c2b114d9d3c70865effee73871525`. Tiene una modificación local en `config/config.txt`; no se mostraron sus valores ni se alteró el archivo. Código upstream actual consultado y clonado superficialmente en `.work/acolite-audit`: `80da0c0c681d9597fd4b7737837d6a3e61907b33`. No se actualizó la instalación activa.

Se inspeccionaron defaults, loaders, run, identificación/extracción, APIs CDSE/EarthExplorer/STAC, lectores Sentinel SAFE/Zarr y Landsat, L1R/L2R/L2W, flags, máscaras, proyección, escritura NetCDF y auxiliares. El manifiesto en `evidence/phase2/manifest.json` identifica archivos de referencia por checksum; inventario no significa que cada rama haya sido ejecutada.

Diferencias relevantes local → upstream: compresión NetCDF False → True; `dsf_tile_smoothing` True → False y nuevos settings de suavizado AOT; cambios de proyección/centros de Landsat, filtros de bandas L2R, descarga CDSE y nuevos productos. Los defaults S2A/B/C y el lector S2 Zarr coinciden en los archivos comparados. No transferir resultados de rendimiento entre revisiones ni actualizar automáticamente durante el estudio.

## Flujo y precedencia

Al importar, ACOLITE carga defaults generales en `settings['defaults']` y copia a `run`. `acolite_run` reinicia `run`, analiza solo overrides en `user`, incorpora argumentos input/output y transforma ciertos settings ROI. Los lectores y L2R/L2W incorporan defaults de sensor solo para claves ausentes en `user`. Por tanto: general → sensor → usuario, pero con transformaciones adicionales durante ejecución; los settings efectivos deben conservarse por etapa.

Fuentes: [acolite/__init__.py:181](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/__init__.py#L181-L187), [acolite/acolite/acolite_run.py:26](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_run.py#L26-L109), [acolite/acolite/settings/merge.py:10](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/settings/merge.py#L10-L29). Comprobación aislada: intercepto general 1000 → S2 200 → override de prueba 123. No se utilizó 123 como configuración científica.

El estado `ac.settings` es global: mantener una escena/proceso y no mezclar AOI concurrentemente en el mismo intérprete. `acolite_run` retorna un diccionario de rutas por entrada/nivel; rutas presentes no certifican productos completos ni QA aprobado. Guarda logs y settings de usuario/L1R/L2R, pero no implementa nuestro historial transaccional entre consultas. Su settings L1R usa `run` aunque el lector retorna `setu`; comprobar el efectivo del sensor, no confiar únicamente en el nombre del archivo de settings.

## Matriz verificada

| Necesidad | ACOLITE | Módulo/API/settings | Limitación observada | Código nuestro |
|---|---|---|---|---|
| Catálogo S2 y filtros | Sí | `api.cdse.query` | Retorno pierde campos top-level | Wrapper; extensión mínima de metadata a evaluar |
| Catálogo Landsat | Sí | `api.earthexplorer.query` | Sin paginación explícita; ROI rectangular asumido | Wrapper y control de completitud |
| Descubrimiento Zarr | Sí, EOPF candidato | `api.stac.query/query_get` | URL sin bbox defectuosa; filtro tile propio mínimo | Selección de metadata |
| Descarga | Sí | `api.cdse.download`, `api.earthexplorer.download` | Sin streaming real en llamadas finales, ni verificación checksum | Reintentos/validación; parche mínimo si necesario |
| Extracción | Sí | `shared.extract_bundle` | Parámetro destino se reinicia dentro de función | Usar salida aislada; no reimplementar |
| SAFE/Landsat | Sí | `sentinel2.l1_convert`, `landsat.l1_convert` | Flujo estudiado exige L1 | Ninguno |
| Zarr remoto | Sí, formato concreto | `sentinel2.zarr.l1_convert` | Reconocimiento automático solo HTTPS terminado en .zarr | Wrapper mínimo si formato/ruta lo exige |
| ROI | Sí | `limit`, `projection_sub` | `polygon_limit` fuerza clipping | Ninguno: usar limit explícito |
| Alineación de bandas | Sí | `read_band` / GDAL Warp | SAFE/Zarr tienen diferencias en geometría | Ninguno |
| DSF y L2R | Sí | `acolite_l2r` | Defaults cambian por sensor/revisión | Ninguno |
| Productos L2W | Sí, salvo OC4 S2 | `acolite_l2w` y coeficientes | Puede omitir un producto sin abortar | QA de variables; sin sustitución científica |
| Tierra/agua | Parcial | `acolite_flags`, `masking.land_water_mask` | FAI/NDVI no usan máscara acuática automática | Aplicación mínima de máscara nativa si se decide |
| Proyección | Sí | `project_acolite_netcdf` y `reproject_acolite_netcdf` | RAM, flags y alineación requieren decisión | No motor propio; adaptar solo límite demostrado |
| NetCDF | Sí | `gem`, `output.nc_write` | Discretización es decisión científica | Ninguno |
| Limpieza | Parcial | flags delete y APIs download | Antes de QA propio | Política mínima posterior a validación |
| Historial/provenance | Insuficiente para requisito | Logs/settings nativos | No historial de revisiones entre consultas | Persistencia propia pequeña |
| Estado/reintentos | Insuficiente para requisito | Retornos y logs | No contrato de ejecución completo | Registro mínimo |
| Validación de contrato AOI | No completa | Outputs y atributos nativos | No certifica grilla/productos requeridos | Validación simple |
| Cubo temporal AOI | No cubierto por flujo auditado | Zarr existente es lector de entrada | Ingestión futura distinta | Posponer a fase 13 |

## Límites

No se realizaron autenticación, consulta de adquisiciones, descarga satelital, corrección atmosférica ni benchmark. La estrategia definitiva de catálogo corresponde a fase 3; configuración científica a fase 4; comparación experimental de fuentes a fases posteriores.
