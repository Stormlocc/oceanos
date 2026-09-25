# L2R y reutilización para nuevos productos

Auditoría estática de fase 2, 25-09-2026. Revisión upstream `80da0c0c681d9597fd4b7737837d6a3e61907b33`. Las capacidades de código no equivalen a validación científica ni prueba con una escena real.

L2R escribe reflectancia de superficie `rhos_*` y conserva por default de S2/L8/L9 `lon,lat,sza,vza,raa,rhot_*`. La presencia de rhot es importante para recalcular flags, no solo para RGB. La cobertura espectral de rhos depende también de filtros de bandas y transmisión de gases: no prometer 13 reflectancias corregidas sin revisar el output.

La relación en L2W es Rrs=rhos/pi; rhow copia rhos con máscara acuática. `rrs` en minúsculas significa reflectancia remota subsuperficial con transformación adicional, no un alias intercambiable de Rrs.

L2R conserva atributos atmosféricos y proyección; flags L2W se calculan después, y no deben suponerse presentes como dataset L2R por defecto. `acolite_l2r` devuelve ruta y settings efectivos, y escribe archivo de settings L2R. Fuente: [acolite/acolite/acolite_l2r.py:528](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2r.py#L528-L530), [acolite/acolite/acolite_l2r.py:568](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2r.py#L568-L586), [acolite/acolite/acolite_l2w.py:232](https://github.com/acolite/acolite/blob/80da0c0c681d9597fd4b7737837d6a3e61907b33/acolite/acolite/acolite_l2w.py#L232-L281).

## Reprocesamiento mínimo

Conservar inicialmente L2R útil sin recortar bandas arbitrariamente. Para una variable nueva, comparar algoritmo/configuración, revisión ACOLITE, grilla y dependencias espectrales/TOA. Si bastan, utilizar `acolite_l2w` sobre ese L2R y registrar resultado derivado con ejecución padre. Si cambia la corrección atmosférica o faltan dependencias, repetir desde fuente/L1R según necesidad.

`acolite_run` distingue un archivo L1R de uno ya procesado y puede llegar a L2W sin repetir AC, pero identify_bundle exige generated_by ACOLITE y al menos rhot/bt. No minimizar L2R hasta romper ese contrato. Rutas/nombres de salida pueden coincidir si se reutiliza directorio: usar directorio distinto por ejecución.

Candidato de conservación: L2R nativo + L2W nativo y solo la salida proyectada que resulte necesaria. La decisión A/B permanece en fases de configuración y benchmark; la auditoría favorece evaluar si single-tile ya mantiene la grilla requerida y evita reproyección redundante.
