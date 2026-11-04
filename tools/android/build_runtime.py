"""Compile the host runtime for Android and link the game library: build/android/<abi>/lib/libsmo.so.

    python tools/android/build_runtime.py [--abi arm64-v8a|x86_64] [--force] [-j N]

libsmo.so = the runtime (runtime/*.c without the Windows-only files, runtime/android/*.c, the NDK's
android_native_app_glue), the generated tables (build/android/gen: sdkdata.c, sdklift_gen.c), the lifted game
(build/android/<abi>/obj/main, tools/android/build_game.py) and shaderc (tools/android/build_shaderc.py). One library:
the exe / game-DLL split of the Windows build only shortens its link. Needs SMO_LAYOUT=android tables (the script sets
it). Environment: ANDROID_NDK / ANDROID_HOME (tools/android/android_env.py), SHADERC_LIBS (default ~/smo-shaderc).
"""
import concurrent.futures
import glob
import os
import subprocess
import sys
import time

os.environ['SMO_LAYOUT'] = 'android'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import android_env as A  # noqa: E402

T = A.T
RT = os.path.join(A.REPO, 'runtime')
GEN = T.build('gen')
LIFT = T.build('lift', 'main')
WINDOWS_ONLY = {'smo_guide.c', 'nnmovie_mf.c', 'nnpad_sdl.c', 'vk_glslang_shim.c', 'vk_shaderc_shim.c', 'gamedll.c', 'game_shim.c',
                'nvn_vk_draw.c', 'nvn_vk_store.c', 'nvn_vk_m4.c', 'nvn_vk_wd.c'}      # the last four are #included by nvn_vk.c
GEN_SOURCES = ['sdkdata.c', 'sdklift_gen.c']
# libadrenotools (a custom Vulkan driver such as Mesa Turnip, runtime/android/android_driver.c): its source in
# ../external/libadrenotools and its arm64 build in build-android there (BUILDING.md); ADRENOTOOLS overrides the folder.
AT_DIR = os.environ.get('ADRENOTOOLS') or os.path.join(os.path.dirname(A.REPO), 'external', 'libadrenotools')
AT_LIBS = [os.path.join(AT_DIR, 'build-android', 'libadrenotools.a'), os.path.join(AT_DIR, 'build-android', 'lib', 'linkernsbypass', 'liblinkernsbypass.a')]


def have_adrenotools(abi):
    return abi == 'arm64-v8a' and all(os.path.exists(p) for p in AT_LIBS)


SHADERC_ORDER = ['libshaderc.a', 'libshaderc_util.a', 'libglslang.a', 'libOSDependent.a', 'libOGLCompiler.a', 'libHLSL.a',
                 'libSPIRV.a', 'libSPIRV-Tools-opt.a', 'libSPIRV-Tools.a']


def sources():
    src = [os.path.join(RT, n) for n in sorted(os.listdir(RT)) if n.endswith('.c') and n not in WINDOWS_ONLY]
    src += sorted(glob.glob(os.path.join(RT, 'android', '*.c')))
    src.append(os.path.join(A.ndk(), 'sources', 'android', 'native_app_glue', 'android_native_app_glue.c'))
    src += [os.path.join(GEN, n) for n in GEN_SOURCES]
    return src


def flags(abi):
    ndk = A.ndk()
    return A.target_flags(abi) + ['-O2', '-g0', '-fPIC', '-w', '-fno-strict-aliasing', '-D_GNU_SOURCE', '-ffunction-sections',
                                  '-I', RT, '-I', os.path.join(RT, 'android'), '-I', GEN, '-I', LIFT,
                                  '-I', os.path.join(RT, 'third_party', 'khronos'),
                                  '-I', os.path.join(ndk, 'sources', 'third_party', 'shaderc', 'libshaderc', 'include'),
                                  '-I', os.path.join(ndk, 'sources', 'android', 'native_app_glue')] + \
        (['-DSMO_ADRENOTOOLS', '-I', os.path.join(AT_DIR, 'include')] if have_adrenotools(abi) else [])


def compile_one(job):
    cmd, src, obj = job
    r = subprocess.run(cmd + ['-c', src, '-o', obj], capture_output=True, text=True)
    return src, r.returncode, (r.stdout + r.stderr)


