# Recursos y benchmark

Entorno declarado: Intel Core i9 de 13.ª generación, 16 GB RAM físicos, WSL Ubuntu sobre Windows 11, asignación dinámica de RAM, WSL 2.6.1.0, aproximadamente 100 GB SSD libres y conexión de 100 Mbps. Presupuesto máximo de temporales: 50 GB. Estos valores no sustituyen mediciones del entorno efectivo.

Procesar una escena a la vez. Ya existen mediciones de una escena SAFE, analizadas en [fase 8](29_phase8_benchmark.md): procesamiento 519,38 s, RSS máximo 4,74 GB y ocupación final 3,42 GB. Los productos acuáticos no fueron aceptados; estos resultados no representan todavía la producción de una escena científicamente válida.

## Plan de medición

Instrumentar la primera escena desde adquisición para medir consulta, descarga, extracción, L1R, L2R, L2W, proyección y duración total. Obtener tiempos de etapas solo si son observables de manera fiable en logs o puntos de ejecución; indicar no disponible en otro caso.

Medir bytes transferidos cuando sea posible, tamaño adquirido, pico de RAM incluyendo subprocesos, pico de disco temporal y tamaños L1R/L2R/L2W. Registrar espacio persistente final después de limpieza, dependencias, fuente, revisión ACOLITE y configuración.

Para disco medir simultáneamente descarga, extracción, intermedios y salida todavía no validada. No sumar tamaños finales como sustituto del pico. Para RAM distinguir RSS del proceso y memoria efectiva de WSL; registrar método y frecuencia de muestreo.

Una conexión nominal de 100 Mbps equivale teóricamente a 12,5 MB/s, antes de sobrecarga y límites del proveedor. No es una predicción del tiempo real de descarga.

Evaluar NetCDF, compresión y discretización en código antes de cambiar defaults. No usar pérdida de precisión para ahorrar disco sin justificación científica. GeoTIFF solo para inspección o exportación específica.

## Resultados de auditoría de fase 2

`output.nc_write` usa compresión zlib controlada por settings; upstream actual tiene compresión=True y nivel=4, mientras la instalación local tiene False. Discretisation=False y least_significant_digit=None evitan cuantización explícita por defecto. El escritor puede convertir Float64 a Float32 si no se solicita double; no describir el formato como preservación bit a bit de todos los intermediarios. NetCDF projection agrega coordenadas y grid_mapping. Fuente: [acolite/output/nc_write.py:72](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/output/nc_write.py#L72-L91), [acolite/output/nc_write.py:231](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/output/nc_write.py#L231-L281).

GeoTIFF está desactivado por defecto para L1R/L2R/L2W. Sin embargo rgb_rhot/rgb_rhos=True genera mapas RGB PNG aunque map_l1r/map_l2r=False; candidato desactivarlos si no se requieren. No confundir esos PNG con GeoTIFF.

Entorno inspeccionado: GDAL 3.13.3 con drivers JP2OpenJPEG, netCDF y Zarr disponibles; Python packages numpy 2.5.3, netCDF4 1.7.4, pyproj 3.8.0, pyresample 1.35.0, zarr 3.3.0, fsspec 2026.7.0, aiohttp 3.14.3, scipy 1.18.1. Existencia/import de drivers no prueba una escena EOPF remota.

La ruta project_acolite_netcdf apila datasets y hace copias; la descarga nativa CDSE/EarthExplorer no usa streaming explícito. Ambos factores justifican mantener concurrencia uno y medir RAM. LUT/auxiliares también ocupan disco. No hay benchmark ejecutado en fase 2.


## Resultado de fase 6

El ensayo real generó los tres NetCDF y confirmó la grilla, pero dejó todos los productos acuáticos enmascarados. Recursos y evidencia están en [el informe de fase 6](27_phase6_first_scene.md). No hay aceptación científica ni limpieza autorizada. El diagnóstico corresponde a fase 7.

## Actualización de fase 10

Ocho adquisiciones completadas (cinco Sentinel-2 y tres Landsat), con grilla común y flags comprobados. Inventario final 27,84 GB; máximo RSS individual 6,57 GB. El acceso USGS y la alineación Landsat quedaron resueltos; la aceptación científica y el ensayo Zarr siguen pendientes. No se inició fase 11. Ver [informe y evidencias](31_phase10_multidate.md).
