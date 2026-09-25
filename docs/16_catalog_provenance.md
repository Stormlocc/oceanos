# Catálogo y provenance — diseño de fase 3

Fecha: 25 de septiembre de 2026. Estado: diseño documental terminado, sin base de datos creada ni código de implementación. Se apoya en las firmas y límites de ACOLITE auditados en fase 2, revisión `80da0c0c681d9597fd4b7737837d6a3e61907b33`.

## 1. Decisión de almacenamiento

Usar **SQLite como único catálogo**, con columnas consultables y campos JSON de metadata seleccionada. Los NetCDF, logs, settings y reportes permanecerán como archivos. No crear inicialmente JSONL paralelo, Parquet, servicio de base de datos ni un catálogo satelital propio.

El volumen inicial es un AOI, Sentinel-2 y veinte días. No se ha consultado el número de adquisiciones, por lo que no se inventa un conteo. El patrón esperado es una escritura secuencial por consulta/escena y consultas por adquisición, revisión, AOI, configuración y estado. SQLite permite transacciones y relaciones para este patrón, mientras JSONL requeriría lógica adicional para actualizar estado, buscar dependencias y recuperar interrupciones. Parquet no aporta una ventaja necesaria al seguimiento transaccional inicial.

Los snapshots serán filas inmutables en SQLite, no duplicados de todos los resultados en archivos JSON. JSON externo será solo exportación explícita para inspección/intercambio. Mantener un único escritor en el MVP; no activar infraestructura de concurrencia antes de necesitarla.

Ubicación: `storage/catalog/catalog.sqlite`, dentro del filesystem Linux de WSL. No operar una misma base activa simultáneamente desde Windows, WSL y Colab. Una exportación/respaldo de SQLite debe ser consistente mediante su mecanismo de backup o cerrando todos los escritores; no copiar archivos activos a ciegas. Colab/nube se resolverá en sus fases, no con una base compartida sobre Drive.

## 2. Separar lo que identificamos

| Concepto | Identidad y alcance |
|---|---|
| AOI | Identificador humano, hash del archivo geométrico y versión del perfil |
| Adquisición | Observación física: plataforma, instante original y tile S2 o path/row Landsat; órbita si está disponible |
| Producto publicado | Proveedor + colección + identificador del producto; nivel y baseline/versionado son atributos explícitos |
| Representación | SAFE, Zarr u otra fuente compatible del producto; URI estable y checksum con algoritmo si existe |
| Snapshot de metadata | Estado seleccionado de ese producto/representación observado en una consulta |
| Ejecución | Intento de producir un conjunto de resultados con entrada, AOI, versión ACOLITE y configuración identificados |
| Artefacto | Archivo producido por una ejecución, con tipo, variables, grilla y estado de validación |

No deduplicar por fecha sola: pueden existir dos plataformas, horas, órbitas o revisiones diferentes el mismo día. No confundir misma adquisición con mismo producto procesado. El checksum de un ZIP no será igual al de una representación Zarr; eso no demuestra cambio científico por sí mismo.

S2: proponer acquisition_key con plataforma + sensing datetime + tile y órbita cuando esté disponible. Mantener precisión original del timestamp, sin redondear ni agrupar por cercanía. Landsat: plataforma + fecha/hora disponible + path/row. Los valores derivados del nombre se marcan como derivados, no como campos explícitos del proveedor.

Si falta información, conservar la identidad del proveedor y usar vínculo de adquisición provisional. No fusionar automáticamente registros ambiguos. Si SAFE y Zarr no tienen una correspondencia verificable de adquisición, nivel y baseline, no declararlos equivalentes solo porque se solapan espacialmente.

## 3. Modelo mínimo: seis tablas

Los nombres siguientes son el contrato documental, no SQL ejecutable. Identificadores internos opacos, timestamps UTC, rutas de artefactos relativas a la raíz del almacenamiento. La codificación interna puede usar claves ASCII; toda documentación será en español.

