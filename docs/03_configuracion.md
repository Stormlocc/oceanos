# Perfil y settings de ACOLITE

Los perfiles de `config/aoi/lapargera_v1/` son configuración de OCEANOS: **ACOLITE no lee esos YAML**. `oceanos/config.py` (`profile()` y `native_settings()`) los interpreta y genera los settings nativos que se escriben en `settings.txt` de cada ejecución. Todo lo no listado conserva el default de la [revisión fijada](02_acolite.md).

## Archivos

| Archivo | Contenido |
|---|---|
| `project.yaml` | Perfil común y Sentinel-2: AOI y hash del KMZ, búsqueda (tile 19QGV, S2A/S2B/S2C, intervalo, nubosidad), productos, grilla, reintentos (3 intentos, esperas 60/300 s) y presupuesto de 50 GB |
| `landsat.yaml` | Landsat 8/9 (`--sensor landsat`): path/row 005/048, dataset `landsat_ot_c2_l1`, intervalo, productos sin NDCI y proyección del L1R |
| `W2C_South_AOI.kmz` | Geometría original. Su SHA-256 se comprueba al cargar el perfil: si cambia, el wrapper se detiene |

Intervalos actuales: Sentinel-2 [2026-01-01, 2026-02-28) y Landsat [2026-08-01, 2026-08-21), en UTC con fin excluido. Se sustituyen por comando con `--start/--end` sin editar el YAML; Landsat exige límites a las 00:00 UTC. `--satelite` restringe las plataformas del perfil y `--products` la lista de productos.

## Settings generados

| Setting | Sentinel-2 | Landsat | Motivo |
|---|---|---|---|
| `region_name` | `lapargera_v1` | igual | Nombre de las salidas |
| `limit` | 17.835068, -67.091769, 18.047433, -66.402412 (S, O, N, E) | igual | Recorte rectangular sin buffer |
| `l2w_parameters` | `Rrs_*,tur_nechad2009,chl_oc3,ndci,fai,ndvi` | sin `ndci` | Productos del perfil |
| `rgb_rhot`, `rgb_rhos` | False | False | Evitar PNG no solicitados |
| `l1r/l2r/l2w_delete_netcdf`, `delete_extracted_input` | False | False | La limpieza la decide OCEANOS tras el QA |
| `delete_acolite_run_text_files` | True | True | No conservar logs de éxito |
| `output_projection`, `reproject_before_ac` | default (False) | True | Proyectar L1R antes de AC para conservar flags |
| `output_projection_epsg` / `_resolution` / `_metres` | — | 32619 / 10,10 / True | Grilla común en metros |
| `output_projection_xrange` / `_yrange` | — | 701980,775330 / 1997360,1972960 | Rango oeste→este y norte→sur |
| `output_projection_resolution_align` | — | False | Los rangos ya están alineados |
| `output_projection_resampling_method` | — | nearest | Sin mezclar píxeles de 30 m |
| `dsf_tile_dimensions` | default (600,600) | 600,600 | Mantener tiles DSF de ≈6 km a 10 m |

Al regenerar desde un L1R retenido (`derive` o reutilización automática) se añaden `output_projection=False`, `reproject_before_ac=False` y `l1r_crop=False`: el L1R ya está en la grilla final.

## Defaults que se conservan a propósito

- Recorte y lectura: `merge_tiles=False`, `extend_region=False`, `polygon=None`, `limit_buffer=None`, `l1r_crop=False`, `s2_target_res=10`, `geometry_res=60`.
- Corrección: DSF tiled con los valores por sensor, gases y auxiliares MERRA-2, presión y viento por defecto, sin glint residual, adyacencia ni DEM.
- Máscara L2W: `l2w_mask=True`, onda 1600 nm, umbral 0,0215, suavizado sigma 3. No se modifica para "obtener" píxeles (ver [resultados](05_resultados.md)).
- NetCDF: proyección incluida, compresión zlib nivel 4, sin discretización ni GeoTIFF. S2C usa `rsr_version=V4`; S2A/S2B no.

La tabla completa de defaults está en [`config/defaults.txt`](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/defaults.txt) y en `config/defaults/<sensor>.txt` de la revisión fijada.

## Grilla verificada

EPSG:32619, 2440 filas × 7335 columnas, píxel 10 m, borde superior izquierdo (701980, 1997360) m, centros extremos x 701985–775325 e y 1997355–1972965 m. La validación técnica de cada ejecución compara los ejes completos y el EPSG; cualquier diferencia detiene la ejecución en lugar de aceptar un desplazamiento.
