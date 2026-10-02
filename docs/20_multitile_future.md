# Nuevos AOI y mult tile

Cada AOI requiere análisis independiente. No heredar automáticamente EPSG, extensión, grilla, algoritmos ni estrategia de entrada de `lapargera_v1`.

La condición single-tile de lapargera_v1 está confirmada con 19QGV. Para cada nuevo AOI debe comprobarse de nuevo; no activar mezcla silenciosamente.

Para futuros AOI múltiples tiles, auditar `merge_tiles`, `merge_full_tiles`, `extend_region`, `max_merge_time`, tiempos de adquisición, cruces UTM y comportamiento de proyección. Los nombres y defaults deberán verificarse en la revisión elegida.

No construir todavía lógica mult tile, caché compartida ni contabilidad de referencias entre AOI. Volver a descargar una escena para otro AOI es aceptable.

## Actualización después de fase 1

El análisis de `01_aoi_analysis.md` confirma cobertura completa con 19QGV y ausencia de cruce UTM. EPSG candidato: 32619. Grilla geométrica propuesta: xrange 701980–775320 m, yrange 1973040–1997350 m, 2431 filas × 7334 columnas a 10 m. Estas mediciones resuelven los pendientes espaciales anteriores; su propuesta de grilla fue sustituida por la grilla nativa 2440×7335, x 701980–775330 e y 1997360–1972960, verificada en fases 6/10. Landsat 005/048 cubre nominalmente 99,886 %, no el AOI íntegro.

## Resultados de auditoría de fase 2

Los lectores SAFE/Zarr ya implementan merge_tiles, merge_full_tiles, extend_region y controles de sensor/tiempo; max_merge_time aparece como argumento de lector (600 s), no debe inventarse como setting global sin seguir su propagación. Para nuestro AOI merge_tiles=False ya es default y single-tile está confirmado. No activar mezcla ni extrapolar cruces UTM a partir de un caso sin cruce.

## Política vigente de conservación

Un L1R recortado no permite ampliar después el AOI ni recuperar bandas descartadas. Un AOI más grande puede requerir fuentes nuevas; conservar L1R no implica reutilización universal. Ver [decisión transversal](33_retention_and_reset.md).
