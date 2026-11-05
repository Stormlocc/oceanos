# Superimagen Water2Coast

Desde noviembre de 2026 OCEANOS procesa el AOI `water2coast_v1`. En vez de guardar L1R/L2W de una grilla común, guarda una **superimagen**: por zona, sensor y escena, los productos de ACOLITE en COG listos para combinar, y a partir de ellos los mapas diarios de sargazo y los compuestos de calidad de agua. Este documento reúne qué se guarda, cómo se calcula y **cada decisión con su justificación y su fuente**. Requisitos de los investigadores: memoria `superimagen-requisitos` y el plan en Claude Doc.

## Flujo de `oceanos run`

```text
por sensor (sentinel2 → landsat → olci):
  máscaras de tierra (una vez por zona y resolución)
  búsqueda y registro de escenas nuevas ─► estimación de descarga y de disco (--plan se detiene aquí)
  por escena (en paralelo):  descarga una vez ─► extracción
        por zona que toca:  nubes ─► ACOLITE ─► validación ─► auxiliares reales ─► COG verificados ─► linaje
        se borran crudo, extracción, L1R, L2R y L2W
  sargazo diario de los días con escenas
  compuestos de los meses completos, y de sus estaciones y años
```

Todo es reanudable e idempotente: una adquisición con todas sus zonas terminadas no se descarga otra vez, y un compuesto o mapa diario con la misma firma de entradas no se recalcula. `oceanos sargazo` y `oceanos componer` recalculan sin descargar.

## Carpetas

| Ruta en `storage/superimagen/` | Contenido |
|---|---|
| `escenas/<zona>/<S2|Landsat|OLCI>/<AAAA-MM-DD>_<lugar>/` | Un COG por variable del L2W (`Rrs_<λ>.tif`, `chl_oc3.tif`, `fai.tif`…) y `calidad.tif` |
| `sargazo/<zona>/<sensor>/diario/<AAAA-MM-DD>/` | `fai.tif`, `ndvi.tif`, `escena_origen.tif` |
| `calidad_agua/<zona>/<sensor>/mensual/<AAAA-MM>/<método>/` | Un COG por variable, `fecha_origen.tif`, `n_observaciones.tif` y `rhog_ref.tif`/`angulo_glint.tif` (mejor píxel) o `peso_total.tif` (media ponderada) |
| `calidad_agua/<zona>/<sensor>/estacional/<AAAA-DEF|MAM|JJA|SON>/<método>/` y `anual/<AAAA>/<método>/` | Igual que el mensual, calculado desde los mensuales |
| `mascaras/tierra_<zona>_<sensor>_<res>m.tif` | Máscara de tierra: 0 agua, 1 tierra (con margen), 2 fuera de la zona |

**Decisión:** la carpeta de escena lleva el lugar (`2025-12-16_19QGV`, `2025-12-16_005048`, `2025-12-16_R082T1450`). El requisito decía `<fecha>`, pero dos tiles o path/row del mismo día cubren la misma zona (p. ej. 19QFV y 19QGV en La Parguera) y se pisarían. El sargazo diario y los compuestos los combinan después.

## Zonas, grillas y resolución

| Zona | EPSG | Sentinel-2 (tiles) | Landsat (path/row) | Grilla 10 m (filas × col.) |
|---|---|---|---|---|
| `mayaguez_cabo_rojo` | 32619 | 19QFA, 19QFV | 005047, 005048 | 3783 × 2179 |
| `la_parguera_guanica` | 32619 | 19QFV, 19QGV | 005048 | 1702 × 3070 |
| `ponce_guayanilla` | 32619 | 19QGV | 005048 | 2014 × 6154 |
| `fajardo_culebra` | 32620 | 20QKF | 004047 | 2693 × 5481 |

