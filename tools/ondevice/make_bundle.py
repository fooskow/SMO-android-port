"""The on-device build's bundle (assets/builder.tar.gz of the APK): the build scripts and the runtime's sources from this
repository, plus what is prebuilt for arm64 because it does not depend on the game. Fork for the AYN Thor Max.

    python tools/ondevice/make_bundle.py --shaderc <obj/local/arm64-v8a> --adrenotools <libadrenotools> --out <builder.tar.gz>

Layout (unpacked by Builder.java into files/builder): tools/, runtime/, prebuilt/sdktest_data.h (gen_sdktest.py, needs
Pillow), prebuilt/shaderc/*.a (build_shaderc.py), prebuilt/adrenotools/{include,build-android/...} (BUILDING.md)."""
import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHADERC = ['libshaderc.a', 'libshaderc_util.a', 'libglslang.a', 'libOSDependent.a', 'libOGLCompiler.a', 'libHLSL.a',
           'libSPIRV.a', 'libSPIRV-Tools-opt.a', 'libSPIRV-Tools.a']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shaderc', required=True)
    ap.add_argument('--adrenotools', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    w = tempfile.mkdtemp(prefix='bundle_')
    ign = shutil.ignore_patterns('__pycache__', '*.pyc', '*.bat', '*.exe')
    shutil.copytree(os.path.join(REPO, 'tools'), os.path.join(w, 'tools'), ignore=ign)
    shutil.copytree(os.path.join(REPO, 'runtime'), os.path.join(w, 'runtime'), ignore=ign)
    pre = os.path.join(w, 'prebuilt')
    os.makedirs(os.path.join(pre, 'shaderc'))
    # The SDK self-test's reference data (game-independent; Pillow is not on the device).
    env = dict(os.environ, SMO_LAYOUT='android')
    subprocess.run([sys.executable, os.path.join(REPO, 'tools', 'lifter', 'gen_sdktest.py')], check=True, env=env)
    sys.path.insert(0, os.path.join(REPO, 'tools'))
    os.environ['SMO_LAYOUT'] = 'android'
    import target as T  # noqa: E402
    shutil.copy2(T.build('gen', 'sdktest_data.h'), os.path.join(pre, 'sdktest_data.h'))
    for n in SHADERC:
        shutil.copy2(os.path.join(a.shaderc, n), os.path.join(pre, 'shaderc', n))
    at = os.path.join(pre, 'adrenotools')
    shutil.copytree(os.path.join(a.adrenotools, 'include'), os.path.join(at, 'include'))
    for rel in ('build-android/libadrenotools.a', 'build-android/lib/linkernsbypass/liblinkernsbypass.a'):
        os.makedirs(os.path.dirname(os.path.join(at, rel)), exist_ok=True)
        shutil.copy2(os.path.join(a.adrenotools, rel), os.path.join(at, rel))
    with tarfile.open(a.out, 'w:gz', compresslevel=6) as t:
        t.add(w, arcname='.')
    print('bundle: %.0f MB %s' % (os.path.getsize(a.out) / 2 ** 20, a.out))
    shutil.rmtree(w)


if __name__ == '__main__':
    main()
