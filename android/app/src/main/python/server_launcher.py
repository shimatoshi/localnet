"""APK内でFlaskサーバーを起動するランチャー"""

import os
import sys
import threading


def start_server(app_dir, port):
    """バックグラウンドスレッドでFlaskサーバーを起動"""
    # パス設定
    os.environ['LOCALNET_BASE'] = app_dir
    os.environ['LOCALNET_PORT'] = str(port)

    # Pythonモジュールパスに追加
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    def _run():
        from localnet_server import create_app
        app = create_app(app_dir, port)
        app.run(host='127.0.0.1', port=port, debug=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
