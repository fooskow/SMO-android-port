"""The compiler the app carries to build the game ON the device: Termux's clang, lld and Python, unpacked from Termux's
own packages, plus the NDK's sysroot (so the code is built against the same Android API as a PC build).

    python tools/ondevice/fetch_toolchain.py --arch aarch64|x86_64 --ndk <ndk> --out <dir> [--tar <out.tar.gz>]

<out> is laid out as a prefix: bin/ (clang, ld.lld, python3), lib/ (their libraries, lib/clang/<v> the compiler's own
headers and runtime), lib/python3.x/ (the standard library), sysroot/ (the NDK's: usr/include, usr/lib/<triple>/<api>).
Termux's binaries look for their libraries in /data/data/com.termux/files/usr/lib; the app runs them with
LD_LIBRARY_PATH=<prefix>/lib and PYTHONHOME=<prefix>, which win over that.
Termux packages: https://github.com/termux/termux-packages (each package under its own licence; the toolchain is LLVM,
Apache-2.0 with LLVM exceptions, and Python, PSF).
"""
import argparse
import io
import os
import re
import shutil
import sys
import tarfile
import urllib.request

REPO_URL = 'https://packages-cf.termux.dev/apt/termux-main'
WANT = ['clang', 'lld', 'python']
SKIP = {'ndk-sysroot', 'binutils-is-llvm', 'make', 'termux-tools', 'termux-exec', 'termux-keyring', 'dash', 'bash',
        'coreutils', 'dpkg', 'apt', 'gpgv', 'grep', 'sed', 'tar', 'gzip', 'less', 'procps', 'psmisc', 'findutils',
        'util-linux', 'diffutils', 'patch', 'unzip', 'xz-utils', 'bzip2', 'ed', 'debianutils', 'termux-licenses',
        'termux-am', 'termux-am-socket', 'inetutils', 'net-tools', 'ca-certificates', 'openssl', 'libcurl', 'curl',
        'resolv-conf', 'libgnutls', 'sqlite', 'gdbm', 'tcl', 'tk', 'libx11'}
PREFIX = 'data/data/com.termux/files/usr/'
DROP = [r'^share/(man|doc|info|locale|LICENSES)/', r'^lib/python3\.\d+/(test|idlelib|tkinter|turtledemo|ensurepip|lib2to3|pydoc_data)/',
        r'/__pycache__/', r'^include/(?!python)', r'^lib/.*\.a$', r'^bin/(clang-check|clang-tidy|clangd|clang-format|lldb|scan-|c-index|diagtool|'
        r'clang-(apply|change|doc|extdef|include|linker|move|nvlink|offload|query|refactor|rename|reorder|repl|scan|tblgen))',
        r'^lib/libclang\.so', r'^lib/liblldb', r'^share/(clang|scan-)', r'^opt/']


def get(url):
    print('GET', url, flush=True)
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def packages(arch):
    text = get('%s/dists/stable/main/binary-%s/Packages' % (REPO_URL, arch)).decode()
    db = {}
    for block in text.split('\n\n'):
        f = dict(re.findall(r'^([\w-]+): (.*)$', block, re.M))
        if 'Package' in f:
            db[f['Package']] = f
    return db


def resolve(db, want):
    out, todo = [], list(want)
    while todo:
        p = todo.pop()
        if p in out or p in SKIP:
            continue
        if p not in db:
            print('  (not in the index: %s)' % p)
            continue
        out.append(p)
        for d in (db[p].get('Depends', '') + ',' + db[p].get('Pre-Depends', '')).split(','):
            d = d.split('|')[0].strip()
            d = re.sub(r'\s*\(.*\)', '', d).strip()
            if d:
                todo.append(d)
    return out


def deb_data(blob):
    """The data.tar.* member of a .deb (an ar archive)."""
    assert blob[:8] == b'!<arch>\n'
    i = 8
    while i < len(blob):
        name = blob[i:i + 16].decode().strip().rstrip('/')
        size = int(blob[i + 48:i + 58].decode().strip())
        data = blob[i + 60:i + 60 + size]
        if name.startswith('data.tar'):
            return data
        i += 60 + size + (size & 1)
    raise ValueError('no data.tar in the .deb')


