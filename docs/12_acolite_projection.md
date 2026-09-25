# Grilla y proyección

No existe una grilla universal obligatoria. Derivar EPSG de la ubicación; extensión y origen del AOI alineados a una grilla. Para Sentinel-2 MVP, resolución final 10 m. Landsat futuro deberá coincidir en una grilla común cuya resolución se decidirá al incorporarlo.

Cada adquisición y producto comparable debe coincidir en CRS, origen, resolución, extent, shape y coordenadas. No basta con que comparta EPSG y tamaño de píxel.

Preferencia de flujo: alineación interna necesaria → corrección atmosférica → L2R/L2W → una reproyección final si corresponde. Verificar `reproject_before_ac` y comportamiento real antes de establecer overrides.

Auditar todos los settings `output_projection*`, rangos x/y, unidades, alineación y resolución por defecto. `output_projection_resolution_align` no se considera garantía suficiente sin inspección.

Examinar `project_acolite_netcdf.py`: carga de datasets, apilado, copias, buffers de resampling y manejo de tipos. Verificar que flags categóricos no sufran interpolación inapropiada.

Comparar L2R+L2W proyectados con solo L2W proyectado, manteniendo requisitos de reutilización. Co-registration por contenido queda fuera del MVP.

## Actualización después de fase 1

El análisis de `01_aoi_analysis.md` confirma cobertura completa con 19QGV y ausencia de cruce UTM. EPSG candidato: 32619. Grilla geométrica propuesta: xrange 701980–775320 m, yrange 1973040–1997350 m, 2431 filas × 7334 columnas a 10 m. Estas mediciones resuelven los pendientes espaciales anteriores; su traducción a settings ACOLITE sigue pendiente. Landsat 005/048 cubre nominalmente 99,886 %, no el AOI íntegro.
