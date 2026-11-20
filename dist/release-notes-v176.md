El Buscador ahora inicia sesión desde **https://portal.defontana.com/login**, utilizando el botón **Confirmar**. Desde allí continúa hacia Punto de Ventas y ERP Digital para actualizar artículos, packs, precios y proveedores.

- Se retira el uso del formulario de acceso de Tivendo, que está presentando errores de autenticación.
- Reconoce una sesión del portal ya abierta, incluso si la redirección ocurre mientras carga el formulario.
- Comprueba que apareció el menú de módulos antes de continuar. Si el resultado del acceso es incierto, requiere verificación o está bloqueado, se detiene sin reenviar la contraseña automáticamente.
- Mantiene los reintentos por fuente, la cancelación de actualizaciones y los datos anteriores cuando una descarga falla.
- El correo y la contraseña de Defontana se pueden editar desde la tuerca de Configuración.
- Compilación con Python oficial 3.13.17 y dependencias verificadas en un entorno independiente. El usuario no necesita instalar Python para usar el programa.

Se conservan la búsqueda, los formatos de Excel y el lanzador habitual. La actualización se recibirá al cerrar y volver a abrir el programa desde el acceso de siempre.

Verificación: 121 pruebas automáticas, siete escenarios de acceso simulados sin conexión, comprobación de arranque del ejecutable y prueba real confirmada por el usuario. El paquete completo se verifica con los lanzadores 1.0 y 1.1 antes de publicarlo.
