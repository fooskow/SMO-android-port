"""Package the Android app: build/android/smo-<abis>.apk.

    python tools/android/build_apk.py [--abi arm64-v8a] [--abi x86_64] [--release] [--install]

aapt2 (manifest android/AndroidManifest.xml, the icon from tools/android/make_icon.py; SMO_ICON=<png>: your own picture on it) -> lib/<abi>/libsmo.so added (stripped) -> zipalign (16 KB pages for the
library) -> apksigner with a debug key made once in build/android/debug.keystore. No game data goes into the APK.
--release: not debuggable, signed with a release key made once in build/android/release.keystore (its password in
release.keystore.txt beside it; keep both: an update must be signed with the same key) -> build/android/odyssey-<version>.apk.
--install: adb install -r on the one device or emulator attached.
"""
import os
import re
import secrets
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import android_env as A  # noqa: E402

BUILD_TOOLS = '35.0.0'
PLATFORM = 'android-35'


def tool(name):
    exe = {'aapt2': 'aapt2.exe', 'zipalign': 'zipalign.exe', 'apksigner': 'apksigner.bat', 'd8': 'd8.bat'}[name] if os.name == 'nt' else name
    return os.path.join(A.sdk(), 'build-tools', BUILD_TOOLS, exe)


def java_env():
    env = dict(os.environ)
    jdk = os.environ.get('JAVA_HOME') or next((os.path.join(os.path.dirname(A.sdk()), d) for d in os.listdir(os.path.dirname(A.sdk())) if d.startswith('jdk')), None)
    if jdk:
        env['JAVA_HOME'] = jdk
        env['PATH'] = os.path.join(jdk, 'bin') + os.pathsep + env.get('PATH', '')
    return env


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        raise SystemExit('%s failed:\n%s' % (os.path.basename(cmd[0]), (r.stdout + r.stderr)[-4000:]))
    return r.stdout


def java_dex(env):
    """android/java/**/*.java -> classes.dex (javac against android.jar, then d8). None when there is no Java."""
    src = [os.path.join(d, n) for d, _, ns in os.walk(os.path.join(A.REPO, 'android', 'java')) for n in ns if n.endswith('.java')]
    if not src:
        return None
    out = A.T.build('android', 'java')
    classes, dexdir = os.path.join(out, 'classes'), os.path.join(out, 'dex')
    for d in (classes, dexdir):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    jar = os.path.join(A.sdk(), 'platforms', PLATFORM, 'android.jar')
    run([os.path.join(env['JAVA_HOME'], 'bin', 'javac'), '-source', '11', '-target', '11', '-encoding', 'UTF-8', '-nowarn',
         '-classpath', jar, '-d', classes] + src, env=env)
    cls = [os.path.join(d, n) for d, _, ns in os.walk(classes) for n in ns if n.endswith('.class')]
    run([tool('d8'), '--release', '--min-api', str(A.API), '--lib', jar, '--output', dexdir] + cls, env=env)
    return os.path.join(dexdir, 'classes.dex')