def unpack(blob, out):
    with tarfile.open(fileobj=io.BytesIO(deb_data(blob))) as t:
        for m in t.getmembers():
            n = m.name.lstrip('./')
            if not n.startswith(PREFIX):
                continue
            rel = n[len(PREFIX):]
            if not rel or any(re.search(p, rel) for p in DROP):
                continue
            dst = os.path.join(out, rel)
            if m.isdir():
                os.makedirs(dst, exist_ok=True)
            elif m.issym():
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.lexists(dst):
                    os.remove(dst)
                target = m.linkname
                if target.startswith('/' + PREFIX):              # absolute Termux paths -> relative
                    target = os.path.relpath(os.path.join(out, target[len(PREFIX) + 1:]), os.path.dirname(dst))
                os.symlink(target, dst)
            elif m.isfile():
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with t.extractfile(m) as src, open(dst, 'wb') as o:
                    shutil.copyfileobj(src, o)
                os.chmod(dst, m.mode | (0o755 if rel.startswith('bin/') else 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arch', default='aarch64')
    ap.add_argument('--ndk', required=True)
    ap.add_argument('--api', default='30')
    ap.add_argument('--out', required=True)
    ap.add_argument('--tar')
    a = ap.parse_args()
    shutil.rmtree(a.out, ignore_errors=True)
    os.makedirs(a.out)
    db = packages(a.arch)
    pkgs = resolve(db, WANT)
    print('packages:', ' '.join(sorted(pkgs)))
    for p in pkgs:
        unpack(get('%s/%s' % (REPO_URL, db[p]['Filename'])), a.out)
    # The NDK's sysroot: headers and this API's libraries (and the shared ones above it) of this ABI only.
    triple = {'aarch64': 'aarch64-linux-android', 'x86_64': 'x86_64-linux-android'}[a.arch]
    sr = os.path.join(a.ndk, 'toolchains', 'llvm', 'prebuilt', 'linux-x86_64', 'sysroot')
    dst = os.path.join(a.out, 'sysroot')
    shutil.copytree(os.path.join(sr, 'usr', 'include'), os.path.join(dst, 'usr', 'include'), symlinks=True)
    libsrc = os.path.join(sr, 'usr', 'lib', triple)
    libdst = os.path.join(dst, 'usr', 'lib', triple)
    os.makedirs(libdst)
    for n in os.listdir(libsrc):
        s = os.path.join(libsrc, n)
        if os.path.isfile(s):
            shutil.copy2(s, libdst)
    shutil.copytree(os.path.join(libsrc, a.api), os.path.join(libdst, a.api))
    # The NDK clang's own runtime pieces the Android target links (builtins, unwinder), beside Termux's.
    rt = os.path.join(a.ndk, 'toolchains', 'llvm', 'prebuilt', 'linux-x86_64', 'lib', 'clang')
    ndk_clang = os.path.join(rt, sorted(os.listdir(rt))[-1], 'lib', 'linux')
    ndk_rt_dst = os.path.join(a.out, 'ndk-rt')
    os.makedirs(ndk_rt_dst)
    for n in os.listdir(ndk_clang):
        if a.arch in n and n.endswith('.a') and ('builtins' in n or 'unwind' in n):
            shutil.copy2(os.path.join(ndk_clang, n), ndk_rt_dst)
    arch_dir = os.path.join(ndk_clang, a.arch)
    if os.path.isdir(arch_dir):
        for n in os.listdir(arch_dir):
            shutil.copy2(os.path.join(arch_dir, n), ndk_rt_dst)
    size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(a.out) for n in ns if not os.path.islink(os.path.join(d, n)))
    print('toolchain: %.0f MB in %s' % (size / 2 ** 20, a.out))
    if a.tar:
        with tarfile.open(a.tar, 'w:gz', compresslevel=6) as t:
            t.add(a.out, arcname='.')
        print('tar: %.0f MB %s' % (os.path.getsize(a.tar) / 2 ** 20, a.tar))


if __name__ == '__main__':
    sys.exit(main())