- **Geometría:** `config/aoi/water2coast_v1/AOI_Water2Coast.zip` (campo `Name`), con su SHA-256 comprobado al cargar el perfil. Nada se hereda de `lapargera_v1`.
- **Fajardo–Culebra en UTM 20N:** está al este de 66° O. 19QHA también la cubre, pero en UTM 19, así que se usa 20QKF, que la cubre al 100 %.
- **Tiles y path/row:** salen de la cobertura medida con las huellas reales de diciembre de 2025 (solo metadata). Se omitió un lugar cuando cubre poco y otro ya cubre la zona entera; por ejemplo 19QGA cubre el 22 % de Ponce y 19QGV el 100 %. Una escena entra en las zonas de su lugar cuya huella toca (`native.zones_for`). OLCI no tiene tiles: entra en toda zona que su huella cubra.
- **Grilla por zona y sensor:** el rectángulo envolvente de la zona en su UTM, ampliado hacia afuera a múltiplos de la resolución (`zonas.grid`).
  - S2 a 10 m, Landsat a 30 m sin remuestrear a 10 m, OLCI a 300 m.
  - ACOLITE proyecta el L1R a esa grilla antes de la corrección (`reproject_before_ac`, vecino más cercano, `resolution_align=False`). Por eso L1R, L2R y L2W quedan alineados y se conserva `l2_flags`.
  - En S2 y Landsat es un recorte exacto, sin mezclar píxeles.
- **Una descarga, varias zonas:** una escena que toca varias zonas se descarga y extrae una vez, y ACOLITE corre una vez por zona con su grilla.

## Productos de ACOLITE

Nombres verificados en `acolite/acolite/acolite_l2w.py` de la revisión `80da0c0`:

| Producto pedido | S2 | Landsat | OLCI | Nota |
|---|---|---|---|---|
| Rrs | `Rrs_*` | `Rrs_*` | `Rrs_*` | Siempre |
| OC2 | `chl_oc2` | `chl_oc2f` | — | OLI no tiene `chl_oc2`; ACOLITE ofrece `chl_oc2f` para OLI |
| OC3 | `chl_oc3` | `chl_oc3` | — | |
| OC4 | — | — | `chl_oc4` | Solo OLCI (510 nm) |
| Gons | `chl_re_gons` | — | — | Usa el borde rojo de MSI |
| CI | `chl_ci` | `chl_ci` | `chl_ci` | |
| NDCI | `ndci` | — | `ndci` | Necesita 705–709 nm |
| Turbidez / SPM (Nechad) | `tur_nechad2009`, `spm_nechad2010` | igual | igual | |
| QAA y Kd490 | `qaa_v6_Kd_490` | igual | — | Kd490 sale del QAA; se pide la clave exacta para no escribir todas las salidas QAA. En OLCI no existe: ACOLITE solo configura el QAA para OLI y MSI, y el P3QAA tampoco tiene coeficientes OLCI (`acolite_l2w.py` y `data/Shared/algorithms/P3QAA/center_wl.csv` de la revisión fijada). Se detectó en el ensayo de enero de 2026: las 20 primeras escenas OLCI fallaron la validación por «Producto requerido ausente» |
| FAI / FAIT / NDVI | `fai`, `fait`, `ndvi` | igual | — | FAI necesita ~1610 nm: OLCI no lo tiene. FAIT existe (`fait`, Dogliotti) |

`--products` solo puede pedir un subconjunto del perfil. La validación técnica exige cada producto pedido en el L2W y todas las `Rrs_*` del L2R (`validation.product_variables`). `fai` no se satisface con `fait`.

**Glint:** se activan `dsf_residual_glint_correction=True` y `glint_write_rhog_ref=True`. Esto viene del requisito y de Vanhellemont (2019), *Remote Sens. Environ.* 225, 175–192. ACOLITE escribe `rhog_ref` solo donde corrige el glint, es decir, donde rhos(1600 nm) ≤ `glint_mask_rhos_threshold` = 0,05 (`acolite_l2r.py`, `sub_gc`). Fuera de esa zona queda NaN.

## Datos externos que pide ACOLITE

Verificado en la revisión fijada:

