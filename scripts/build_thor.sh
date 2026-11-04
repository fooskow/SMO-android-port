#!/usr/bin/env bash
# build_thor.sh - from YOUR dump and YOUR prod.keys to the Thor Max APK, in one command (Windows + Git Bash, or Linux).
#
#   bash scripts/build_thor.sh --dump "C:/path/to/dump-folder" --keys "C:/path/to/prod.keys" [--jobs 8] [--install]
#
# --dump  the folder that holds the NSP of Super Mario Odyssey 1.0.0 (the base game: [0100000000010000] in the name)
# --keys  your prod.keys
# --jobs  compile processes (default: the number of CPUs)
# --install  adb install the APK on the device attached (USB debugging on)
#
# Every step is resumable: run it again after an error and the finished steps are skipped.
# Needs (see THOR_MAX.md): Python 3.11+, JDK 17, the Android SDK with build-tools 35.0.0, platform android-35,
# cmake 3.31.6 and NDK 28.2.13676358 (ANDROID_HOME pointing at the SDK), git. The APK holds code made from your
# own copy of the game: it is for your own device, do not share it.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
DUMP=""; KEYS=""; JOBS=""; INSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dump) DUMP="$2"; shift 2 ;;
    --keys) KEYS="$2"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --install) INSTALL=1; shift ;;
    -h|--help) sed -n 2,14p "$0"; exit 0 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done
[ -n "$DUMP" ] && [ -n "$KEYS" ] || { echo "usage: bash scripts/build_thor.sh --dump <folder> --keys <prod.keys>"; exit 2; }
[ -d "$DUMP" ] || { echo "dump folder not found: $DUMP"; exit 1; }
[ -f "$KEYS" ] || { echo "prod.keys not found: $KEYS"; exit 1; }
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 8)}"

step() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERRORE: %s\033[0m\n' "$*"; exit 1; }

# ---- tools
step "Controllo degli strumenti"
[ -n "${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}" ] || [ -d "$REPO/../toolchain/sdk" ] || die "ANDROID_HOME non impostato (la cartella dell'Android SDK)"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$REPO/../toolchain/sdk}}"
case "$SDK" in *" "*) die "il percorso dell'SDK contiene spazi ($SDK): spostalo (es. C:/smo/toolchain/sdk)";; esac
case "$REPO" in *" "*) die "il percorso del repository contiene spazi ($REPO): clonalo in una cartella senza spazi (es. C:/smo)";; esac
NDK="${ANDROID_NDK:-$(ls -d "$SDK"/ndk/* 2>/dev/null | sort | tail -1)}"
[ -d "$NDK" ] || die "NDK non trovato in $SDK/ndk (installa ndk;28.2.13676358 con sdkmanager)"
export ANDROID_HOME="$SDK" ANDROID_NDK="$NDK"
CMAKE_DIR="$(ls -d "$SDK"/cmake/* 2>/dev/null | sort | tail -1)/bin"
[ -x "$CMAKE_DIR/cmake" ] || [ -x "$CMAKE_DIR/cmake.exe" ] || die "cmake non trovato in $SDK/cmake (installa cmake;3.31.6 con sdkmanager)"
[ -d "$SDK/build-tools/35.0.0" ] || die "build-tools 35.0.0 mancanti (sdkmanager \"build-tools;35.0.0\")"
[ -d "$SDK/platforms/android-35" ] || die "platform android-35 mancante (sdkmanager \"platforms;android-35\")"
command -v git >/dev/null || die "git non trovato"
echo "SDK $SDK"; echo "NDK $NDK"; echo "cmake $CMAKE_DIR"

# ---- Python venv
if [ -x .venv/Scripts/python.exe ] || [ -x .venv/Scripts/python ]; then PY=.venv/Scripts/python
elif [ -x .venv/bin/python ]; then PY=.venv/bin/python
else
  step "Ambiente Python (.venv)"
  SYS_PY="$(command -v python3 || command -v python || command -v py)" || die "Python 3 non trovato"
  "$SYS_PY" -m venv .venv
  if [ -x .venv/Scripts/python.exe ] || [ -x .venv/Scripts/python ]; then PY=.venv/Scripts/python; else PY=.venv/bin/python; fi
fi
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet pycryptodome lz4 zstandard capstone unicorn numpy Pillow PyYAML

# ---- 1. dump -> files, then the game's code -> C
step "1/6 Estrazione dal tuo dump (ExeFS, RomFS ~5 GB, manuale)"
"$PY" scripts/setup.py --dump "$DUMP" --keys "$KEYS" --only extract
"$PY" scripts/setup.py --dump "$DUMP" --keys "$KEYS" --only romfs
"$PY" scripts/setup.py --dump "$DUMP" --keys "$KEYS" --only manual || echo "(manuale saltato: facoltativo)"
"$PY" scripts/setup.py --only functions

step "2/6 Ricompilazione del codice del gioco in C (la parte lunga, circa un'ora)"
export SMO_LAYOUT=android
if [ -f build/android/lift/.thor_done ]; then echo "gia' fatto (cancella build/android/lift per rifarlo)"
else
  "$PY" tools/lifter/recomp.py full
  "$PY" tools/lifter/gen_tables.py
  "$PY" tools/lifter/gen_sdktest.py
  "$PY" tools/lifter/sdklift.py gen
  touch build/android/lift/.thor_done
fi

# ---- 2. libadrenotools: without it the APK can only use the stock Adreno driver (no Turnip: the biggest gain on Adreno)
step "3/6 libadrenotools (driver Turnip)"
AT="$REPO/../external/libadrenotools"
if [ ! -f "$AT/build-android/libadrenotools.a" ]; then
  [ -d "$AT/.git" ] || git clone --recursive https://github.com/bylaws/libadrenotools "$AT"
  "$CMAKE_DIR/cmake" -S "$AT" -B "$AT/build-android" -G Ninja -DCMAKE_MAKE_PROGRAM="$CMAKE_DIR/ninja" \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-30 \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF
  "$CMAKE_DIR/cmake" --build "$AT/build-android"
else echo "gia' compilata"; fi

# ---- 3. C -> libsmo.so -> APK
step "4/6 shaderc (una volta sola)"
"$PY" tools/android/build_shaderc.py

step "5/6 Compilazione per arm64 (circa 40 minuti, $JOBS processi)"
"$PY" tools/android/build_game.py "$JOBS" --abi arm64-v8a
"$PY" tools/android/build_runtime.py --abi arm64-v8a

step "6/6 APK firmato"
"$PY" tools/android/build_apk.py --abi arm64-v8a --release
APK="$(ls -t build/android/odyssey-*.apk | head -1)"
[ -f "$APK" ] || die "APK non creato"
echo
echo "APK pronto: $REPO/$APK"
echo "Chiave di firma: build/android/release.keystore (+ release.keystore.txt). TIENILE: gli aggiornamenti devono avere la stessa chiave."
if [ "$INSTALL" = 1 ]; then
  step "Installazione con adb"
  "$SDK/platform-tools/adb" install -r "$APK"
fi
