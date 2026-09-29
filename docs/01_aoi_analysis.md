# Análisis del AOI lapargera_v1 — fase 1

Fecha de análisis: 25 de septiembre de 2026. Fase 1 completada con las limitaciones cartográficas indicadas. No se auditó ni ejecutó ACOLITE.

## Resultado principal

El AOI completo cabe en el footprint nominal Sentinel-2 **19QGV**. También intersecta tres tiles vecinos por sus solapamientos: intersectar varios footprints no implica necesitar un mosaico. El perfil single-tile es espacialmente viable; la cobertura útil de cada adquisición debe verificarse después con su metadata y píxeles válidos.

## Archivo y geometría

Archivo: `config/aoi/lapargera_v1/W2C_South_AOI.kmz`. SHA-256: `e7934bc269e0566f289cc8ab995a5fcb937065ec1b630789f84f226b50f981d5`.

Contiene `doc.kml`, un Placemark `W2C_South` y un Polygon con cinco vértices distintos más cierre, sin huecos. Geometría válida, no vacía, sin reparación. Es casi rectangular, pero no un rectángulo geográfico exacto. Las coordenadas KML están en longitud/latitud WGS84 (orden x/y, equivalente horizontal a EPSG:4326); las altitudes son cero y no se usan para superficie.

| Magnitud | Resultado |
|---|---:|
| Oeste | -67.0917688064° |
| Sur | 17.8350676807° |
| Este | -66.4024118577° |
| Norte | 18.0474326373° |
| Centroide plano lon/lat, orientativo | -66.7469888231°, 17.9413972596° |
| Área geodésica WGS84 | 1.712,231 km² |
| Perímetro geodésico | 192,908 km |
| Ancho del envolvente UTM | 73,332 km |
| Alto del envolvente UTM | 24,301 km |
| Zona | UTM 19 norte, banda MGRS Q |
| CRS proyectado candidato | EPSG:32619, WGS84 / UTM zone 19N |
| Cruce de zonas UTM | No; todo el AOI está entre -72° y -66° |

No debe confundirse el identificador elegido `lapargera_v1` con un límite administrativo: este archivo cubre una franja regional del sur de Puerto Rico.

## Sentinel-2

Intersección geométrica con el KML oficial enlazado en [Copernicus SentiWiki](https://sentiwiki.copernicus.eu/web/s2-products). El archivo de grilla publicado lleva identificador de 2015; consulta y descarga realizadas el 25-09-2026. Se conserva el ZIP original y su checksum.

| Tile | Porcentaje del AOI intersectado | Contiene todo el AOI |
|---|---:|---|
| 19QGV | 100 % | Sí |
| 19QGA | 28,730 % | No |
| 19QFV | 10,519 % | No |
| 19QFA | 2,873 % | No |

Los porcentajes se solapan y no deben sumarse. Selección espacial candidata: 19QGV. No se necesita unir tiles para cubrir este AOI. Todavía no se congela ningún setting ACOLITE: su semántica se verificará en fase 2.

## Landsat WRS-2

Fuente: [capa oficial WRS2 Descending de USGS](https://nimbus.cr.usgs.gov/arcgis/rest/services/Outlines/WRS_Path_Row/MapServer/3). Se consultó por envolvente y luego se calculó la intersección exacta con el polígono, conservando la respuesta GeoJSON.

| Path/Row | Porcentaje del AOI intersectado | Contiene todo el AOI |
|---|---:|---|
| 005/048 | 99,886 % | No |
| 005/047 | 16,877 % | No |

005/048 deja nominalmente fuera cerca de 1,95 km². No asumir cobertura completa ni incorporar mezcla automática: cuando se agregue Landsat se revisarán footprints reales, validez de píxeles y si la pequeña franja afecta el área oceánica objetivo. WRS es una referencia nominal; no garantiza adquisición o cobertura válida de una escena concreta.

## Tierra, agua y costa

Estimación cartográfica de contexto con [Natural Earth Land 5.1.1](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/), escala **1:10 millones**, no resolución de 10 metros.

- Tierra aproximada: 641,67 km², 37,48 % del AOI.
- Complemento acuático aproximado: 1.070,56 km², 62,52 %.
- Longitud de costa representada dentro del AOI: aproximadamente 87,87 km, medida en UTM.

La capa generaliza costa y omite detalles de cayos, lagunas e islas pequeñas. Estas cifras demuestran presencia sustancial de tierra, costa y agua, pero no son inventario preciso ni máscara científica. El complemento de tierra tampoco clasifica por sí mismo océano, lagunas o agua somera. La máscara final se resolverá con ACOLITE en las fases científicas, sin convertir esta referencia en una máscara a 10 m.

## Grilla candidata de 10 m

Se densificaron los segmentos lon/lat a pasos máximos de 0,001° antes de proyectar, para obtener un envolvente que contemple curvatura en UTM. La superficie se calculó separadamente con geodésicas WGS84 entre vértices originales; ambas convenciones son aproximaciones explícitas de los bordes del KML.

Envolvente UTM calculado: xmin 701986,677; ymin 1973043,012; xmax 775319,142; ymax 1997344,379 m.

Propuesta geométrica alineada hacia afuera a múltiplos de 10 m:

| Parámetro | Valor candidato |
|---|---|
| CRS | EPSG:32619 |
| xrange | 701980 a 775320 m |
| yrange | 1973040 a 1997350 m |
| Origen superior izquierdo, borde | 701980, 1997350 m |
| Tamaño de píxel | 10 m × 10 m |
| Shape, filas × columnas | 2431 × 7334 |
| Transformación affine north-up | (10, 0, 701980, 0, -10, 1997350) |
| Primer centro de píxel | 701985, 1997345 m |
| Total de píxeles | 17.828.954 |

Esta es una propuesta geométrica, no una configuración ACOLITE ejecutable ni garantía de su convención de rangos. La auditoría deberá comprobar bordes/centros, alineación y forma obtenida. El pequeño redondeo de extent no es un buffer científico. Una variable float32 de esta forma ocupa aproximadamente 71,32 MB decimales sin compresión; no representa la RAM total de procesamiento.

## Evidencias y verificaciones simples

[evidence/phase1/analysis.json](evidence/phase1/analysis.json) conserva métricas completas; los GeoJSON preservan AOI y footprints locales, y [manifest.json](evidence/phase1/manifest.json) registra tamaños y SHA-256. Se comprobó validez geométrica, cobertura e intersecciones, y se inspeccionó visualmente el mapa. Herramientas: Python del entorno local `acolite`, Shapely 2.1.2 y pyproj 3.8.0. Se utilizaron cálculos de análisis puntuales, sin crear un wrapper ni software del pipeline.

![Mapa de cobertura](evidence/phase1/aoi_coverage.png)

## Decisiones al cerrar fase 1

Mantener el AOI recibido, candidato single-tile 19QGV, EPSG:32619, resolución final Sentinel-2 de 10 m y sin buffer adicional. La grilla propuesta y el manejo terrestre quedan sujetos a comprobación en ACOLITE. La fase 2 requiere una nueva orden del usuario.

## Actualización de fase 4

El [perfil candidato](25_phase4_aoi_configuration.md) adopta recorte nativo sin warp final. projection_sub sobre el bounding box y extent nominal 19QGV produce 2440×7335; esto sustituye la grilla geométrica 2431×7334 como candidata del primer ensayo, no como resultado validado con una escena. Ver el informe para la diferencia de extent y método.
