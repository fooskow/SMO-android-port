"""The whole build of the game library ON the device (fork for the AYN Thor Max, milestone 2): from an extracted ExeFS
to libsmo.so, with the toolchain the app carries. The app runs it with the bundle's Python:

    python3 tools/ondevice/build_on_device.py --exefs <folder or .zip> [--jobs N]

Environment (set by the app): SMO_ONDEVICE_TC (the toolchain prefix), SHADERC_LIBS and ADRENOTOOLS (prebuilt in the
bundle). The steps are the PC build's own scripts (BUILDING.md), in the same order; each one is marked done in
build/ondevice_steps.txt, so a build stopped half way (the app closed, the battery) goes on from the step it was in.
Lines for the app: "STEP <k>/<n> <name>", the scripts' own output, and "BUILD OK <path of libsmo.so>" or "BUILD FAILED".
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
ABI = 'arm64-v8a'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exefs', required=True)
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 8) - 2))
    ap.add_argument('--redo', action='store_true', help='forget the steps already done')
    a = ap.parse_args()
    os.chdir(REPO)
    env = dict(os.environ)
    env['SMO_LAYOUT'] = 'android'
    env.setdefault('RECOMP_TIME_LIMIT', '1200')      # a slower CPU than a PC's: more time before a file is built without optimisation
    env['PYTHONUNBUFFERED'] = '1'
    os.environ.update(env)
    sys.path.insert(0, os.path.join(REPO, 'tools'))
    import target as T                               # noqa: E402 (after SMO_LAYOUT)
    gen = T.build('gen')
    t = lambda *p: os.path.join(REPO, 'tools', *p)   # noqa: E731
    steps = [
        ('the game code from the ExeFS', [PY, t('extract', 'from_exefs.py'), a.exefs]),
        ('the list of functions', [PY, t('extract', 'functions.py')]),
        ('ARM64 -> C (the longest Python step)', [PY, t('lifter', 'recomp.py'), 'full', T.build('lift', 'main'), str(a.jobs)]),
        ('tables', [PY, t('lifter', 'gen_tables.py')]),
        ('SDK functions -> C', [PY, t('lifter', 'sdklift.py'), 'gen']),
        ('compiling the game (the longest step)', [PY, t('android', 'build_game.py'), str(a.jobs), '--abi', ABI]),
        ('compiling the runtime and linking', [PY, t('android', 'build_runtime.py'), '--abi', ABI, '-j', str(a.jobs)]),
    ]
    mark = os.path.join(REPO, 'build', 'ondevice_steps.txt')
    os.makedirs(os.path.dirname(mark), exist_ok=True)
    if a.redo and os.path.exists(mark):
        os.remove(mark)
    done = set(open(mark).read().split('\n')) if os.path.exists(mark) else set()
    # The SDK self-test's reference data does not depend on the game; the bundle carries it (it needs Pillow to make).
    pre = os.path.join(REPO, 'prebuilt', 'sdktest_data.h')
    if os.path.exists(pre):
        os.makedirs(gen, exist_ok=True)
        shutil.copy2(pre, os.path.join(gen, 'sdktest_data.h'))
    t_all = time.time()
    for k, (name, cmd) in enumerate(steps, 1):
        key = str(k)
        if key in done:
            print('STEP %d/%d %s: done before' % (k, len(steps), name), flush=True)
            continue
        print('STEP %d/%d %s' % (k, len(steps), name), flush=True)
        t0 = time.time()
        r = subprocess.run(cmd, env=env)
        if r.returncode:
            print('BUILD FAILED at step %d (%s), exit code %d' % (k, name, r.returncode), flush=True)
            return 1
        with open(mark, 'a') as f:
            f.write(key + '\n')
        print('STEP %d/%d done in %.0f s' % (k, len(steps), time.time() - t0), flush=True)
    lib = os.path.join(T.build('android', ABI, 'lib'), 'libsmo.so')
    if not os.path.exists(lib):
        print('BUILD FAILED: no %s' % lib, flush=True)
        return 1
    print('BUILD OK %s (%.0f MB, %.0f min)' % (lib, os.path.getsize(lib) / 2 ** 20, (time.time() - t_all) / 60), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