- **MERRA-2 meteorológico** (ozono, vapor, presión, viento): siempre, con `ancillary_data=True` (default).
- **Aerosol MERRA-2:** solo si `dsf_aot_estimate` empieza con `ancillary`. No es el caso: el default es DSF.
- **DEM:** solo con `dem_pressure` o `dem_shadow_mask`. **TACT:** solo con `tact_run`. Ninguno está activo.
- **LUT:** se descargan la primera vez por sensor (`acolite/data/LUT`), incluidas `S3A_OLCI`/`S3B_OLCI` para OLCI.
- **Fallo silencioso de auxiliares:** si MERRA-2 no se consigue, ACOLITE sigue con los valores por defecto (`uoz_default` 0,3, `uwv_default` 1,5, `pressure_default` 1013,25) sin avisar.
  - OCEANOS compara los valores del L2R con esos defaults (`Pipeline.check_ancillary`). Si coinciden los tres, la escena queda `FALLIDA` con motivo `AUXILIAR_POR_DEFECTO` y no entra a la superimagen; el próximo `run` la reintenta sin volver a descargar.
  - Los valores usados quedan en el linaje (`auxiliares`).

## Etapa escenas

Después de cada ACOLITE, por zona (`escenas.export`):

- **COG por variable** (Float32, ZSTD con predictor, teselas de 512, sin overviews para no gastar disco). La tierra y lo que cae fuera de la zona quedan en NoData (NaN).
- **`calidad.tif`** con 13 bandas, leídas siempre por nombre (`QUALITY_BANDS`):
  - Bits 0–5 de `l2_flags`, decodificados: `flag_swir`, `flag_cirrus`, `flag_toa_alto`, `flag_rrs_negativa`, `flag_fuera_escena`, `flag_mixto`. Los exponentes salen de `config/defaults.txt` de ACOLITE.
  - `rhog_ref` del L2R.
  - Residuo Rrs SWIR cerca de 1600 y 2200 nm (residuo de glint o espuma tras la corrección).
  - Ángulo de glint por píxel, calculado con `ac.shared.glint_angle` y la geometría del L2R.
  - `aot_550`: espesor óptico de aerosol a 550 nm por píxel, del DSF de ACOLITE (desde noviembre de 2026; ver abajo).
  - `vza` y `raa`: ángulo cenital de vista y azimut relativo (grados) del L2R. Con geometría resuelta varían por píxel; si ACOLITE solo deja el valor de la escena, se repite.
  - Lo que ACOLITE no escribió queda NaN.
  - **Compatibilidad:** los productos de enero de 2026 tienen el `calidad.tif` anterior de 10 bandas, sin las tres últimas. Las bandas nuevas van siempre al final y se leen por nombre, así que compuestos y sargazo siguen leyendo los dos formatos. Pedir `aot_550`, `vza` o `raa` a un archivo antiguo falla: esas bandas no existen ahí.

