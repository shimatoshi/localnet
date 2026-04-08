package net.localnet.app;

import android.util.Log;

public class PythonLauncher {
    private static final String TAG = "Localnet-PythonLauncher";

    static {
        try {
            Log.i(TAG, "Loading android-support...");
            System.loadLibrary("android-support");
            Log.i(TAG, "Loading python3.13...");
            System.loadLibrary("python3.13");
            Log.i(TAG, "Loading python_launcher...");
            System.loadLibrary("python_launcher");
            Log.i(TAG, "All native libraries loaded successfully");
        } catch (UnsatisfiedLinkError e) {
            Log.e(TAG, "Failed to load native library: " + e.getMessage(), e);
            throw e;
        }
    }

    /** Cレベルでstdout/stderrをファイルにリダイレクト */
    public static native void redirectStderr(String path);

    /** Cレベルでsetenv()を呼ぶ */
    public static native void setEnv(String key, String value);

    /** Pythonのメイン関数を実行（Py_Main相当） */
    public static native int runPython(String[] args);
}
