# Documentación OCEANOS

Actualizado: 4 de noviembre de 2026 (versión 0.4.0). AOI vigente: `water2coast_v1` (4 zonas). Legado: `lapargera_v1`.

| Documento | Para qué sirve |
|---|---|
| [01_proyecto.md](01_proyecto.md) | Objetivo, acuerdos, AOI Water2Coast y resumen de fases |
| [02_acolite.md](02_acolite.md) | Cómo usa OCEANOS cada parte de ACOLITE, sus límites, instalación y `prepare` |
| [03_configuracion.md](03_configuracion.md) | Perfil `water2coast_v1` y settings que se envían a ACOLITE por zona |
| [04_operacion.md](04_operacion.md) | Comandos, flujo de `run`, estados, legado, retención, catálogo SQLite y pruebas |
| [05_resultados.md](05_resultados.md) | Ensayos: legado `lapargera_v1` y ensayo de la superimagen |
| [06_pendientes.md](06_pendientes.md) | Pendientes científicos, riesgos y trabajo futuro |
| [07_superimagen.md](07_superimagen.md) | Superimagen: carpetas, escenas, máscara, nubes, sargazo, compuestos, glint y disco, con cada decisión y su fuente |

## Estado

- **Superimagen Water2Coast implementada.** Comprende:
  - escenas COG por zona con `calidad.tif` y linaje;
  - máscara WorldCover;
  - sargazo diario;
  - compuestos (a) mejor píxel y (b) media ponderada, mensuales, estacionales y anuales;
  - `run` único;
  - Landsat por M2M;
  - OLCI;
  - presupuesto de 120 GB.

  Usa el catálogo SQLite v5 y tiene 100 pruebas sin red.
- **Ensayo real de enero de 2026 completo:** S2, Landsat y OLCI en las 4 zonas; 148 zonas OK y ~20 GB. Umbrales de glint calibrados para enero ([resultados](05_resultados.md#superimagen-ensayo-dic-2025--ene-2026)).
- **Legado:** las 14 adquisiciones Sentinel-2 de `lapargera_v1` se conservan en `storage/runs/0001_…` a `0014_…`, fuera de la superimagen.

Credenciales en `~/.netrc`, nunca en el repositorio ni en el catálogo.

Los informes por fase (00–35) se consolidaron el 07-10-2026; las versiones anteriores se recuperan con `git show 8bbd881:docs/<archivo>`.
