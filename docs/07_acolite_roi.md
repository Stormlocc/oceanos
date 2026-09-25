# ROI, clipping y máscara terrestre

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

`limit` usa **sur,oeste,norte,este** en grados. Para este AOI: 17.83506768071816, -67.09176880642183, 18.047432637275, -66.40241185767644. Reduce el extent L1R mediante `projection_sub` y el warp de lectura; no es únicamente una máscara posterior.

`region_name` modifica nombres de producto, no geometría. `limit_buffer=None` no extiende el AOI; unidades posibles grados/metros/kilómetros se convierten en `shared.limit.buffer`. `extend_region=False` conserva recorte a cobertura fuente; al mezclar tiles con limit el lector puede forzarlo a True. `l1r_crop=False`; si se activa, run recorta un L1R existente después de conversión, no sustituye reducir lectura inicial.

Advertencia confirmada: `polygon_check` con archivo y `polygon_limit=True` devuelve `polygon_clip=True`, aunque el default general de polygon_clip sea False. Para salida rectangular sin máscara poligonal, candidato mínimo: limit explícito y polygon no enviado a run. El KMZ sigue siendo la fuente de configuración AOI y su hash se conserva.

Fuentes: [acolite/shared/limit/polygon_check.py:35](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/shared/limit/polygon_check.py#L35-L48), [acolite/shared/limit/buffer.py:15](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/shared/limit/buffer.py#L15-L48), [acolite/acolite/acolite_run.py:79](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_run.py#L79-L108), [acolite/acolite/acolite_run.py:187](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_run.py#L187-L194).

## Tierra y calidad

La máscara L2W principal usa rhot SWIR cercano a 1600 nm >0,0215 y flags de cirrus, TOA alta, reflectancia negativa y otros. No es una máscara geográfica exclusiva del océano y puede enmascarar agua muy reflectante. El suavizado por defecto sigma=3 píxeles puede afectar costa. No alterar umbrales todavía.

FAI y NDVI fijan `mask=False`, por lo que la configuración acuática habitual no los deja solo sobre agua. ACOLITE también ofrece `masking.land_water_mask(ncf, add_lakes=True, extend=False, ...)`, que rasteriza GSHHG y opcionalmente HydroLAKES, devuelve array y no aplica automáticamente la máscara a cada producto. Su disponibilidad evita construir un rasterizador propio. Requiere probar metadata de proyección y dataset de costa antes de adoptarlo, especialmente cayos y lagunas.

Fuentes: [acolite/acolite/acolite_flags.py:61](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_flags.py#L61-L147), [acolite/masking/land_water_mask.py:6](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/masking/land_water_mask.py#L6-L125). La máscara cartográfica Natural Earth de fase 1 no se usará como máscara científica a 10 m.
