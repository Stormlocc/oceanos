# Fase 7 — validación del ensayo y diagnóstico del enmascarado

Fecha: 29 de septiembre de 2026. **Revisión técnica completada; escena no aceptada para productos acuáticos con el perfil actual.** La validación científica queda pendiente de datos in situ. No se cambió la configuración científica, no se reprocesó para forzar píxeles válidos y no se avanzó a fase 8.

## Resultado principal

El enmascarado total tiene una explicación técnica comprobada: todos los píxeles de `rhot_1610` superan el umbral nativo `l2w_mask_threshold=0.0215`. El mínimo real es 0,026 y la mediana del recorte es 0,067. Por ello ACOLITE activa el bit SWIR de `l2_flags` en todo el recorte y enmascara Rrs, turbidez, OC3 y NDCI.

No se encontró un error de offset, cuantificación, transferencia TOA entre L1R/L2R o geolocalización en las comprobaciones realizadas. Esto no prueba que toda la cadena científica sea correcta: descarta esas causas concretas dentro del alcance medido.

## Pruebas ejecutadas

El SAFE original declara baseline 05.12, `QUANTIFICATION_VALUE=10000` y `RADIO_ADD_OFFSET=-1000` para las 13 bandas. Se leyeron independientemente los JP2 B02 y B11 con GDAL, se remuestrearon a la misma grilla y se comparó `(DN-1000)/10000` con L1R sobre todo el recorte.

| Comprobación | Resultado |
|---|---|
| Escala SAFE → L1R en B02 | Error máximo absoluto 0 |
| Escala SAFE → L1R en B11 | Error máximo absoluto 0 |
| Conservación de las 13 bandas rhot entre L1R y L2R | Igualdad completa, lectura por bloques |
| Lon/lat frente a coordenadas UTM transformadas independientemente | Error máximo 0,000003813 grados; dentro de tolerancia 0,00001 |
| SWIR sobre umbral nativo en todo el recorte | Confirmado |
| Bit SWIR activo en todo L2W | Confirmado |

Las seis pruebas pasaron como comprobaciones de contrato y diagnóstico. **No equivalen a seis pruebas de aceptación científica:** confirman también la condición que hace inutilizables los productos acuáticos de este ensayo. Las comprobaciones previas de grilla, variables y archivos están conservadas en fase 6.

Script reproducible: [validate_scene.py](evidence/phase7/validate_scene.py). Resultado: [contract_checks.json](evidence/phase7/contract_checks.json). Se ejecutó con el entorno activado mediante micromamba, sin nuevas dependencias ni cambios al código de ACOLITE.

## Evidencia espacial y posible brillo solar

![Diagnóstico RGB, SWIR y geometría](evidence/phase7/diagnostic.png)

La inspección visual muestra costa y océano en la ubicación esperada, con SWIR elevado también sobre el agua. Como apoyo diagnóstico se muestreó cada 20 píxeles (200 m) y se separó tierra mediante la cartografía Natural Earth ya disponible. Esa cartografía es aproximada y **no constituye la máscara operacional a 10 m**. Se analizaron 27.613 puntos clasificados como agua por esa referencia gruesa.

En esa muestra, el SWIR tiene mediana 0,0604. El ángulo calculado por la función nativa `shared.glint_angle` varía aproximadamente de 17,73° a 22,35°, con mediana 19,75°. La configuración auditada usa 40° como umbral de su opción de activación de corrección de glint por geometría. Por tanto, la geometría señala riesgo de brillo solar y justifica investigarlo, **pero no demuestra que el glint sea la causa única del SWIR elevado**. No se separaron cuantitativamente sus contribuciones de atmósfera, oleaje u otros efectos.

Fuentes de la revisión ejecutada: [glint_angle](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/shared/glint_angle.py), [settings de glint](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/config/defaults.txt#L350), [activación por geometría en L2R](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2r.py#L1501).

## Decisión sobre parámetros y productos

Se mantiene el perfil sin cambios científicos. Subir el umbral hasta obtener datos o desactivar la máscara haría aparecer valores, pero no demostraría calidad del agua recuperada correctamente. Tampoco basta activar `dsf_residual_glint_correction`: la máscara acuática L2W se calcula sobre **rhot TOA**, no sobre rhos corregida. Una evaluación de glint deberá considerar conjuntamente reflectancias, selección de agua y flags, con un experimento separado y trazable.

La implementación nativa de la máscara está en [acolite_flags](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_flags.py#L57), y su aplicación a los productos en [acolite_l2w](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L175).

| Aspecto | Dictamen |
|---|---|
| Descarga, integridad y archivos | Aprobado técnicamente en este ensayo |
| Grilla y geolocalización | Coherentes con AOI y perfil |
| Rrs, turbidez, OC3 y NDCI | No aceptados: cero píxeles válidos |
| FAI y NDVI | Presentes, pero sin validación científica ni máscara exclusivamente oceánica |
| Exactitud radiométrica y bioóptica | No demostrada por estas pruebas |
| Limpieza de ZIP/SAFE/L1R | No autorizada por estos resultados; conservar |
| Perfil para todas las fechas | Sigue candidato; una escena no valida todo el intervalo |

El estado recomendado para el catálogo futuro es `sin_pixeles_acuaticos_validos`, separado de un fallo de descarga o de ejecución. La escena no se elimina del historial ni se descarta por nubosidad del catálogo. Su falta de píxeles acuáticos útiles se registra como resultado de calidad posterior al procesamiento.

## Pendientes y límite de fase

Se requiere validación científica independiente: observaciones coincidentes de turbidez/clorofila, ubicación, profundidad, hora y control de calidad, si están disponibles. No se recibieron datos in situ y no se inventan tolerancias de aceptación.

Antes de promover un perfil revisado conviene realizar un ensayo separado de corrección de glint y máscara acuática nativa, con comparación espacial y espectral; eso permanece pendiente, sin adoptar parámetros nuevos aquí. La evaluación de otras fechas tampoco se ejecutó: el procesamiento repetido corresponde a su fase autorizada.

La revisión técnica de fase 7 queda entregada con dictamen no aceptado para los productos acuáticos. La validación científica sigue abierta. No se inició el análisis de benchmark de fase 8 ni se limpiaron fuentes.
