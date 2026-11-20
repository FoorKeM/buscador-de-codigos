# Compilación v176

La v176 conserva el inicio de sesión por `https://portal.defontana.com/login`
y sus controles para evitar reenviar la contraseña tras un resultado incierto.
La v175 detectada por Defender no se restauró ni se reutilizó como ejecutable.

## Entorno independiente

El usuario autorizó preparar Python como herramienta de compilación, sin
reemplazar el Python existente ni modificar Defender.

- Python oficial 3.13.17, instalador Windows x64 de python.org.
- SHA-256 del instalador:
  `5da012101ba2e17113a9a1cd901e9ce1441086f2b7ecb5de06ec94163899a190`.
- Firma Authenticode válida de Python Software Foundation, verificada antes
  de ejecutar el instalador.
- Instalación en `build/toolchain-v176/python313`, sin modificar PATH,
  asociaciones, accesos directos ni instalar otro lanzador de Python.
- Entorno de compilación en `build/venv-v176`.
- 17 paquetes obtenidos de PyPI; sus artefactos y hashes se contrastaron con
  la API de PyPI. Las versiones y hashes están en
  `requirements-build-v176.lock` y el informe original de pip en
  `build/toolchain-v176/dependencies-report.json`.
- PyInstaller 6.22.3 y hooks 2026.8; salida onedir, sin UPX.
- Caché de compilación privada: `build/toolchain-v176/pyinstaller-cache`.

Comando de compilación, con el entorno ya preparado:

```powershell
$env:PYINSTALLER_CONFIG_DIR = "$PWD/build/toolchain-v176/pyinstaller-cache"
$env:PYTHONHASHSEED = '0'
& 'build/venv-v176/Scripts/python.exe' -I -m PyInstaller --clean --log-level WARN --noconfirm BuscadorCodigos-v176.spec
```

## Comprobaciones

- 121 pruebas unitarias sin interfaz: correctas.
- Siete escenarios de login con Edge sin conexión, solicitudes interceptadas
  y credenciales ficticias: correctos.
- Código de la aplicación dentro del EXE comparado con la fuente: coincide.
- Bibliotecas de Python 3.13 y controlador de Playwright incluidos.
- Análisis personalizado previo de la distribución: cero detecciones v176.
- Ejecución real del nuevo EXE con `--check-installation`, ventana oculta y
  APPDATA/LOCALAPPDATA temporales: salida 0; informe en
  `build/toolchain-v176/startup-check.json`.
- Esa comprobación cargó NumPy, pandas, Tk y Playwright e hizo una lectura y
  escritura de Excel en memoria. No abrió la interfaz ni el navegador, no leyó
  cuentas guardadas ni intentó autenticarse.
- Consulta posterior a la ejecución: cero detecciones v176 registradas por
  Defender; el ejecutable sigue presente y conserva el SHA-256 verificado.

SHA-256 del ejecutable:
`0eef8d9d721b38edd5be782c1432a085045b54600faf58c27f7412888d062f31`.

El análisis y la comprobación de instalación no equivalen a confirmar un falso
positivo ni garantizan el comportamiento de Defender en una operación real.
Posteriormente, el usuario confirmó que la v176 funciona bien y autorizó su
publicación oficial. Se publica el mismo ejecutable probado, sin recompilarlo.

El ZIP de distribución contiene 1.804 archivos, sin preferencias ni credenciales
locales. Su integridad y todos sus archivos extraídos se comprobaron con las
funciones de instalación de los lanzadores 1.0 y 1.1, tanto con una instalación
v174 previa como sin el ejecutable anterior. Ambos detectan la nueva versión.
SHA-256 del ZIP:
`34bb8fa2f90e5236003053f100e2a175b069855605d5dccdf91f5e99bf7fd568`.
