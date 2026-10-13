# Documentación OCEANOS

Actualizado: 8 de octubre de 2026 (versión 0.3.0). AOI: `lapargera_v1`.

| Documento | Para qué sirve |
|---|---|
| [01_proyecto.md](01_proyecto.md) | Objetivo, acuerdos, AOI y resumen de fases |
| [02_acolite.md](02_acolite.md) | Cómo usa OCEANOS cada parte de ACOLITE, sus límites, instalación y `prepare` |
| [03_configuracion.md](03_configuracion.md) | Perfiles YAML, settings que se envían a ACOLITE y grilla |
| [04_operacion.md](04_operacion.md) | Comandos, cola search→run, `sync`, progreso, retención, catálogo SQLite y pruebas |
| [05_resultados.md](05_resultados.md) | Ensayos: diagnóstico del enmascarado, recursos, multifecha, regeneración y estado de los datos |
| [06_pendientes.md](06_pendientes.md) | Pendientes científicos, riesgos, pendientes del paralelo y trabajo futuro |

## Estado

- Wrapper local operativo, en paralelo con la CPU y RAM libres del equipo, para Sentinel-2 (CDSE) y Landsat 8/9 (USGS), con catálogo SQLite v4 legible (escenas, procesos, búsquedas, eventos y vistas) y 62 pruebas.
- 14 adquisiciones Sentinel-2 con L1R y L2W en `storage/runs/0001_…` a `0014_…`, registradas como importadas en el catálogo nuevo.
- **Ciencia pendiente:** los productos acuáticos quedan casi totalmente enmascarados por el umbral SWIR nativo y faltan datos in situ.
- Paralelo implementado sin ensayo real con descargas ([06](06_pendientes.md#paralelo-resuelto-y-pendiente)). Docker/Airflow y el cubo temporal no están iniciados.

**No descargar escenas, LUT, auxiliares ni dependencias sin autorización explícita.** Credenciales en `~/.netrc`, nunca en el repositorio ni en el catálogo.

Los informes por fase (00–35) se consolidaron en estos documentos el 07-10-2026; las versiones anteriores se recuperan con `git show 8bbd881:docs/<archivo>`.