def main():
    abi = A.abi_from_args(sys.argv)
    force = '--force' in sys.argv
    jobs = int(sys.argv[sys.argv.index('-j') + 1]) if '-j' in sys.argv else max(1, (os.cpu_count() or 8) - 2)
    if not os.path.exists(os.path.join(GEN, 'image.h')):
        raise SystemExit('no %s: run the lift, tables and sdk steps with SMO_LAYOUT=android first (BUILDING.md)' % os.path.join(GEN, 'image.h'))
    obj_dir = A.build_dir(abi, 'obj', 'host')
    game_dir = A.build_dir(abi, 'obj', 'main')
    lib_dir = A.build_dir(abi, 'lib')
    os.makedirs(obj_dir, exist_ok=True)
    os.makedirs(lib_dir, exist_ok=True)
    clang = A.clang()
    deps = glob.glob(os.path.join(RT, '*.h')) + glob.glob(os.path.join(RT, '*.inc')) + glob.glob(os.path.join(RT, 'android', '*.h')) + \
        glob.glob(os.path.join(GEN, '*.h')) + [os.path.join(RT, n) for n in ('nvn_vk_draw.c', 'nvn_vk_store.c', 'nvn_vk_m4.c', 'nvn_vk_wd.c')]
    newest = max(os.path.getmtime(d) for d in deps)
    todo, objs = [], []
    for src in sources():
        obj = os.path.join(obj_dir, os.path.basename(src)[:-2] + '.o')
        objs.append(obj)
        if force or not os.path.exists(obj) or os.path.getmtime(obj) < max(os.path.getmtime(src), newest):
            todo.append(([clang] + flags(abi), src, obj))
    t0 = time.time()
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        for src, code, out in pool.map(compile_one, todo):
            if code:
                failed += 1
                print('FAILED %s\n%s' % (os.path.basename(src), out[-5000:]))
    print('runtime: %d of %d files compiled, %d failed (%.0fs)' % (len(todo), len(objs), failed, time.time() - t0))
    if failed:
        return 1
    game = sorted(glob.glob(os.path.join(game_dir, '*.obj')))
    if len(game) < 200:
        raise SystemExit('only %d lifted objects in %s: run tools/android/build_game.py --abi %s first' % (len(game), game_dir, abi))
    sc = os.environ.get('SHADERC_LIBS') or os.path.join(os.path.expanduser('~'), 'smo-shaderc', 'obj', 'local', abi)
    # the NDK's shaderc build makes some of the component libraries only on some hosts / NDK versions: the ones there
    sclibs = [os.path.join(sc, n) for n in SHADERC_ORDER if os.path.exists(os.path.join(sc, n))]
    missing = [p for p in [os.path.join(sc, n) for n in ('libshaderc.a', 'libglslang.a', 'libSPIRV-Tools.a')] if not os.path.exists(p)]
    if missing:
        raise SystemExit('shaderc libraries missing (%s): run tools/android/build_shaderc.py' % ', '.join(os.path.basename(m) for m in missing))
    rsp = os.path.join(lib_dir, 'link.rsp')
    with open(rsp, 'w') as f:
        f.write('\n'.join('"%s"' % p.replace('\\', '/') for p in objs + game))
    out = os.path.join(lib_dir, 'libsmo.so')
    if have_adrenotools(abi):
        sclibs = sclibs + AT_LIBS
    print('libadrenotools: %s' % ('linked (a custom Vulkan driver can be used)' if have_adrenotools(abi) else 'not built: the system Vulkan driver only'))
    cmd = [A.llvm_bin('clang++')] + A.target_flags(abi) + ['-shared', '-o', out, '@' + rsp] + sclibs + \
        ['-static-libstdc++', '-landroid', '-lnativewindow', '-llog', '-laaudio', '-lmediandk', '-lm', '-ldl',
         '-Wl,-z,max-page-size=16384', '-Wl,-Bsymbolic', '-Wl,--wrap=f_400072e61c', '-Wl,--wrap=f_4000731fdc', '-Wl,--wrap=f_4000a58394', '-Wl,--gc-sections', '-Wl,--no-undefined', '-Wl,-soname,libsmo.so',
         '-u', 'ANativeActivity_onCreate', '-Wl,--Map=' + out + '.map']
    t1 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print((r.stdout + r.stderr)[-12000:])
        return 1
    print('linked %s: %.0f MB in %.0fs' % (out, os.path.getsize(out) / 2 ** 20, time.time() - t1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