### consultas

Una fila por intento de consultar un proveedor. Campos: query_id, batch_id para agrupar proveedores de una solicitud, parent_query_id para reintento, aoi_id, geometry_sha256, proveedor, endpoint estable, colección, requested_filter_json, effective_filter_json, adapter_version, revision_acolite, started_at, finished_at, status, completeness, returned_count, unique_count, error_summary y coverage_notes_json.

Estados: STARTED, SUCCEEDED, PARTIAL, FAILED, INTERRUPTED. Completitud: COMPLETE, UNKNOWN o INCOMPLETE. SUCCEEDED significa que el adaptador terminó, no que haya demostrado cobertura completa. Una consulta vacía debe persistirse, pero no considerarse éxito completo si pudo haber un error HTTP o paginación incompleta.

### versiones_producto

Una fila inmutable por snapshot de metadata seleccionada. Campos: product_version_id, proveedor, colección, provider_product_id, acquisition_key, identity_status, platform, sensor, level, acquisition_start/end, tile, path, row, orbit, baseline, processing_time, provider_updated_at, metadata_json, field_provenance_json, representation_json, metadata_hash, content_signature, signature_confidence y first_observed_at.

Una restricción lógica evita duplicar proveedor + colección + identificador + metadata_hash. content_signature puede ser desconocida; nunca convertir null en una supuesta prueba de igualdad. La representación contiene tipo de formato, identificador estable, URI saneada, checksum/algoritmo, tamaño y relación explícita con otra fuente si se conoce.

La misma adquisición puede tener varios snapshots, productos y representaciones. Un cambio administrativo puede crear snapshot nuevo manteniendo la misma firma científica demostrada. No modificar snapshots previos para mostrar únicamente la versión más reciente.

### observaciones

Relación query_id + product_version_id, única para cada par. Campos adicionales: observed_at, occurrences_in_response, eligibility, selection_reason, comparison_class y compared_to_version_id.

Permite responder cuándo volvió a aparecer un producto sin duplicar metadata idéntica en cada consulta. Las repeticiones dentro de la misma respuesta se cuentan y no producen varias ejecuciones.

### ejecuciones

Campos: run_id, aoi_id, geometry_sha256, query_id, product_version_id, requested_products_json, source_snapshot_json, config_snapshot_json, settings_files_json, processing_key, provenance_hash, parent_artifact_id, status, validation_status, cleanup_status, attempt_count, started_at, finished_at y error_summary.

La configuración científica y de entorno se guarda como snapshot inmutable al comenzar el intento; el estado operativo se actualiza mediante transacciones acompañadas de eventos. Un reintento completo de procesamiento usa un nuevo run_id y registra la relación con el anterior. Un reintento de transporte previo al procesamiento se registra como evento del mismo run.

No imponer unicidad global a processing_key: un intento fallido no debe impedir el siguiente. Para el MVP secuencial, buscar una ejecución validada y artefactos disponibles antes de omitir procesamiento. Bloquear futuras ejecuciones concurrentes del mismo trabajo solo cuando exista esa concurrencia.

### artefactos

Campos: artifact_id, run_id, tipo (L1R/L2R/L2W/log/settings/validation/metrics), relative_path, size_bytes, sha256 si calculado, variables_json, grid_json, algorithm_metadata_json, validation_status, availability y created_at.

availability distingue PRESENT, MISSING, DELETED y SUPERSEDED cuando proceda. Un resultado antiguo reemplazado puede permanecer disponible; superseded no equivale a borrado. No marcar como presente un archivo no comprobado. Un L2R reutilizado se referencia como padre y nunca se sobrescribe al derivar otro L2W.

### eventos

Campos: event_id, run_id opcional, query_id opcional, timestamp, event_type, attempt, state_before/after y details_json saneado. Registrar inicio/fallo/reintento, fallback, validación, publicación de artefactos, limpieza e interrupción. No almacenar trazas que contengan tokens ni cuerpos de respuesta de autenticación.

