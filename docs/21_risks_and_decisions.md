# Riesgos y decisiones pendientes

| Riesgo o incertidumbre | Acción prevista |
|---|---|
| AOI no confirma single-tile | Resolver en fase 1 antes de fijar perfil |
| Instalación local distinta de upstream | Identificar ambas revisiones y diferencias |
| Productos solicitados incompatibles | Presentar alternativas sin sustituir automáticamente |
| Máscara de agua elimina señal útil | Revisar FAI/NDVI y aguas someras explícitamente |
| RAM insuficiente | Una escena, recorte apropiado y medición de proyección |
| Temporales superan 50 GB | Presupuesto previo y seguimiento durante ejecución |
| Zarr no disponible o incompatible | Reintentos acotados y fallback informado |
| Fuente cambia sin checksum fuerte | Preservar incertidumbre y metadata/versiones |
| Outputs insuficientes para nuevas variables | Verificar dependencias antes de evitar descarga |
| Falta validación in situ | Recordatorio obligatorio antes de fase 7 |
| Persistencia sin respaldo | Definir destino de backup más adelante |

Pendientes técnicos: EPSG, MGRS/WRS, extent y origen; versión ACOLITE; firmas API; defaults efectivos; soporte de productos; origen de auxiliares; comparación de fuentes; grilla Landsat; formato definitivo de catálogo; selección L2R/L2W; límites de aceptación científica y métricas reales.

No se necesitan más preguntas de Discovery para documentar el alcance. Los pendientes técnicos deben resolverse mediante las fases autorizadas, no mediante supuestos presentados como hechos.

## Actualización después de fase 1

El análisis de `01_aoi_analysis.md` confirma cobertura completa con 19QGV y ausencia de cruce UTM. EPSG candidato: 32619. Grilla geométrica propuesta: xrange 701980–775320 m, yrange 1973040–1997350 m, 2431 filas × 7334 columnas a 10 m. Estas mediciones resuelven los pendientes espaciales anteriores; su traducción a settings ACOLITE sigue pendiente. Landsat 005/048 cubre nominalmente 99,886 %, no el AOI íntegro.

## Resultados de auditoría de fase 2

Pendientes resueltos: defaults y precedencia identificados; firmas/retornos API auditados; soporte L1C SAFE/EOPF confirmado en código; OC4 no configurado para MSI; EPSG/MGRS/grilla geométrica ya calculados en fase 1.

Actualización del 29 de septiembre: revisión ACOLITE fijada en fase 4; OC4 excluido por el usuario; ensayo sin reproyección final; fase 5 consultó Zarr (sin resultados) y CDSE (cinco SAFE). Siguen pendientes la máscara oceánica para FAI/NDVI, preparar el entorno de la revisión elegida, comprobar autenticación de descarga, validar recursos y ejecutar el ensayo. El diseño de captura de metadata/reintentos aún no está implementado. La instalación local no se modificó.

## Actualización de fase 3

Resuelto el formato de persistencia: SQLite único, metadata seleccionada en JSON interno y archivos científicos externos. Definidas identidad, cambios, recuperación y reutilización. Se eligió una extensión futura opcional del retorno CDSE para evitar un cliente propio; aún no implementada. Se documenta explícitamente que UTC es la convención del intervalo y que identidad incompleta impide deduplicación científica automática.


## Resultado de fase 6

El ensayo real generó los tres NetCDF y confirmó la grilla, pero dejó todos los productos acuáticos enmascarados. Recursos y evidencia están en [el informe de fase 6](27_phase6_first_scene.md). No hay aceptación científica ni limpieza autorizada. El diagnóstico corresponde a fase 7.


## Revisión de fase 7

Se confirmó que el SWIR TOA supera el umbral en todo el recorte; las pruebas de escala SAFE/L1R, continuidad TOA y geolocalización pasaron. El brillo solar es una hipótesis compatible con la geometría, no una causa única demostrada. No se cambiaron parámetros; los productos acuáticos siguen no aceptados. Ver [dictamen y evidencia](28_phase7_validation.md).
