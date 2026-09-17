# Validación y grabación en Windows

## Incidencia actual: 15 de septiembre de 2026

El inicio está bloqueado antes de compilar SRB2. Incluso ejecutar
`C:\msys64\ucrt64\bin\cmake.exe --version` termina con `0xC0E90002`
(`3236495362` sin signo, `-1058471934` con signo).
El evento 3077 de `Microsoft-Windows-CodeIntegrity/Operational` identifica
`C:\msys64\ucrt64\bin\libexpat-1.dll` como el archivo que no satisface la
política de integridad. El evento 3118 asociado indica Smart App Control.
Esto confirma un bloqueo de Windows; no demuestra que el archivo esté corrupto.

El launcher ahora informa este bloqueo de forma explícita. Para resolver la
ejecución, el proveedor de la herramienta o el administrador del equipo debe
revisar una versión o instalación compatible con la política de confianza.
No se desactivaron protecciones ni se sustituyeron DLL para eludir la política.
No tiene sentido repetir descargas de MaleCNS o reconstruir SRB2 mientras
CMake no pueda arrancar.

Verificación del 15/09: 22 pruebas Python aprobadas, excluyendo explícitamente
`tests/test_srb2_loop.py`; simulación sintética de 10 segundos terminada con
código 0. Registro independiente en `artifacts/diagnostic-20260915.*`.
La prueba actual no confirma funcionamiento del juego. Los resultados del
9 de septiembre documentados abajo son históricos.

Para consultar el diagnóstico en PowerShell:

```powershell
Get-WinEvent -LogName 'Microsoft-Windows-CodeIntegrity/Operational' -MaxEvents 20 |
    Select-Object TimeCreated, Id, Message | Format-List
```

Una vez resuelta la incidencia de confianza, comprobar primero `cmake.exe
--version`, después `python run_flysonic.py --build-only` y finalmente
`.\run-flysonic.cmd --demo-model` antes de la ejecución completa.

Trabaja desde PowerShell en la carpeta del clon, rama `sonic`:

```powershell
cd "C:\Users\elmas\Documents\SENSORIA\Fly Brain\fly-OwO"
git status --short --branch
.\run-flysonic.cmd --demo-model
```

Esta primera ejecución usa SRB2 real con un modelo pequeño de 4.096 neuronas.
Para grabar MaleCNS completo, cierra esa ejecución y ejecuta:

```powershell
.\run-flysonic.cmd
```

Abre el dashboard en http://127.0.0.1:8765/ si no aparece automáticamente.
Comprueba que indica MaleCNS y 166.700 neuronas, que la miniatura cambia con el
juego y que `Game received` recibe controles. F6 permite apagar y volver a
encender el control neuronal. Observa el factor de tiempo real: un valor menor
que 1 significa que el modelo avanza más lento que el reloj.

Graba las ventanas del juego y del dashboard con tu grabador de pantalla.
Los archivos `artifacts/latest-replay.*` son registros científicos de la
simulación, no un video. Cada ejecución reutiliza esos nombres: copia el conjunto
completo a otra carpeta antes de iniciar otra si quieres conservarlo.

## Publicar los cambios

El 9 de septiembre de 2026 se comprobó con `git ls-remote` que el fork ya tenía
`sonic` en `d40cb5a` y `main` en `58a28d2`. La portada de GitHub muestra `main`
por defecto; selecciona `sonic` para ver la adaptación a Sonic.

Después de revisar y validar los cambios locales:

```powershell
git diff --check
git diff
git add README.md run-flysonic.cmd run_flysonic.py flysonic/srb2.py patches/srb2-flysonic.patch tests/test_launcher.py tests/test_srb2_loop.py docs/windows-validation.md
git commit -m "fix: make Fly Sonic startup work on Windows"
git push -u origin sonic
```

Revisa `git status --short` antes del commit por si hay otros archivos corregidos
que debas incluir. La caché, el entorno virtual y los registros ya están excluidos
por `.gitignore`. Guarda el video como archivo de una release o enlázalo desde el
README; evita añadir las descargas o los videos grandes al historial del código.

Para que la portada muestre Sonic, abre un pull request **dentro de tu fork**:
base `LoowieOblivion-Serafin/fly-OwO:main`, compare `sonic`. Revisa y fusiona cuando
la validación sea satisfactoria. No es necesario sincronizar con el repositorio
original ni forzar un push para publicar este trabajo.

## Diagnóstico inicial

Python 3.11.9 y 3.14 estaban instalados. La inspección restringida no podía verlos;
la comprobación en la sesión real de Windows sí los encontró. Faltaba MSYS2 en
las rutas esperadas. Se instaló MSYS2 y las dependencias UCRT64 del README.

El acceso `.cmd` ahora detecta un intérprete válido y conserva los errores en
pantalla. El launcher verifica el compilador antes de descargar MaleCNS y muestra
la preparación de datos sin retener sus mensajes en un búfer. La compilación fija
C17 para SRB2 2.2.15 y selecciona las herramientas del entorno MSYS2 explícitamente.
El código del modelo neuronal no se modificó.
El parche también corrige los argumentos de `GetProcAddress` en la carga de PNG
de SRB2. La prueba de integración utiliza el mismo entorno de DLL que el launcher.

Pruebas iniciales: 17 pruebas aprobadas y la de SRB2 omitida antes de compilar;
dos pruebas nuevas de arranque aprobadas. Replay sintético exacto: 500 pasos.
MaleCNS completo preparado: 166.700 neuronas y 25.582.938 conexiones; prueba aislada
de 15 segundos, replay exacto de 589 pasos y factor final aproximado de 0,78×.
Esta medición aislada no demuestra todavía control del juego.

## Resultado con SRB2 real

La compilación Windows terminó correctamente con MSYS2 UCRT64 y GCC 16.2.
La suite completa pasó: **20 pruebas, ninguna omitida**. La prueba de SRB2
verificó imágenes entrantes, desplazamiento, salto y liberación del mando al
interrumpir las señales.

Una ejecución de MaleCNS completo con SRB2, de 90 segundos, terminó con código
de salida 0 y un factor de tiempo real aproximado de 0,85×. Se preservó su registro
en `artifacts/validation-90s/`. En una segunda ejecución visible se comprobaron
el juego y el dashboard: 166.700 neuronas, MAP01, 2 anillos, velocidad y posición,
imagen retinal y confirmaciones de avance y salto. El dashboard mostró 0,76×
en esa observación. El rendimiento depende de la carga del PC; no se garantiza
tiempo real ni que Sonic complete el nivel.

El replay del registro de 90 segundos pasó la comparación exacta de **3.834
pasos neuronales**, tanto espigas como controles:

```powershell
.\.venv\Scripts\python.exe -m flysonic.replay artifacts/validation-90s/latest-replay.index.json
```

La ventana puede indicar `FOCUS LOST` al seleccionar el dashboard; el launcher
mantiene `pauseifunfocused 0` para que la simulación continúe. Estas pruebas
se hicieron con el renderizador software. OpenGL y la grabación de video no
formaron parte de esta validación.
