# Zarr remoto: soporte real y comparación de fuentes

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

El código demuestra viabilidad, no disponibilidad de 19QGV en agosto de 2026 ni equivalencia numérica. Mantener preferencia condicionada y fallback. No seleccionar definitivamente la fuente antes de fase 5.


## Actualización de fase 5 — 29 de septiembre de 2026

La consulta de metadata encontró cinco SAFE L1C de 19QGV y ningún Zarr para el intervalo inicial. Se mantiene preferencia Zarr con comprobación al ejecutar; SAFE es la entrada prevista del primer ensayo. Ver [estrategia de adquisición y evidencia](26_phase5_input_strategy.md). No se descargaron escenas ni se midió rendimiento.
