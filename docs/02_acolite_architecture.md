# Arquitectura y auditoría de ACOLITE

## Estado

Auditoría pendiente de fase 2. Se localizó la instalación preferida en `/home/antho/acolite`; todavía no se comprobó su versión, revisión, dependencias ni correspondencia con upstream.

Registrar revisión upstream, revisión local, diferencias y fecha. Toda afirmación técnica final debe apuntar a archivo, función y líneas de esa revisión. No sustituir inspección de código por README.

## Recorrido obligatorio

Revisar `config/defaults.txt`, `config/defaults/`, `acolite_run.py`, `inputfile_test.py`, `identify_bundle.py`, `acolite_l1r.py`, `acolite_l2r.py`, `acolite_l2w.py`, módulos API CDSE/EarthExplorer/STAC, Sentinel-2 y su submódulo Zarr, Landsat, output, proyección, NetCDF y datos auxiliares. Confirmar las rutas en la revisión auditada.

Seguir el flujo efectivo de settings desde defaults generales hasta defaults de sensor y overrides del usuario; documentar mutaciones durante ejecución y guardado de settings efectivos.

## Matriz preliminar de responsabilidades

“Por verificar” indica que no se ha demostrado la capacidad ni su limitación. Las rutas son objetivos de inspección, no resultados.

| Necesidad | ¿ACOLITE lo hace? | Módulo a inspeccionar | API/settings | Limitación por comprobar | Código propio previsto |
|---|---|---|---|---|---|
| Catálogo y filtros | Por verificar | `api/cdse`, `api/earthexplorer`, `api/stac` | Firmas reales pendientes | Paginación, atributos, fechas | Wrapper mínimo |
| Descarga | Por verificar | APIs y utilidades download | Pendiente | Reintentos, credenciales | Control de ejecución |
| Zarr remoto | Por verificar | `sentinel2/zarr` | Pendiente | Proveedor, lectura parcial | Ninguno si suficiente |
| SAFE y Landsat | Por verificar | `sentinel2`, `landsat` | Pendiente | Niveles y compresión | Ninguno |
| Recorte AOI | Por verificar | Run y lectores L1 | Pendiente | Extent frente a máscara | Ninguno |
| Alineación de bandas | Por verificar | Lectores y proyección | Pendiente | Interpolación por entrada | Ninguno |
| DSF, L2R y L2W | Por verificar | Procesadores correspondientes | Pendiente | Algoritmos y sensores | Ninguno |
| Proyección y NetCDF | Por verificar | `output`, utilidades NetCDF | Pendiente | Memoria y flags | Ninguno |
| Limpieza | Por verificar | Run y extracción | Pendiente | Orden de eliminación | Política posterior a QA |
| Historial de catálogo | Por verificar | APIs y logs | Pendiente | Versiones entre consultas | Persistencia mínima |
| Seguimiento de ejecución | Por verificar | Run y logs | Pendiente | Reanudación e idempotencia | Registro mínimo |
| Validación | Por verificar | Outputs y metadatos | Pendiente | Contrato del producto | QA simple |
| Cubo Zarr | Fuera del MVP | Auditar antes de implementar | Pendiente | Ingestión temporal | Fase futura |

No crear clientes satelitales ni algoritmos científicos nuevos antes de completar esta matriz con evidencia.
