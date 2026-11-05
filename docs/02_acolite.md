# Uso de ACOLITE en OCEANOS

Revisión fijada: [`80da0c0c681d9597fd4b7737837d6a3e61907b33`](https://github.com/acolite/acolite/tree/80da0c0c681d9597fd4b7737837d6a3e61907b33) (constante `REVISION` en `oceanos/config.py`), instalada en `/home/antho/acolite` con el [parche de catálogo](../patches/acolite-catalog.patch). Las rutas de código citadas abajo son relativas a esa revisión. Lo descrito proviene de la auditoría del código y de los ensayos reales; no implica aceptación científica.

## Reparto de responsabilidades

| Necesidad | ACOLITE | OCEANOS |
|---|---|---|
| Catálogo Sentinel-2 / Landsat / OLCI | `api.cdse.query`, `api.earthexplorer.query` | Intervalo UTC, elegibilidad del perfil, snapshots, completitud |
| Descarga y extracción | `shared.extract_bundle`; credenciales (`shared.auth`, `api.earthexplorer.auth`) y URLs (`ac.config`) | Descarga propia en streaming: CDSE para S2 y OLCI (`native.cdse_download`), USGS M2M con respaldo EarthExplorer para Landsat (`native.usgs_download`); reintentos, checksums, rutas aisladas, presupuesto de disco |
| Lectura, ROI y alineación | `sentinel2.l1_convert`, `landsat.l1_convert`, `sentinel3.l1_convert`, `limit` | Ninguno: solo genera los settings |
| Corrección atmosférica, glint, L2R y L2W | `acolite_run` → `acolite_l2r` → `acolite_l2w` | Detecta auxiliares por defecto (MERRA-2 no conseguido) |
| Flags y máscara acuática | `acolite_flags`, `l2_flags` | Decodifica los bits en `calidad.tif`; máscara de tierra WorldCover propia; no relaja umbrales |
| Proyección | `reproject_before_ac` (L1R a la grilla de cada zona) | Grilla por zona y sensor (`zonas.grid`) |
| Ángulo de glint | `shared.glint_angle` | Lo calcula por píxel con la geometría del L2R |
| Historial, superimagen, limpieza | No cubierto | SQLite, validación técnica, COG con linaje, sargazo, compuestos y retención |

## Settings: precedencia

ACOLITE aplica defaults generales (`config/defaults.txt`), luego los del sensor (`config/defaults/S2A_MSI.txt`, `L8_OLI.txt`, …) solo para claves que el usuario no fijó, y por último los overrides del usuario. `acolite_run` además transforma algunos settings de ROI durante la ejecución. Consecuencia: copiar un valor general como override destruye el default del sensor; OCEANOS envía solo los overrides necesarios ([configuración](03_configuracion.md)). `ac.settings` es estado global del intérprete: por eso cada etapa corre en un proceso aislado (`oceanos/worker.py`).

## Catálogo

**CDSE** (`api/cdse/query.py`). Con `collection='SENTINEL-2', level=1` busca S2MSI1C; `tile` acepta `19QGV` o `T19QGV`; `sensor` no filtra plataforma (OCEANOS filtra S2A/S2B/S2C después). Fecha inicial `ContentDate/Start gt inicio`; la final suma un día y usa `lt`, por eso OCEANOS ajusta los extremos para obtener un intervalo semiabierto [inicio, fin). Sigue `@odata.nextLink` hasta agotar resultados (`max_results` es tamaño de página). El retorno nativo descarta los campos superiores (Id, `ContentLength`, `Checksum`, footprint): el parche añade un retorno opcional con esa metadata, timeouts y errores HTTP explícitos.

**USGS** (`api/earthexplorer/query.py`). Dataset `landsat_ot_c2_l1` para L8/L9, autenticación con el token M2M (`earthexplorer_token` en `.netrc`). La nativa pide `scene-search` con `maxResults=1000` y **no pagina**. Por eso OCEANOS usa su propia consulta (`native.usgs_search`), sin modificar ACOLITE. Usa el mismo token, el mismo rectángulo, intervalo y nubosidad, y el mismo identificador `Landsat Product Identifier L1`, pero sigue `nextRecord` hasta reunir `totalHits`. Se validó el 03-11-2026 contra M2M: con páginas de 5 recorrió 31 páginas y trajo las 152 escenas, las mismas que en una sola página. No filtra tier, path/row ni sensor: lo hace OCEANOS. El ROI toma los puntos 0 y 2 del contorno como esquinas: enviar siempre un rectángulo. Para Landsat no añade un día al final (regla distinta de CDSE). El tamaño de cada bundle no viene en la consulta: OCEANOS lo pide a `download-options` de M2M (o, sin acceso, a la página de opciones de EarthExplorer) y `run --plan` lo suma.

## Descarga y extracción

- `api.cdse.download` **ya no se usa** (13-10-2026). Al seguir la redirección de `catalogue.dataspace…` a `download.dataspace…` hace un `session.get` sin `stream=True` que baja el ZIP completo y luego `dl = session.get(url)` lo baja otra vez: medido con una escena real de 734,8 MB, recibió 1.472 MB (2,0×) y usó 1,65 GB de RAM; un corte de conexión a mitad de la transferencia sale como excepción sin controlar. No reintenta, no tiene timeout ni verifica checksum, y con `verbosity>1` imprime el token. Sin cambios upstream desde mayo de 2026.
- `native.cdse_download` (OCEANOS) la reemplaza siguiendo la [documentación de CDSE](https://documentation.dataspace.copernicus.eu/APIs/OData.html#product-download): toma credenciales (`shared.auth('cdse')`) y URLs (`CDSE_odata`, `CDSE_auth`) de ACOLITE, sigue a mano las redirecciones solo dentro de `dataspace.copernicus.eu` y sin bajar de https a http (requests quitaría el token al cambiar de host), escribe en streaming a un `.part` con MD5 y SHA-256 calculados mientras baja, y cierra la sesión del token al terminar (CDSE admite 100 sesiones activas). Misma escena: 737 MB recibidos (1,0×), 6–7 MB de RAM extra, MD5 oficial correcto. El archivo es el mismo producto del proveedor, por lo que la entrada de ACOLITE y las claves de reutilización no cambian.
- `api.earthexplorer.download` inicia sesión en EROS, lee la página de opciones de EarthExplorer y descarga el botón "Download Product". Repite el patrón de dos `get` sin streaming. **Ya no se usa** (03-11-2026).
- `native.usgs_download` (OCEANOS) usa primero M2M, la vía oficial de USGS, aprobada para la cuenta el 04-11-2026: `download-options` (producto Level-1 *Product Bundle* disponible) → `download-request` → `availableDownloads[].url` (o `download-retrieve` si queda en preparación), en streaming y con el pedido retirado al terminar (`download-order-remove`). Si M2M no entrega URL, recurre a EarthExplorer con los mismos pasos que la nativa pero en una sola transferencia. La vía queda en el linaje (`via_descarga`).
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

Gases y auxiliares activos (`gas_transmittance=True`, `ancillary_data=True`, GMAO MERRA-2): `ancillary.get` **descarga** auxiliares y, si falla, sigue en silencio con los defaults (`uoz_default`, `uwv_default`, `pressure_default`); OCEANOS lo detecta ([superimagen](07_superimagen.md#datos-externos-que-pide-acolite)). **Glint residual activo** desde Water2Coast (`dsf_residual_glint_correction=True`, `glint_write_rhog_ref=True`): ACOLITE la corrige donde rhos(1600 nm) ≤ `glint_mask_rhos_threshold` (0,05) y escribe `rhog_ref`. Adyacencia (GLAD/RAdCor), interfaz y DEM siguen desactivados. La primera ejecución prepara LUT en `acolite/data` (≈0,6 GB en el ensayo; hoy `data` ocupa ≈1,8 GB) y cuenta en el presupuesto de disco.

## L2R

`acolite_run` reconoce un L1R ACOLITE y ejecuta **L1R → AC → L2R → L2W**. En la superimagen L1R, L2R y L2W son temporales: de L2R se leen `rhog_ref`, la geometría y los auxiliares usados, y se borra tras exportar. No se regenera desde L1R (el comando `derive` del legado se retiró); reprocesar significa volver a descargar, porque un L1R recortado a una zona no sirve para otra.

## L2W, productos y flags

| Producto | Soporte | Máscara acuática |
|---|---|---|
| `Rrs_*` | Se expande a las bandas `rhos` presentes (rhos/π, sr⁻¹) | Sí |
| `tur_nechad2009`, `spm_nechad2010` | Banda cercana a 665 nm | Sí |
| `chl_oc2`, `chl_oc3` | Coeficientes por sensor; OLI usa `chl_oc2f` | Sí |
| `chl_oc4` | Solo OLCI en el perfil; no configurado para S2A/B/C | Sí |
| `chl_re_gons`, `ndci` | Borde rojo: MSI (y OLCI para NDCI) | Sí |
| `chl_ci` | Todos los sensores | Sí |
| `qaa_v6_Kd_490` | Solo OLI y MSI: ACOLITE imprime «QAA not configured» para OLCI y no lo escribe | Sí |
| `fai`, `fait`, `ndvi` | MSI y OLI (FAI necesita ~1610 nm; OLCI no la tiene) | **No** (`mask=False`) |

Detalle por sensor: [superimagen](07_superimagen.md#productos-de-acolite).

`l2_flags` (entero) siempre se escribe: bit 0 SWIR/no agua, 1 cirrus, 2 TOA alta, 3 reflectancia negativa, 4 fuera de escena, 5 mixto, 6 sombra DEM. La máscara usa `rhot` cerca de 1600 nm > 0,0215 (`l2w_mask_threshold`), suavizada con sigma 3 píxeles: no es una máscara geográfica de océano y puede enmascarar agua muy reflectante (ver [resultados](05_resultados.md)). ACOLITE puede avisar "Parameter not computed" y continuar: OCEANOS verifica las variables finales, no solo que exista el NetCDF. Existe `masking.land_water_mask` (GSHHG/HydroLAKES) como máscara tierra/agua separada, aún no evaluada.

## Proyección

`output.project_acolite_netcdf` apila todas las variables 2D en memoria y **omite `l2_flags` al escribir**. Por eso en todos los sensores se proyecta **el L1R antes de AC** (`reproject_before_ac=True`, `nearest`) a la grilla de cada zona: los flags se generan después, ya en la grilla final. Contrato de rangos: `output_projection_resolution` = resolución nativa, `output_projection_metres=True`, xrange oeste→este, **yrange norte→sur** y `output_projection_resolution_align=False` (con `True` ACOLITE realinea rangos ya alineados y la forma cambia en un píxel).

## Zarr retirado

ACOLITE puede leer Zarr EOPF remoto (`sentinel2.zarr.l1_convert`, descubierto con `api.stac.query`), pero el STAC EOPF solo publica 2025-04-18 para este AOI y CDSE entrega únicamente SAFE. Se retiró del wrapper el 01-10-2026; la última versión con Zarr está en el commit `9af82a6`. Reincorporarlo exige cobertura real, un ensayo y comparar grilla y radiometría con SAFE.

## Instalación y `prepare`

```bash
oceanos prepare                       # una vez, o tras restaurar/actualizar ACOLITE
git -C /home/antho/acolite status     # solo deben aparecer los archivos del parche
```

`prepare` comprueba que `HEAD` sea `REVISION`; si el parche no está aplicado y la instalación no tiene otros cambios, lo aplica; devuelve la identidad del motor (revisión, SHA-256 del parche y del diff efectivo). La identidad se recalcula en cada `search`/`run` y queda en el linaje de cada producto (`productos_escena.acolite`): con otra revisión o parche el wrapper se detiene antes de consultar y no reutiliza salidas previas. El parche solo toca la capa de consulta (`cdse/query.py`, `earthexplorer/query.py`), no código científico. Identidad vigente desde el 01-10-2026: `patch_sha256` `5cc22d82…a8f5aa`, `working_diff_sha256` `06eb7f52…bbbf57`.

**Actualizar ACOLITE** (nunca `git pull` sobre la instalación): clonar la revisión nueva aparte, comprobar el parche con `git apply --check`, comparar `config/defaults.txt` y los defaults del sensor con lo que genera `native_settings()`, ejecutar las pruebas con `--acolite` apuntando a la copia, procesar una escena de referencia con ambas versiones y comparar variables L2W, flags y NaN. Solo entonces cambiar `REVISION`, revertir el parche, cambiar de revisión y repetir `prepare`. Otros proyectos que usen `/home/antho/acolite` ven la revisión con el parche; su retorno por defecto es compatible.
