# Zarr remoto: soporte real y comparación de fuentes

> Estado vigente (01-10-2026): **Zarr retirado del wrapper.** OCEANOS adquiere Sentinel-2 solo como SAFE L1C desde CDSE. Este documento conserva la auditoría del lector Zarr de ACOLITE. Ver [retirada del wrapper](#retirada-del-wrapper-01-10-2026). No descargar sin autorización.

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

## Proveedor y contrato

Descubrimiento nativo STAC dirigido por defecto a EOPF/EODC, colección `sentinel-2-l1c`. No es una lista universal de proveedores compatibles. El lector exige grupos `measurements/reflectance/r10m,r20m,r60m`, geometry y detector footprints en `conditions`, además de atributos `stac_discovery` y `other_metadata`. Rechaza nivel diferente de L1C.

El acceso combina `zarr.open` para metadata/arrays auxiliares y GDAL `ZARR:"/vsicurl/..."` para bandas. Requiere Zarr moderno y GDAL con driver Zarr; fsspec/aiohttp forman parte del entorno declarado. El parser de metadata tiene una concatenación accidental de literales entre `cycle_number` y `UTM_zone_identification`, por lo que esas claves individuales pueden no recuperarse; CRS se obtiene de `horizontal_CRS_code`.

Fuentes: [acolite/zarr/meta.py:7](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/zarr/meta.py#L7-L22), [acolite/zarr/meta_parse.py:19](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/zarr/meta_parse.py#L19-L49), [acolite/sentinel2/zarr/l1_convert.py:65](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/zarr/l1_convert.py#L65-L81).

## Qué se lee

Reflectancias se leen con warp al extent del ROI a través de GDAL. Los chunks realmente transferidos dependen del layout, driver y cachés; ACOLITE no proporciona un contador de chunks. `sub` deja de determinar la lectura cuando `read_band` recibe `warp_to`: GDAL usa los bounds del destino.

Los vectores de coordenadas, ángulos solares y de visión se leen completos; detector footprints se leen sobre el tile completo a `geometry_res` (60 m por defecto). Por ello no equivale a descargar únicamente los píxeles del AOI. Auxiliares meteorológicos completos se leen si se activa `s2_auxiliary_include`.

Fuentes: [acolite/sentinel2/zarr/l1_convert.py:127](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/zarr/l1_convert.py#L127-L151), [acolite/sentinel2/zarr/l1_convert.py:229](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/zarr/l1_convert.py#L229-L288), [acolite/sentinel2/zarr/l1_convert.py:447](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/zarr/l1_convert.py#L447-L454), [acolite/sentinel2/zarr/l1_convert.py:626](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/zarr/l1_convert.py#L626-L654), [acolite/shared/read_band.py:41](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/shared/read_band.py#L41-L114).

## Comparación

| Criterio | Zarr EOPF remoto | SAFE temporal |
|---|---|---|
| Soporte estático | Sí, contrato concreto | Sí, L1C |
| Fuente completa local | No exigida por lector | Descarga y extracción |
| Lectura espacial | Warp del ROI, más geometría completa | Warp desde JP2 locales |
| Escalado radiométrico | `_eopf_attrs`, escala/offset si uint16 | RADIO_ADD_OFFSET y cuantificación SAFE |
| Geometría | Ruta propia de interpolación/footprints | Ruta SAFE; no idéntica |
| Riesgo | Layout, servicio y formato de URL | RAM de descarga, espacio y extracción |
| Ahorro medido | No medido | No medido |
| Producción validada | No | No para este perfil |

El código demuestra viabilidad, no disponibilidad de 19QGV en agosto de 2026 ni equivalencia numérica. La fase 5 seleccionó SAFE para el ensayo por ausencia de candidatos Zarr. La preferencia condicionada por Zarr quedó retirada el 01-10-2026; ver la sección siguiente.


## Actualización de fase 5 — 29 de septiembre de 2026

La consulta de metadata encontró cinco SAFE L1C de 19QGV y ningún Zarr para el intervalo inicial. SAFE fue la entrada del primer ensayo; Zarr se retiró del wrapper el 01-10-2026. Ver [estrategia de adquisición y evidencia](26_phase5_input_strategy.md). En fase 5 no se descargaron escenas ni se midió rendimiento; los ensayos posteriores están en fases 6/8/10.

## Retirada del wrapper — 01-10-2026

**De dónde sale cada formato.** En ACOLITE, Zarr y SAFE vienen de catálogos distintos:

| Función nativa | Catálogo | Formato entregado | Uso en OCEANOS |
|---|---|---|---|
| `api.cdse.query` / `api.cdse.download` | CDSE OData | SAFE en ZIP | Única entrada Sentinel-2 |
| `api.stac.query` | STAC EOPF/EODC (`stac.core.eopf.eodc.eu`, `sentinel-2-l1c`) | URL Zarr remota | No usado |

CDSE no entrega Zarr. ACOLITE sí puede leer Zarr remoto (`sentinel2.zarr.l1_convert`) sin descarga previa, pero solo si existe la escena en el catálogo EOPF.

**Evidencia (consulta de metadata, 01-10-2026).**

- STAC EOPF con bbox del AOI y sin filtro de fecha: 4 ítems, todos del 2025-04-18 (19QGV, 19QGA, 19QFV, 19QFA). Ninguno en 2026. La colección se actualiza globalmente (extent temporal hasta 2026-10-01): no está descontinuada, pero es un servicio de muestras sin cobertura continua de este AOI.
- CDSE OData para 19QGV L1C, agosto y septiembre de 2026: 15 productos, todos `.SAFE`.

**Decisión.** Zarr no aporta escenas para este AOI. Se eliminó del wrapper para que el flujo sea directo: `search` consulta CDSE (Sentinel-2) o USGS (Landsat) con 3 intentos y esperas de 60 y 300 s; `batch` ejecuta una vez cada producto; no hay consulta STAC, prioridad Zarr ni fallback entre formatos.

**Si se quiere recuperar.** La última versión con soporte Zarr (consulta STAC, prioridad por escena y fallback a SAFE) está en el commit `9af82a6` (`oceanos/native.py`, `oceanos/pipeline.py`, `tests/test_wrapper.py`). Antes de reincorporarlo: comprobar que el STAC EOPF publica fechas recientes para el AOI, ensayar una escena real y validar que la grilla y la radiometría sean coherentes con SAFE (ver [documento 25](25_phase4_aoi_configuration.md)).
