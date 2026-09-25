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

Decisiones abiertas antes de ejecutar: revisión ACOLITE a fijar; tratamiento de OC4; máscara oceánica para FAI/NDVI; evitar reproyección o resolver pérdida de flags/alineación; acceso a metadata CDSE omitida; streaming/reintentos mínimos; disponibilidad Zarr real para período y tile. Estas decisiones se llevan a fases 3–5. Sin selección final ni cambios a la instalación local.
