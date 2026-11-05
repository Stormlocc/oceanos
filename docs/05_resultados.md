# Resultados de los ensayos

Todos los resultados son **técnicos**. La aceptación científica de los productos acuáticos sigue pendiente de datos in situ (CTD, muestras de clorofila y turbidez, observaciones OCEANOS/CariCOOS con control de calidad).

## Antecedentes: AOI de prueba (septiembre–octubre de 2026, retirado)

Antes de Water2Coast se ensayó un AOI de prueba en La Parguera, con una grilla común de 10 m y el glint residual apagado. Con esa configuración la máscara L2W de ACOLITE (`rhot` cerca de 1600 nm > 0,0215, bit 0) cubrió casi todo el agua: Rrs, turbidez, OC3 y NDCI quedaron sin píxeles válidos en 5 de 8 adquisiciones de agosto de 2026. Se descartaron errores de escala, de transferencia de bandas y de geolocalización. Por eso la superimagen activa la corrección residual de glint y guarda `rhog_ref` ([superimagen](07_superimagen.md#productos-de-acolite)).

Ese AOI se retiró por completo el 05-11-2026: perfil, catálogo (migración v6 → v7) y sus L1R/L2W en `storage/runs`. El detalle de aquellos ensayos queda en el historial: `git show dc0ab56:docs/05_resultados.md`.

## Descarga Sentinel-2: nativa de ACOLITE frente a la propia (13-10-2026)

Misma escena (`S2B_MSIL1C_20251107T150719_…SAFE`, 734,8 MB), procesos aislados, bytes leídos por el proceso (`rchar`) como medida de red:

| Método | Recibido por red | RAM extra | Tiempo | MD5 CDSE |
|---|---:|---:|---:|---|
| `ac.api.cdse.download` | 1.472 MB (2,0×) | 1.649 MB | 528 s (red ≈2,8 MB/s); un intento previo cortado por el servidor terminó en excepción sin controlar | correcto |
| `native.cdse_download` | 737 MB (1,0×) | 6–7 MB | 360 s (red ≈2,0 MB/s) y 229 s (red ≈3,2 MB/s) | correcto |

La nativa pide el archivo dos veces (comprobado también con un servidor local: dos peticiones al host de descarga y 3 veces el tamaño del archivo en RAM), lo que explica el pico de ≈3,2 veces el ZIP de las 14 escenas del catálogo v3 y que su velocidad aparente máxima (9,45 MB/s) fuera la mitad de los 20 MB/s por conexión de CDSE. A igual velocidad de red, la descarga propia tarda la mitad. Por eso OCEANOS la reemplazó ([ACOLITE](02_acolite.md#descarga-y-extracción)).

## Superimagen: ensayo dic-2025 – ene-2026

**Primera escena real (04-11-2026).** `S2A_MSIL1C_20260110T145751_N0511_R039_T20QKF`, zona Fajardo–Culebra (la grilla más grande, 2693 × 5481 a 10 m), en un storage de prueba:

- Descarga CDSE de 379,9 MB en 3 min 44 s. ACOLITE tardó ~3,5 min y la exportación 14 s; 7 min 44 s en total.
- Auxiliares MERRA-2 reales: ozono 0,268, vapor 3,87, presión 1014,8 hPa y viento 4,8 m/s. LUT y WorldCover funcionaron.
- Nubes 0 % (`MSK_CLASSI_B00`); la escena cubre el 69 % de la zona.
- Rrs válida en 8,9 M píxeles. En el AOI de prueba, sin glint residual, quedaba enmascarada casi entera.
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

**Decisión del usuario (04-11-2026):** trabajar solo con **enero de 2026** y subir el presupuesto de la superimagen a **120 GB**. Se mantiene Float32 completo. El 05-11-2026 el presupuesto pasó a **300 GB**, el límite de cada computadora que descarga.

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

### Ensayo de enero de 2026: Sentinel-3 OLCI (05-11-2026)

**Corrida y correcciones:** 37 escenas OLCI L1 EFR, 31,5 GB de descarga, corridas después de que S2 y Landsat funcionaran de punta a punta. Para completarse hizo falta corregir dos cosas:

1. **Kd490.** El perfil pedía `qaa_v6_Kd_490`, pero ACOLITE no configura QAA ni P3QAA para OLCI. Las primeras 20 escenas fallaron la validación. Se quitó Kd490 de OLCI ([07](07_superimagen.md#productos-de-acolite)).
2. **Zonas fuera de la franja.** En 4 pasadas de ~14:00 UTC la huella aproximada tocaba una zona que la franja real del sensor no cubre. ACOLITE escribía un L1R vacío sin L2R ni L2W, y la escena fallaba. Ahora esa zona queda `SIN_DATOS`, un estado terminal.

Al reintentar, las escenas fallidas reutilizaron su descarga por SHA-256: 17 en la primera repetición y 4 en la última.

**Resultado (129 zona × escena):**

| Zona | OK | NUBOSA | SIN_DATOS |
|---|---|---|---|
| Fajardo–Culebra | 21 | 10 | 1 |
| La Parguera–Guánica | 25 | 6 | 0 |
| Mayagüez–Cabo Rojo | 24 | 7 | 1 |
| Ponce–Guayanilla | 19 | 11 | 4 |
| **Total** | **89** | **34** | **6** |

**Verificación:**
- **Auxiliares:** los 89 productos OK tienen auxiliares MERRA-2 reales.
- **Nubes:** se miden con los flags de ACOLITE y concuerdan con S2 en días despejados (10 de enero: 0–3 % frente a 0 %).
- **Disco:** cada producto OLCI ocupa 0,3–1 MB por zona; 50 MB en todo el mes.
- **Compuestos:** 8 compuestos mensuales, los dos métodos en las 4 zonas, con 19–25 escenas por zona, observación en el 57–78 % de la zona y hasta 21 observaciones por píxel. La mediana de `chl_oc4` coincide entre métodos en Fajardo y La Parguera. En Mayagüez (0,76 frente a 0,88) y Ponce (0,39 frente a 0,46) el mejor píxel da más. Es esperable: elige la observación de mayor ángulo de glint, no la mediana del mes.

**Corte de glint OLCI (20°):** en el agua sin flags de nubes, el ángulo de glint mínimo de enero es 24,2°, con p1 de 24,3° y mediana de 32–36°. El corte de 20° no descarta nada en enero. Se mantiene como punto de partida y debe revisarse con un mes de verano, cuando el sol está más alto.

### Total del ensayo de enero de 2026

| Sensor | Escenas | Zonas OK | NUBOSA | SIN_DATOS | Productos | Compuestos mensuales | Sargazo diario |
|---|---|---|---|---|---|---|---|
| Sentinel-2 | 35 | 42 | 7 | 0 | 13,8 GB | 8 (4,1 GB) | 30 (1,5 GB) |
| Landsat 8/9 | 12 | 17 | 3 | 0 | 0,7 GB | 8 (0,4 GB) | 14 (0,06 GB) |
| OLCI | 37 | 89 | 34 | 6 | 0,05 GB | 8 (0,01 GB) | — (sin FAI) |
| **Total** | **84** | **148** | **44** | **6** | **14,6 GB** | **24 (4,5 GB)** | **44 (1,6 GB)** |

- **Disco:** la superimagen de enero ocupa ~20 GB de los 120 GB. Los temporales quedaron limpios (152 KB).
- **Descarga:** 62,5 GB de L1 en total, entre S2 19,6, Landsat 12,9 y OLCI ~30, con reintentos y reutilización.

### Primera escena con AOT y geometría (05-11-2026)

Enero se repite con el commit `dc0ab56` (catálogo v6) en otra máquina con el wrapper instalado (WSL con 24 núcleos y 15,5 GB de RAM, la mitad de los 32 GB de Windows por el default de WSL). Primer producto exportado: `S2B_MSIL1C_20260103T145729_N0511_R039_T20QKF`, Fajardo–Culebra.

- **`calidad.tif`:** 13 bandas, 65 MB, 5481 × 2693.
  - `aot_550` tiene valores en el 87 % de la grilla (todo lo que la escena cubre), entre 0,063 y 0,184, con media 0,119.
  - `vza` (8,8–11,8°) y `raa` (41,8–57,7°) tienen valores en el 63 %, la misma cobertura que `angulo_glint`.
- **Linaje `correccion`:** `{"modelo": "ACOLITE-LUT-202110-MOD1", "dsf_aot_estimate": "tiled", "aot_550_escena": 0.1237, "sza": 46.53, "vza": 9.05, "raa": 46.94, "zona": {"aot_550": 0.1043, "vza": 10.44, "raa": 46.86}}`.
- **Migración:** el catálogo v5 de esa máquina pasó a v6 con respaldo, sin perder productos.

**Lecciones de la puesta en marcha:**
- **Credenciales Earthdata:** con una contraseña incorrecta en la máquina `earthdata` de `~/.netrc`, OB.DAAC responde 401 («Credentials (username, password) are invalid»). ACOLITE sigue entonces con los valores por defecto y la escena falla con `AUXILIAR_POR_DEFECTO`. El log no muestra el 401: se diagnosticó pidiendo el mismo archivo MERRA-2 con `requests`.
- **LUT en una máquina nueva:** solo estaban las de S2A. El primer ACOLITE de S2B corrió solo mientras bajaba sus LUT; eso dejó el lote ~20 min con la CPU casi parada.