**Por qué AOT y geometría (04-11-2026).** El ensayo de investigación `~/projects/oceanos-incertidumbre` (incertidumbre aprendida entre sensores) mostró que la calidad del píxel predice el desacuerdo entre sensores, pero le faltaban el aerosol y la geometría. ACOLITE los calcula y OCEANOS los perdía al borrar el L2R.
- **Aerosol:** con `dsf_aot_estimate=tiled`, el default de S2, Landsat y OLCI en la revisión fijada, ACOLITE estima el AOT en teselas de 600×600 píxeles y lo interpola. Por defecto solo guarda el modelo (`ac_model`) y la media (`ac_aot_550_mean`) como atributos. Con `dsf_write_aot_550=True` (perfil, `acolite`) escribe además `aot_550` en el L2R (`acolite_l2r.py`, «write aot to outputfile»).
- **No cambia la Rrs ni los productos:** es una salida más. El SHA de los settings sí cambia y queda en el linaje.
- **No se guarda el L2R:** sigue borrándose tras exportar; solo se copian `aot_550`, `vza` y `raa`, como ya se hacía con `rhog_ref`.
- **Escritura atómica:** se escribe en `<carpeta>.parcial` y se renombra al terminar. Luego se verifica que cada COG existe, tiene su tamaño y GDAL lo abre.
- **Borrado:** solo después de exportar, verificar y registrar el linaje se borran L1R, L2R y L2W de la zona. Al cerrar la escena se borran también el crudo y la extracción. Si algo falla no se borra nada: el proceso queda `FALLIDO` con su temporal (`limpieza APLAZADA`), y el siguiente intento reutiliza el crudo si su SHA-256 coincide.
- **Linaje** (`productos_escena`, una fila por escena, zona y AOI):
  - Identidad de la fuente: ID CDSE/USGS, SHA-256 de la descarga, checksum del proveedor, baseline o colección, vía de descarga (CDSE, M2M o EARTHEXPLORER).
  - Proceso: revisión y parche de ACOLITE, settings nativos, auxiliares usados y fecha de proceso.
  - Medidas: ángulo de glint medio sobre el agua, nubes y su origen, cobertura y capa de tierra con su versión.
  - Corrección atmosférica (`correccion`, JSON, desde el catálogo v6):
    - `modelo`: modelo de aerosol del DSF, p. ej. `ACOLITE-LUT-202110-MOD2`;
    - `dsf_aot_estimate`: modo del DSF;
    - `aot_550_escena`: `ac_aot_550` con DSF `fixed`, o `ac_aot_550_mean` con `tiled`;
    - `sza`, `vza`, `raa`: geometría de la escena según los atributos del L2R;
    - `zona`: medias de `aot_550`, `vza` y `raa` sobre el agua de la zona.
    - Los productos exportados antes de la migración la tienen vacía.
- Los COG llevan además su metadata mínima, legible desde `gdalinfo` o ArcGIS: escena, proveedor, zona, sensor, revisión de ACOLITE, máscara y SHA-256 de los settings.

## Nubes: máximo 50 % por zona

- **Medición:** sobre el polígono de cada zona, con la máscara del propio L1 y antes de correr ACOLITE (`escenas.cloud_fraction`).
  - S2: `MSK_CLASSI_B00` (bandas de nubes opacas y cirros, 60 m) y `B01` para saber dónde hay datos.
  - Landsat: `QA_PIXEL`, bit 0 para el relleno y bits 1–3 para nube dilatada, cirro y nube.
  - OLCI no trae máscara en el L1: se mide después con los flags de ACOLITE (cirros o TOA alto) sobre el agua de la zona.
- **Más de 50 %:** la zona queda `NUBOSA` y no se procesa. **Sin datos sobre la zona:** queda `SIN_DATOS`. Las dos cuentan como resultado terminal y no se reintentan.
- **Por qué no la nubosidad del proveedor:** la publicada es de toda la escena, no de la zona. Por eso la búsqueda no filtra por nubes.

## Máscara de tierra

- **Fuente:** ESA WorldCover 10 m v200 (2021). Es una capa fija y no un umbral de banda, que cambia con nubes, sedimento, arrecifes y sargazo.
  - Origen: bucket público `esa-worldcover.s3.eu-central-1.amazonaws.com`, tiles de 3° N15W069 y N18W066 (descarga autorizada para Puerto Rico y Culebra).
- **Clases:** tierra es toda clase distinta de 80 (agua permanente) y de 0 (sin dato, mar abierto fuera de la cobertura). El manglar (95) cuenta como tierra.
- **Cálculo:**
  1. Se rasteriza a 10 m sobre los mismos límites que la grilla del sensor.
  2. Se agrega a 30 o 300 m: un píxel es tierra si alguno de sus subpíxeles lo es.
  3. Se dilata 2 píxeles hacia el mar (`margin_pixels`) para quitar la orilla mezclada.
  4. Se escribe una vez por zona, sensor y resolución, y se registra en la tabla `mascaras` con su capa, versión y SHA-256.
