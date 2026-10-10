#!/usr/bin/env python3
"""Independent synthetic parity and headless page checks, run concurrently."""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import html
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "engine"))
from sig_extract import extract


def chrome():
    candidates = [os.environ.get("CHROME", ""), shutil.which("google-chrome"),
                  shutil.which("chromium"), shutil.which("chromium-browser"),
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for path in candidates:
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return path
    raise RuntimeError("Install Chrome/Chromium or set CHROME to its executable")


def probe(url, marker, profile):
    command = [chrome(), "--headless", "--disable-gpu", "--no-first-run",
               "--no-default-browser-check", "--disable-background-networking",
               f"--user-data-dir={profile}", "--virtual-time-budget=15000", "--dump-dom", url]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if completed.returncode:
        raise RuntimeError(f"Chrome exited {completed.returncode}")
    match = re.search(r'<pre id="'+marker+r'">(.*?)</pre>', completed.stdout, re.S)
    if not match:
        raise AssertionError(f"Missing browser result {marker}")
    result = json.loads(html.unescape(match[1]))
    if isinstance(result, dict) and result.get("error"):
        raise AssertionError(result["error"])
    return result


def ui_probe(url, server, profile):
    # IndexedDB uses real asynchronous callbacks. Run this page on a real clock
    # and collect its own loopback test result instead of advancing virtual time.
    command = [chrome(), "--headless", "--disable-gpu", "--no-first-run",
               "--no-default-browser-check", "--disable-background-networking",
               f"--user-data-dir={profile}", url]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        if not server.ui_ready.wait(timeout=45):
            raise AssertionError("Timed out waiting for the page's IndexedDB/UI result")
        result = server.ui_result
        if result.get("error"):
            raise AssertionError(result["error"])
        return result
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()


def parity(origin, scratch):
    js = {item["name"]: item for item in probe(
        origin+"/test/test-harness.html", "r", scratch/"parity-profile")}
    cases = [("sig-a", "sig-a.png", False), ("sig-a-deline", "sig-a.png", True),
             ("sig-b", "sig-b.png", False), ("sig-b-deline-noop", "sig-b.png", True)]
    def one(case):
        name, filename, deline = case
        py = extract(ROOT/"test/fixtures"/filename, scratch/f"{name}.png", deline=deline)
        j = js[name]
        assert not j.get("error"), j
        assert abs(j["thr"]-py["thr"]) <= 3, (name, "threshold", j, py)
        assert abs(j["ratio"]-py["ratio"]*100) <= .6, (name, "ratio", j, py)
        if deline:
            assert abs(j["delineDelta"]-py["deline_delta"]) <= .006
            if filename == "sig-a.png":
                assert j["delineDelta"] > .0005 and py["deline_delta"] > .0005
            else:
                assert abs(j["delineDelta"]) <= .0005 and abs(py["deline_delta"]) <= .0005
        return {"name":name,"python_threshold":py["thr"],"js_threshold":j["thr"],
                "python_ratio_percent":py["ratio"]*100,"js_ratio_percent":j["ratio"],
                "python_deline_delta":py["deline_delta"],"js_deline_delta":j["delineDelta"]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, cases))
    print("[PASS] numerical parity: 4 synthetic cases; rule removal and no-op checked")
    return results


def ui(origin, scratch, relative, server):
    encoded = base64.b64encode((ROOT/"test/fixtures/sig-a.png").read_bytes()).decode()
    injection = r'''<script>(async()=>{
const p=document.createElement('pre');p.id='e2e';
document.body.appendChild(p);
const stage=value=>{p.textContent=JSON.stringify({stage:value});};
try {
stage('loadFiles');
const bytes=Uint8Array.from(atob('__IMAGE__'),c=>c.charCodeAt(0));
await loadFiles([new File([bytes],'fictional.png',{type:'image/png'})]);
const card=document.querySelector('.card');
const result=card?._result;
if(!result) throw new Error('No extracted result');
stage('png300');
const png=await png300(result.canvas);
const raw=new Uint8Array(await png.arrayBuffer());
const view=new DataView(raw.buffer);
const ppm=view.getUint32(41),unit=raw[49];
stage('libAdd');
await libAdd({name:'fictional-test',blob:png,w:result.canvas.width,
  h:result.canvas.height,cm:result.cm,ts:0});
stage('renderLib');
await renderLib();
const stored=await libAll();
const network=performance.getEntriesByType('resource').map(x=>new URL(x.name).origin);
p.textContent=JSON.stringify({cards:document.querySelectorAll('.card').length,
  images:document.querySelectorAll('.pv img').length,
  buttons:document.querySelectorAll('.card-ft button').length,
  png:[...document.querySelectorAll('.pv img')].every(x=>x.src.startsWith('data:image/png')),
  save:!!document.querySelector('[data-save]'),
  localLibrary:!!document.querySelector('#libGrid')&&stored.length===1,
  privateLink:!!document.querySelector('a[href*="library.html"]'),
  dpi300:ppm===11811&&unit===1,
  localResourcesOnly:network.every(x=>x===location.origin)});
await libClear();
}catch(error){p.textContent=JSON.stringify({error:String(error.stack||error)});}
await fetch('/__verify_result',{method:'POST',body:p.textContent});
})();</script>'''.replace("__IMAGE__", encoded)
    page = (ROOT/"web/index.html").read_text()
    target = scratch/"page.html"
    # The test page lives in scratch; use a base URL to load the production core.
    page = page.replace("<head>", '<head><base href="'+origin+'/web/">', 1)
    target.write_text(page.replace("</body>", injection+"</body>"))
    r = ui_probe(origin+"/"+relative+"/page.html", server, scratch/"ui-profile")
    for key, value in {"cards":1,"images":2,"buttons":4,"png":True,"save":True,
                       "localLibrary":True,"privateLink":False,"dpi300":True,
                       "localResourcesOnly":True}.items():
        assert r.get(key) == value, (key,r)
    print("[PASS] page UI: loadFiles → render → PNG/300dpi → local IndexedDB; no private link")
    return r


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT),**kwargs)
    def log_message(self,*args):
        pass
    def do_POST(self):
        if self.path != "/__verify_result":
            self.send_error(404); return
        self.server.ui_result = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        self.server.ui_ready.set()
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")


def main(only="all"):
    with tempfile.TemporaryDirectory(prefix=".verify-", dir=ROOT) as temporary:
        scratch = Path(temporary)
        server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
        server.ui_ready = threading.Event()
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = {}
                if only in ("all", "parity"):
                    pending["parity"] = pool.submit(parity,origin,scratch)
                if only in ("all", "ui"):
                    pending["ui"] = pool.submit(ui,origin,scratch,scratch.name,server)
                results = {name:future.result() for name,future in pending.items()}
            print(json.dumps(results,ensure_ascii=False))
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("all", "parity", "ui"), default="all")
    main(parser.parse_args().only)