### Índices previstos

Índices sobre identidad proveedor/colección/producto, acquisition_key, metadata_hash, observaciones por consulta, ejecuciones por AOI+processing_key+estado, artefactos por run/tipo y eventos por run/fecha. Mantener una versión de esquema de base de datos. No diseñar índices sobre cada atributo JSON ni tablas de cada banda antes de medir necesidad.

## 4. Metadata que se conserva

| Campo o grupo | CDSE vía ACOLITE | EarthExplorer vía ACOLITE | STAC vía ACOLITE | Decisión |
|---|---|---|---|---|
| Identificador/nombre | Nombre y UUID en URL | Entity y product identifiers | id | Obligatorio o registro no procesable |
| Proveedor/colección/nivel | Consulta, atributos o nombre | Dataset/metadata | collection/properties | Guardar origen del valor |
| Tiempo/plataforma/tile/órbita | Attributes/nombre según disponibilidad | Metadata según dataset | Properties/id | Guardar para identidad y búsqueda |
| Baseline/versión | Attributes/nombre; no asumir presencia | Metadata/product name | Properties/id según proveedor | Guardar si disponible; desconocido explícito |
| Nubosidad | Attributes si disponible | Metadata si disponible | Properties si disponible | Conservar aunque filtro esté desactivado |
| Footprint | Top-level descartado por retorno actual | No garantizado en listas metadata | geometry | Conservar cuando se exponga; no sustituir por AOI |
| Tamaño/checksum | Top-level normalmente no expuesto | No garantizado | Asset/extensions si existen | No inventar; algoritmo obligatorio si hay checksum |
| Fuentes/formato | URL de descarga | Referencia entity/dataset | Assets y formatos | Identificador recuperable, sin URL secreta |
| Estado de disponibilidad | No garantizado | No garantizado | Según campos del proveedor | Registrar como evidencia, no certeza permanente |
| Parámetros y resultado de consulta | Debe registrar nuestro adaptador | Igual | Igual | Persistir en consultas |

La tabla describe acceso del código auditado; no se han realizado consultas reales de adquisiciones ni demostrado presencia de todos los campos en agosto de 2026.

Guardar únicamente atributos adicionales que expliquen identidad, calidad, cambios o reproducibilidad: product type, procesamiento, órbita, geometría, fechas de publicación/actualización y checksum. No conservar HTML de EarthExplorer, miniaturas, tokens, headers de autenticación ni enlaces de sesión. Mantener nombres originales de los atributos seleccionados para auditar su normalización.

Distinguir tres casos: campo con valor, campo explícitamente nulo y campo no expuesto por el retorno. field_provenance_json contiene estado, ubicación original del campo y si fue derivado del nombre. Un cambio de metadata “desconocida” a “disponible” no demuestra que el producto físico haya cambiado.

## 5. Extensión mínima necesaria de ACOLITE

Decisión para la futura implementación: seguir usando `ac.api.cdse.query(..., attributes=True)` y la paginación nativa. Antes de automatizar, introducir una extensión estrecha y opcional de esa función para exponer metadata seleccionada del objeto `v` que ya recibe, así como estado HTTP/paginación. Mantener el retorno por defecto compatible. No duplicar la búsqueda OData en un cliente propio, no interceptar globalmente requests y no hacer una consulta adicional por cada escena solo para recuperar campos ya recibidos.

La extensión se implementará y probará únicamente cuando corresponda programar; preferir contribución upstream o parche pequeño versionado. Su diff/hash forma parte de la revisión efectiva del procesador. Si no se incorpora, el catálogo funciona con campos desconocidos, pero no debe prometer comparación íntegra de footprint/checksum ni declarar completitud robusta de consultas erróneas.

