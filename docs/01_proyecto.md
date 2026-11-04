# Proyecto OCEANOS

Sistema reproducible y económico en disco alrededor de [ACOLITE](https://github.com/acolite/acolite) para la calidad del agua costera y el sargazo en Puerto Rico y Culebra.

**Regla de diseño:** antes de escribir una función, comprobar si ACOLITE ya la resuelve. OCEANOS solo agrega:
- perfil y catálogo;
- reintentos y verificación;
- la superimagen;
- limpieza.

## Acuerdos vigentes (noviembre de 2026)

**AOI y sensores**
- AOI `water2coast_v1`: 4 zonas en `config/aoi/water2coast_v1/AOI_Water2Coast.zip` (definitivo). Se toma solo como geometría; no hereda EPSG, grilla ni algoritmos de `lapargera_v1`.
- Sensores:
  - Sentinel-2 L1C (SAFE desde CDSE).
  - Landsat 8/9 L1TP Collection 2 Tier 1 (TAR desde USGS por M2M; EarthExplorer como respaldo).
  - Sentinel-3 OLCI L1 EFR (CDSE).

**Procesamiento**
- Resolución nativa por sensor: S2 a 10 m, Landsat a 30 m y OLCI a 300 m, en el UTM de cada zona. No se remuestrea a una grilla común.
- Una zona con más del 50 % de nubes se omite (`NUBOSA`). La nubosidad se mide sobre la zona, no sobre la escena.
- Glint: corrección residual de ACOLITE con `rhog_ref` por píxel; los umbrales se calibran con datos ([superimagen](07_superimagen.md#umbrales-de-glint-origen-y-calibración)).
- Máscara de tierra: ESA WorldCover 10 m.

**Productos y almacenamiento**
- Productos:
  - S2 y Landsat: Rrs, OC2/OC3, Gons (solo S2), CI, NDCI (solo S2), turbidez y SPM de Nechad, Kd490 por QAA, FAI, FAIT y NDVI.
  - OLCI: Rrs, OC4, CI, NDCI, Nechad y Kd490.
- Persisten **la superimagen y el catálogo SQLite**. Crudo, extracción, L1R, L2R y L2W se borran tras exportar y verificar.
- Presupuestos: 120 GB para la superimagen y 50 GB para los temporales.
- **Periodo de trabajo actual: enero de 2026** (decisión del 04-11-2026, por disco). Los 12 meses quedan para después.
- Varias escenas a la vez, con la CPU y RAM libres del equipo ([operación](04_operacion.md#paralelo)).

**Legado**
- `lapargera_v1` (14 L1R/L2W de Sentinel-2) se conserva aparte como legado.

**Código y autorizaciones**
- Código pequeño y legible, pruebas de comportamiento sin red y documentación en español.
- Cada decisión queda en `docs/` con su fuente.
- Las descargas fuera de lo autorizado, el borrado de datos del usuario y los cambios de alcance se consultan antes.

## AOI Water2Coast

| Zona | EPSG | S2 | Landsat | Grilla 10 m | Grilla 30 m | Grilla 300 m |
|---|---|---|---|---|---|---|
| Mayagüez–Cabo Rojo | 32619 | 19QFA, 19QFV | 005047, 005048 | 3783 × 2179 | 1262 × 727 | 127 × 74 |
| La Parguera–Guánica | 32619 | 19QFV, 19QGV | 005048 | 1702 × 3070 | 568 × 1024 | 57 × 103 |
| Ponce–Guayanilla | 32619 | 19QGV | 005048 | 2014 × 6154 | 672 × 2052 | 68 × 206 |
| Fajardo–Culebra | 32620 | 20QKF | 004047 | 2693 × 5481 | 898 × 1828 | 91 × 183 |

Las filas × columnas de 30 y 300 m son la misma envolvente ampliada a múltiplos de la resolución. Cálculo en `oceanos/zonas.py`; las elecciones de tiles y path/row se justifican en [07](07_superimagen.md#zonas-grillas-y-resolución).

## AOI legado `lapargera_v1`

La Parguera, 19QGV, EPSG:32619, una grilla de 2440 × 7335 píxeles de 10 m (geometría `config/aoi/lapargera_v1/W2C_South_AOI.kmz`). Sus 14 L1R/L2W siguen en `storage/runs`. Ver [resultados](05_resultados.md).

## Historia resumida

| Fase | Fecha | Resultado que sigue vigente |
|---|---|---|
| 1–2. AOI y auditoría ACOLITE | 25-09-2026 | ACOLITE cubre consulta, descarga, lectura, AC y L2W; revisión fijada `80da0c0` ([detalle](02_acolite.md)) |
| 3–10. Catálogo, perfil y ensayos `lapargera_v1` | 25/30-09-2026 | Productos acuáticos enmascarados por el umbral SWIR sin glint residual ([resultados](05_resultados.md)) |
| 11. Wrapper, cola, catálogo legible y paralelo | 30-09/03-11-2026 | CLI `oceanos`, SQLite, reintentos, descargas propias en streaming, reparto dinámico del hardware |
| 12. Superimagen Water2Coast | 04-11-2026 | 4 zonas, resolución nativa, glint, COG con calidad y linaje, WorldCover, sargazo, compuestos, `run` único, M2M, OLCI, catálogo v5 ([superimagen](07_superimagen.md)) |
| Siguiente | — | Ensayo dic-2025/ene-2026, calibración de glint y luego 12 meses (nov-2025 a oct-2026). Docker/Airflow sin iniciar ([pendientes](06_pendientes.md)) |
