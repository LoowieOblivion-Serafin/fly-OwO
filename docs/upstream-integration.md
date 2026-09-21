# Mantener Fly Sonic actualizado sin perder ninguna variante

`origin` es tu fork (`LoowieOblivion-Serafin/fly-OwO`). `upstream` es el proyecto
original (`ornata/fly`). La rama `main` del fork sigue al proyecto original;
`sonic` contiene la adaptación y las correcciones de Windows.

Un **push** publica commits de una rama. Un **merge** incorpora otra rama a la
actual. Un **pull request** propone esa fusión en GitHub. El mensaje «This branch
has conflicts» de un PR describe diferencias entre su rama de origen y su base;
no significa que los archivos guardados en las dos ramas estén dañados.

En la captura del PR, la base es `ornata:main` y la rama propuesta es
`LoowieOblivion-Serafin:sonic`: ese borrador propone cambios a la autora original.
Publicar `sonic` en tu fork no requiere fusionar ese PR ni dejar de ser borrador.
Para proponer cambios a tu propio `main`, la base debe ser tu fork. No mezcles
la adaptación en `main` si quieres mantener esa rama como copia de upstream.

## Qué conservar al integrar

| Parte | Sonic | Fly64 original |
| --- | --- | --- |
| Juego y lanzador | SRB2, `run_flysonic.py` y `run-flysonic.cmd` | sm64ex, `run-fly64` en macOS |
| Código Python | `flysonic/` | `fly64/` |
| Visión | Miniatura de pantalla de 64×48 | Cubemap en primera persona y ojos compuestos |
| Interfaz | `web/sonic/index.html` | `web/index.html`, `web/dashboard.css`, `web/dashboard.js` |
| Documentación | `README.md`, `docs/technical-notes.md` | `docs/fly64-readme.md`, `docs/fly64-technical-notes.md` |
| Causalidad | `scripts/validate_causality.py` | `scripts/validate_fly64_causality.py` |
| Registros | `artifacts/latest-replay.*` | `artifacts/fly64/latest-replay.*` |

Los cambios de visión de upstream no son directamente compatibles con el puente
SRB2. Conservar ambos paquetes permite integrar su código sin cambiar la entrada
retinal, la dinámica LIF ni el decodificador que ya utiliza Sonic. Los formatos
de puente, mensajes del dashboard y replay deben coincidir dentro de cada variante.

## Validación de esta integración: 21 de septiembre de 2026

Se integraron las actualizaciones de upstream hasta `f2f4114`, manteniendo las
dos variantes. La suite completa en este equipo Windows terminó con **41 pruebas
aprobadas y 7 omitidas**. Incluye `tests/test_srb2_loop.py` con SRB2 real sin
ventana: verifica la entrada de imágenes, los controles, el movimiento y la
liberación del mando cuando cesan las señales.

Las siete omisiones corresponden a comprobaciones nativas de Fly64 para macOS
o a herramientas no disponibles en este entorno; una indica que falta Clang.
No se ejecutó el juego Mario nativo en Windows. Este resultado no demuestra
que el nuevo renderizado de Fly64 funcione en Windows ni que Sonic complete niveles.

El documento [windows-validation.md](windows-validation.md) conserva las
incidencias y mediciones anteriores con sus fechas. Para la organización actual
de ramas y futuras integraciones, sigue el procedimiento de este documento.

Git puede interpretar archivos parecidos como renombrados de `fly64/` a
`flysonic/`. Revisa estos casos: una fusión automática puede introducir código de
ojos compuestos en Sonic aunque no deje marcadores de conflicto. No aceptes
«ours» o «theirs» para todo el árbol sin comprobar qué programa usa cada archivo.

## Incorporar los próximos cambios

Ejecuta desde PowerShell dentro del clon. Primero guarda tus modificaciones en
un commit y comprueba que no haya una fusión pendiente:

```powershell
git status
git remote -v
git branch --show-current
```

Si aún no existe `upstream`, añádelo una sola vez:

```powershell
git remote add upstream https://github.com/ornata/fly.git
```

Cuando `git status` indique un árbol limpio, descarga las referencias, cambia a
`sonic` y crea un respaldo local con un nombre nuevo:

```powershell
git fetch origin
git fetch upstream
git switch sonic
git merge --ff-only origin/sonic
git branch respaldo-sonic-antes-integracion-01
git merge upstream/main
```

Si `--ff-only` falla, la rama local y la publicada tienen commits distintos:
revisa `git log --graph --oneline --decorate --all -20` antes de decidir cómo
combinarlos. No continúes ciegamente con los pasos siguientes y no uses un push
forzado. Cambia el sufijo del respaldo en cada integración.

## Resolver, probar y publicar

Si la fusión anuncia conflictos, Git mantiene la operación abierta. Lista los
archivos pendientes:

```powershell
git status
git diff --name-only --diff-filter=U
```

Edita cada archivo para conservar el comportamiento correcto. Quita los
marcadores `<<<<<<<`, `=======` y `>>>>>>>` de los bloques resueltos. En un
conflicto modificar/eliminar, decide si el archivo original debe recuperarse
para Fly64 además de conservar su equivalente en `flysonic/`. Revisa también
los archivos que Git fusionó automáticamente.

Marca cada archivo revisado con `git add ruta/del/archivo`. Usa `git rm` solo si
has decidido eliminar ese archivo. Después:

```powershell
git diff --name-only --diff-filter=U
git diff --check
git diff --cached --check
git diff --cached --stat
git diff --cached
.\.venv\Scripts\python.exe -m pytest -q
```

La primera orden debe quedar sin salida. Verifica la funcionalidad de Sonic con
`.\run-flysonic.cmd --demo-model` y luego con `.\run-flysonic.cmd` para MaleCNS
completo. El dashboard debe recibir imágenes y mostrar controles confirmados
por el juego. Las pruebas Python de Fly64 en Windows verifican componentes
portables; no comprueban el juego Mario ni su renderizado nativo para macOS.

Cuando todo esté revisado y probado, termina la fusión y publica:

```powershell
git commit -m "merge: integrate upstream while preserving Fly Sonic"
git push origin sonic
git status --short --branch
```

Esto conserva los commits existentes y actualiza los PR que utilicen `sonic`
como origen. GitHub vuelve a calcular si se puede fusionar con la base actual.
Si upstream avanza otra vez, puede ser necesaria una integración adicional.

Para cancelar una fusión aún pendiente y volver al estado anterior, usa
`git merge --abort`. Esto descarta las resoluciones hechas durante esa fusión;
copia primero cualquier resolución que quieras conservar. Comenzar con el árbol
limpio hace que la recuperación sea predecible. No uses `reset --hard` como
procedimiento habitual para resolver conflictos.

## Actualizar main cuando se mantiene como copia de upstream

Hazlo después de terminar la integración y con el árbol limpio:

```powershell
git fetch origin
git fetch upstream
git switch main
git merge --ff-only origin/main
git merge --ff-only upstream/main
git push origin main
git switch sonic
```

Si alguna fusión rápida falla, revisa las diferencias; no reemplaces `main` por
la fuerza. La sincronización de `main` por sí sola no integra esos commits en
`sonic`. Para grabación, compilación y el historial de incidencias de Windows,
consulta [windows-validation.md](windows-validation.md). Sus resultados están
fechados; vuelve a ejecutar la validación tras modificar código.
