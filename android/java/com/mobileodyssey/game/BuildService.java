/* BuildService - builds the game library on the device (fork for the AYN Thor Max), as a foreground service so it goes
 * on with the screen off or the launcher closed: about an hour or more on a Snapdragon 8 Gen 2, done once.
 *
 * Input: the ExeFS the player imported (<external files>/dump/base/exefs, LauncherActivity). Runs
 * tools/ondevice/build_on_device.py with the app's own Python and clang (Builder), writes everything it says to
 * files/build.log, keeps the notification on the current step, and on "BUILD OK" copies libsmo.so to files/game/.
 * A stopped build (the app killed, the battery) starts again from the step it was in (build_on_device.py's marks).
 * The CPU is held with a partial wake lock; the build uses all but two cores, so the device stays usable. */
package com.mobileodyssey.game;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.IBinder;
import android.os.PowerManager;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

public class BuildService extends Service {
    static final String CHANNEL = "build";
    static final int NOTE = 1;
    static volatile boolean running;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTE, note("Preparing the compiler…"));
        if (!running) {
            running = true;
            new Thread(this::build, "build").start();
        }
        return START_NOT_STICKY;
    }

    Notification note(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm.getNotificationChannel(CHANNEL) == null)
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Game build", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, LauncherActivity.class), PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentTitle("Building the game").setContentText(text).setStyle(new Notification.BigTextStyle().bigText(text))
                .setOngoing(true).setContentIntent(open).build();
    }

    void update(String text) {
        ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).notify(NOTE, note(text));
    }

    void build() {
        PowerManager.WakeLock wl = ((PowerManager) getSystemService(Context.POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "odyssey:build");
        wl.acquire(6 * 3600 * 1000L);
        String result;
        try (OutputStream log = new FileOutputStream(Builder.log(this))) {
            Builder.writeState(this, "running");
            File root = getExternalFilesDir(null);
            File exefs = new File(root, "dump/base/exefs");
            if (!new File(exefs, "main").isFile()) throw new IllegalStateException("no ExeFS imported (dump/base/exefs/main)");
            update("Unpacking the compiler (once per app version)…");
            File tc = Builder.tc(this), bundle = Builder.bundle(this);
            Builder.unpack(this, "tc.tar.gz", tc);
            Builder.unpack(this, "builder.tar.gz", bundle);
            new File(bundle, "tmp").mkdirs();                     /* Python's process pool (/proc/self/cwd/tmp: fetch_toolchain.py) */
            int jobs = Math.max(1, Runtime.getRuntime().availableProcessors() - 2);
            ProcessBuilder pb = new ProcessBuilder(tc + "/bin/python3", "tools/ondevice/build_on_device.py",
                    "--exefs", exefs.getPath(), "--jobs", String.valueOf(jobs)).directory(bundle).redirectErrorStream(true);
            Map<String, String> env = pb.environment();
            env.put("LD_LIBRARY_PATH", tc + "/lib");
            env.put("PYTHONHOME", tc.getPath());
            env.put("HOME", getFilesDir().getPath());
            env.put("TMPDIR", getCacheDir().getPath());
            env.put("PATH", tc + "/bin:/system/bin");
            env.put("SMO_ONDEVICE_TC", tc.getPath());
            env.put("SHADERC_LIBS", bundle + "/prebuilt/shaderc");
            env.put("ADRENOTOOLS", bundle + "/prebuilt/adrenotools");
            Process p = pb.start();
            String ok = null;
            try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                String step = "";
                for (String s; (s = r.readLine()) != null; ) {
                    log.write((s + "\n").getBytes(StandardCharsets.UTF_8));
                    log.flush();
                    if (s.startsWith("STEP ")) { step = s.substring(5); update(step); }
                    else if (s.matches("\\s+\\d+/\\d+ done.*")) update(step + "\n" + s.trim());
                    else if (s.startsWith("BUILD OK ")) ok = s.substring(9).split(" \\(")[0];
                }
            }
            int rc = p.waitFor();
            if (rc != 0 || ok == null) throw new IllegalStateException("the build stopped (exit code " + rc + "): see the build log");
            File lib = Builder.gameLib(this), tmp = new File(lib.getPath() + ".new");
            lib.getParentFile().mkdirs();
            try (java.io.InputStream in = new java.io.FileInputStream(ok); OutputStream o = new FileOutputStream(tmp)) { LauncherActivity.pipe(in, o); }
            if (!tmp.renameTo(lib)) throw new IllegalStateException("could not place " + lib);
            /* The game reads its executables from dump/base/elf (android_main.c): the build made them from the ExeFS. */
            File elfOut = new File(root, "dump/base/elf"), elfIn = new File(bundle, "build/dump/base/elf");
            elfOut.mkdirs();
            String[] elfs = elfIn.list();
            if (elfs != null) for (String n : elfs)
                try (java.io.InputStream in = new java.io.FileInputStream(new File(elfIn, n)); OutputStream o = new FileOutputStream(new File(elfOut, n))) { LauncherActivity.pipe(in, o); }
            Builder.stampGame(this);
            result = "ok";
            update("Done: the game is built. Open the app and press Play.");
        } catch (Throwable e) {
            result = "failed: " + e.getMessage();
            try (OutputStream log = new FileOutputStream(Builder.log(this), true)) {
                log.write(("\n" + android.util.Log.getStackTraceString(e)).getBytes(StandardCharsets.UTF_8));
            } catch (Exception ignored) { }
        }
        Builder.writeState(this, result);
        running = false;
        if (wl.isHeld()) wl.release();
        stopForeground(STOP_FOREGROUND_DETACH);
        ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).notify(NOTE, new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_download_done).setContentTitle(result.equals("ok") ? "Game built" : "Game build failed")
                .setContentText(result.equals("ok") ? "Open the app and press Play" : result).setAutoCancel(true)
                .setContentIntent(PendingIntent.getActivity(this, 0, new Intent(this, LauncherActivity.class), PendingIntent.FLAG_IMMUTABLE)).build());
        stopSelf();
    }
}
