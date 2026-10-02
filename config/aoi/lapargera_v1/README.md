# Perfil científico lapargera_v1

`project.yaml` expresa el contrato OCEANOS; **ACOLITE no interpreta este YAML**. El wrapper de fase 11 interpreta este perfil y ejecuta ACOLITE; ver [operación](../../../README.md). No hay archivos de settings de ACOLITE en el perfil: el wrapper genera los settings nativos desde los YAML (`region_name`, `limit`, `l2w_parameters` y, en Landsat, la proyección de L1R y `dsf_tile_dimensions`) y añade valores fijos (sin RGB ni borrado nativo). Todo lo demás conserva los defaults de la revisión auditada.

El KMZ es la geometría original; no se alteró. El límite enviado a ACOLITE está en orden sur, oeste, norte, este y produce un recorte rectangular. No se pasa `polygon`, porque la ruta auditada de polygon_limit activa clipping.

## Configuración vigente

- Sentinel-2 L1C, tile 19QGV, 1–14 agosto 2026 inclusive en UTC (fin exclusivo 15 de agosto); nubosidad del catálogo desactivada.
- Revisión fijada ACOLITE `80da0c0c681d9597fd4b7737837d6a3e61907b33`. No ejecutar silenciosamente con otra revisión: los defaults locales difieren.
- DSF, auxiliares, gases, geometría y compresión: conservar defaults por plataforma de esa revisión.
- Resolución 10 m, merge_tiles=False, sin buffer y sin reproyección final. Estos valores ya son defaults, por eso el wrapper no los envía.
- Conservar L1R y L2W; L2R es temporal hasta el QA técnico y registro en SQLite. Regenerar desde L1R repite AC.
- No activar borrado nativo de NetCDF. El wrapper elimina RAW/L2R después del QA técnico y registro; remove_zip=False y remove_tar=False evitan borrado anticipado.
- OC4 excluido por decisión del usuario del 29 de septiembre de 2026; OC3 permanece activo.
- FAI/NDVI permanecen sin máscara acuática nativa; una salida exclusivamente oceánica para todas las variables sigue pendiente. El usuario permite conservar tierra y aplicar filtro posteriormente.

## Grilla verificada técnicamente

La grilla calculada con projection_sub y confirmada con escenas reales es EPSG:32619, 2440 filas × 7335 columnas, xrange 701980–775330 m y yrange 1997360–1972960 m. Es distinta del envolvente del polígono calculado en fase 1: ahora se recorta su bounding box geográfico y se usa la alineación nativa de ACOLITE.

La grilla fue confirmada con cinco SAFE y tres Landsat en fase 10. Zarr no se usa; si se reincorpora, debe producir coordenadas/extent coherentes; cualquier diferencia requiere revisión antes de publicar o acumular fechas. No tolerar silenciosamente un desplazamiento de medio píxel.

Landsat dispone de `landsat.yaml`, con intervalo vigente 1–20 de agosto de 2026 (fin exclusivo 21), probados técnicamente en tres adquisiciones; la aprobación científica permanece pendiente. Ver [cierre de fase 10](../../../docs/31_phase10_multidate.md).

Detalles y límites: [informe de fase 4](../../../docs/25_phase4_aoi_configuration.md).

## Ensayo real de fase 6

La grilla candidata fue confirmada con la escena del 4 de agosto. L1R, L2R y L2W se generaron, pero Rrs, turbidez, OC3 y NDCI quedaron totalmente enmascarados. El perfil conserva estado candidato; no modificar umbrales ni declarar aceptación científica. Ver [informe de fase 6](../../../docs/27_phase6_first_scene.md).

Los ensayos históricos usaron 1–20 de agosto para ambos sensores; cambiar el intervalo actual no altera sus resultados. No descargar escenas, LUT, auxiliares ni dependencias sin autorización. `run` y `derive` pueden solicitar auxiliares aun con entrada local; el CLI no bloquea la red.
