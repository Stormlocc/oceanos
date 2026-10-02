# Fase 4 — configuración científica candidata de lapargera_v1

> Informe histórico. Estado vigente al 30-09-2026: perfil ensayado en cinco Sentinel-2 y tres Landsat, grilla verificada y ciencia pendiente. Sentinel-2 usa ahora 1–14 de agosto; Landsat conserva 1–20. Los JSON/manifiestos de la entrega se retiraron. Rige la [política L1R/L2W y reinicio](33_retention_and_reset.md); las cifras y decisiones originales no describen la disponibilidad actual de archivos.

Fecha: 25 de septiembre de 2026. Estado actualizado el 29 de septiembre: **fase 4 cerrada como configuración candidata; OC4 excluido por decisión del usuario**. Al cierre de fase 4 faltaba el ensayo; después se completó técnicamente en fases 6/10 y la ciencia sigue pendiente. La continuación autorizada de fase 5 está en el informe 26.

## Archivos entregados

- [project.yaml](../config/aoi/lapargera_v1/project.yaml): contrato del AOI, búsqueda, productos, grilla, presupuesto y políticas. Es configuración OCEANOS, no settings que ACOLITE lea directamente.
- `acolite_s2.txt`: cinco overrides nativos, sin input/output fijos. Eliminado el 1 de octubre de 2026; el wrapper genera ahora esos settings desde los YAML.
- [README del perfil](../config/aoi/lapargera_v1/README.md): modo de uso y límites.
- [Comprobaciones del perfil — evidencia consolidada](33_retention_and_reset.md#historial) y [grilla nativa candidata — evidencia consolidada](33_retention_and_reset.md#historial).

En fase 4 no se creó CLI ni wrapper. El perfil Landsat se incorporó en fase 10 y el wrapper en fase 11.

## Versión de referencia

Se elige como candidata para el primer ensayo la revisión auditada upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. La instalación `/home/antho/acolite` permanece en `f73cbe73887c2b114d9d3c70865effee73871525` y no se modificó. La revisión elegida se preparó y se utilizó en los ensayos posteriores; no basta dar el mismo TXT a la instalación anterior y asumir resultados equivalentes.

El perfil usa defaults de esa revisión: DSF tiled, intercepto 200 y tiles 600×600 para MSI; rango 400–900; geometría nativa; gases/auxiliares activos; glint/adyacencia sin activar experimentalmente; NetCDF comprimido nivel 4 y sin discretización. S2C mantiene RSR V4. Es una referencia científica inicial, no una afirmación de optimalidad en La Parguera.

## Overrides mínimos

| Setting | Default general / sensor | Valor AOI | Razón |
|---|---|---|---|
| region_name | vacío / hereda | lapargera_v1 | Identificar resultados |
| limit | None / hereda | S,W,N,E del KMZ | Recorte rectangular sin buffer |
| l2w_parameters | None / hereda | Rrs_*, tur_nechad2009, chl_oc3, ndci, fai, ndvi | Productos soportados solicitados |
| rgb_rhot | True / hereda | False | No generar PNG no requerido |
| rgb_rhos | True / hereda | False | No generar PNG no requerido |

Valores ya cubiertos por defaults y no duplicados: s2_target_res=10, merge_tiles=False, output_projection=False, reproject_before_ac=False, polygon=None, limit_buffer=None, todos los flags de borrado NetCDF/extracción False, exportación GeoTIFF False.

La [tabla de 81 settings](14_selected_aoi_configuration.md) conserva las fuentes exactas del commit. Las opciones de reproyección allí descritas son alternativas auditadas, no settings activos del perfil presente.

## Productos y máscara

Se mantienen activos los seis parámetros nativos compatibles y se exige l2_flags como dataset de calidad generado por ACOLITE. Rrs_* se expande a bandas presentes; la validación debe comprobar presencia útil y coherencia, no solo que exista algún nombre Rrs. Turbidez puede escribirse como TUR_Nechad2009_<longitud>; no validar el nombre de entrada como si fuera exactamente el nombre del dataset.

El 29 de septiembre el usuario excluyó OC4. Se elimina `products.pending`; los seis parámetros activos constituyen la solicitud vigente. OC3 permanece como producto de clorofila, sin introducir un sustituto para OC4.

La máscara L2W nativa se conserva para productos acuáticos. FAI/NDVI mantienen valores sobre tierra porque su implementación no aplica esa máscara. Esto sigue la excepción permitida por el usuario: conservar y filtrar posteriormente cuando corresponda. No se publica como salida exclusivamente oceánica. La aplicación de `masking.land_water_mask` se evaluará con datos reales antes de convertirla en parte del flujo; no se utiliza Natural Earth como máscara a 10 m ni se inventa un setting para forzar FAI/NDVI.

## Grilla y conservación

Decisión para el ensayo: **L2R y L2W sobre la grilla nativa del mismo tile, sin reproyección final**. Evita el consumo adicional del proyector general y la pérdida de l2_flags observada en auditoría. La corrección se ejecutará después de la alineación interna normal del lector.

Se ejecutó solamente `shared.projection_sub` de la revisión auditada, con extent nominal 19QGV del KML ESA: x=699960–809760; y=2000040–1890240; píxel 10,-10. Para el bounding box del AOI retorna:

| Parámetro | Candidato nativo |
|---|---|
| EPSG | 32619 |
| xrange | 701980,775330 m |
| yrange norte→sur | 1997360,1972960 m |
| Shape filas×columnas | 2440×7335 |
| Origen de borde superior izquierdo | 701980,1997360 m |
| Resolución | 10 m |

La propuesta de fase 1 (2431×7334) se calculó sobre el envolvente proyectado del polígono densificado. La actual usa el bounding box geográfico y el redondeo nativo de ACOLITE; no son cálculos del mismo extent con métodos intercambiables. Se adopta la nativa como referencia candidata para evitar imponer una reproyección innecesaria. La extensión sigue cubriendo el AOI y no incorpora un buffer científico.

Las escenas de fases 6/10 confirmaron shape, extent, origen y centros de píxel. También debe comprobarse consistencia SAFE/Zarr antes de intercambiar fuentes o acumular fechas. Si hay diferencia, detener publicación y revisar; no aceptar automáticamente offsets ni reajustar cada escena silenciosamente. La grilla común Landsat quedó verificada en fase 10 mediante proyección nativa de L1R antes de AC.

Política vigente: retener L1R completo y L2W nativo. L2R conserva temporalmente rhos/rhot para productos y flags; se retira tras registrar el QA técnico. RAW y archivos duplicados también son temporales. Regenerar desde L1R requiere repetir AC.

## Búsqueda y operación

Intervalo histórico del ensayo UTC [2026-08-01,2026-08-21); actualmente Sentinel-2 termina el 15 de agosto, exclusivo; tile 19QGV; nivel L1C; plataformas S2A/B/C; sin filtro de nubosidad, pero con nubosidad configurable y registrada. Una escena a la vez, 50.000.000.000 bytes como techo conjunto de temporales.

La fase 5 consultó disponibilidad: cero candidatos Zarr y cinco SAFE en el intervalo histórico. El wrapper posterior implementó reintentos; Zarr se retiró el 01-10-2026 por falta de cobertura (documento 06). No se afirma disponibilidad remota ni se ejecuta autenticación en esta fase. Los argumentos remove_zip/remove_tar deben desactivarse o manejarse según política al adquirir; los settings de procesamiento no los controlan.

## Validación realizada

Nueve comprobaciones simples aprobadas: integridad del KMZ, settings reconocidos por defaults auditados, coherencia de productos YAML/TXT, coherencia del limit, ausencia de OC4 no soportado en solicitud nativa, nubosidad desactivada, y defaults operativos de S2A, S2B y S2C. Se ejecutaron los parsers/merge nativos en aislamiento; no se replicaron sus algoritmos. Los settings seleccionados se registraron en JSON de evidencia; esos archivos independientes se retiraron en el reinicio.

En fase 4 la grilla se calculó con función nativa, sin escena. Los ensayos posteriores verificaron grilla y midieron recursos; la validación científica y la exactitud de máscara siguen pendientes. La lista de productos y la salida oceánica aún contienen las limitaciones indicadas.

## Límite de fase

Perfil candidato entregado y decisión de productos cerrada. El usuario autorizó continuar con fase 5; ver informe 26. Los resultados reales se documentaron en fases 6–10 y el wrapper en fase 11. Los manifiestos de fases 4/5 registraron hashes de aquellas entregas; ya no se conservan como archivos independientes. La política actual y el reinicio están en el documento 33.
