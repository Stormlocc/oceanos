# Perfil y settings de ACOLITE

Los perfiles de `config/aoi/water2coast_v1/` son configuración de OCEANOS: **ACOLITE no lee esos YAML**. `oceanos/config.py` (`profile()` y `zone_settings()`) los interpreta y genera, **por zona**, los settings nativos que se escriben en `settings.txt` de cada ejecución. Todo lo que no figura aquí conserva el default de la [revisión fijada](02_acolite.md). Las decisiones y fuentes de la superimagen están en [07](07_superimagen.md).

## Archivos

| Archivo | Contenido |
|---|---|
| `project.yaml` | Perfil común: AOI (archivo, SHA-256, campo `Name`), zonas con su EPSG, orden de los sensores, settings ACOLITE comunes (glint y AOT por píxel), nubes ≤ 50 % por zona, reintentos (3 intentos, esperas de 10/30 s), presupuestos (50 GB temporales, 120 GB superimagen), máscara WorldCover, umbrales de glint y bits de flags de sargazo y compuestos |
| `sentinel2.yaml` | S2A/S2B/S2C L1C desde CDSE, 10 m, tiles por zona y productos |
| `landsat.yaml` | L8/L9 L1TP C2 T1 desde USGS (`landsat_ot_c2_l1`), 30 m, path/row por zona y productos |
| `olci.yaml` | S3A/S3B `OL_1_EFR___` desde CDSE, 300 m y productos (sin FAI: OLCI no tiene ~1610 nm) |
| `AOI_Water2Coast.zip` | Shapefile de las 4 zonas. Si su SHA-256 no coincide, el wrapper se detiene |

**Intervalo.** El intervalo del perfil es [2025-11-01, 2026-11-01) en UTC, con el fin excluido.
- `--start/--end` lo reemplazan sin editar el YAML. Landsat exige límites a las 00:00 UTC.
- `--satelite`, `--zona` y `--products` restringen lo del perfil; no pueden agregar nada que no esté.

El perfil `config/aoi/lapargera_v1/` queda solo como registro del legado: `run` no lo usa.

## Settings generados por zona

| Setting | Valor | Motivo |
|---|---|---|
| `region_name` | id de la zona (`ponce_guayanilla`) | Nombre de las salidas |
| `limit` | Envolvente geográfica de la grilla de la zona más un píxel | Que la proyección no deje bordes vacíos |
| `l2w_parameters` | Productos del sensor (ver [07](07_superimagen.md#productos-de-acolite)) | Productos del perfil |
| `output_projection`, `reproject_before_ac` | True | Proyectar el L1R a la grilla de la zona antes de AC y conservar `l2_flags` |
| `output_projection_epsg` | 32619 o 32620 | UTM de la zona |
| `output_projection_resolution`, `_metres` | 10, 30 o 300 m; True | Resolución nativa del sensor |
| `output_projection_xrange` / `_yrange` | Envolvente de la zona alineada a la resolución | Grilla por zona y sensor (`zonas.grid`) |
| `output_projection_resolution_align` | False | Los rangos ya están alineados; con True ACOLITE cambia la forma en un píxel |
| `output_projection_resampling_method` | nearest | Sin mezclar píxeles |
| `dsf_residual_glint_correction`, `glint_write_rhog_ref` | True | Corrección de glint y `rhog_ref` por píxel |
| `dsf_write_aot_550` | True | AOT a 550 nm por píxel en el L2R, que OCEANOS copia a `calidad.tif`; no cambia Rrs ni productos |
| `rgb_rhot`, `rgb_rhos` | False | Evitar PNG no solicitados |
| `l1r/l2r/l2w_delete_netcdf`, `delete_extracted_input` | False | La limpieza la decide OCEANOS después de exportar y verificar |
| `delete_acolite_run_text_files` | True | No conservar logs de éxito |

## Defaults que se conservan a propósito

- **Corrección:** DSF por tiles con los valores por sensor, gases y meteorología MERRA-2, sin adyacencia ni DEM. La detección de auxiliares por defecto está en [07](07_superimagen.md#datos-externos-que-pide-acolite).
- **Máscara L2W:** `l2w_mask=True`, a 1600 nm con umbral 0,0215. Los COG la heredan como NaN. La validez para los compuestos se decide aparte, con `l2_flags` y `rhog_ref`.
- **NetCDF:** compresión zlib nivel 4. `S2C` usa `rsr_version=V4`.

La tabla completa de defaults está en [`config/defaults.txt`](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/defaults.txt) y en `config/defaults/<sensor>.txt` de la revisión fijada.

## Verificación de la grilla

La validación técnica de cada zona (`validation.validate`) compara el EPSG y los ejes completos del L2W con la grilla esperada. Si hay cualquier diferencia, la zona falla en vez de aceptar un desplazamiento.
