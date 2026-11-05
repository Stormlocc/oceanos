# Documentación OCEANOS

Actualizado: 5 de noviembre de 2026 (versión 0.4.0). AOI: `water2coast_v1` (4 zonas).

| Documento | Para qué sirve |
|---|---|
| [01_proyecto.md](01_proyecto.md) | Objetivo, acuerdos, AOI Water2Coast y resumen de fases |
| [02_acolite.md](02_acolite.md) | Cómo usa OCEANOS cada parte de ACOLITE, sus límites, instalación y `prepare` |
| [03_configuracion.md](03_configuracion.md) | Perfil `water2coast_v1` y settings que se envían a ACOLITE por zona |
| [04_operacion.md](04_operacion.md) | Comandos, flujo de `run`, estados, `sync` entre computadoras, retención, catálogo SQLite y pruebas |
| [05_resultados.md](05_resultados.md) | Ensayos: antecedentes, descargas y ensayo de enero de 2026 de la superimagen |
| [06_pendientes.md](06_pendientes.md) | Pendientes científicos, riesgos y trabajo futuro |
| [07_superimagen.md](07_superimagen.md) | Superimagen: carpetas, escenas, máscara, nubes, sargazo, compuestos, glint y disco, con cada decisión y su fuente |

## Estado

- **Superimagen Water2Coast implementada.** Comprende:
  - escenas COG por zona con `calidad.tif` (13 bandas: flags, glint, AOT y geometría) y linaje, incluida la corrección atmosférica;
  - máscara WorldCover;
  - sargazo diario;
  - compuestos (a) mejor píxel y (b) media ponderada, mensuales, estacionales y anuales;
  - `run` único;
  - Landsat por M2M;
  - OLCI;
  - presupuesto de 300 GB;
  - `oceanos sync` para reunir la superimagen de varias computadoras.

  Usa el catálogo SQLite v7 y tiene 102 pruebas sin red.
- **Ensayo real de enero de 2026 completo:** S2, Landsat y OLCI en las 4 zonas; 148 zonas OK y ~20 GB. Umbrales de glint calibrados para enero ([resultados](05_resultados.md#superimagen-ensayo-dic-2025--ene-2026)).
- **Sin legado:** el AOI de prueba `lapargera_v1` se retiró el 05-11-2026 (perfil, catálogo y `storage/runs`).

Credenciales en `~/.netrc`, nunca en el repositorio ni en el catálogo.

Los informes por fase (00–35) se consolidaron el 07-10-2026; las versiones anteriores se recuperan con `git show 8bbd881:docs/<archivo>`.
