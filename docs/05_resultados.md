# Resultados de los ensayos

Las secciones hasta «Reinicio» corresponden al AOI legado `lapargera_v1` (glint apagado, grilla común). Todos los resultados son **técnicos**. La aceptación científica de los productos acuáticos sigue pendiente de datos in situ (CTD, muestras de clorofila y turbidez, observaciones OCEANOS/CariCOOS con control de calidad). Los archivos de los ensayos de septiembre se retiraron en el reinicio; sus cifras y hashes quedan en el catálogo.

## Primer ensayo y diagnóstico del enmascarado (29-09-2026)

Escena `S2B_MSIL1C_20260804T150719_N0512_R082_T19QGV_20260804T182348.SAFE` (ZIP de 789.574.421 bytes, MD5 verificado). Se generaron L1R (315 MB), L2R (774 MB) y L2W (122 MB) en la grilla esperada, pero **Rrs, turbidez, OC3 y NDCI quedaron con 0 píxeles válidos**; FAI y NDVI tienen valores en el 100 % del recorte porque no reciben la máscara acuática.

Causa técnica comprobada: `rhot_1610` supera el umbral nativo 0,0215 en **todo** el recorte (mínimo 0,026, mediana 0,067), por lo que el bit 0 de `l2_flags` está activo en el 100 %. Se descartaron, con error nulo o dentro de tolerancia, la escala SAFE→L1R (B02 y B11), la transferencia de las 13 bandas `rhot` entre L1R y L2R y la geolocalización (error máximo 0,0000038°). El ángulo de brillo solar en el agua es de 17,7°–22,4° (mediana 19,8°), por debajo de los 40° que ACOLITE usa como referencia de glint: el **glint es una hipótesis compatible, no una causa demostrada**.

Decisión: no subir el umbral ni desactivar la máscara para "obtener" datos. Activar `dsf_residual_glint_correction` no basta, porque la máscara se calcula sobre `rhot` (TOA), no sobre la reflectancia corregida. Evaluar glint y máscara requiere un experimento separado y datos in situ.

Lección operativa: ejecutar siempre con `micromamba run -p /home/antho/micromamba/envs/acolite …`; sin el entorno activado, GDAL no encuentra la base PROJ y falla el L1R.

## Recursos de una escena

| Medición (escena del 4 de agosto, caché de LUT fría) | Valor |
|---|---:|
| Descarga SAFE | 368 s (tasa útil aparente ≈17 Mbps) |
| L1R / L2R (incluye preparar LUT) / L2W | 38 s / 423 s / 58 s |
| Procesamiento completo | 519 s |
| RSS máximo del proceso | 4,74 GB (máximo en los 8 ensayos: 6,57 GB) |
| Disco ocupado al terminar (RAW, salidas, scratch y data) | 3,42 GB |

