# Preparación Landsat de fase 10

Estado actualizado el 30 de septiembre: acceso USGS verificado; las tres adquisiciones Landsat 8/9 finalizaron y pasaron las comprobaciones técnicas. El perfil sigue candidato científicamente. La siguiente descripción conserva el bloqueo inicial y su resolución. El 29 de septiembre CDSE respondió HTTP 403 (DAT-ZIP-608) al sondeo de descarga, aunque publica metadata de seis productos. En ese momento no había credenciales nativas earthexplorer_token/earthexplorer disponibles. Se solicitó configuración local, sin pedir secretos en el chat.

Los footprints reales de 005/048 cubren el AOI rectangular para Landsat 9 del 1 y 17 de agosto y Landsat 8 del 9. Se proponen esas tres escenas para evitar adquirir tiles vecinos redundantes; la selección es espacial, sin filtro de nubes. No se confunde cobertura nominal WRS con footprint real de la escena.

Perfil candidato: config/aoi/lapargera_v1/acolite_l89_candidate.txt. Usa ACOLITE nativo, productos compatibles y remuestreo nearest de L1R a la grilla común de este AOI, antes de AC. L2_flags se genera después, evitando la omisión de ese dataset en el proyector final. La resolución de entrega sería 10 m; la información OLI sigue siendo de 30 m. Tile DSF 600×600 a 10 m mantiene el tamaño físico aproximado de 200×200 a 30 m. Esa elección debe comprobarse con escena y puede afectar el ajuste: el perfil no está aprobado científicamente.

NDCI no está soportado nativamente para OLI en la revisión auditada; queda explícitamente fuera de esta solicitud Landsat, sin producto sustituto ni equivalencia inventada. El perfil Sentinel-2 sí conserva NDCI. OC4 permanece excluido por decisión del usuario.

Cierre: tres escenas descargadas y procesadas, con productos, grilla y flags comprobados. Permanece pendiente la validación científica. Ver [informe final](../../31_phase10_multidate.md).

## Configuración local utilizada (bloqueo inicial resuelto)

La ruta nativa auditada consulta dos entradas distintas de `/home/antho/.netrc`. Completar localmente, sin enviar valores al chat:

```text
machine earthexplorer_token
  login USUARIO_USGS
  password TOKEN_DE_APLICACION_M2M
machine earthexplorer
  login USUARIO_USGS
  password CONTRASENA_USGS
```

La primera se usa en login-token de la API; la segunda en la ruta de descarga de EarthExplorer. Mantener permisos 600 y conservar las demás entradas del archivo. No reutilizar credenciales de CDSE o Earthdata para otro proveedor. Tener un token no demuestra todavía que la cuenta tenga acceso a la API; se comprobará sin imprimir credenciales cuando esté configurado.

## Resolución del acceso y corrección de grilla

El 30 de septiembre las dos entradas USGS estuvieron disponibles y la autenticación nativa funcionó. Se consultaron seis productos y se inició el procesamiento de los tres de 005/048. El 403 inicial de CDSE no se resolvió cambiando credenciales de proveedor: se utilizó la ruta autorizada USGS.

El primer ensayo mostró que xrange/yrange no se aplican sin `output_projection_metres=True`. Se agregó ese setting, se conservó el intento incorrecto y se reprocesó Landsat 9 desde su L1R original, sin descargar otra vez. El segundo intento confirmó x/y comunes y l2_flags presentes. Los intentos posteriores usan el perfil corregido.

El default OLI `compute_contrabands=True` puede generar una banda sintética alrededor de 613 nm que aparece en Rrs_*. No se presenta como una banda directamente observada. El inventario de variables mantiene los nombres reales por sensor.
