# Fly Sonic 🪰💙

Un modelo del cerebro de una mosca (el conectoma **MaleCNS**, 166 700 neuronas
con su cableado medido) jugando **Sonic Robo Blast 2** en lugar de Super Mario 64.

Es un fork de [Fly64](https://github.com/barrelshifter/fly64) de Jessica Paquette
([tweet original](https://x.com/barrelshifter/status/2097004115826200898)), que
hizo lo mismo con Mario. El cerebro es el mismo; lo que cambia es el "cuerpo":
en vez de parchear `sm64ex` se parchea SRB2, que es software libre (GPLv2) y cuyos
datos se distribuyen gratis, así que **no hace falta ningún ROM**.

```text
Pantalla de SRB2 → fotorreceptores R1-R8 → red MaleCNS (LIF) → neuronas descendentes → mando de Sonic → pantalla
```

> ⚠️ Es un experimento hecho con cableado real y reglas simples. **No** es una mosca
> viva ni un jugador entrenado: no hay recompensa, objetivo ni aprendizaje. Sonic
> puede quedarse pegado a una pared, caerse o dar vueltas. Sonic es marca de SEGA;
> SRB2 es un fan game de Sonic Team Junior.

## Qué necesitas

- Python **3.11 o más nuevo** y `git`.
- Un compilador de C, CMake y Ninja, más las librerías de SRB2: SDL2, SDL2_mixer,
  libpng, zlib, curl, libgme y libopenmpt (abajo está el comando por sistema).
- Espacio: ~1.1 GB para los datos de MaleCNS, ~250 MB para SRB2 (fuente + datos),
  y unos GB temporales mientras se prepara el conectoma.
- RAM: 16 GB recomendados para el modelo completo (el fixture de prueba corre en cualquier PC).
- Internet la primera vez (descarga de MaleCNS, del código de SRB2 y de sus datos).

### Windows 10/11

1. Instala [Python](https://www.python.org/downloads/windows/) (marca *Add python.exe to PATH*) y [Git](https://git-scm.com/download/win).
2. Instala [MSYS2](https://www.msys2.org) en `C:\msys64` (la ruta por defecto). Abre el acceso
   directo **"MSYS2 UCRT64"** y pega:

   ```sh
   pacman -S --needed mingw-w64-ucrt-x86_64-toolchain mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja \
     mingw-w64-ucrt-x86_64-SDL2 mingw-w64-ucrt-x86_64-SDL2_mixer mingw-w64-ucrt-x86_64-libpng \
     mingw-w64-ucrt-x86_64-zlib mingw-w64-ucrt-x86_64-curl mingw-w64-ucrt-x86_64-libgme mingw-w64-ucrt-x86_64-libopenmpt git
   ```

   (si MSYS2 está en otra carpeta, define la variable de entorno `FLYSONIC_MSYS2` con esa ruta).
3. En PowerShell, dentro de esta carpeta:

   ```powershell
   python run_flysonic.py
   ```

   También puedes usar `.\run-flysonic.cmd --demo-model` para probar primero
   Sonic con el modelo pequeño. El acceso `.cmd` busca Python y mantiene visible
   cualquier error de inicio. Para el conectoma completo, usa `.\run-flysonic.cmd`.
   El launcher comprueba las herramientas de compilación antes de descargar MaleCNS.

   Si `python` no responde, comprueba `py --list-paths` y prueba
   `py -3.11 run_flysonic.py --demo-model` desde una ventana de PowerShell ya abierta.
   `--synthetic --duration 10 --no-browser` prueba el modelo y el servidor sin SRB2;
   esa prueba por sí sola no demuestra que Sonic recibe controles.

   Consulta la [validación en Windows y guía de grabación/publicación](docs/windows-validation.md).

### Arch Linux

```sh
sudo pacman -S --needed base-devel cmake ninja git python sdl2 sdl2_mixer libpng zlib curl libgme libopenmpt
python run_flysonic.py
```

### Debian / Ubuntu

```sh
sudo apt install build-essential cmake ninja-build git python3 python3-venv libsdl2-dev libsdl2-mixer-dev \
  libpng-dev zlib1g-dev libcurl4-openssl-dev libgme-dev libopenmpt-dev
python3 run_flysonic.py
```

### macOS

```sh
brew install cmake ninja sdl2 sdl2_mixer libpng game-music-emu libopenmpt
python3 run_flysonic.py
```

## Correrlo

`python run_flysonic.py` hace todo en orden y se puede interrumpir y relanzar:

1. crea `.venv/` e instala las dependencias de Python;
2. descarga y prepara MaleCNS v1.0 en `.cache/malecns/` (tarda un buen rato la primera vez);
3. clona SRB2 2.2.15 en `.cache/srb2/`, le aplica `patches/srb2-flysonic.patch` y lo compila;
4. descarga los datos oficiales de SRB2 (`srb2.pk3`, `zones.pk3`, …) a `.cache/srb2-data/`;
5. lanza el modelo, el juego (directo en Greenflower Zone 1 con Sonic) y el dashboard
   en <http://127.0.0.1:8765/>.

Opciones útiles:

```sh
python run_flysonic.py --synthetic        # sin juego: fixture de 4 096 células + mundo sintético (prueba rápida)
python run_flysonic.py --prepare-data     # solo descargar/preparar MaleCNS
python run_flysonic.py --build-only       # solo bajar, parchear y compilar SRB2
python run_flysonic.py --demo-model       # juego real con el fixture pequeño (para PCs con poca RAM)
python run_flysonic.py --map 4 --opengl   # otro mapa, renderizador OpenGL (por defecto software)
python run_flysonic.py --start-disabled   # arranca con el control neuronal apagado
python run_flysonic.py --duration 90 --no-browser
```

Dentro del juego:

- **F6** enciende/apaga el control neuronal (también sirve la consola: `` ` `` y `fly_neural on|off|toggle`).
- Mientras el control está apagado puedes jugar tú con el teclado normal de SRB2.
- Para parar todo: cierra la ventana del juego o **Ctrl+C** en la terminal.
- El juego no se pausa al perder el foco (`pauseifunfocused 0`), así puedes mirar el dashboard.
- Variables de consola: `fly_jumptics` (cuántos tics se mantiene el salto, 8), `fly_spintics` (8),
  `fly_infinitelives` (vidas infinitas para que la demo no termine en *game over*, On).

Si el dashboard dice **GAME NOT CONNECTED**, el juego no está corriendo o no encontró
el puente; **STALE CONTROLLER** significa que el modelo va demasiado lento para mandar
controles a tiempo (prueba `--demo-model`).

## Cómo funciona

Son tres programas: el juego (SRB2 parcheado), el modelo del cerebro (Python) y el
dashboard (navegador). Se comunican por un archivo compartido en memoria
(`runtime/fly_bridge.bin`), igual que en Fly64.

### El modelo "ve" la pantalla

SRB2 toma una miniatura de **64 × 48 píxeles** de su pantalla diez veces por segundo
(renderizador de software u OpenGL). El código mide luminancia, color y cambios entre
imágenes y lo inyecta en los fotorreceptores modelados (6 006 células R1–R8, con las
columnas ópticas publicadas por los autores de MaleCNS cuando existen).

### Las señales cruzan la red

La red es MaleCNS v1.0: 166 700 neuronas y 25.6 millones de conexiones medidas. La
dinámica es una integración-y-disparo simple (50 pasos por segundo) con ruido
reproducible y una corriente de fondo; GABA, glutamato e histamina se tratan como
inhibitorios. Todo esto viene tal cual de Fly64 (`flysonic/model.py`, `flysonic/data.py`).

### Algunas señales se vuelven el mando de Sonic

Se lee la actividad del último cuarto de segundo de unos grupos de neuronas descendentes:

- **DNg100** → avance (eje analógico "adelante" de SRB2, `forwardmove` 0…50);
- **DNa02/DNg13** derecha-menos-izquierda → giro (eje analógico de giro, ±1023);
- una ráfaga en **DNp01/DNp10** → salto (`BT_JUMP` durante `fly_jumptics` tics; si Sonic ya
  está en el aire, un segundo salto es el *thok*).

El juego trata esos valores como si vinieran de un joystick analógico, después de su
propia zona muerta. Son reglas que escribimos nosotros para convertir actividad neuronal
en controles; no hay patas ni músculos simulados.

### El dashboard

Muestra la miniatura que ve la mosca, la actividad de todas las células, la densidad de
espigas, los controles pedidos y lo que el juego **realmente aplicó** ("Game received"),
más telemetría leída de SRB2: anillos, mapa, tiempo de nivel, velocidad y posición de Sonic.

### Cada paso se guarda

`artifacts/latest-replay.*` guarda miniaturas, espigas y controles de cada tick con la semilla,
y `python -m flysonic.replay artifacts/latest-replay.index.json` vuelve a pasarlas por el modelo
y comprueba que salen exactamente las mismas espigas y controles, sin necesidad de SRB2.

## Pruebas

```sh
.venv/bin/pytest -q            # Linux/macOS
.venv\Scripts\pytest -q        # Windows
```

`tests/test_srb2_loop.py` arranca el SRB2 parcheado sin ventana (drivers "dummy" de SDL),
comprueba que llegan miniaturas a ~10 Hz, que el juego aplica el avance y el salto, que Sonic
se mueve, y que suelta los controles cuando el modelo se calla. Se salta solo si todavía no
compilaste SRB2 (`--build-only`).

Más detalles, límites y el formato exacto del puente: [docs/technical-notes.md](docs/technical-notes.md).

## Créditos y licencias

- Fly64 — Jessica Paquette ([@barrelshifter](https://x.com/barrelshifter)). El modelo, la
  preparación de datos, el dashboard y la idea del puente vienen de ahí.
- MaleCNS v1.0 — Berg et al., *Sexual dimorphism in the complete connectome of the Drosophila
  male central nervous system* ([datos, CC-BY](https://male-cns.janelia.org/download/)).
- Sonic Robo Blast 2 — [Sonic Team Junior](https://www.srb2.org/), GPLv2
  (código en `.cache/srb2`, commit fijado `8701ef41`). Los archivos de datos de SRB2 se descargan
  del paquete oficial 2.2.15 y no se redistribuyen en este repositorio. Sonic the Hedgehog y
  personajes relacionados son marcas de SEGA.