- **Descarga:** 3 intentos con espera y reanudación del `.part`. Si no se consigue, el error nombra el tile.

## Sargazo diario

- **Entradas:** por zona, sensor y día se combinan las escenas del día. Antes se descartan los píxeles con los bits 1, 2 o 4 (cirros, TOA alto o fuera de escena) y la tierra ya viene en NoData.
- **Por qué no el bit 0:** el bit 0 (SWIR alto) no se usa porque lo activa el propio sargazo flotante.
- **Salida:** por píxel, el FAI máximo, el NDVI de la misma escena y `escena_origen` (id de `productos_escena`).
- **Catálogo:** se registra como compuesto `sargazo_diario` con la lista de escenas.
- **Alcance:** solo S2 y Landsat; OLCI no tiene FAI.

## Compuestos de calidad de agua

**Mensual por zona y sensor**, solo de meses completos. Un mes está completo cuando:

1. ya terminó;
2. búsquedas OK del AOI y del sensor lo cubren entero;
3. toda escena del mes que toca la zona tiene resultado terminal en ella.

Un mes sin escenas válidas no tiene compuesto, pero cuenta como completo para su estación y su año.

1. **Un valor por día.** Las escenas de un mismo día (tiles solapados de una pasada) se reducen primero a una observación por píxel: la de menor glint. Así un mismo día no cuenta doble.
2. **Píxel válido.**
   - Se descartan los bits 0–4 de `l2_flags` (`superimagen.composite.discard_flag_bits`): SWIR alto, cirros, TOA alto, Rrs negativa y fuera de escena. El 5 (mixto) solo informa.
   - En S2 y Landsat se exige `rhog_ref` finito, lo que descarta lo que ACOLITE no corrigió (rhos 1600 > 0,05), y π·Rrs(1600) ≤ 0,05.
   - En OLCI, ángulo de glint ≥ 20°.
3. **Método (a) `mejor_pixel`:** gana la observación de menor `rhog_ref` (en OLCI, mayor ángulo de glint). La observación se toma entera, con todas sus variables, para no mezclar espectros. Capas: `fecha_origen`, `n_observaciones` y la medida de glint elegida.
4. **Método (b) `media_ponderada`:**
   - **Peso:** 1 si `rhog_ref` ≤ 0,005; lineal hasta 0 en 0,02; descarte por encima. En OLCI el peso es 1 si pasa el ángulo.
   - **Media:** cada variable promedia con los pesos de las observaciones donde tiene dato.
   - **Capas:** `fecha_origen` (la observación de mayor peso), `n_observaciones` (con peso > 0) y `peso_total`.
5. **Estación (DEF, MAM, JJA, SON; DEF de diciembre del año anterior) y año calendario:** se calculan solo cuando sus meses están completos, desde los mensuales del mismo método.
   - (a) gana el mes de menor glint: es exacto, igual que hacerlo desde las escenas.
   - (b) pondera cada mensual por su `peso_total`. Es exacto salvo donde una variable faltaba en parte de las observaciones del mes.
6. **Bandas gemelas:** las bandas equivalentes de satélites gemelos (S2A 665 nm y S2B 664 nm) se unen bajo un nombre si difieren en ≤ 10 nm.
7. **Idempotencia y linaje:** cada compuesto tiene una firma (SHA-256 de sus entradas con su fecha de proceso, parámetros y versión del método). Con la misma firma no se recalcula. `compuesto_escenas` guarda las escenas que entraron.
8. **Memoria:** todo se calcula por bloques de 512 filas y una variable a la vez (`bloques.py`). La RAM depende del ancho de la zona y de las escenas del mes, no del tamaño total.

### Umbrales de glint: origen y calibración

