> **Fork per AYN Thor Max** (Snapdragon 8 Gen 2): impostazioni di default per il Thor, salvataggio periodico della cache
> shader e uno script che compila l'APK in un comando. Leggi **[THOR_MAX.md](THOR_MAX.md)**.

the one official source of this port, anywhere else is NOT done by me
# SMO Android Port

A native Android port of *Super Mario Odyssey* (version 1.0.0), built on the static recompilation from
[smo-recomp](https://github.com/Coz-0/smo-recomp).

This is **not an emulator**. There is no CPU interpreter, no JIT and no compatibility layer: the game's ARM64 code is
translated to C ahead of time and compiled for Android with the NDK. The console's system libraries, NVN graphics
(on Vulkan), shaders, audio, input and file system are re-implemented by this project's runtime.

> **This repository contains no game code, no game assets, no keys and no firmware.**
> You need your own copy of the game and the keys dumped from your own console.

> **Made with AI.** Most of this port's code was written by Claude, Anthropic's AI assistant (through Claude Code),
> directed, reviewed and tested on a real phone by the project's creator. Expect rough edges, and please report
> problems with logs (see below).

## Status: beta

The game boots, plays and saves. It has been played on one phone so far, a Galaxy S24
Ultra (Snapdragon 8 Gen 3). Other phones, including Mali (Exynos, MediaTek, Tensor) and lower-end chips, are untested.

**Performance is not where we want it yet, and we are working on it.** On the S24 Ultra:

- The **30 fps mode** (recommended) runs the game at full speed and holds 30 fps most of the time, with 1% lows of
  about 22–27 fps, on both the phone's own driver and Turnip. (you can use a custom driver if you would like for a lil more frames but it is NOT required.
- The **60 fps mode** runs at about 30–45 fps on my phone, so the game plays slower than normal there.
- The limit is the CPU (the game's main thread and the threads it waits on) and how Android clocks the CPU for this
  kind of workload, not the GPU. The work in progress is described in [PROGRESS.md](PROGRESS.md).
- The first start builds the graphics for your phone (a loading screen shows the progress; about 2-3 minutes once).
  After that the title screen comes in about 20 seconds. The first visit to each area can still hitch once.

The goal is to run well on Snapdragon and Mali with the phone's own driver. Custom drivers are optional.

## Features

**Game**
- Import your own game in the app: your `prod.keys`, then your NSP or XCI of 1.0.0 (base game, no update). The
  keys stay in the app's private storage until you remove them.
- 30 fps mode (full game speed) and 60 fps mode.
- Save export and import as a .zip (the current save is kept as a backup).
- RomFS mods, turned on and off in the app.

**Graphics**
- Vulkan 1.3 renderer.
- Docked (1080p) or handheld (720p) resolution, scale presets, or a custom resolution scale.
- FXAA, sharpening, anisotropic filtering, FPS counter, FPS limit.
- The phone's own Vulkan driver by default; custom AdrenoTools driver packages (such as Mesa Turnip) on Snapdragon.

**Controls**
- On-screen touch controls with Switch-style button icons and a layout editor: move and resize every button and stick.
- Controllers that Android sees as gamepads, with button rebinding in the app.
- Leave the game from the house button in the touch controls or the controller's Home button (rebindable): it asks
  first, waits for any save in progress, and returns to the app's menu.
- The phone's motion sensors for motion controls.

**Problem reports**
- **Advanced → Export logs** makes a .zip with the game's logs, a crash log, your settings and your phone model. The
  log has a speed line every 10 seconds (fps, 1% low, CPU clocks, thermal state), so it shows how the game runs on
  your phone. It contains no save, keys or game files.

## Requirements

- Android 11 or newer, 64-bit ARM
- Vulkan 1.3
- About 8 GB of free space for the game files
- Your own *Super Mario Odyssey* 1.0.0 dump and `prod.keys` from your own console

## Using the app

1. Install the APK and open it.
2. **Game** tab: **Import prod.keys…**, then **Import from NSP / XCI…**.
3. Press **Play**.

Settings are on the **Graphics**, **Controls**, **Advanced** and **Mods** tabs.

## Building from source

See [BUILDING.md](BUILDING.md). In short:

1. Extract your dump with `scripts/setup.py` (your own keys and game).
2. Lift the game's code to C with `tools/lifter`, using `SMO_LAYOUT=android`.
3. Compile and package it with `tools/android/build_game.py`, `build_runtime.py` and `build_apk.py` (`--release` gives
   a signed release APK).

The lifted code is made from your own copy of the game, so an APK built this way contains code derived from the game.

## Reporting problems

Open an issue with your phone model, what happened, and the .zip from **Advanced → Export logs**. Reports from phones
other than the S24 Ultra, especially Mali ones, help the most.

## Legal

This project is not affiliated with, endorsed or sponsored by Nintendo. *Super Mario Odyssey* and *Nintendo Switch*
are trademarks of Nintendo and are named only to say what this software works with. This repository contains only
source code and documentation under GPL-3.0-or-later (see [LICENSE](LICENSE)). It contains no game code, binaries,
assets, keys or firmware, and it does not help anyone obtain them. You must own the game and dump it yourself.

## Credits

- **holdup.lethimcook** (Discord),quandaile (reddit): creator of the Android port. Direction, design, testing and play-testing.
- **Claude** (Anthropic's AI assistant, used through Claude Code): co-developer. Wrote much of the Android port's code
  (the Android host, the Vulkan renderer's work for phones, the launcher, the 30 fps mode, the graphics options) and
  the measurements in PROGRESS.md.
- [smo-recomp](https://github.com/Coz-0/smo-recomp) by Coz-0: the static recompilation of Super Mario Odyssey (the
  lifter, the runtime, the NVN-to-Vulkan renderer and the shader translator) that this port is built on.
- [ssbu-recomp](https://github.com/Denkishi/ssbu-recomp) by Denkishi: the design and runtime smo-recomp builds on.
- [SuperMarioWonderRecomp](https://github.com/hesanaltdoesgithub/SuperMarioWonderRecomp): the reference for the
  Android host (NativeActivity, a fixed guest mapping, an APK built without Gradle).
- [OdysseyDecomp](https://github.com/MonsterDruide1/OdysseyDecomp) by MonsterDruide1 and contributors: the decompilation
  project, used as a reference only. None of its code is included.
- [libadrenotools](https://github.com/bylaws/libadrenotools) by bylaws (BSD-2-Clause): loads custom Vulkan drivers.
- [Mesa](https://mesa3d.org/)'s Turnip driver and K11MCH1's
  [AdrenoToolsDrivers](https://github.com/K11MCH1/AdrenoToolsDrivers) builds: the custom driver tested.
- The Eden, yuzu/suyu and Ryujinx emulators: their sources and documentation were consulted for console behaviour,
  Maxwell shader instructions and how emulators handle drivers, pipelines and resolution. Where used, they are cited in
  the code; their code is not copied.
- [shaderc / glslang](https://github.com/google/shaderc) (Google, Khronos): GLSL to SPIR-V on the phone.
- [stb_truetype](https://github.com/nothings/stb) by Sean Barrett: font rendering.
- [Unicorn](https://www.unicorn-engine.org/) and [Capstone](https://www.capstone-engine.org/): reference CPU emulation
  and disassembly for testing the lifter.
- [SDL3](https://github.com/libsdl-org/SDL): controllers in the Windows build.
- FXAA after Timothy Lottes (NVIDIA). The sharpening follows the idea of AMD FidelityFX Contrast Adaptive Sharpening.
- The Android NDK and SDK, and the Vulkan SDK.

The Windows project's own README is kept in [docs/PC_README.md](docs/PC_README.md).
