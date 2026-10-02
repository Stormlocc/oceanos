# Fase 6 — ensayo real del 4 de agosto de 2026

> Informe histórico. Estado vigente al 30-09-2026: diagnóstico completado en fase 7; repetición y wrapper completados en fases 10/11. RAW, NetCDF y registros independientes de este ensayo fueron retirados; quedan resumen y hashes históricos. Rige la [política L1R/L2W y reinicio](33_retention_and_reset.md); las cifras y decisiones originales no describen la disponibilidad actual de archivos.

Fecha: 29 de septiembre de 2026. **Ejecución completada; productos acuáticos no aceptados para uso científico.** Se generaron L1R, L2R y L2W, pero todos los píxeles de Rrs, turbidez, OC3 y NDCI quedaron enmascarados. FAI y NDVI contienen valores. No se cambiaron máscaras ni parámetros para forzar un resultado y en ese ensayo no se inició la fase 7, completada posteriormente.

## Entrada y entorno

Escena: `S2B_MSIL1C_20260804T150719_N0512_R082_T19QGV_20260804T182348.SAFE`, identificador CDSE `59d2d637-7e0f-4c84-bb72-c592660b033c`. Se repitió la consulta Zarr: sin resultados, fallback SAFE informado. La autenticación CDSE respondió HTTP 200. Las credenciales se usaron por la función nativa, sin mostrarlas ni copiarlas a la evidencia.

Revisión ejecutada: `80da0c0c681d9597fd4b7737837d6a3e61907b33`, desde `.work/acolite-audit`, con el entorno `/home/antho/micromamba/envs/acolite`. No se actualizó la instalación anterior ni se alteró el código científico de ACOLITE. Se usó el perfil versión 2, sin OC4; su copia está en la evidencia. La versión 3 solo actualiza el estado observado del ensayo y de la grilla.

Se comprobaron 789.574.421 bytes del ZIP y su MD5 publicado. SHA-256 calculado: `57145c15556f5f5c129249d079dd42e62cf5aaad4b3432d3c2d508633826d968`. El SAFE se extrajo mediante ACOLITE. El ZIP y el SAFE se conservaron entonces y fueron retirados en el reinicio posterior.

## Incidencia y reanudación

El primer intento descargó y verificó correctamente el ZIP, pero falló en L1R porque se invocó Python sin activar completamente el entorno: GDAL no pudo abrir la base PROJ. Se comprobó que `PROJ_DATA` resolvía EPSG:32619 y se reanudó mediante `micromamba run`. No hizo falta reinstalar paquetes ni cambiar algoritmos. El segundo intento reutilizó el ZIP y completó el procesamiento. Los logs y métricas se registraron por separado; los archivos independientes se retiraron al consolidar el historial.

Comando del ensayo reanudado, desde la raíz del proyecto:

```bash
/home/antho/.local/bin/micromamba run   -p /home/antho/micromamba/envs/acolite   python -u .work/phase6_trial.py
```

