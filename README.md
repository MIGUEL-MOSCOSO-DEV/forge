# Forge

A local development process supervisor with port checks, environment validation and service logs.

[![CI](https://github.com/MIGUEL-MOSCOSO-DEV/forge/actions/workflows/ci.yml/badge.svg)](https://github.com/MIGUEL-MOSCOSO-DEV/forge/actions/workflows/ci.yml) · [Descargas](https://github.com/MIGUEL-MOSCOSO-DEV/forge/releases/latest) · [MIT](LICENSE)

Un supervisor de procesos de desarrollo que se ejecuta en primer plano. Reúne servicios, dependencias, variables y logs en el directorio de tu proyecto.

## Qué incluye

- Comandos como listas de argumentos, ejecutados sin shell.
- Orden de inicio por dependencias y detección de ciclos.
- Validación previa de puertos y variables de entorno requeridas.
- Logs individuales, rotación acotada y apagado de los procesos iniciados por el supervisor.

## Descargar para Windows

En [Releases](https://github.com/MIGUEL-MOSCOSO-DEV/forge/releases/latest) encontrarás Forge.exe y su archivo SHA256SUMS.txt. Es una aplicación portable para Windows 10/11 de 64 bits: no necesita instalar Python ni permisos de administrador. Ejecuta el programa desde tu terminal; --help muestra los comandos disponibles. Los ejecutables no tienen firma digital.

## Ejecutar desde el código

Necesitas Python 3.11 o superior. Crea un entorno virtual para mantener las dependencias separadas.

```sh
git clone https://github.com/MIGUEL-MOSCOSO-DEV/forge.git
cd forge
python -m venv .venv
```

En Windows:

```powershell
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\python.exe launch.py --help
```

En Linux o macOS puedes usar .venv/bin/python. Las pruebas de la lógica se ejecutan en Windows y Linux.

## Uso

Ejecuta forge init dentro de tu proyecto y configura forge.toml. Cada entrada dentro de services necesita command como lista de argumentos. Puede incluir cwd, ports, required_env y depends_on. cwd parte de la carpeta del TOML; ports contiene puertos TCP de localhost; required_env contiene nombres y depends_on nombres de otros servicios. El archivo inicial está vacío para que definas tus propios procesos.

- forge check revisa la configuración sin iniciar procesos.
- forge up inicia los servicios y mantiene el supervisor en primer plano.
- forge down solicita el cierre del supervisor de ese mismo directorio. Ctrl+C también lo detiene.
- forge status muestra el estado reciente; forge logs NOMBRE --lines 60 imprime las últimas líneas.
- --config RUTA debe ir antes del subcomando si no usas el archivo predeterminado.
- .env admite líneas NOMBRE=valor, sin expansión ni interpolación. Las variables ya presentes en el proceso tienen prioridad.

## Datos y privacidad

La instalación comienza sin registros de demostración. Los archivos de ejecución y logs quedan en .forge dentro del proyecto supervisado. La configuración y .env se leen desde el directorio del TOML. No subas logs ni variables privadas al repositorio.

## Alcance actual

Solo ejecuta configuraciones de confianza: sus comandos tienen los permisos de tu usuario. Espera hasta 30 segundos para que estén disponibles los puertos declarados. Si un servicio termina, cierra el resto; no reinicia automáticamente. No instala dependencias, contenedores ni servicios de Windows. Cada log conserva unos 5 MB más su versión anterior; la comprobación de puertos no garantiza disponibilidad continua ni elimina todas las carreras de inicio.

## Desarrollo y pruebas

```sh
python -m pip install . -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
```

Las pruebas usan directorios y datos temporales. GitHub Actions verifica formato y pruebas en Windows y Linux y construye un ejecutable de Windows como artefacto del workflow. No hay una aplicación web ni un servidor remoto requerido.

## Generar el ejecutable

Desde Windows, con las dependencias de desarrollo instaladas:

```sh
python -m PyInstaller --noconfirm --clean --onefile --name Forge launch.py
```

El resultado queda en dist/Forge.exe. PyInstaller construye para el sistema donde se ejecuta; para generar Windows necesitas construir desde Windows. Los archivos de compilación y los datos locales se excluyen de Git.

## Estructura

supervisor.py valida la configuración, ordena dependencias, bloquea supervisores duplicados y administra procesos y logs; cli.py contiene los comandos.

## Contribuir

Abre un issue con el sistema operativo, la versión y los pasos para reproducir el problema. No incluyas archivos privados, contraseñas ni bases reales. Para cambiar reglas de negocio, añade una prueba que describa el caso.

Creado por [Miguel Moscoso](https://github.com/MIGUEL-MOSCOSO-DEV). Licencia MIT.
