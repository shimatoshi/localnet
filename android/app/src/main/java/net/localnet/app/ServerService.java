package net.localnet.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.file.Files;
import java.util.zip.GZIPInputStream;

/**
 * Foreground Service: Pythonサーバーをバックグラウンドで維持し、
 * クロールジョブの完了/エラーを通知する。
 */
public class ServerService extends Service {

    private static final String TAG = "Localnet-Service";
    private static final int PORT = 8789;
    private static final String CHANNEL_SERVICE = "localnet_service";
    private static final String CHANNEL_CRAWL = "localnet_crawl";
    private static final int NOTIFICATION_SERVICE = 1;
    private static final int NOTIFICATION_CRAWL = 2;

    private Handler handler;
    private boolean serverReady = false;
    private boolean monitoring = false;
    private String lastKnownJobId = null;

    // ジョブ監視間隔
    private static final long POLL_INTERVAL_MS = 5000;

    @Override
    public void onCreate() {
        super.onCreate();
        handler = new Handler(Looper.getMainLooper());
        createNotificationChannels();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFICATION_SERVICE, buildServiceNotification("起動中..."));

        new Thread(() -> {
            try {
                extractPythonBundle();
                extractAppSource();
                startPythonServer();
                waitForServer();
                serverReady = true;

                updateServiceNotification("サーバー稼働中");
                Log.i(TAG, "Server ready, starting job monitor");
                startJobMonitor();
            } catch (Exception e) {
                Log.e(TAG, "Server startup failed", e);
                updateServiceNotification("起動失敗: " + e.getMessage());
            }
        }).start();

        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        monitoring = false;
        super.onDestroy();
    }

    // === 通知チャンネル ===

    private void createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = getSystemService(NotificationManager.class);

            NotificationChannel service = new NotificationChannel(
                    CHANNEL_SERVICE, "サーバー稼働",
                    NotificationManager.IMPORTANCE_LOW);
            service.setDescription("バックグラウンドサーバーの状態");
            nm.createNotificationChannel(service);

            NotificationChannel crawl = new NotificationChannel(
                    CHANNEL_CRAWL, "クロール通知",
                    NotificationManager.IMPORTANCE_HIGH);
            crawl.setDescription("クロールの完了・エラー通知");
            nm.createNotificationChannel(crawl);
        }
    }

    private Notification buildServiceNotification(String text) {
        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_SERVICE);
        } else {
            builder = new Notification.Builder(this);
        }
        return builder
                .setContentTitle("ShimaNet")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
    }

    private void updateServiceNotification(String text) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.notify(NOTIFICATION_SERVICE, buildServiceNotification(text));
    }

    private void showCrawlNotification(String title, String text) {
        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_CRAWL);
        } else {
            builder = new Notification.Builder(this);
        }
        Notification n = builder
                .setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build();

        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.notify(NOTIFICATION_CRAWL, n);
    }

    // === ジョブ監視 ===

    private void startJobMonitor() {
        monitoring = true;
        new Thread(() -> {
            String trackingJobId = null;
            String trackingDomain = null;

            while (monitoring) {
                try {
                    Thread.sleep(POLL_INTERVAL_MS);
                } catch (InterruptedException e) {
                    break;
                }

                try {
                    // アクティブジョブを確認
                    String activeJson = httpGet("http://127.0.0.1:" + PORT + "/api/jobs/active");
                    if (activeJson == null) continue;

                    if (activeJson.equals("[]")) {
                        // ジョブなし — 追跡中のジョブがあれば完了チェック
                        if (trackingJobId != null) {
                            String jobJson = httpGet("http://127.0.0.1:" + PORT + "/api/jobs/" + trackingJobId);
                            if (jobJson != null) {
                                // 簡易JSON解析
                                String status = extractJsonString(jobJson, "status");
                                String pageCount = extractJsonString(jobJson, "page_count");
                                String error = extractJsonString(jobJson, "error");

                                if ("done".equals(status)) {
                                    showCrawlNotification(
                                            "クロール完了",
                                            trackingDomain + " (" + pageCount + "ページ)");
                                    updateServiceNotification("サーバー稼働中");
                                } else if ("error".equals(status)) {
                                    showCrawlNotification(
                                            "クロールエラー",
                                            trackingDomain + ": " + (error != null ? error : "不明なエラー"));
                                    updateServiceNotification("サーバー稼働中");
                                }
                            }
                            trackingJobId = null;
                            trackingDomain = null;
                        }
                    } else {
                        // アクティブジョブあり — 追跡開始
                        String jobId = extractJsonString(activeJson, "job_id");
                        String domain = extractJsonString(activeJson, "domain");
                        String pageCount = extractJsonString(activeJson, "page_count");
                        if (jobId != null && !jobId.equals(trackingJobId)) {
                            trackingJobId = jobId;
                            trackingDomain = domain;
                            Log.i(TAG, "Tracking job: " + jobId + " (" + domain + ")");
                        }
                        updateServiceNotification("クロール中: " + domain + " (" + pageCount + "p)");
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Job monitor error: " + e.getMessage());
                }
            }
        }, "job-monitor").start();
    }

    private String httpGet(String urlStr) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(2000);
            conn.setReadTimeout(2000);
            if (conn.getResponseCode() != 200) {
                conn.disconnect();
                return null;
            }
            BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream()));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            br.close();
            conn.disconnect();
            return sb.toString();
        } catch (Exception e) {
            return null;
        }
    }

    /** 簡易JSON文字列抽出（ライブラリ不要） */
    private String extractJsonString(String json, String key) {
        String search = "\"" + key + "\":";
        int idx = json.indexOf(search);
        if (idx < 0) return null;
        int start = idx + search.length();
        // 空白スキップ
        while (start < json.length() && json.charAt(start) == ' ') start++;
        if (start >= json.length()) return null;
        char c = json.charAt(start);
        if (c == '"') {
            int end = json.indexOf('"', start + 1);
            return end > start ? json.substring(start + 1, end) : null;
        } else if (c == 'n') {
            return null; // null
        } else {
            // 数値
            int end = start;
            while (end < json.length() && json.charAt(end) != ',' && json.charAt(end) != '}') end++;
            return json.substring(start, end).trim();
        }
    }

    // === Python起動（MainActivityから移植） ===

    private void extractPythonBundle() throws IOException {
        File pythonDir = new File(getFilesDir(), "python-bundle");
        File versionFile = new File(pythonDir, ".version");
        String currentVersion = BuildConfig.VERSION_NAME;

        if (versionFile.exists()) {
            try (BufferedReader r = new BufferedReader(new FileReader(versionFile))) {
                if (currentVersion.equals(r.readLine())) return;
            } catch (IOException ignored) {}
        }

        deleteRecursive(pythonDir);

        try (InputStream is = getAssets().open("python-bundle.bin");
             GZIPInputStream gis = new GZIPInputStream(is)) {
            extractTar(gis, getFilesDir());
        }

        File symlinkTarget = new File(pythonDir, "lib/python3.13");
        symlinkTarget.getParentFile().mkdirs();
        if (!symlinkTarget.exists()) {
            Files.createSymbolicLink(symlinkTarget.toPath(),
                    new File(pythonDir, "stdlib").toPath());
        }

        try (FileWriter w = new FileWriter(versionFile)) {
            w.write(currentVersion);
        }
    }

    private void extractAppSource() throws IOException {
        File appDir = getFilesDir();
        File srcVersion = new File(appDir, ".src_version");
        String currentVersion = BuildConfig.VERSION_NAME;

        if (srcVersion.exists()) {
            try (BufferedReader r = new BufferedReader(new FileReader(srcVersion))) {
                if (currentVersion.equals(r.readLine())) return;
            } catch (IOException ignored) {}
        }

        copyAssetDir("app-source", appDir);
        new File(appDir, "cache").mkdirs();
        new File(appDir, "sites").mkdirs();

        try (FileWriter w = new FileWriter(srcVersion)) {
            w.write(currentVersion);
        }
    }

    private void startPythonServer() {
        File appDir = getFilesDir();
        File pythonDir = new File(appDir, "python-bundle");

        String bundleLibDir = new File(pythonDir, "lib").getAbsolutePath();
        String nativeLibDir = getApplicationInfo().nativeLibraryDir;
        String stdlibDir = new File(pythonDir, "stdlib").getAbsolutePath();
        String siteDir = new File(pythonDir, "site-packages").getAbsolutePath();

        PythonLauncher.redirectStderr(new File(appDir, "python_stderr.log").getAbsolutePath());

        PythonLauncher.setEnv("LD_LIBRARY_PATH", bundleLibDir + ":" + nativeLibDir);
        PythonLauncher.setEnv("PYTHONHOME", pythonDir.getAbsolutePath());
        PythonLauncher.setEnv("PYTHONPATH", stdlibDir + ":" + siteDir + ":" + appDir.getAbsolutePath());
        PythonLauncher.setEnv("LOCALNET_BASE", appDir.getAbsolutePath());
        PythonLauncher.setEnv("LOCALNET_PORT", String.valueOf(PORT));

        new Thread(() -> {
            try {
                int code = PythonLauncher.runPython(new String[]{
                        "python3", new File(appDir, "boot.py").getAbsolutePath()
                });
                Log.i(TAG, "Python exited with code " + code);
            } catch (Exception e) {
                Log.e(TAG, "Python crashed", e);
            }
        }, "python-server").start();
    }

    private void waitForServer() {
        for (int i = 0; i < 60; i++) {
            try {
                URL url = new URL("http://127.0.0.1:" + PORT + "/api/version");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(500);
                conn.setReadTimeout(500);
                int code = conn.getResponseCode();
                conn.disconnect();
                if (code == 200) return;
            } catch (Exception ignored) {}
            try { Thread.sleep(500); } catch (InterruptedException ignored) {}
        }
    }

    // === ユーティリティ（MainActivityと共通） ===

    private void extractTar(InputStream is, File destDir) throws IOException {
        byte[] header = new byte[512];
        while (true) {
            int read = readFully(is, header);
            if (read < 512) break;
            boolean allZero = true;
            for (int i = 0; i < 512; i++) { if (header[i] != 0) { allZero = false; break; } }
            if (allZero) break;
            String name = new String(header, 0, 100).trim().replace('\0', ' ').trim();
            if (name.isEmpty()) break;
            long size = parseTarOctal(header, 124, 12);
            byte type = header[156];
            File outFile = new File(destDir, name);
            if (type == '5' || name.endsWith("/")) {
                outFile.mkdirs();
            } else {
                outFile.getParentFile().mkdirs();
                try (FileOutputStream fos = new FileOutputStream(outFile)) {
                    long remaining = size;
                    byte[] buf = new byte[8192];
                    while (remaining > 0) {
                        int toRead = (int) Math.min(buf.length, remaining);
                        int n = is.read(buf, 0, toRead);
                        if (n <= 0) break;
                        fos.write(buf, 0, n);
                        remaining -= n;
                    }
                }
            }
            long pad = (512 - (size % 512)) % 512;
            is.skip(pad);
        }
    }

    private int readFully(InputStream is, byte[] buf) throws IOException {
        int total = 0;
        while (total < buf.length) {
            int n = is.read(buf, total, buf.length - total);
            if (n <= 0) break;
            total += n;
        }
        return total;
    }

    private long parseTarOctal(byte[] header, int offset, int length) {
        String s = new String(header, offset, length).trim().replace('\0', ' ').trim();
        if (s.isEmpty()) return 0;
        try { return Long.parseLong(s, 8); } catch (NumberFormatException e) { return 0; }
    }

    private void deleteRecursive(File f) {
        if (f.isDirectory()) {
            File[] children = f.listFiles();
            if (children != null) { for (File child : children) deleteRecursive(child); }
        }
        f.delete();
    }

    private void copyAssetDir(String assetPath, File targetDir) throws IOException {
        String[] list = getAssets().list(assetPath);
        if (list == null || list.length == 0) {
            targetDir.getParentFile().mkdirs();
            try (InputStream is = getAssets().open(assetPath);
                 OutputStream os = new FileOutputStream(targetDir)) {
                byte[] buf = new byte[8192];
                int len;
                while ((len = is.read(buf)) > 0) os.write(buf, 0, len);
            }
        } else {
            targetDir.mkdirs();
            for (String child : list) {
                copyAssetDir(assetPath + "/" + child, new File(targetDir, child));
            }
        }
    }
}