Con ≈7,6 GiB de RAM disponibles en WSL, dos procesos ACOLITE con ese pico no caben: el paralelo reserva RAM por etapa y en este equipo solo solapa descargas ([paralelo](04_operacion.md#paralelo)). NetCDF comprimido zlib nivel 4, variables Float32 y flags enteros; no se introdujo compresión con pérdida. Con productos casi totalmente enmascarados el L2W comprime mucho: su tamaño no representa escenas con agua válida.

## Multifecha y Landsat (agosto de 2026)

Ocho adquisiciones en la grilla común (EPSG:32619, 2440 × 7335, ejes completos verificados) y flags `int32`:

| Sensor y fecha | Píxeles finitos OC3 | % del rectángulo | Procesamiento (s) |
|---|---:|---:|---:|
| S2B 2026-08-04 | 0 | 0 | 519,4 |
| S2C 2026-08-09 | 0 | 0 | 268,5 |
| S2A 2026-08-11 | 16.713 | 0,093 | 300,9 |
| S2B 2026-08-14 | 0 | 0 | 178,4 |
| S2C 2026-08-19 | 40.374 | 0,226 | 185,9 |
| L9 2026-08-01 | 0 | 0 | 191,8 |
| L8 2026-08-09 | 0 | 0 | 452,4 |
| L9 2026-08-17 | 58 | 0,0003 | 155,8 |

Cinco adquisiciones no tienen valores acuáticos finitos y tres conservan fracciones muy pequeñas: el enmascarado no es un caso aislado. En Landsat, la banda Rrs cercana a 613 nm proviene de contrabandas sintéticas nativas, no de una banda observada. El primer ensayo Landsat dio una grilla incorrecta por faltar `output_projection_metres=True`; se corrigió y se reprocesó desde L1R. Landsat 8 usó la LUT genérica remuestreada porque la específica no era descargable.

## Descarga Sentinel-2: nativa de ACOLITE frente a la propia (13-10-2026)

Misma escena (`S2B_MSIL1C_20251107T150719_…SAFE`, 734,8 MB), procesos aislados, bytes leídos por el proceso (`rchar`) como medida de red:

| Método | Recibido por red | RAM extra | Tiempo | MD5 CDSE |
|---|---:|---:|---:|---|
| `ac.api.cdse.download` | 1.472 MB (2,0×) | 1.649 MB | 528 s (red ≈2,8 MB/s); un intento previo cortado por el servidor terminó en excepción sin controlar | correcto |
| `native.cdse_download` | 737 MB (1,0×) | 6–7 MB | 360 s (red ≈2,0 MB/s) y 229 s (red ≈3,2 MB/s) | correcto |

La nativa pide el archivo dos veces (comprobado también con un servidor local: dos peticiones al host de descarga y 3 veces el tamaño del archivo en RAM), lo que explica el pico de ≈3,2 veces el ZIP de las 14 escenas del catálogo v3 y que su velocidad aparente máxima (9,45 MB/s) fuera la mitad de los 20 MB/s por conexión de CDSE. A igual velocidad de red, la descarga propia tarda la mitad. Por eso OCEANOS la reemplazó ([ACOLITE](02_acolite.md#descarga-y-extracción)).

## Regeneración desde L1R (legado)

Antes del reinicio se regeneró L2W desde L1R conservados, sin descargar: S2C del 19-08-2026 (19 variables 2D) y L9 del 17-08-2026 (L1R ya proyectado, 16 variables) dieron **valores idénticos**, incluidos flags y patrón de NaN. La igualdad se limita a esas condiciones (misma revisión, settings, LUT y auxiliares); no se compara el NetCDF byte a byte porque cambian timestamps.

## Reinicio y datos del legado `lapargera_v1`

El 30-09-2026, por orden del usuario, se retiraron 31,54 GB de datos de ensayo (RAW, NetCDF, cachés de la copia auditada, evidencias sueltas y scripts manuales); los artefactos quedaron marcados `DELETED` en el catálogo. Se conservaron el AOI, los perfiles, el código, el parche y las dos figuras.

Entre el 2 y el 7 de octubre se procesaron 14 adquisiciones Sentinel-2: las 12 del 1 de enero al 25 de febrero de 2026 y las del 4 y 9 de agosto. Las 14 descargas sumaron 53,2 min (10,05 GB, ≈3,2 MB/s); 4 procesos necesitaron reintentos y 3 de ellos agotaron los intentos antes de completarse en una ejecución posterior.

Estado al 08-10-2026: catálogo nuevo v4 (el anterior quedó como `catalog/catalog_v3_respaldo_20261008_003347.sqlite`, con ese historial de tiempos e intentos). Los 14 pares L1R/L2W se registraron con `sync storage/runs --hash` como procesos 1–14 `IMPORTADO`, en carpetas `runs/0001_S2C_2026-01-01` … `runs/0014_S2C_2026-08-09`: 4,65 GB de L1R y 3,89 GB de L2W. Una búsqueda de enero–febrero los unificó con sus 12 escenas CDSE (`IMPORTADA`). Landsat consultado para enero–febrero (7 escenas 005/048, 7,1 GB en bundles), sin descargas. Cifras actualizadas: `SELECT * FROM v_resumen` y [`sql/consultas.sql`](../sql/consultas.sql).

Desde la migración a v5 (superimagen) esos 14 procesos quedan con `legado=1`: se conservan y se consultan con `oceanos status --legado`, pero no cuentan para la cola ni para la superimagen.

## Superimagen: ensayo dic-2025 – ene-2026

**Primera escena real (04-11-2026).** `S2A_MSIL1C_20260110T145751_N0511_R039_T20QKF`, zona Fajardo–Culebra (la grilla más grande, 2693 × 5481 a 10 m), en un storage de prueba:

- Descarga CDSE de 379,9 MB en 3 min 44 s. ACOLITE tardó ~3,5 min y la exportación 14 s; 7 min 44 s en total.
- Auxiliares MERRA-2 reales: ozono 0,268, vapor 3,87, presión 1014,8 hPa y viento 4,8 m/s. LUT y WorldCover funcionaron.
- Nubes 0 % (`MSK_CLASSI_B00`); la escena cubre el 69 % de la zona.
- Rrs válida en 8,9 M píxeles. En `lapargera_v1`, sin glint residual, quedaba enmascarada casi entera.
- `rhog_ref`: mediana 0,0013 y p95 0,0049. El 95,1 % del agua queda con peso 1 (≤ 0,005), el 98,5 % es ≤ 0,02 y el 2,4 % no fue corregido (NaN). El ángulo de glint mediano es 38,6°.
- **Disco: 615 MB por producto de zona.** `calidad.tif` ocupa 71 MB; cada variable, 10–32 MB. Son 42 bytes por píxel de grilla. El sargazo diario de esa zona y día ocupa 61 MB.

**Proyección de disco.** El plan S2 de dic–ene estima 106 productos de zona y ~43,6 GB, sin descontar las zonas que saldrán `NUBOSA`. Landsat suma 40 productos, ~3,7 GB con la estimación sin medir. Doce meses de S2 darían ~260 GB, más que los 100 GB del presupuesto.

**Prueba de precisión.** Se redondeó la mantisa Float32 de las variables antes de comprimir con ZSTD:

| Bits | Tamaño | Error relativo máximo |
|---|---|---|
| 14 | 62 % | 3·10⁻⁵ |
| 12 | 56 % | 1,2·10⁻⁴ |
| 10 | 47 % | 4,9·10⁻⁴ |

Con 12 bits, 12 meses de S2 quedarían en ~160 GB: sigue por encima del presupuesto.

**Decisión del usuario (04-11-2026):** trabajar solo con **enero de 2026** y subir el presupuesto de la superimagen a **120 GB**. Se mantiene Float32 completo.

### Ensayo de enero de 2026: Sentinel-2 y Landsat (04-11-2026)

Se corrió con `oceanos run --start 2026-01-01 --end 2026-02-01 --sensor sentinel2`, luego `--sensor landsat`, sobre `storage/` (catálogo migrado a v5). El ensayo se interrumpió una vez y se retomó con el mismo comando: las adquisiciones ya terminadas no se volvieron a descargar.

| Sensor | Escenas | Fallidas | Zonas OK | NUBOSA | Descarga | Tiempo |
|---|---|---|---|---|---|---|
| Sentinel-2 | 35 | 0 | 42 | 7 | 19,6 GB | ~22 min + 50 min (en dos tandas, 5–7 escenas a la vez) |
| Landsat 8/9 | 12 | 0 | 17 | 3 | 12,9 GB | 24,5 min |

**Verificación de la implementación**
- **Auxiliares:** los 59 productos tienen auxiliares MERRA-2 reales (ozono 0,244–0,269, vapor 2,49–4,50); ninguno con los valores por defecto.
- **Linaje y archivos:** linaje completo en todos los productos (SHA-256, ID del proveedor, ACOLITE, settings y máscara). Ningún COG falta y GDAL abre todos.
- **Vías de descarga:** CDSE en 42 productos, M2M en 9 escenas Landsat y EarthExplorer en 3. Las 3 por EarthExplorer fueron las primeras del lote. El motivo no quedó registrado, porque el respaldo no lo guardaba; desde el commit 1170de9 queda como `EARTHEXPLORER:<motivo>`. Se descartó que el `logout` de un token M2M invalide los de descargas paralelas: se probó contra M2M y el otro token sigue válido.
- **Reanudación:** un corte de descarga de S2 se reanudó en el segundo intento.
- **Sargazo diario:** 44 mapas (zona × día), 1,5 GB.
- **Compuestos mensuales:** los 8 pares zona × sensor de enero tienen los dos métodos lado a lado, 16 compuestos en total.
  - Cubren el 64–87 % de la zona con al menos una observación.
  - Las medianas de `chl_oc3` difieren entre métodos en menos de 0,03 mg/m³ (p. ej. Fajardo S2: 0,355 mejor píxel y 0,364 media ponderada).
  - `n_observaciones` máximo: 12 en Fajardo S2 y 6 donde dos tiles cubren la zona el mismo día, porque cada día cuenta una vez.
- **Estacionales y anuales:** no hay. Es lo esperado: DEF necesita diciembre y febrero completos, y el año está incompleto.

**Disco real del mes (S2 + Landsat):**

| Carpeta | Tamaño | Detalle |
|---|---|---|
| `escenas/` | 14 GB | S2 de 188 MB (La Parguera) a 542 MB (Fajardo) por producto; Landsat de 27–70 MB |
| `calidad_agua/` | 4,2 GB | |
| `sargazo/` | 1,5 GB | |
| Total | ~19,7 GB | El plan estimó ~15,7 GB solo para S2 con 11 productos medidos |

**Calibración del glint (`rhog_ref`, agua dentro de la zona y sin bits 0–4):**

| Zona | Sensor | p50 | p95 | p99 | ≤ 0,005 | ≤ 0,02 |
|---|---|---|---|---|---|---|
| Fajardo–Culebra | S2 | 0,0043 | 0,0152 | 0,0177 | 55,6 % | 99,8 % |
| Fajardo–Culebra | Landsat | 0,0033 | 0,0083 | 0,0139 | 73,8 % | 99,7 % |
| La Parguera–Guánica | S2 | 0,0038 | 0,0077 | 0,0108 | 69,1 % | 100 % |
| La Parguera–Guánica | Landsat | 0,0026 | 0,0060 | 0,0119 | 91,3 % | 99,8 % |
| Mayagüez–Cabo Rojo | S2 | 0,0025 | 0,0081 | 0,0110 | 80,3 % | 100 % |
| Mayagüez–Cabo Rojo | Landsat | 0,0010 | 0,0036 | 0,0053 | 98,6 % | 100 % |
| Ponce–Guayanilla | S2 | 0,0054 | 0,0105 | 0,0135 | 46,0 % | 100 % |
| Ponce–Guayanilla | Landsat | 0,0030 | 0,0079 | 0,0094 | 68,4 % | 99,9 % |

Píxeles de agua descartados por flags: 14–44 % según zona y sensor.

| Flag | Descarta | Causa |
|---|---|---|
| Bit 0 (SWIR alto en TOA) | 5–34 % | Causa principal |
| Bit 1 (cirros) | 0–39 % | Landsat en Ponce, una escena con cirros |
| Bit 2 (TOA alto) | 0–12 % | |

De los píxeles marcados solo por el bit 0, el 51–94 % tampoco tiene `rhog_ref` ≤ 0,02: ACOLITE no corrigió su glint (rhos 1600 > 0,05), o son bordes de nube o de costa.

**Decisión de calibración (enero de 2026):** se mantienen `full_weight_max` = 0,005 y `discard_above` = 0,02, y se mantiene el descarte del bit 0.

- **0,005:** queda cerca de la mediana–p75 de los datos. Con él la media ponderada sí distingue: entre el 46 % (Ponce S2) y el 99 % (Mayagüez Landsat) del agua limpia tiene peso 1, y el resto baja de forma gradual.
- **0,02:** casi nunca descarta (≤ 0,3 % del agua limpia), porque el bit 0 ya quitó el glint fuerte. Funciona como tope de seguridad.
- **Revisión pendiente:** enero es temporada de glint bajo a 18° N. Los cortes deben revisarse con un mes de verano antes de procesar los 12 meses. Sentinel-2 tiene más glint que Landsat en las cuatro zonas: p50 0,0025–0,0054 frente a 0,0010–0,0033.

Pendiente: OLCI en enero de 2026, con el histograma del ángulo de glint para revisar el corte de 20°.