def main():
    abis = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--abi'] or ['arm64-v8a']
    out_dir = A.T.build('android')
    os.makedirs(out_dir, exist_ok=True)
    env = java_env()
    release = '--release' in sys.argv
    base = os.path.join(out_dir, 'base.apk')
    manifest = os.path.join(A.REPO, 'android', 'AndroidManifest.xml')
    text = open(manifest, encoding='utf-8').read()
    version = re.search(r'android:versionName="([^"]+)"', text).group(1)
    if release:                                      # the same manifest without android:debuggable
        manifest = os.path.join(out_dir, 'AndroidManifest.release.xml')
        open(manifest, 'w', encoding='utf-8').write(re.sub(r'\s*android:debuggable="true"', '', text))
    res = os.path.join(out_dir, 'res')                # the launcher icon (tools/android/make_icon.py), compiled by aapt2
    run([sys.executable, os.path.join(A.REPO, 'tools', 'android', 'make_icon.py'), res])
    flat = os.path.join(out_dir, 'res.zip')
    run([tool('aapt2'), 'compile', '--dir', res, '-o', flat])
    run([tool('aapt2'), 'link', '-o', base, '-I', os.path.join(A.sdk(), 'platforms', PLATFORM, 'android.jar'), '-R', flat,
         '--manifest', manifest, '--min-sdk-version', str(A.API), '--target-sdk-version', '28'] +
        # fork for the AYN Thor Max: SMO_APK_ASSETS=<folder>: the on-device build's toolchain and bundle (stored as they are)
        (['-A', os.environ['SMO_APK_ASSETS'], '-0', 'gz'] if os.environ.get('SMO_APK_ASSETS') else []))
    dex = java_dex(env)                              # the launcher (android/java): javac, then d8
    with zipfile.ZipFile(base, 'a', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        if dex:
            z.write(dex, 'classes.dex')
            print('classes.dex: the launcher (%d KB)' % (os.path.getsize(dex) // 1024))
        for abi in abis:
            lib = A.build_dir(abi, 'lib', 'libsmo.so')
            no_game = os.environ.get('SMO_APK_NO_GAME') == '1'      # fork: the game library is built on the device
            if no_game:
                lib = None
            if lib and not os.path.exists(lib):
                raise SystemExit('%s missing: run tools/android/build_runtime.py --abi %s' % (lib, abi))
            if lib:
                stripped = lib + '.stripped'
                run([A.llvm_bin('llvm-strip'), '--strip-unneeded', '-o', stripped, lib])
                z.write(stripped, 'lib/%s/libsmo.so' % abi)
            hooks = os.path.join(os.environ.get('ADRENOTOOLS') or os.path.join(os.path.dirname(A.REPO), 'external', 'libadrenotools'), 'build-android', 'src', 'hook')
            if abi == 'arm64-v8a' and os.path.isdir(hooks):          # libadrenotools' hooks (a custom Vulkan driver, android_driver.c)
                for n in sorted(os.listdir(hooks)):
                    if n.endswith('.so'):
                        z.write(os.path.join(hooks, n), 'lib/%s/%s' % (abi, n))
                        print('%s: %s (adrenotools hook)' % (abi, n))
            if lib:
                print('%s: libsmo.so %.0f MB (stripped from %.0f MB)' % (abi, os.path.getsize(stripped) / 2 ** 20, os.path.getsize(lib) / 2 ** 20))
            else:
                print('%s: no libsmo.so (built on the device)' % abi)
    if release:                                      # nothing in a release names the builder: no home folder in any file
        user = os.path.basename(os.path.expanduser('~')).lower().encode()
        with zipfile.ZipFile(base) as z:
            bad = [n for n in z.namelist() if not n.startswith('assets/') and any(p + user in z.read(n).lower() for p in (b'users/', b'users' + bytes([92]), b'home/'))]
        if bad:
            raise SystemExit('the home folder of whoever built it is named in %s: rebuild them with android_env.prefix_maps()' % ', '.join(bad))
        print('release: no file names the home folder of whoever built it')
    aligned = os.path.join(out_dir, 'aligned.apk')
    run([tool('zipalign'), '-f', '-P', '16', '4', base, aligned])
    if release:
        ks = os.path.join(out_dir, 'release.keystore')
        if not os.path.exists(ks):
            pw = secrets.token_urlsafe(18)
            run([os.path.join(env['JAVA_HOME'], 'bin', 'keytool'), '-genkeypair', '-keystore', ks, '-storepass', pw, '-keypass', pw,
                 '-alias', 'release', '-keyalg', 'RSA', '-keysize', '4096', '-validity', '10000', '-dname', 'CN=Odyssey Android port'], env=env)
            open(ks + '.txt', 'w').write(pw + '\n')
        pw = open(ks + '.txt').read().strip()
        apk = os.path.join(out_dir, 'odyssey-%s.apk' % version)
    else:
        ks, pw = os.path.join(out_dir, 'debug.keystore'), 'android'
        if not os.path.exists(ks):
            run([os.path.join(env['JAVA_HOME'], 'bin', 'keytool'), '-genkeypair', '-keystore', ks, '-storepass', 'android', '-keypass', 'android',
                 '-alias', 'androiddebugkey', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000', '-dname', 'CN=Android Debug,O=Android,C=US'], env=env)
        apk = os.path.join(out_dir, 'smo-%s.apk' % '-'.join(abis))
    run([tool('apksigner'), 'sign', '--ks', ks, '--ks-pass', 'pass:' + pw, '--key-pass', 'pass:' + pw, '--out', apk, aligned], env=env)
    run([tool('apksigner'), 'verify', apk], env=env)
    print('APK: %s (%.0f MB)' % (apk, os.path.getsize(apk) / 2 ** 20))
    if '--install' in sys.argv:
        print(run([os.path.join(A.sdk(), 'platform-tools', 'adb.exe' if os.name == 'nt' else 'adb'), 'install', '-r', apk]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
