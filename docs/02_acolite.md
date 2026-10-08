# Uso de ACOLITE en OCEANOS

Revisión fijada: [`80da0c0c681d9597fd4b7737837d6a3e61907b33`](https://github.com/acolite/acolite/tree/80da0c0c681d9597fd4b7737837d6a3e61907b33) (constante `REVISION` en `oceanos/config.py`), instalada en `/home/antho/acolite` con el [parche de catálogo](../patches/acolite-catalog.patch). Las rutas de código citadas abajo son relativas a esa revisión. Lo descrito proviene de la auditoría del código y de los ensayos reales; no implica aceptación científica.

## Reparto de responsabilidades

| Necesidad | ACOLITE | OCEANOS |
|---|---|---|
| Catálogo Sentinel-2 / Landsat | `api.cdse.query`, `api.earthexplorer.query` | Intervalo UTC, elegibilidad del perfil, snapshots, completitud |
| Descarga y extracción | `api.cdse.download`, `api.earthexplorer.download`, `shared.extract_bundle` | Reintentos, checksums, rutas aisladas, presupuesto de disco |
| Lectura, ROI y alineación | `sentinel2.l1_convert`, `landsat.l1_convert`, `limit` | Ninguno: solo genera los settings |
| Corrección atmosférica, L2R y L2W | `acolite_run` → `acolite_l2r` → `acolite_l2w` | Ninguno |
| Flags y máscara acuática | `acolite_flags`, `l2_flags` | Verifica que existan; no relaja umbrales |
| Proyección (Landsat) | `output.project_acolite_netcdf` | Rangos y resolución en el perfil |
| Historial, estados, QA del contrato AOI, limpieza | No cubierto | SQLite, validación técnica y política de retención |

## Settings: precedencia

ACOLITE aplica defaults generales (`config/defaults.txt`), luego los del sensor (`config/defaults/S2A_MSI.txt`, `L8_OLI.txt`, …) solo para claves que el usuario no fijó, y por último los overrides del usuario. `acolite_run` además transforma algunos settings de ROI durante la ejecución. Consecuencia: copiar un valor general como override destruye el default del sensor; OCEANOS envía solo los overrides necesarios ([configuración](03_configuracion.md)). `ac.settings` es estado global del intérprete: por eso cada etapa corre en un proceso aislado (`oceanos/worker.py`).

## Catálogo

**CDSE** (`api/cdse/query.py`). Con `collection='SENTINEL-2', level=1` busca S2MSI1C; `tile` acepta `19QGV` o `T19QGV`; `sensor` no filtra plataforma (OCEANOS filtra S2A/S2B/S2C después). Fecha inicial `ContentDate/Start gt inicio`; la final suma un día y usa `lt`, por eso OCEANOS ajusta los extremos para obtener un intervalo semiabierto [inicio, fin). Sigue `@odata.nextLink` hasta agotar resultados (`max_results` es tamaño de página). El retorno nativo descarta los campos superiores (Id, `ContentLength`, `Checksum`, footprint): el parche añade un retorno opcional con esa metadata, timeouts y errores HTTP explícitos.

**USGS** (`api/earthexplorer/query.py`). Dataset `landsat_ot_c2_l1` para L8/L9, autenticación con el token M2M (`earthexplorer_token` en `.netrc`). Pide `scene-search` con `maxResults=1000` y **no pagina**; descarta `totalHits`/`recordsReturned`, que OCEANOS lee de la respuesta sin modificar ACOLITE. No filtra tier, path/row ni sensor: lo hace OCEANOS. El ROI toma los puntos 0 y 2 del contorno como esquinas: enviar siempre un rectángulo. Para Landsat no añade un día al final (regla distinta de CDSE). El tamaño de cada bundle no viene en la consulta; ver [operación](04_operacion.md#información-de-search).

## Descarga y extracción

- `api.cdse.download` usa `session.get` sin `stream=True`: el ZIP completo pasa por memoria y se escribe al final. No reintenta, no tiene timeout ni verifica checksum; un ZIP existente se reutiliza aunque esté incompleto. Con `verbosity>1` imprime el token.
- `api.earthexplorer.download` inicia sesión en EROS (usuario y contraseña de `.netrc`), lee la página de opciones de EarthExplorer y descarga el botón "Download Product" (Product Bundle). Depende del HTML del portal.
- `remove_zip=True` / `remove_tar=True` borran antes de nuestro QA: OCEANOS usa `extract_zip=False`, `remove_zip=False`, `remove_tar=False`, verifica tamaño y checksums y luego extrae con `shared.extract_bundle` dentro de `storage/temporary/<run>`. El argumento `targ_bundle` de esa función se reinicia internamente: no sirve para confinar la extracción; OCEANOS revisa antes rutas y enlaces del archivo.

Entradas que reconoce `acolite_run`: SAFE L1C (rechaza otro nivel), ZIP/TAR comprimidos (los extrae), bundle Landsat L1 con MTL (no procesa L2 como L1) y NetCDF ACOLITE (L1R o L2R).

## ROI y recorte

`limit` = **sur, oeste, norte, este** en grados: reduce el extent desde la lectura (`projection_sub` y warp), no es una máscara posterior. `region_name` solo cambia nombres. No se envía `polygon`: con `polygon_limit=True` (default) ACOLITE fuerza `polygon_clip=True` y recortaría al polígono. `limit_buffer=None`, `extend_region=False` y `l1r_crop=False` se mantienen por defecto.

## L1R

- **Sentinel-2:** CRS y grillas 10/20/60 m desde la metadata del gránulo; `s2_target_res=10`; GDAL Warp con `average` lleva las bandas a 10 m; aplica `RADIO_ADD_OFFSET` y cuantificación. Geometría por defecto en grilla de 60 m.
- **Landsat:** lee Collection 2 por MTL (exige L1) y usa `nearest`. Tier 1 es un criterio de selección del catálogo, no del lector. NDCI no existe para OLI (no hay banda red-edge).
- L1R contiene `rhot_*`, lon/lat, geometría y la proyección NetCDF; es el intermedio que OCEANOS conserva.

## Corrección atmosférica (DSF)

Defaults de la revisión fijada, conservados sin cambios:

| Grupo | Sentinel-2 (S2A/B/C) | Landsat 8/9 |
|---|---|---|
| Método | `dark_spectrum`, AOT `tiled`, `intercept`, 2 bandas | igual |
| Rango espectral de ajuste | 400–900 nm | 400–2500 nm |
| Píxeles de intercepto | 200 | 200 |
| Tiles DSF | 600×600 (≈6 km a 10 m) | 200×200 a 30 m; el perfil usa 600×600 a 10 m (≈6 km) |

Gases y auxiliares activos (`gas_transmittance=True`, `ancillary_data=True`, GMAO MERRA-2): `ancillary.get` puede **descargar** auxiliares. Sin auxiliares rigen `pressure_default=1013,25 hPa` y `wind_default=2 m/s`. Glint residual, adyacencia (GLAD/RAdCor), interfaz y DEM permanecen desactivados: cambiarlos es un experimento científico, no un ajuste operativo. La primera ejecución prepara LUT en `acolite/data` (≈0,6 GB en el ensayo; hoy `data` ocupa ≈1,8 GB) y cuenta en el presupuesto de disco.

## L2R y regeneración

`acolite_run` reconoce un L1R ACOLITE y ejecuta **L1R → AC → L2R → L2W**: L1R basta como entrada, pero no produce L2W sin repetir AC. La igualdad del resultado requiere la misma revisión, settings, LUT/RSR y auxiliares; L1R no recupera bandas descartadas ni amplía un AOI recortado. L2R se usa como temporal (conserva `rhot` y `rhos` para productos y flags) y se borra tras el QA técnico. Al regenerar Landsat no se vuelve a proyectar el L1R.

## L2W, productos y flags

| Producto | Soporte | Máscara acuática |
|---|---|---|
| `Rrs_*` | Se expande a las bandas `rhos` presentes (rhos/π, sr⁻¹) | Sí |
| `tur_nechad2009` | Sale como `TUR_Nechad2009_<λ>` (banda cercana a 665 nm), FNU | Sí |
| `chl_oc3` | Coeficientes distintos para MSI y OLI; tolera bandas a ±20 nm | Sí |
| `ndci` | Solo MSI (670/705 nm) | Sí |
| `fai`, `ndvi` | MSI y OLI | **No** (`mask=False`) |
| `chl_oc4` | No configurado para S2A/B/C: ACOLITE lo omitiría sin error | Excluido |

`l2_flags` (entero) siempre se escribe: bit 0 SWIR/no agua, 1 cirrus, 2 TOA alta, 3 reflectancia negativa, 4 fuera de escena, 5 mixto, 6 sombra DEM. La máscara usa `rhot` cerca de 1600 nm > 0,0215 (`l2w_mask_threshold`), suavizada con sigma 3 píxeles: no es una máscara geográfica de océano y puede enmascarar agua muy reflectante (ver [resultados](05_resultados.md)). ACOLITE puede avisar "Parameter not computed" y continuar: OCEANOS verifica las variables finales, no solo que exista el NetCDF. Existe `masking.land_water_mask` (GSHHG/HydroLAKES) como máscara tierra/agua separada, aún no evaluada.

## Proyección

`output.project_acolite_netcdf` apila todas las variables 2D en memoria (no trabaja por bloques) y **omite `l2_flags` al escribir**. Por eso Sentinel-2 no reproyecta (usa la grilla nativa del tile recortado) y Landsat proyecta **el L1R antes de AC** (`reproject_before_ac=True`, `nearest`): los flags se generan después, ya en la grilla final. Contrato de rangos: `output_projection_resolution=10,10`, `output_projection_metres=True`, xrange oeste→este, **yrange norte→sur**, y `output_projection_resolution_align=False`, porque con `True` ACOLITE vuelve a alinear rangos ya alineados y la forma cambia en un píxel.

## Zarr retirado

ACOLITE puede leer Zarr EOPF remoto (`sentinel2.zarr.l1_convert`, descubierto con `api.stac.query`), pero el STAC EOPF solo publica 2025-04-18 para este AOI y CDSE entrega únicamente SAFE. Se retiró del wrapper el 01-10-2026; la última versión con Zarr está en el commit `9af82a6`. Reincorporarlo exige cobertura real, un ensayo y comparar grilla y radiometría con SAFE.

## Instalación y `prepare`

```bash
oceanos prepare                       # una vez, o tras restaurar/actualizar ACOLITE
git -C /home/antho/acolite status     # solo deben aparecer los archivos del parche
```

`prepare` comprueba que `HEAD` sea `REVISION`; si el parche no está aplicado y la instalación no tiene otros cambios, lo aplica; devuelve la identidad del motor (revisión, SHA-256 del parche y del diff efectivo). La identidad se recalcula en cada `search`/`run`/`derive` y entra en `correction_key`: con otra revisión o parche el wrapper se detiene antes de consultar y no reutiliza salidas previas. El parche solo toca la capa de consulta (`cdse/query.py`, `earthexplorer/query.py`), no código científico. Identidad vigente desde el 01-10-2026: `patch_sha256` `5cc22d82…a8f5aa`, `working_diff_sha256` `06eb7f52…bbbf57`.

**Actualizar ACOLITE** (nunca `git pull` sobre la instalación): clonar la revisión nueva aparte, comprobar el parche con `git apply --check`, comparar `config/defaults.txt` y los defaults del sensor con lo que genera `native_settings()`, ejecutar las pruebas con `--acolite` apuntando a la copia, procesar una escena de referencia con ambas versiones y comparar variables L2W, flags y NaN. Solo entonces cambiar `REVISION`, revertir el parche, cambiar de revisión y repetir `prepare`. Otros proyectos que usen `/home/antho/acolite` ven la revisión con el parche; su retorno por defecto es compatible.
