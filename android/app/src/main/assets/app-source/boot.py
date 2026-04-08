import sys, os, traceback

log_path = os.path.join(os.environ.get('LOCALNET_BASE', '.'), 'python_out.txt')
LOG = open(log_path, 'w')

try:
    print('boot.py starting...', file=LOG, flush=True)

    base = os.environ.get('LOCALNET_BASE', os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)

    print('importing server...', file=LOG, flush=True)
    from server import app
    from config import PORT
    print(f'starting Flask on port {PORT}...', file=LOG, flush=True)
    LOG.flush()

    app.run(host='127.0.0.1', port=PORT, debug=False, threaded=True)

    # ここに来たらサーバーが正常終了した
    print('Flask server stopped normally', file=LOG, flush=True)
except SystemExit as e:
    print(f'SystemExit: {e}', file=LOG, flush=True)
    traceback.print_exc(file=LOG)
except Exception as e:
    print(f'Exception: {e}', file=LOG, flush=True)
    traceback.print_exc(file=LOG)
finally:
    LOG.close()