EarthExplorer requiere igual consideración para estado/completitud y metadata top-level cuando se incorpore Landsat; no crear esa extensión ahora. STAC conservará el retorno completo de features en memoria para seleccionar campos, con `select_features=False`; no persistir todos sus assets indiscriminadamente.

Esta limitación demostrada justifica adaptar el retorno existente. No autoriza cambiar algoritmos científicos ni reemplazar clientes.

## 6. Intervalo y selección

Contrato interno: rango UTC semiabierto **[2026-08-01T00:00:00Z, 2026-08-21T00:00:00Z)**, equivalente al 1–20 de agosto inclusive. Se adopta UTC como convención del catálogo satelital; si en el futuro se piden días civiles de Puerto Rico, convertir explícitamente, no reinterpretar estos valores silenciosamente.

- CDSE: la función usa inicio estricto `gt` y suma un día al end_date. La adaptación mínima debe permitir inicio inclusivo sin extender por segunda vez el final. Antes del parche, una consulta manual puede usar inicio algo anterior y aplicar filtro exacto posterior, dejando ambos intervalos registrados.
- STAC: siempre proporcionar bbox para evitar el defecto auditado sin limit. Solicitar hasta 21-08T00:00Z y excluir localmente adquisiciones con inicio igual o posterior; así no depender de si el servicio incluye su frontera final. La semántica se probará con metadata real.
- EarthExplorer: no asumir la regla CDSE; establecer filtro propio conforme al contrato de su API al incorporarlo y aplicar pertenencia temporal final.

Filtrar tile 19QGV, plataforma Sentinel-2, nivel L1C y correspondencia espacial; nubosidad desactivada mediante valor nulo del filtro, no cero. Guardar nubosidad observada. Procesar todas las adquisiciones elegibles y las revisiones científicamente distintas encontradas. No elegir “la mejor escena del día”. No añadir un límite de nube implícito.

La ausencia de una escena en una consulta posterior no prueba eliminación del proveedor: puede deberse a filtros, paginación, servicio o ventana temporal. Solo actualizar last_seen derivable de observaciones; nunca eliminar historial por ausencia.

## 7. Hashes e idempotencia

### Metadata seleccionada

metadata_hash = SHA-256 de la representación canónica de metadata seleccionada y estable, con versión de normalizador incluida. Ordenar claves de objetos; usar JSON UTF-8, fechas UTC normalizadas, sin NaN/Infinity; conservar precisión numérica y cadenas baseline. Ordenar listas solo si semánticamente son conjuntos. No redondear geometrías, reordenar coordenadas ni cambiar el algoritmo de checksum.

Excluir timestamps de consulta, URLs firmadas/caducables, rutas temporales, orden de páginas y valores de logging. Mantener los valores originales seleccionados por separado. Cambios de normalizador generan una nueva versión del esquema de hash, no una falsa revisión científica.

### Identidad científica de la entrada

content_signature combina evidencia disponible de producto, baseline/processing version, checksum y tipo de representación. Guardar signature_confidence como STRONG, VERSIONED o UNKNOWN. Un checksum se compara solo dentro del mismo algoritmo y representación comparable. No calcular un “checksum total Zarr remoto” descargando todos los chunks: usar identidad/versionado/manifest del proveedor si existe y declarar el límite si no existe.

### Trabajo previsto y provenance final

processing_key se calcula antes de ejecutar: AOI+hash geométrico, revisión de entrada elegida, revisión ACOLITE y parche si existe, defaults/overrides relevantes resueltos, productos solicitados y definición de grilla, política de auxiliares y versiones de tablas/RSR conocidas. Es una clave de trabajo, no garantía de igualdad numérica bit a bit.

provenance_hash se completa después con settings efectivos por etapa, fuentes auxiliares y LUT realmente usadas, entorno, algoritmos/bandas reales y artefactos. Los auxiliares resueltos durante ejecución no pueden inventarse en una clave previa. Si se usan recursos no versionados, registrar URI/fecha/checksum disponibles y la incertidumbre; la ejecución sigue trazable sin afirmar reproducibilidad exacta.

