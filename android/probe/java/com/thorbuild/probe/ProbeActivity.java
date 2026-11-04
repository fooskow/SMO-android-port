/* ProbeActivity - does the on-device toolchain work INSIDE an app? (Fork for the AYN Thor Max, milestone 1.)
 *
 * Unpacks the toolchain the APK carries (assets/tc.tar.gz: Termux's clang, lld and Python with the NDK's sysroot,
 * tools/ondevice/fetch_toolchain.py) into the app's files, then, as the app's own user and SELinux domain:
 *   1. clang compiles a small C file into a shared library with a JNI function, and the app loads it (System.load) and
 *      calls it: the path the game library will take;
 *   2. Python runs the parts of the standard library the lifter needs, multiprocessing included.
 * Every result goes to logcat (tag PROBE), ending with "PROBE DONE"; the CI emulator test waits for it. */
package com.thorbuild.probe;

import android.app.Activity;
import android.os.Bundle;
import android.system.Os;
import android.util.Log;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.zip.GZIPInputStream;

public class ProbeActivity extends Activity {
    static final String T = "PROBE";
    TextView view;
    final StringBuilder shown = new StringBuilder();

    static native int answer();

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        view = new TextView(this);
        view.setTextSize(12);
        view.setPadding(24, 24, 24, 24);
        setContentView(view);
        new Thread(this::run, "probe").start();
    }

    void say(String s) {
        Log.i(T, s);
        runOnUiThread(() -> { shown.append(s).append('\n'); view.setText(shown); });
    }

    void run() {
        String clang = "fail", python = "fail";
        try {
            File tc = new File(getFilesDir(), "tc");
            long t0 = System.nanoTime();
            if (!new File(tc, ".ok").exists()) {
                deleteTree(tc);
                try (InputStream in = new GZIPInputStream(getAssets().open("tc.tar.gz"), 1 << 16)) { untar(in, tc); }
                new File(tc, ".ok").createNewFile();
            }
            say(String.format("toolchain unpacked in %.1f s: %s", (System.nanoTime() - t0) / 1e9, tc));
            String abi = android.os.Build.SUPPORTED_ABIS[0];
            String triple = abi.startsWith("arm64") ? "aarch64-linux-android30" : "x86_64-linux-android30";

            File work = new File(getFilesDir(), "probe");
            deleteTree(work);
            work.mkdirs();
            new File(work, "tmp").mkdirs();          /* named semaphores: /proc/self/cwd/tmp (fetch_toolchain.py) */
            File src = new File(work, "hello.c"), lib = new File(work, "libhello.so");
            write(src, "#include <jni.h>\n#include <pthread.h>\n#include <sys/mman.h>\n"
                    + "static int twice(int x) { return 2 * x; }\n"
                    + "JNIEXPORT jint JNICALL Java_com_thorbuild_probe_ProbeActivity_answer(JNIEnv *e, jclass c) {\n"
                    + "  (void)e; (void)c; return twice(21) + (MAP_FIXED_NOREPLACE ? 0 : 1); }\n");
            t0 = System.nanoTime();
            int rc = exec(tc, work, tc + "/bin/clang", "--target=" + triple, "--sysroot=" + tc + "/sysroot",
                    "-fuse-ld=lld", "-O2", "-fPIC", "-shared", "-o", lib.getPath(), src.getPath());
            say(String.format("clang exit %d in %.1f s", rc, (System.nanoTime() - t0) / 1e9));
            if (rc == 0 && lib.exists()) {
                System.load(lib.getPath());
                int v = answer();
                say("libhello.so loaded, answer() = " + v);
                if (v == 42) clang = "ok";
            }

            t0 = System.nanoTime();
            rc = exec(tc, work, tc + "/bin/python3", "-c",
                    "import sys, struct, zlib, json, bisect, csv, collections, concurrent.futures, multiprocessing as m\n"
                    + "print('python', sys.version.split()[0], 'prefix', sys.prefix)\n"
                    + "with m.Pool(2) as p: r = p.map(abs, [-1, -2, -3])\n"
                    + "print('pool', r)\n"
                    + "assert r == [1, 2, 3]\n"
                    + "print('PYOK')");
            say(String.format("python exit %d in %.1f s", rc, (System.nanoTime() - t0) / 1e9));
            if (rc == 0 && shown.indexOf("PYOK") >= 0) python = "ok";
        } catch (Throwable e) {
            say("error: " + Log.getStackTraceString(e));
        }
        say("PROBE RESULT clang=" + clang + " python=" + python);
        say("PROBE DONE");
    }

    int exec(File tc, File cwd, String... cmd) throws IOException, InterruptedException {
        ProcessBuilder pb = new ProcessBuilder(cmd).directory(cwd).redirectErrorStream(true);
        Map<String, String> env = pb.environment();
        env.put("LD_LIBRARY_PATH", tc + "/lib");
        env.put("PYTHONHOME", tc.getPath());
        env.put("HOME", getFilesDir().getPath());
        env.put("TMPDIR", getCacheDir().getPath());
        env.put("PATH", tc + "/bin:/system/bin");
        Process p = pb.start();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
            for (String s; (s = r.readLine()) != null; ) say("  | " + s);
        }
        return p.waitFor();
    }

    static void write(File f, String s) throws IOException {
        try (OutputStream o = new FileOutputStream(f)) { o.write(s.getBytes(StandardCharsets.UTF_8)); }
    }

    static void deleteTree(File f) {
        File[] l = f.listFiles();
        if (l != null && !isLink(f)) for (File c : l) deleteTree(c);
        f.delete();
    }

    static boolean isLink(File f) {
        try { return android.system.Os.lstat(f.getPath()).st_mode / 0x1000 == 0xA; } catch (Exception e) { return false; }
    }

    /* A tar reader (ustar + pax names, files, folders, symbolic links, modes): what Python's tarfile writes. */
    static void untar(InputStream in, File root) throws Exception {
        byte[] h = new byte[512];
        String paxPath = null, paxLink = null;
        String rootPath = root.getCanonicalPath();
        root.mkdirs();
        while (readFully(in, h, 512)) {
            if (h[0] == 0) break;
            String name = str(h, 0, 100), prefix = str(h, 345, 155), link = str(h, 157, 100);
            if (!prefix.isEmpty()) name = prefix + "/" + name;
            int mode = (int) oct(h, 100, 8);
            long size = oct(h, 124, 12);
            char type = (char) h[156];
            if (type == 'x' || type == 'g') {
                byte[] d = new byte[(int) size];
                readFully(in, d, (int) size);
                skip(in, pad(size));
                if (type == 'x') {
                    String recs = new String(d, StandardCharsets.UTF_8);
                    int i = 0;
                    while (i < recs.length()) {
                        int sp = recs.indexOf(' ', i);
                        int len = Integer.parseInt(recs.substring(i, sp));
                        String kv = recs.substring(sp + 1, i + len - 1);
                        int eq = kv.indexOf('=');
                        String k = kv.substring(0, eq), v = kv.substring(eq + 1);
                        if (k.equals("path")) paxPath = v;
                        if (k.equals("linkpath")) paxLink = v;
                        i += len;
                    }
                }
                continue;
            }
            if (paxPath != null) { name = paxPath; paxPath = null; }
            if (paxLink != null) { link = paxLink; paxLink = null; }
            while (name.startsWith("./")) name = name.substring(2);
            File out = new File(root, name);
            if (!out.getCanonicalPath().startsWith(rootPath) && !name.isEmpty() && !name.equals(".")) throw new IOException("bad path " + name);
            if (type == '5') { out.mkdirs(); }
            else if (type == '2') { out.getParentFile().mkdirs(); out.delete(); Os.symlink(link, out.getPath()); }
            else if (type == '0' || type == 0) {
                out.getParentFile().mkdirs();
                try (OutputStream o = new FileOutputStream(out)) {
                    byte[] buf = new byte[1 << 16];
                    long left = size;
                    while (left > 0) {
                        int n = in.read(buf, 0, (int) Math.min(buf.length, left));
                        if (n < 0) throw new IOException("short tar");
                        o.write(buf, 0, n);
                        left -= n;
                    }
                }
                Os.chmod(out.getPath(), mode & 0777);
                skip(in, pad(size));
            } else skip(in, size + pad(size));
        }
    }

    static long pad(long size) { return (512 - size % 512) % 512; }
    static boolean readFully(InputStream in, byte[] b, int n) throws IOException {
        int got = 0;
        while (got < n) { int r = in.read(b, got, n - got); if (r < 0) return false; got += r; }
        return true;
    }
    static void skip(InputStream in, long n) throws IOException {
        byte[] b = new byte[8192];
        while (n > 0) { int r = in.read(b, 0, (int) Math.min(b.length, n)); if (r < 0) throw new IOException("short tar"); n -= r; }
    }
    static String str(byte[] h, int off, int len) {
        int e = off;
        while (e < off + len && h[e] != 0) e++;
        return new String(h, off, e - off, StandardCharsets.UTF_8);
    }
    static long oct(byte[] h, int off, int len) {
        String s = str(h, off, len).trim();
        return s.isEmpty() ? 0 : Long.parseLong(s, 8);
    }
}
