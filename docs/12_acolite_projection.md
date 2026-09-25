# Proyección: grilla, memoria y flags

Auditoría estática de fase 2, 25-09-2026. Revisión `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Pendiente de validación con escena real.

## Ruta invocada por run

`acolite_run` llama a `output.project_acolite_netcdf` tanto para opción previa como final. Con defaults output_projection=False no se proyecta; reproject_outputs=L1R,L2R,L2W solo aplica cuando se activa proyección. Mantener reproject_before_ac=False evita el warp adicional previo, pero no elimina la alineación interna de bandas que el lector necesita.

Fuente: [acolite/acolite/acolite_run.py:161](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_run.py#L161-L175), [acolite/acolite/acolite_run.py:283](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_run.py#L283-L298).

## Contrato exacto para rangos

`output_projection_resolution` debe tener dos elementos; la función cambia el signo del segundo internamente. Candidato: `10,10`, no escalar 10 ni 10,-10. EPSG se trata como string; en diccionario usar `'32619'` o `'EPSG:32619'`.

`output_projection_metres=True` permite rangos explícitos; xrange oeste→este y **yrange norte→sur**. Para la propuesta fase 1: xrange=701980,775320; yrange=1997350,1973040. Documentación geométrica previa mostraba ymin/ymax ascendente: eso no es el orden de entrada a esta función.

Con `output_projection_resolution_align=True`, los rangos ya alineados producen xrange=701980,775330 y yrange=1997350,1973050: 2430×7335, frente al esperado 2431×7334. Se reprodujo ejecutando únicamente el bloque AST original. La suma de un píxel en xmax y el cálculo de y explican la diferencia. Para rangos fijados externamente y comprobados, candidato `output_projection_resolution_align=False`. Aún debe probarse una salida real.

Fuentes: [acolite/output/project_acolite_netcdf.py:87](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/output/project_acolite_netcdf.py#L87-L201). Evidencia: `evidence/phase2/alineacion_reproducida.json`. Alineación=True por sí sola no fija CRS, origen, extensión ni forma.

## RAM y flags

La función lee todos los datasets 2D —incluyendo geolocalización y flags— y los incorpora con `np.dstack` repetido. Coexisten arrays, pila, copias y estructuras de vecinos/resampling. No es procesamiento por chunks. Bilinear es default, radius=3 píxeles, epsilon=0, neighbours=32. También implementa nearest. Fillnans=False por default evita rellenar huecos; activarlo convierte ceros en NaN y rellena hasta filldistance, por lo que no es un ahorro inocuo.

Al escribir, **omite l2_flags** explícitamente. Seleccionar nearest no soluciona esa omisión. Por tanto, L2W proyectado solo no satisface conservar flags interpretables sobre su grilla. Mantener el original y resolver la estrategia antes de configuración final.

Para 17.828.954 píxeles, cada banda float32 sin compresión ocupa 71,32 MB decimales; 30 bandas suman 2,14 GB antes de copias, vecinos y salida. Mezclar dtypes puede promover la pila. Es una cota de arrays, no estimación fiable del pico. Comparar L2R+L2W proyectados contra solo L2W, y considerar evitar reproyección si el recorte single-tile ya satisface la grilla estable.

Fuentes: [acolite/output/project_acolite_netcdf.py:228](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/output/project_acolite_netcdf.py#L228-L246), [acolite/output/project_acolite_netcdf.py:278](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/output/project_acolite_netcdf.py#L278-L341).

## Otra función nativa

`reproject_acolite_netcdf(ncf,dct,...,warp_alg='bilinear')` trabaja un dataset a la vez mediante GDAL, pero fuerza Float32 para buffers, comparte interpolación para todas las variables, usa add_half_pixel=False y no resuelve automáticamente el contrato de flags/geometría. No sustituir a ciegas la ruta general. Fuente: [acolite/output/reproject_acolite_netcdf.py:7](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/output/reproject_acolite_netcdf.py#L7-L114).

La prioridad es comprobar grilla nativa de 19QGV en varias fechas antes de introducir un warp redundante. Si se demuestra una limitación, emplear función nativa y un ajuste mínimo específico, nunca construir un motor propio. Co-registration permanece fuera del MVP.