No incluir rutas de salida, run_id, verbosidad, número de reintentos o timestamp del run en la clave científica. Una configuración sin cambios y resultados validados disponibles permite omitir trabajo bajo la misma política versionada. Si se exige reproducibilidad estricta y la identidad de fuente/auxiliares es desconocida, no omitir automáticamente sin resolver esa incertidumbre.

El hash del KMZ se conserva para trazabilidad; un cambio de empaquetado puede cambiar bytes sin cambiar geometría. Inicialmente eso provoca una nueva revisión AOI conservadora. No construir normalización geométrica sofisticada en el MVP.

## 8. Detección de cambios y acción

| Observación | Registro | Acción de procesamiento |
|---|---|---|
| Producto nuevo | Nuevo snapshot y observación | Procesar si elegible |
| Mismo snapshot en otra consulta | Nueva observación, reutiliza snapshot | Omitir solo si trabajo ya validado y archivos disponibles |
| Mismo producto, nueva baseline/versión | Nuevo snapshot, relación con anterior | Reprocesar; conservar ambos históricos |
| Checksum distinto, representación comparable | Nueva revisión de contenido | Reprocesar aunque el proveedor reutilice id |
| Metadatos administrativos distintos | Nuevo snapshot administrativo | No recalcular ciencia sin otro cambio |
| Nueva representación Zarr equivalente demostrada | Registrar fuente y vínculo | No recalcular producto válido solo por cambiar acceso |
| SAFE frente a Zarr sin equivalencia demostrada | Fuentes relacionadas provisionalmente | No deduplicar científicamente; comprobar antes de omitir |
| Campo antes desconocido ahora disponible | Nuevo snapshot enriquecido | Resolver identidad; no clasificar automáticamente como cambio de imagen |
| Fuente desaparece de una consulta | Conservar last_seen e historial | No borrar ni marcar producto eliminado |
| Cambia configuración/ACOLITE | Nuevo processing_key | Reprocesar o derivar según dependencias |
| Archivo final falta o no valida | Registrar indisponibilidad/fallo | Recalcular parte necesaria; no omitir por un registro viejo |

Ante cambio no clasificable: marcar REVIEW_REQUIRED, registrar motivo y no usarlo para omitir trabajo. En operación futura puede continuarse con otras adquisiciones; no introducir equivalencia científica por defecto.

## 9. Reutilización de L2R

Antes de descargar por un producto nuevo, buscar artefactos L2R PRESENT y validados para la misma adquisición/revisión, AOI, corrección y grilla compatible. Verificar archivo, variables, metadatos y las dependencias nativas del algoritmo solicitado.

Rrs requiere rhos; TUR, OC3, NDCI, FAI y NDVI requieren sus bandas específicas, y los productos acuáticos necesitan además TOA/bandas para regenerar flags. El contrato exacto depende de ACOLITE, no de una suposición basada solo en el nombre del archivo. El L2R de un producto con baseline diferente no sustituye la nueva revisión. Si cambia AC atmosférica no basta generar otro L2W.

Si basta L2R: crear nuevo run de derivación con parent_artifact_id, mismo provenance de fuente y configuración del nuevo producto, sin descargar SAFE ni repetir AC. Si falta información: adquirir entrada y reprocesar. Si el producto no está soportado —OC4 en MSI auditado— marcar UNSUPPORTED y no descargar para intentar resolverlo.

Sin modificar productos anteriores, el catálogo distingue requested_products de produced_variables. No declarar cumplida una solicitud porque ACOLITE produjo un L2W parcial.

## 10. Transacciones y recuperación

