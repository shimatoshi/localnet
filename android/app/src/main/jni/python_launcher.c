#include <jni.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <fcntl.h>
#include <unistd.h>
#include <dlfcn.h>

/* libpython3.13.soのPy_Mainを呼ぶ */
extern int Py_Main(int argc, wchar_t **argv);

/* Cレベルのstderrをファイルにリダイレクト */
JNIEXPORT void JNICALL
Java_net_localnet_app_PythonLauncher_redirectStderr(JNIEnv *env, jclass cls, jstring path) {
    const char *p = (*env)->GetStringUTFChars(env, path, NULL);
    int fd = open(p, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd >= 0) {
        dup2(fd, STDERR_FILENO);
        dup2(fd, STDOUT_FILENO);
        close(fd);
    }
    (*env)->ReleaseStringUTFChars(env, path, p);
}

/* Java側から環境変数をCレベルで設定するためのJNI関数 */
JNIEXPORT void JNICALL
Java_net_localnet_app_PythonLauncher_setEnv(JNIEnv *env, jclass cls, jstring key, jstring value) {
    const char *k = (*env)->GetStringUTFChars(env, key, NULL);
    const char *v = (*env)->GetStringUTFChars(env, value, NULL);
    setenv(k, v, 1);
    (*env)->ReleaseStringUTFChars(env, key, k);
    (*env)->ReleaseStringUTFChars(env, value, v);
}

JNIEXPORT jint JNICALL
Java_net_localnet_app_PythonLauncher_runPython(JNIEnv *env, jclass cls, jobjectArray args) {
    /* デバッグ: 環境変数とPy_Mainの結果をファイルに記録 */
    const char *home = getenv("PYTHONHOME");
    const char *path = getenv("PYTHONPATH");
    const char *base = getenv("LOCALNET_BASE");

    FILE *dbg = fopen("/data/user/0/net.localnet.app/files/python_debug.log", "w");
    if (dbg) {
        fprintf(dbg, "PYTHONHOME=%s\n", home ? home : "(null)");
        fprintf(dbg, "PYTHONPATH=%s\n", path ? path : "(null)");
        fprintf(dbg, "LOCALNET_BASE=%s\n", base ? base : "(null)");
        fflush(dbg);
    }

    int argc = (*env)->GetArrayLength(env, args);
    wchar_t **wargv = (wchar_t **)malloc(sizeof(wchar_t *) * (argc + 1));

    for (int i = 0; i < argc; i++) {
        jstring jstr = (jstring)(*env)->GetObjectArrayElement(env, args, i);
        const char *utf = (*env)->GetStringUTFChars(env, jstr, NULL);
        size_t len = mbstowcs(NULL, utf, 0) + 1;
        wargv[i] = (wchar_t *)malloc(sizeof(wchar_t) * len);
        mbstowcs(wargv[i], utf, len);
        (*env)->ReleaseStringUTFChars(env, jstr, utf);
        if (dbg) { fprintf(dbg, "argv[%d]=%s\n", i, utf); fflush(dbg); }
    }
    wargv[argc] = NULL;

    /* stderrをログファイルにリダイレクト（このスレッドで実行） */
    {
        const char *logpath = "/data/user/0/net.localnet.app/files/python_stderr.log";
        int logfd = open(logpath, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (logfd >= 0) {
            dup2(logfd, STDERR_FILENO);
            dup2(logfd, STDOUT_FILENO);
            close(logfd);
            if (dbg) { fprintf(dbg, "stderr redirected to %s\n", logpath); fflush(dbg); }
        }
    }

    /* LD_LIBRARY_PATHが効かないので、手動でdlopen()でプリロード */
    const char *ld_path = getenv("LD_LIBRARY_PATH");
    if (ld_path && dbg) { fprintf(dbg, "Preloading libs from %s\n", ld_path); fflush(dbg); }
    if (ld_path) {
        /* LD_LIBRARY_PATHの最初のディレクトリからプリロード */
        char libdir[512];
        const char *colon = strchr(ld_path, ':');
        size_t dirlen = colon ? (size_t)(colon - ld_path) : strlen(ld_path);
        if (dirlen < sizeof(libdir)) {
            memcpy(libdir, ld_path, dirlen);
            libdir[dirlen] = '\0';

            const char *libs[] = {
                "libz.so.1", "libffi.so", "libsqlite3.so", "libexpat.so.1",
                "liblzma.so.5", "libbz2.so.1.0", "libcrypto3.so", "libssl3.so",
                "libandroid-support.so", NULL
            };
            for (int i = 0; libs[i]; i++) {
                char fullpath[1024];
                snprintf(fullpath, sizeof(fullpath), "%s/%s", libdir, libs[i]);
                void *h = dlopen(fullpath, RTLD_NOW | RTLD_GLOBAL);
                if (dbg) {
                    if (h) fprintf(dbg, "  preloaded %s\n", libs[i]);
                    else fprintf(dbg, "  FAILED %s: %s\n", libs[i], dlerror());
                    fflush(dbg);
                }
            }
        }
    }

    if (dbg) { fprintf(dbg, "Calling Py_Main...\n"); fflush(dbg); }

    int result = Py_Main(argc, wargv);

    if (dbg) { fprintf(dbg, "Py_Main returned %d\n", result); fclose(dbg); }

    for (int i = 0; i < argc; i++) free(wargv[i]);
    free(wargv);

    return result;
}
