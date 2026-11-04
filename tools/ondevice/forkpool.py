"""A process pool without semaphores, for Python inside an Android app (fork for the AYN Thor Max).

multiprocessing.Pool needs named POSIX semaphores, which an app cannot make work there (Termux's emulation needs hard
links in the app's folder; Android forbids them). The lifter (tools/lifter/recomp.py) only uses Pool(n, initializer,
initargs) with imap_unordered / imap / map, so this pool does exactly that with plain os.fork() and pipes: n workers
forked once (each runs the initializer), tasks and results pickled through one pipe pair per worker.

Installed as the toolchain's sitecustomize.py (tools/ondevice/fetch_toolchain.py): on Android, multiprocessing.Pool is
replaced by ForkPool when it is first imported. SMO_FORKPOOL=0 keeps the real one."""
import os
import pickle
import select
import struct
import sys
import traceback


def _send(fd, obj):
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    data = struct.pack('<Q', len(data)) + data
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        view = view[n:]


def _read_exact(fd, n):
    parts = []
    while n:
        b = os.read(fd, min(n, 1 << 20))
        if not b:
            raise EOFError('worker pipe closed')
        parts.append(b)
        n -= len(b)
    return b''.join(parts)


def _recv(fd):
    n, = struct.unpack('<Q', _read_exact(fd, 8))
    return pickle.loads(_read_exact(fd, n))


class ForkPool:
    def __init__(self, processes=None, initializer=None, initargs=(), *args, **kw):
        self._n = max(1, processes or os.cpu_count() or 1)
        self._workers = []                      # (pid, task_w, result_r)
        sys.stdout.flush()
        sys.stderr.flush()
        for _ in range(self._n):
            tr, tw = os.pipe()
            rr, rw = os.pipe()
            pid = os.fork()
            if pid == 0:                        # the worker
                os.close(tw)
                os.close(rr)
                for _, w, r in self._workers:
                    os.close(w)
                    os.close(r)
                code = 0
                try:
                    if initializer:
                        initializer(*initargs)
                    while True:
                        task = _recv(tr)
                        if task is None:
                            break
                        fn, tid, arg = task
                        try:
                            res = (tid, True, fn(arg))
                        except BaseException:      # noqa: BLE001 - reported to the parent
                            res = (tid, False, traceback.format_exc())
                        _send(rw, res)
                except EOFError:
                    pass
                except BaseException:              # noqa: BLE001
                    traceback.print_exc()
                    code = 1
                finally:
                    sys.stdout.flush()
                    sys.stderr.flush()
                    os._exit(code)
            os.close(tr)
            os.close(rw)
            self._workers.append((pid, tw, rr))

    def _run(self, fn, iterable):
        """Yields (task index, result) as results come."""
        tasks = enumerate(iterable)
        idle = list(range(len(self._workers)))
        busy = {}                                 # result fd -> worker index
        done = False
        while True:
            while idle and not done:
                try:
                    tid, arg = next(tasks)
                except StopIteration:
                    done = True
                    break
                w = idle.pop()
                _send(self._workers[w][1], (fn, tid, arg))
                busy[self._workers[w][2]] = w
            if not busy:
                return
            ready, _, _ = select.select(list(busy), [], [])
            for fd in ready:
                tid, ok, val = _recv(fd)
                idle.append(busy.pop(fd))
                if not ok:
                    raise RuntimeError('worker failed:\n' + val)
                yield tid, val

    def imap_unordered(self, fn, iterable, chunksize=1):
        for _, v in self._run(fn, iterable):
            yield v

    def imap(self, fn, iterable, chunksize=1):
        pending, nxt = {}, 0
        for tid, v in self._run(fn, iterable):
            pending[tid] = v
            while nxt in pending:
                yield pending.pop(nxt)
                nxt += 1

    def map(self, fn, iterable, chunksize=None):
        return list(self.imap(fn, iterable))

    def close(self):
        for pid, tw, rr in self._workers:
            try:
                _send(tw, None)
            except OSError:
                pass

    def terminate(self):
        import signal
        for pid, _, _ in self._workers:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def join(self):
        for pid, tw, rr in self._workers:
            for fd in (tw, rr):
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass
        self._workers = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            self.close()
        else:
            self.terminate()
        self.join()
        return False


def install():
    """multiprocessing.Pool -> ForkPool (on Android, unless SMO_FORKPOOL=0)."""
    if os.environ.get('SMO_FORKPOOL', '1') == '0':
        return
    import multiprocessing
    import multiprocessing.pool as mp_pool
    multiprocessing.Pool = ForkPool
    mp_pool.Pool = ForkPool