1. Persistir STARTED de consulta antes de llamar al proveedor. Finalizar resultado y observaciones en una transacción corta; nunca mantener una transacción abierta durante red o ACOLITE.
2. Si el cliente retorna todo al final, solo persistir resultados efectivamente devueltos. Ante fallo a mitad de paginación sin retorno parcial, registrar fallo/completitud desconocida; no inventar páginas recuperadas.
3. Crear run y snapshot de configuración antes de adquirir. Cada cambio de estado y su evento se confirman juntos.
4. Escribir resultados inicialmente en directorio de ejecución. Validar, registrar artefactos y completar commit de validación antes de autorizar limpieza raw.
5. SQLite y filesystem no comparten transacción atómica. Ante interrupción, reconciliar existencia/legibilidad de archivos y registros: salida huérfana no equivale a validada; estado PROCESSING no demuestra que siga ejecutándose.
6. Fallo de limpieza después de éxito deja run validado y cleanup pendiente/fallida. Reintentar limpieza no repite AC.
7. Limpieza por fallo agotado se registra separadamente con motivo y referencia recuperable; nunca marca VALIDATED.

Guardar configuración efectiva y logs en storage/runs/<run_id>; sus rutas y hashes se enlazan desde artefactos. Conservar productos en directorios por run para no colisionar entre revisiones. Retención del catálogo indefinida por ahora. Respaldar antes de migraciones de esquema y al cerrar lotes importantes; destino externo de respaldo sigue pendiente.

## 11. Comprobaciones mínimas y tests futuros

La fase actual valida coherencia del diseño, no una base de datos implementada. Tests necesarios cuando se programe:

| Caso | Resultado esperado |
|---|---|
| Repetir consulta idéntica | Dos consultas, dos observaciones, un snapshot; cero cálculo duplicado si artefacto válido |
| Duplicado dentro de respuesta | Una observación con contador, no dos ejecuciones |
| Baseline o checksum cambia | Nueva revisión y nuevo trabajo; historial intacto |
| Cambia solo URL firmada | No cambia metadata_hash científico ni provoca reprocesamiento |
| Nuevo Zarr sin equivalencia demostrada | No fusiona producto científico automáticamente |
| Solicitar nuevo producto derivable | Reutiliza L2R, conserva padre, no descarga |
| Solicitar OC4 MSI no soportado | Estado explícito, sin descarga ni éxito ficticio |
| Query vacía con error o truncada | No se registra completa y exitosa por tener lista vacía |
| Fechas límite | Incluye 01-08 00:00; excluye 21-08 00:00 bajo contrato interno |
| Interrupción antes de validación | No elimina raw ni acepta artefacto huérfano |
| Artefacto registrado pero ausente | No omite procesamiento basándose solo en SQLite |
| Error borrando después de validación | Reintenta limpieza, sin repetir procesamiento |

No crear suite genérica de bases de datos ni tests de fórmulas científicas que ya pertenecen a ACOLITE. Pruebas de adaptadores con pequeñas respuestas saneadas, más integración real posterior de una escena.

## 12. Cierre y pendientes delimitados

Quedan definidos almacenamiento, entidades, metadata importante, clasificación de cambios, claves, recuperación y política de reutilización. No se necesita conocer todavía el número exacto de escenas para decidir SQLite; se medirá con la primera consulta autorizada de adquisición.

Pendientes de implementación futura: extensión compatible del retorno CDSE, mapeo de nombres reales de campos con una respuesta del servicio, completitud HTTP/paginación, creación/migración de SQLite y tests. Pendientes científicos de fase 4: OC4, máscara FAI/NDVI, versión de ejecución y estrategia de proyección. No confundir esos pendientes con ausencia de diseño del catálogo.

Fuentes técnicas: [auditoría de APIs](03_acolite_catalog.md), [L2R y dependencias](10_acolite_l2r.md), [productos y flags](11_acolite_l2w.md), [política de limpieza](17_raw_cleanup_policy.md) y [evidencia de funciones nativas](evidence/phase2/comprobaciones.json). No se escribieron SQL, wrapper ni cliente satelital durante esta fase.
