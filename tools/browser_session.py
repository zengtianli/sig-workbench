"""Run the real Web workbench in an explicitly owned, hidden agent profile."""
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ('index.html', 'sig-core.js', 'sig-product.js', 'sig-product-ui.js', 'version.json')


def run(action, profile, *, script=None, timeout=35):
    profile = Path(profile).resolve()
    marker = profile / 'sig-agent-profile.json'
    if profile.exists() and any(profile.iterdir()) and not marker.is_file():
        raise ValueError('Refusing an existing non-Sig browser profile')
    profile.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.write_text(json.dumps({'product': 'sig', 'schema_version': 1}))
    if json.loads(marker.read_text()) != {'product': 'sig', 'schema_version': 1}:
        raise ValueError('Invalid Sig agent profile identity')
    lock = (profile / 'agent.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close(); raise RuntimeError('This Sig profile is already in use')
    # A stable origin preserves the actual IndexedDB/localStorage across CLI processes.
    port = 23000 + int(hashlib.sha256(str(profile).encode()).hexdigest()[:6], 16) % 16000
    origin = f'http://127.0.0.1:{port}'
    payload = json.dumps(action, ensure_ascii=True).replace('<', '\\u003c')
    program = script or (ROOT / 'tools/workspace_actions.js').read_text()
    program = program.replace('__SIG_REQUEST__', payload)
    done = threading.Event()
    result = {}
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            name = self.path.split('?', 1)[0].lstrip('/') or 'index.html'
            requests.append({'method': 'GET', 'path': self.path})
            if name not in ASSETS:
                self.send_error(404); return
            body = (ROOT / 'web' / name).read_bytes()
            if name == 'index.html':
                body = body.replace(b'</body>', ('<script>' + program + '</script></body>').encode())
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if name.endswith('.html') else 'application/json' if name.endswith('.json') else 'text/javascript')
            self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            if self.path != '/__sig_result':
                self.send_error(404); return
            result.update(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok'); done.set()
    server = None
    process = None
    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        chrome = os.environ.get('CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                                    '--disable-background-networking', '--user-data-dir=' + str(profile / 'chrome'), origin + '/'],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        if not done.wait(timeout): raise TimeoutError('Sig workspace did not return a result')
        result['requests'] = requests
        return result
    finally:
        if process:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
        if server:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        lock.close()