El script manual original instrumentó funciones nativas, timeout HTTP y medición cada cinco segundos para una escena con directorios fijos. Fue retirado; el [registro de consolidación](33_retention_and_reset.md#historial) no contiene una copia ejecutable. El wrapper posterior de fase 11 sustituye esa instrumentación manual.

## Archivos y comprobaciones

Directorio de salida: `.work/phase6_20260804/output/`. Prefijo común: `S2B_MSI_2026_08_04_15_08_03_T19QGV_lapargera_v1_`.

| Producto | Tamaño (bytes) | Resultado |
|---|---:|---|
| L1R.nc | 314.882.514 | Legible; 13 bandas rhot |
| L2R.nc | 773.895.782 | Legible; conserva rhot y 11 bandas rhos |
| L2W.nc | 121.980.380 | Variables solicitadas presentes; productos acuáticos totalmente enmascarados |

Grilla real común de los tres archivos: EPSG:32619, 2440×7335, píxel 10,-10 m, borde x=701980–775330 e y=1997360–1972960. Centros extremos x=701985–775325 e y=1997355–1972965. Coincide con la candidata; no se ejecutó reproyección final.

Cuatro comprobaciones estructurales pasaron: lectura de NetCDF, productos obligatorios presentes, grilla candidata y coordenadas comunes. **La comprobación de píxeles acuáticos válidos no pasó.** Se registró el resultado sin aceptar éxito científico parcial. No se evaluaron aún exactitud radiométrica, plausibilidad, equivalencia entre fuentes o máscara oceánica final.

| Grupo | Píxeles finitos |
|---|---:|
| Cada una de las 11 bandas Rrs | 0 |
| TUR_Nechad2009_665, chl_oc3, ndci | 0 |
| fai, ndvi | 17.897.400 cada uno (100 %) |

`l2_flags` está presente. El bit 0, correspondiente al umbral nativo no acuático SWIR, está activo en el 100 % del recorte. Los valores de flags observados son 1, 5 y 7. Esto identifica la condición que enmascara la salida; **no demuestra que todo el AOI sea tierra ni explica todavía la causa física o radiométrica**. FAI/NDVI no reciben esa máscara nativa, por lo que su presencia no prueba que los productos acuáticos estén correctos. El diagnóstico se completó después en fase 7; no se relajó el umbral de forma arbitraria.

La hora de catálogo es 15:07:19.024 UTC y la hora del gránulo que ACOLITE guarda es 15:08:03.261575 UTC. Ambas se conservan, junto con el identificador original, sin deduplicar por el nombre de salida.

## Mediciones observadas

| Etapa | Duración |
|---|---:|
| Descarga SAFE, primer intento | 368,03 s |
| Extracción, intento completado | 1,13 s |
| L1R | 38,44 s |
| L2R, incluyendo preparación de LUT | 423,06 s |
| L2W | 57,85 s |
| Procesamiento total completado | 519,38 s (8 min 39 s) |

El segundo intento registra descarga ≈0 s porque reutilizó el ZIP; no es una medición de transferencia remota. Los tiempos de tabla no incluyen toda la intervención para resolver el entorno. La caché de LUT estaba inicialmente sin preparar: el tiempo L2R no predice una ejecución posterior con caché.

Máximo RSS del proceso informado por Linux: 4.744.155.136 bytes (4,74 GB decimales). Pico muestreado del árbol de procesos: 4.612.444.160 bytes. Disco máximo muestreado: 3.360.989.947 bytes; medición al finalizar: 3.419.458.515 bytes (3,42 GB). El muestreo puede omitir picos entre lecturas; el valor final es mayor que el último pico muestreado y se conserva por separado.

El alcance de disco incluye RAW, salidas, scratch y toda la carpeta data de la copia auditada, incluida su base preexistente; es conservador respecto del temporal nuevo. Permaneció por debajo de 50 GB. WSL presentó aproximadamente 7,6 GiB de RAM y el disco C: tenía unos 374 GB libres al inicio. El espacio libre virtual de WSL no se tomó como espacio físico del host. No se midieron bytes reales de red ni picos totales de memoria de Windows. Estas son mediciones del ensayo, no el análisis de benchmark de fase 8.

## Evidencia y conservación

- [Resultado resumido — evidencia consolidada](33_retention_and_reset.md#historial), [métricas — evidencia consolidada](33_retention_and_reset.md#historial) y [primer intento — evidencia consolidada](33_retention_and_reset.md#historial).
- [Comprobaciones y hashes NetCDF — evidencia consolidada](33_retention_and_reset.md#historial), [conteo de flags — evidencia consolidada](33_retention_and_reset.md#historial) y [comprobación técnica reproducible — evidencia consolidada](33_retention_and_reset.md#historial).
- [Metadata de origen — evidencia consolidada](33_retention_and_reset.md#historial), [consultas públicas — evidencia consolidada](33_retention_and_reset.md#historial), [dependencias — evidencia consolidada](33_retention_and_reset.md#historial) e [inventario de 38 archivos LUT — evidencia consolidada](33_retention_and_reset.md#historial).
- Settings nativos e inventario de hashes registrados durante el ensayo; archivos de evidencia retirados después. Los hashes de LUT describen recursos disponibles, sin demostrar exhaustivamente cuáles fueron consumidos por la escena.

En el cierre original se conservaron NetCDF, ZIP, SAFE y L1R fuera de Git. Posteriormente se implementó SQLite y se retiraron esos archivos y los JSON independientes por orden de reinicio. La procedencia útil y los resultados históricos permanecen en el catálogo; no son productos científicos publicados.

## Siguiente paso

Fase 6 termina con la incidencia explícita de enmascarado total. La fase 7 posterior revisó reflectancias, escala radiométrica y el flag SWIR sin cambiar umbrales para forzar resultados. Sigue pendiente disponer de datos in situ para validación científica; las comprobaciones de archivos no los sustituyen.
