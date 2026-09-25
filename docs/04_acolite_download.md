# Adquisición y fallback

Preferencia condicional: Zarr remoto compatible; alternativa: escena completa temporal mediante ACOLITE.

Propuesta operativa: hasta tres intentos totales de acceso remoto ante errores transitorios, con esperas de 1 y 5 minutos. Después informar el fallo y continuar automáticamente con otra fuente compatible. Registrar proveedor, causa y cambio de fuente. No repetir errores deterministas de autenticación o formato como si fueran fallos transitorios.

La descarga alternativa tendrá hasta tres intentos totales frente a fallos transitorios. Si tampoco funciona, registrar fallo terminal y continuar con las demás adquisiciones cuando el procesamiento por lotes esté habilitado.

No implementar todavía esta política. Verificar primero los reintentos nativos de ACOLITE para evitar multiplicarlos con los del wrapper.

Antes de adquirir, comprobar espacio para archivo, extracción y resultados temporales simultáneos dentro del máximo de 50 GB. Si no hay espacio suficiente, detener esa adquisición y registrar el motivo; no borrar datos ajenos ni resultados persistentes.

Usar las credenciales locales existentes sin copiarlas a documentación, catálogo o logs. No conservar URLs firmadas con secretos cuando pueda guardarse un identificador estable.