| Parámetro (`superimagen.glint`) | Valor | Fuente |
|---|---|---|
| `full_weight_max` | 0,005 | Requisito de los investigadores (glint bajo) |
| `discard_above` | 0,02 | ≈ π × 0,005, umbral de glint alto de NASA en radiancia normalizada (Wang & Bailey 2001, *Appl. Opt.* 40, 4790–4798) |
| `rhos_mask_threshold` | 0,05 | `glint_mask_rhos_threshold` de ACOLITE (`config/defaults.txt`) |
| `minimum_glint_angle_deg` (OLCI) | 20° | Punto de partida de Digital Earth Australia, según el requisito |

**Calibración con enero de 2026 (S2 y Landsat, 4 zonas):** se mantienen 0,005 y 0,02, con el bit 0 descartado. La mediana de `rhog_ref` en el agua limpia va de 0,0010 a 0,0054 y el p99 no pasa de 0,018. Con 0,005, entre el 46 % y el 99 % del agua tiene peso 1. El corte de 0,02 casi nunca actúa (≤ 0,3 %), porque el bit 0 ya quitó el glint fuerte. Histogramas y justificación: [resultados](05_resultados.md#superimagen-ensayo-dic-2025--ene-2026). A 18° N el sol está bajo en enero a la hora de paso (~10:30 local) y el glint es menor que en verano: hay que revisar los cortes con un mes de verano antes de procesar los 12 meses.

## Disco

- **Presupuesto propio:** 120 GB para `storage/superimagen` (subido de 100 GB por el usuario el 04-11-2026, tras medir la primera escena) (`storage.superimagen_budget_bytes`). Los temporales siguen con su presupuesto de 50 GB.
- **Estimación:** antes de descargar, `run --plan` muestra la lista de escenas, cuántos productos de zona se exportarán y cuánto ocuparán: la mediana medida de cada zona o, si la zona aún no tiene, los bytes por píxel medidos en el sensor por el tamaño de su grilla; sin mediciones, Float32 por capa con un 50 % de compresión.
- **Al acercarse al límite:** si la estimación supera el presupuesto, `run` avisa. Antes de cada descarga y de cada exportación se comprueba que quepa otro producto; si no, la escena queda `FALLIDA` con `PRESUPUESTO_SUPERIMAGEN`, sin descargar.

## Legado `lapargera_v1`

- **Migración:** al abrir un catálogo v4, OCEANOS lo copia como respaldo (`catalog_v4_respaldo_<fecha>.sqlite`) y lo migra (hoy hasta v6).
  - Los procesos de `lapargera_v1` quedan con `legado=1`.
  - Las escenas vuelven a `NUEVA`, porque su estado de cola era del AOI anterior.
  - Se registra un evento `LEGADO`.
- **Conservación:** los L1R/L2W del legado se conservan en `storage/runs` y nunca se borran. Tampoco entran a la superimagen, a la cola ni al cálculo de "ya tenemos esta adquisición": tenían el glint apagado y otra grilla.
- **Consulta aparte:** con `oceanos status --legado` y `oceanos reporte --legado`. `oceanos sync` registra los L1R/L2W importados también como legado.

## Landsat por M2M

- **Vía principal:** desde el 04-11-2026 la cuenta tiene acceso de descarga M2M. La descarga Landsat usa `download-options` → `download-request` → `download-retrieve` → URL. El pedido se retira al terminar (`download-order-remove`) para no acumular pedidos abiertos.
- **Respaldo:** EarthExplorer, solo si M2M no entrega una URL. La vía usada queda en el linaje (`via_descarga`).

## Sentinel-3 OLCI

- **Descarga:** OLCI L1 EFR (`OL_1_EFR___`) desde CDSE, con el mismo cliente en streaming que S2 y el mismo tope de 4 descargas a la vez.
- **Identidad:** cada escena se identifica por su órbita relativa y su hora (`R<órbita>T<HHMM>`); el baseline es `timeliness_baseline`.
- **Procesamiento:** se procesa a 300 m con `chl_oc4`.
- **Orden:** OLCI se integra después de que S2 y Landsat funcionen de punta a punta (requisito 11).
