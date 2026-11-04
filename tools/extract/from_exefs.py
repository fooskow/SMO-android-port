"""The extract step from an already extracted ExeFS instead of the NSP and the keys (fork for the AYN Thor Max: the
cloud build gets the game's code only, never the package or the console's keys).

    python tools/extract/from_exefs.py <exefs folder or .zip> [--out build/dump]

<exefs> holds what hactool / any ExeFS extractor writes for the PROGRAM NCA of Super Mario Odyssey 1.0.0 (base game):
main, main.npdm, rtld, sdk, subsdk* (anywhere inside the folder or the zip). Writes what tools/extract/extract.py
writes for the base package, minus control.nacp (not needed to build): <out>/base/exefs/*, <out>/base/elf/*.elf and
<out>/version.json with the fields the later steps read (modules[].build_id, the program's SDK version).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import switchfs as S  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAMES = re.compile(r'^(main|main\.npdm|rtld|sdk|subsdk\d+)$')
SMO_TITLE = 0x0100000000010000


def find_exefs(root):
    """The folder under root that holds `main` and `main.npdm` (the shallowest one)."""
    best = None
    for d, _, files in os.walk(root):
        if 'main' in files and 'main.npdm' in files:
            if best is None or d.count(os.sep) < best.count(os.sep):
                best = d
    if not best:
        raise SystemExit('no ExeFS found (a folder with `main` and `main.npdm`) in %s' % root)
    return best


def npdm_title(d):
    """The program id of main.npdm: the ACI0 block's title id."""
    off = d.find(b'ACI0')
    return int.from_bytes(d[off + 0x10:off + 0x18], 'little') if off >= 0 else None


def sdk_version(elf):
    """NintendoSDK version from the sdk module's own version string ("NintendoSdk_nnSdk-3_5_1-Release")."""
    m = re.search(rb'NintendoSdk_nnSdk-(\d+)_(\d+)_(\d+)', elf)
    return '%s.%s.%s.0' % tuple(x.decode() for x in m.groups()) if m else '3.5.1.0'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('--out', default=os.path.join(REPO, 'build', 'dump'))
    a = ap.parse_args()
    tmp = None
    src = a.src
    if os.path.isfile(src) and zipfile.is_zipfile(src):
        tmp = tempfile.mkdtemp(prefix='exefs_')
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():                     # file names only: nothing written outside tmp
                base = os.path.basename(n.rstrip('/'))
                if base and not n.endswith('/') and NAMES.match(base):
                    sub = os.path.join(tmp, *[p for p in os.path.dirname(n).split('/') if p not in ('', '.', '..')])
                    os.makedirs(sub, exist_ok=True)
                    with z.open(n) as f, open(os.path.join(sub, base), 'wb') as o:
                        shutil.copyfileobj(f, o)
        src = tmp
    src = find_exefs(src)
    dst = os.path.join(a.out, 'base')
    for sub in ('exefs', 'elf'):
        shutil.rmtree(os.path.join(dst, sub), ignore_errors=True)
        os.makedirs(os.path.join(dst, sub))
    npdm = open(os.path.join(src, 'main.npdm'), 'rb').read()
    tid = npdm_title(npdm)
    print('main.npdm program id: %s' % ('%016x' % tid if tid is not None else 'unknown'))
    if tid is not None and tid != SMO_TITLE:
        raise SystemExit('this ExeFS is not Super Mario Odyssey (program id %016x, expected %016x)' % (tid, SMO_TITLE))
    modules, sdk_elf = {}, b''
    for name in sorted(os.listdir(src)):
        if not NAMES.match(name):
            continue
        d = open(os.path.join(src, name), 'rb').read()
        open(os.path.join(dst, 'exefs', name), 'wb').write(d)
        m = {'size': len(d), 'sha256': hashlib.sha256(d).hexdigest()}
        if d[:4] == b'NSO0':
            elf, meta = S.nso_to_elf(d)
            open(os.path.join(dst, 'elf', name + '.elf'), 'wb').write(elf)
            m.update({'build_id': meta['build_id'], 'segments_sha_ok': meta['segments_sha_ok'], 'nsym': meta['nsym'],
                      'elf_sha256': hashlib.sha256(elf).hexdigest()})
            if name == 'sdk':
                sdk_elf = elf
            if not meta['segments_sha_ok']:
                raise SystemExit('%s: segment hashes do not match: the file is damaged' % name)
        modules[name] = m
        print('  %-10s %10d bytes  %s' % (name, len(d), m.get('build_id', '')[:40]))
    for need in ('main', 'sdk', 'main.npdm'):
        if need not in modules:
            raise SystemExit('the ExeFS has no %s' % need)
    sdk = sdk_version(sdk_elf)
    info = {'base': {'package': 'exefs (from_exefs.py)', 'meta': {'title_id': '%016x' % SMO_TITLE, 'version': 0},
                     'ncas': [{'name': 'program', 'type': 'Program', 'title_id': '%016x' % SMO_TITLE, 'sdk_version': sdk}],
                     'nacp': {'display_version': '1.0.0', 'name': 'Super Mario Odyssey'},
                     'program_sdk_version': sdk, 'modules': modules}}
    with open(os.path.join(a.out, 'version.json'), 'w') as f:
        json.dump(info, f, indent=1)
    print('SDK %s; wrote %s' % (sdk, os.path.join(a.out, 'version.json')))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
