# L1R, alineación Sentinel-2 y Landsat

> Estado vigente (30-09-2026): L1R persistente y regeneración implementados; grilla común comprobada con cinco Sentinel-2 y tres Landsat. Landsat proyecta L1R antes de AC y no vuelve a proyectarlo al derivar. Véanse [multifecha](31_phase10_multidate.md) y [conservación](33_retention_and_reset.md).

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

## Sentinel-2 SAFE

`projection` deriva CRS y grillas 10/20/60 m del metadata del granule, usando `s2_target_res` para elegir destino. `l1_convert` recorta al ROI, conserva proyección UTM nativa y usa `res_method='average'` en GDAL Warp para llevar bandas a la grilla destino. Conservar este mecanismo nativo; 10 m no transforma bandas gruesas en observaciones de mayor detalle.

Geometría por defecto: `output_geometry=True`, `geometry_type=grids_footprint`, `geometry_res=60`, no per-band, no fixed footprint. SAFE usa nearest para rasterizar/leer detector footprints de geometría, mientras la ruta Zarr tiene diferencias de interpolación. No asumir equivalencia de píxeles entre fuentes.

L1R contiene `rhot_*`, lon/lat, geometría seleccionada, atributos sensor/isodate/granule y proyección NetCDF. Aplica RADIO_ADD_OFFSET y cuantificación en SAFE. El lector Zarr escala según dtype y atributos EOPF; una metadata fill_value ausente podría dejar data_mask sin inicializar: limitación de contrato, no fallo real reproducido.

Fuentes: [acolite/sentinel2/projection.py:48](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/projection.py#L48-L88), [acolite/sentinel2/l1_convert.py:217](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/l1_convert.py#L217-L283), [acolite/sentinel2/l1_convert.py:669](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/l1_convert.py#L669-L689), [acolite/sentinel2/zarr/l1_convert.py:638](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/sentinel2/zarr/l1_convert.py#L638-L659).

## Landsat separado

Lee Collection 2 mediante MTL, exige nivel L1, obtiene tamaño reflectivo de GRID_CELL_SIZE_REFLECTIVE y CRS/UTM del MTL. `landsat.projection` interpreta esquinas con ajuste de medio píxel; upstream expresa dimensiones (x,y), a diferencia de la revisión local comparada. `l1_convert` usa nearest, no el average de S2. Puede producir PAN y thermal además de reflectivas, según settings; revisarlos para no conservar productos innecesarios.

Tier 1 es un criterio de selección del catálogo, no una restricción automáticamente impuesta por este lector. NDCI no será trasladable a Landsat mediante simple remuestreo: falta la banda red-edge y el código no lo habilita para OLI.

Fuentes: [acolite/landsat/projection.py:12](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/landsat/projection.py#L12-L25), [acolite/landsat/projection.py:72](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/landsat/projection.py#L72-L107), [acolite/landsat/l1_convert.py:87](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/landsat/l1_convert.py#L87-L101), [acolite/landsat/l1_convert.py:333](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/landsat/l1_convert.py#L333-L335).

## Política vigente de conservación

L1R pasa a ser el intermedio persistente para regeneración: conservar bandas TOA, geometría y metadata completas. Para Landsat retener el L1R ya proyectado y no remuestrearlo de nuevo. Regenerar L2W repite la corrección atmosférica; L2R permanece temporal. Ver [decisión transversal](33_retention_and_reset.md).
