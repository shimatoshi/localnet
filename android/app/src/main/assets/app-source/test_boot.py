import sys
import os

print('Python boot OK', file=sys.stderr)
print(f'Python version: {sys.version}', file=sys.stderr)
print(f'sys.path: {sys.path}', file=sys.stderr)
print(f'PYTHONHOME: {os.environ.get("PYTHONHOME", "NOT SET")}', file=sys.stderr)
print(f'PYTHONPATH: {os.environ.get("PYTHONPATH", "NOT SET")}', file=sys.stderr)

try:
    import flask
    print(f'Flask imported OK: {flask.__version__}', file=sys.stderr)
except Exception as e:
    print(f'Flask import FAILED: {e}', file=sys.stderr)

try:
    from curl_cffi import requests
    print('curl_cffi imported OK', file=sys.stderr)
except Exception as e:
    print(f'curl_cffi import FAILED: {e}', file=sys.stderr)

print('All imports done, starting server...', file=sys.stderr)
from server import app
app.run(host='127.0.0.1', port=8789, debug=False, threaded=True)
