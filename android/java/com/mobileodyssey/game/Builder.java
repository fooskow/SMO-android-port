/* Builder - the on-device build's files (fork for the AYN Thor Max).
 *
 * The APK carries no game code. It carries a compiler instead (assets/tc.tar.gz: Termux's clang, lld and Python with
 * the NDK's sysroot, tools/ondevice/fetch_toolchain.py) and the build's own scripts and runtime sources with the
 * prebuilt libraries (assets/builder.tar.gz, tools/ondevice/make_bundle.py). BuildService unpacks both into the app's
 * internal files once per APK version and runs tools/ondevice/build_on_device.py on the player's own ExeFS; the
 * result, the game library, is files/game/libsmo.so, which GameActivity loads instead of a library inside the APK. */
package com.mobileodyssey.game;

import android.content.Context;
import android.system.Os;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;

public final class Builder {
    private Builder() { }

    static File tc(Context c) { return new File(c.getFilesDir(), "tc"); }
    static File bundle(Context c) { return new File(c.getFilesDir(), "builder"); }
    static File gameLib(Context c) { return new File(new File(c.getFilesDir(), "game"), "libsmo.so"); }
    static File log(Context c) { return new File(c.getFilesDir(), "build.log"); }
    static File state(Context c) { return new File(c.getFilesDir(), "build.state"); }     /* running | ok | failed: <why> */
    static boolean built(Context c) { return gameLib(c).isFile(); }
    /* The game library was built by this APK's runtime (an update brings a new runtime: build again, minutes). */
    static boolean current(Context c) {
        try (InputStream in = new java.io.FileInputStream(new File(gameLib(c).getParentFile(), "stamp"))) {
            long stamp = c.getPackageManager().getPackageInfo(c.getPackageName(), 0).lastUpdateTime;
            return new String(LauncherActivity.readAll(in), StandardCharsets.UTF_8).trim().equals(String.valueOf(stamp));
        } catch (Exception e) { return false; }
    }
    static void stampGame(Context c) {
        try (OutputStream o = new FileOutputStream(new File(gameLib(c).getParentFile(), "stamp"))) {
            o.write(String.valueOf(c.getPackageManager().getPackageInfo(c.getPackageName(), 0).lastUpdateTime).getBytes(StandardCharsets.UTF_8));
        } catch (Exception ignored) { }
    }

    static String readState(Context c) {
        try (InputStream in = new java.io.FileInputStream(state(c))) {
            return new String(LauncherActivity.readAll(in), StandardCharsets.UTF_8).trim();
        } catch (IOException e) { return ""; }
    }
    static void writeState(Context c, String s) {
        try (OutputStream o = new FileOutputStream(state(c))) { o.write(s.getBytes(StandardCharsets.UTF_8)); } catch (IOException ignored) { }
    }

    /* The last line of the build log that says where the build is ("STEP 3/7 ...", "  150/257 done ..."). */
    static String progress(Context c) {
        String step = "", sub = "";
        try (java.io.BufferedReader r = new java.io.BufferedReader(new java.io.InputStreamReader(new java.io.FileInputStream(log(c)), StandardCharsets.UTF_8))) {
            for (String s; (s = r.readLine()) != null; ) {
                if (s.startsWith("STEP ")) { step = s.substring(5); sub = ""; }
                else if (s.matches("\\s+\\d+/\\d+ done.*")) sub = s.trim();
            }
        } catch (IOException ignored) { }
        return sub.isEmpty() ? step : step + " · " + sub;
    }

    /* Unpacks an asset tarball into dir unless dir was made from this same APK (its stamp). */
    static void unpack(Context c, String asset, File dir) throws Exception {
        long stamp = c.getPackageManager().getPackageInfo(c.getPackageName(), 0).lastUpdateTime;
        File mark = new File(dir, ".stamp");
        if (mark.exists()) {
            try (InputStream in = new java.io.FileInputStream(mark)) {
                if (new String(LauncherActivity.readAll(in), StandardCharsets.UTF_8).trim().equals(String.valueOf(stamp))) return;
            }
        }
        /* The builder's build/ folder (the lifted code, the compiled objects) outlives an app update: only what the
         * update changed is built again (the runtime at least: its last two steps are forgotten). */
        File keep = new File(dir, "build"), kept = new File(dir.getParentFile(), dir.getName() + ".build-kept");
        LauncherActivity.deleteTree(kept);
        boolean saved = keep.isDirectory() && keep.renameTo(kept);
        LauncherActivity.deleteTree(dir);
        try (InputStream in = new GZIPInputStream(c.getAssets().open(asset), 1 << 16)) { untar(in, dir); }
        if (saved) {
            kept.renameTo(keep);
            File marks = new File(keep, "ondevice_steps.txt");
            if (marks.exists()) {
                StringBuilder sb = new StringBuilder();
                try (InputStream in = new java.io.FileInputStream(marks)) {
                    for (String l : new String(LauncherActivity.readAll(in), StandardCharsets.UTF_8).split("\n"))
                        if (!l.trim().isEmpty() && Integer.parseInt(l.trim()) < 6) sb.append(l.trim()).append('\n');
                }
                try (OutputStream o = new FileOutputStream(marks)) { o.write(sb.toString().getBytes(StandardCharsets.UTF_8)); }
            }
        }
        try (OutputStream o = new FileOutputStream(mark)) { o.write(String.valueOf(stamp).getBytes(StandardCharsets.UTF_8)); }
    }

    /* A tar reader (ustar + pax names, files, folders, symbolic links, modes): what Python's tarfile writes. */
    static void untar(InputStream in, File root) throws Exception {
        byte[] h = new byte[512];
        String paxPath = null, paxLink = null;
        root.mkdirs();
        String rootPath = root.getCanonicalPath();
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
            if (name.isEmpty() || name.equals(".")) { if (type != '5') skip(in, size + pad(size)); continue; }
            File out = new File(root, name);
            if (!out.getCanonicalPath().startsWith(rootPath)) throw new IOException("bad path in archive: " + name);
            if (type == '5') out.mkdirs();
            else if (type == '2') { out.getParentFile().mkdirs(); out.delete(); Os.symlink(link, out.getPath()); }
            else if (type == '0' || type == 0) {
                out.getParentFile().mkdirs();
                try (OutputStream o = new FileOutputStream(out)) {
                    byte[] buf = new byte[1 << 16];
                    long left = size;
                    while (left > 0) {
                        int n = in.read(buf, 0, (int) Math.min(buf.length, left));
                        if (n < 0) throw new IOException("short archive");
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
        while (n > 0) { int r = in.read(b, 0, (int) Math.min(b.length, n)); if (r < 0) throw new IOException("short archive"); n -= r; }
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
