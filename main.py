"""Localnet — buildozer APK entry point.

バックグラウンドでFlaskサーバーを起動し、
フルスクリーンWebViewでローカルホストに接続する。
"""

import os
import sys
import threading
import time

# Set working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kivy.app import App
from kivy.clock import Clock
from kivy.utils import platform

PORT = 8789


def start_flask():
    """Flaskサーバーをバックグラウンドで起動"""
    # buildozer環境ではAPK内のファイルディレクトリを使う
    if platform == 'android':
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        app_dir = activity.getFilesDir().getAbsolutePath()

        # cache, sitesディレクトリ作成
        os.makedirs(os.path.join(app_dir, 'cache'), exist_ok=True)
        os.makedirs(os.path.join(app_dir, 'sites'), exist_ok=True)

        os.environ['LOCALNET_BASE'] = app_dir
        os.environ['LOCALNET_PORT'] = str(PORT)

        # frontendをapp_dirにコピー（初回のみ）
        src_frontend = os.path.join(os.path.dirname(__file__), 'frontend', 'dist')
        dst_frontend = os.path.join(app_dir, 'frontend', 'dist')
        if os.path.isdir(src_frontend) and not os.path.isdir(dst_frontend):
            import shutil
            shutil.copytree(src_frontend, dst_frontend)
    else:
        os.environ.setdefault('LOCALNET_PORT', str(PORT))

    from server import app
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)


class LocalnetApp(App):
    def build(self):
        server_thread = threading.Thread(target=start_flask, daemon=True)
        server_thread.start()

        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.INTERNET])
            Clock.schedule_once(self._start_webview, 2.0)
        else:
            Clock.schedule_once(self._open_browser, 1.0)

        from kivy.uix.label import Label
        return Label(text='Localnet\nLoading...', halign='center',
                     font_size='24sp', color=(1, 1, 1, 1))

    def _start_webview(self, dt):
        """Android WebViewを起動"""
        from jnius import autoclass
        from android.runnable import run_on_ui_thread

        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        WebView = autoclass('android.webkit.WebView')
        WebViewClient = autoclass('android.webkit.WebViewClient')
        WebSettings = autoclass('android.webkit.WebSettings')
        LinearLayout = autoclass('android.widget.LinearLayout')
        LayoutParams = autoclass('android.widget.LinearLayout$LayoutParams')
        activity = PythonActivity.mActivity

        @run_on_ui_thread
        def create_webview():
            webview = WebView(activity)
            WebView.setWebContentsDebuggingEnabled(True)

            settings = webview.getSettings()
            settings.setJavaScriptEnabled(True)
            settings.setDomStorageEnabled(True)
            settings.setAllowFileAccess(True)
            settings.setDatabaseEnabled(True)
            webview.setWebViewClient(WebViewClient())

            layout = LinearLayout(activity)
            layout.setOrientation(LinearLayout.VERTICAL)
            layout.addView(webview, LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))

            activity.setContentView(layout)

            # サーバー起動待ち
            def load_when_ready(retry=0):
                if retry > 30:
                    return
                try:
                    import urllib.request
                    urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/version', timeout=1)
                    webview.loadUrl(f'http://127.0.0.1:{PORT}')
                except Exception:
                    from android.runnable import run_on_ui_thread
                    Clock.schedule_once(lambda dt: load_when_ready(retry + 1), 0.5)

            load_when_ready()

        create_webview()

    def _open_browser(self, dt):
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{PORT}')


if __name__ == '__main__':
    LocalnetApp().run()
