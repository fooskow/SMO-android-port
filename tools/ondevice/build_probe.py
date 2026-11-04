"""Build the toolchain probe APK (android/probe) with a toolchain tarball as its asset.

    python tools/ondevice/build_probe.py --tc <tc.tar.gz> --out <probe.apk>

Needs ANDROID_HOME with build-tools 35.0.0 and platforms;android-35, and JAVA_HOME (javac, keytool)."""
import argparse
import os
import shutil
import subprocess
import tempfile
import zipfile

BT = '35.0.0'


def run(cmd):
    print('+', ' '.join(cmd[:6]), '...' if len(cmd) > 6 else '', flush=True)
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tc', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    sdk = os.environ['ANDROID_HOME']
    bt = os.path.join(sdk, 'build-tools', BT)
    jar = os.path.join(sdk, 'platforms', 'android-35', 'android.jar')
    jbin = os.path.join(os.environ['JAVA_HOME'], 'bin')
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    probe = os.path.join(repo, 'android', 'probe')
    w = tempfile.mkdtemp(prefix='probe_')
    classes, dex, assets = (os.path.join(w, d) for d in ('classes', 'dex', 'assets'))
    for d in (classes, dex, assets):
        os.makedirs(d)
    src = [os.path.join(d, n) for d, _, ns in os.walk(os.path.join(probe, 'java')) for n in ns if n.endswith('.java')]
    run([os.path.join(jbin, 'javac'), '-source', '11', '-target', '11', '-encoding', 'UTF-8', '-nowarn', '-classpath', jar, '-d', classes] + src)
    cls = [os.path.join(d, n) for d, _, ns in os.walk(classes) for n in ns if n.endswith('.class')]
    run([os.path.join(bt, 'd8'), '--release', '--min-api', '30', '--lib', jar, '--output', dex] + cls)
    shutil.copy(a.tc, os.path.join(assets, 'tc.tar.gz'))
    base = os.path.join(w, 'base.apk')
    run([os.path.join(bt, 'aapt2'), 'link', '-o', base, '-I', jar, '--manifest', os.path.join(probe, 'AndroidManifest.xml'),
         '--min-sdk-version', '30', '--target-sdk-version', '28', '-A', assets, '-0', 'gz'])
    with zipfile.ZipFile(base, 'a', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(dex, 'classes.dex'), 'classes.dex')
    aligned = os.path.join(w, 'aligned.apk')
    run([os.path.join(bt, 'zipalign'), '-f', '-P', '16', '4', base, aligned])
    ks = os.path.join(w, 'debug.keystore')
    run([os.path.join(jbin, 'keytool'), '-genkeypair', '-keystore', ks, '-storepass', 'android', '-keypass', 'android',
         '-alias', 'debug', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000', '-dname', 'CN=probe'])
    run([os.path.join(bt, 'apksigner'), 'sign', '--ks', ks, '--ks-pass', 'pass:android', '--out', a.out, aligned])
    print('probe APK: %s (%.0f MB)' % (a.out, os.path.getsize(a.out) / 2 ** 20))


if __name__ == '__main__':
    main()
