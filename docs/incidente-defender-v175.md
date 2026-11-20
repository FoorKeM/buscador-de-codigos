# Detección de Defender en la v175

Fecha: 20-11-2026, America/Santiago. La v175 es una compilación local de prueba;
la versión publicada sigue siendo v174.

## Evidencia

- Detección: `Trojan:Win32/Bearfoos.A!ml`, ThreatID `2147731250`.
- Primera detección registrada: 10:24:55. Los registros de Defender incluyen
  el proceso de la v175 y su ejecutable de distribución.
- Defender registra una acción de corrección satisfactoria. El ejecutable
  `dist/BuscadorCodigos-v175/BuscadorCodigos-v175.exe` ya no está presente.
- Inteligencia de seguridad registrada: `1.463.384.0`.
- SHA-256 registrado antes de la detección:
  `cf04fd3ca4d054c99bbcf06bb919e212f5c1ae8fbbca285693c4f084dbbe2c6a`.
- El código empaquetado se había comparado con la fuente y coincidía. Las
  119 pruebas unitarias y siete escenarios de navegador sin conexión pasaron.
- El análisis personalizado previo había registrado cero detecciones. Este
  resultado no predijo ni invalida la detección posterior durante la ejecución.

## Comparación sin ejecutar el archivo bloqueado

El diff de la aplicación respecto a v174 cambia el acceso al portal de
Defontana, su confirmación y los controles que impiden reenviar la contraseña
si el resultado es incierto. También actualiza etiquetas y la versión. No se
identificó en ese diff funcionalidad nueva de inyección, persistencia ni
descarga y ejecución de programas.

Se compararon los 1.821 archivos de dependencias de ambas distribuciones:

- No hay archivos agregados ni ausentes.
- 98 binarios cambian sus firmas Authenticode o checksum. Al excluir únicamente
  la tabla de certificados y los campos de firma/checksum del PE, sus contenidos
  coinciden. No se encontraron cambios en su código binario con esta comparación.
- Las cuatro muestras de firma verificadas (Python y un módulo de NumPy en
  ambas versiones) tienen estado válido y el mismo firmante, OpenAI OpCo, LLC,
  con emisor Microsoft ID Verified CS AOC CA 04.
- `base_library.zip` tiene los mismos archivos y contenidos descomprimidos.
- El otro archivo distinto es el manifiesto de instalación `RECORD` de NumPy.
- El ejecutable original de v174 conserva su SHA-256 documentado:
  `7c897e43ddddde7331fb25443cf1f84cff6eb0250ff5e27362b6e16d7249ee0d`.

Esta revisión reduce las diferencias a investigar, pero no determina qué
provocó la clasificación ni demuestra que sea un falso positivo. No es un
análisis integral de malware.

## Estado y siguiente paso

No se restauró ni ejecutó la v175 durante esta revisión, no se alteró Defender
y no se intentó iniciar sesión. No se generó otra variante del ejecutable.
No se publicó la v175 ni se enviaron archivos a terceros.

Para disputar la clasificación, Microsoft indica presentar el archivo como
desarrollador y esperar su determinación. El envío requiere autenticación y
compartir el archivo; no se ha realizado ni se presupone autorización para ello.

Fuentes oficiales:

- https://learn.microsoft.com/en-us/defender-xdr/developer-faq
- https://learn.microsoft.com/en-us/defender-xdr/submission-guide
- https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?name=Trojan%3AWin32%2FBearfoos.A%21ml

Mientras se investiga, la v174 permite trabajar con la búsqueda y archivos
Excel cargados manualmente. Su actualización automática todavía usa el acceso
de Tivendo que el usuario informó como defectuoso; debe evitarse durante esa
incidencia del proveedor.
