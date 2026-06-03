"""
HTTP Command Bridge for Packet Tracer.

Allows Python to send JavaScript commands to PT via PTBuilder extension.
Works by running a local HTTP server that the PTBuilder webview polls for commands.

Usage:
    1. Start the bridge: bridge = PTCommandBridge(); bridge.start()
    2. User pastes bootstrap() output in Builder Code Editor ONCE
    3. Send commands: bridge.send("addDevice('R1','2911',100,100)")
"""

import http.server
import threading
import time
import json
from http.server import ThreadingHTTPServer
from queue import Queue, Empty
from urllib.parse import urlparse, parse_qs


class PTCommandBridge:
    """HTTP bridge between Python and Packet Tracer's PTBuilder extension."""

    def __init__(self, port: int = 54321):
        self.port = port
        self._queue: Queue[str] = Queue()
        self._results: Queue[str] = Queue()
        self._server = None
        self._thread = None
        self._connected = False
        self._last_poll_time: float = 0.0

    def start(self):
        """Start the HTTP command server."""
        bridge = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/next":
                    try:
                        cmd = bridge._queue.get_nowait()
                    except Empty:
                        cmd = ""
                    self._respond(200, cmd)
                    bridge._connected = True
                    bridge._last_poll_time = time.time()
                elif self.path == "/ping":
                    self._respond(200, "pong")
                    bridge._connected = True
                elif self.path == "/status":
                    ago = time.time() - bridge._last_poll_time
                    connected = bridge._last_poll_time > 0 and ago < 5.0
                    self._respond(200, json.dumps({"connected": connected, "last_poll_ago": round(ago, 1)}))
                elif self.path == "/drain":
                    # Drain any orphaned/stale results so a caller can avoid
                    # popping a previous timed-out command's late result.
                    n = 0
                    while True:
                        try:
                            bridge._results.get_nowait()
                            n += 1
                        except Empty:
                            break
                    self._respond(200, json.dumps({"drained": n}))
                elif self.path.startswith("/result"):
                    # Long-poll: block until PT posts a result (or timeout). The
                    # caller may request a longer wait via ?timeout=N (capped),
                    # so operations slower than the old fixed 9s no longer falsely
                    # time out and orphan their result.
                    wait = 9.0
                    if "?" in self.path:
                        try:
                            q = parse_qs(urlparse(self.path).query)
                            wait = min(float(q.get("timeout", ["9"])[0]), 30.0)
                        except Exception:
                            wait = 9.0
                    try:
                        result = bridge._results.get(timeout=max(0.1, wait))
                        self._respond(200, result)
                    except Empty:
                        self._respond(204, "")
                elif self.path == "/ui":
                    # Diagnostic + bridge page. Tests $se availability and reports
                    # back via POST /result so we can read it from outside.
                    html = (
                        "<!DOCTYPE html><html><head><title>MCP Bridge</title></head><body>"
                        "<p id='s' style='font:11px sans-serif;color:#999;padding:4px'>MCP Bridge - testing...</p>"
                        "<script>"
                        f"var BASE='http://127.0.0.1:{bridge.port}';"
                        # Report $se availability immediately on load
                        "function report(msg){"
                        "var r=new XMLHttpRequest();"
                        "r.open('POST',BASE+'/result',true);"
                        "r.setRequestHeader('Content-Type','text/plain');"
                        "r.send(msg);"
                        "document.getElementById('s').textContent='MCP Bridge: '+msg;"
                        "}"
                        "try{"
                        "if(typeof $se==='function'){report('$se=OK');}"
                        "else{report('$se=MISSING (type:'+typeof $se+')');}}"
                        "catch(e){report('$se=ERROR:'+e);}"
                        # Main polling loop
                        "setInterval(function(){"
                        "var x=new XMLHttpRequest();"
                        "x.open('GET',BASE+'/next',true);"
                        "x.onload=function(){if(x.status===200&&x.responseText){"
                        "try{$se('runCode',x.responseText);}catch(e){report('runCode error:'+e);}"
                        "}};"
                        "x.onerror=function(){};"
                        "x.send();"
                        "},500);"
                        "</script>"
                        "</body></html>"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self._cors_headers()
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/se-test":
                    # Navigate PTBuilder's own webview here via window.webview.setUrl(...)
                    # Tests whether $se persists after navigation (C++ WebChannel registration).
                    html = (
                        "<!DOCTYPE html><html><body>"
                        "<p id='s' style='font:12px sans-serif;padding:8px'>Testing $se...</p>"
                        "<script>"
                        f"var BASE='http://127.0.0.1:{bridge.port}';"
                        "function post(msg){"
                        "  var r=new XMLHttpRequest();"
                        "  r.open('POST',BASE+'/result',true);"
                        "  r.setRequestHeader('Content-Type','text/plain');"
                        "  r.send(msg);"
                        "  document.getElementById('s').textContent=msg;"
                        "}"
                        "try{"
                        "  if(typeof $se==='function'){"
                        "    $se('runCode','addDevice(\"SE_TEST\",\"2911\",600,300)');"
                        "    post('$se=OK');"
                        "  } else {"
                        "    post('$se=MISSING:'+typeof $se);"
                        "  }"
                        "} catch(e){ post('$se=ERROR:'+e); }"
                        "setInterval(function(){"
                        "  var x=new XMLHttpRequest();"
                        "  x.open('GET',BASE+'/next',true);"
                        "  x.onload=function(){if(x.status===200&&x.responseText){"
                        "    try{$se('runCode',x.responseText);}catch(e){}"
                        "  }};"
                        "  x.onerror=function(){};"
                        "  x.send();"
                        "},500);"
                        "</script></body></html>"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self._cors_headers()
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                else:
                    self._respond(404, "")

            def do_POST(self):
                if self.path == "/result":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8") if length else ""
                    bridge._results.put(body)
                    self._respond(200, "ok")
                elif self.path == "/queue":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8") if length else ""
                    if body:
                        bridge._queue.put(body)
                    self._respond(200, "queued")
                else:
                    self._respond(404, "")

            def do_OPTIONS(self):
                self.send_response(200)
                self._cors_headers()
                self.end_headers()

            def _respond(self, code, body):
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def _cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def log_message(self, format, *args):
                pass  # Silence logs

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None

    @property
    def is_connected(self) -> bool:
        if self._last_poll_time == 0:
            return False
        return time.time() - self._last_poll_time < 5.0

    def send(self, js_code: str, timeout: float = 10.0) -> bool:
        """Queue a JavaScript command for execution in PT."""
        self._queue.put(js_code)
        return True

    def send_and_wait(self, js_code: str, timeout: float = 10.0) -> str | None:
        """Send a command and wait for result callback.

        Uses reportResult() from userfunctions.js which routes the HTTP
        POST through the QWebEngine webview (XMLHttpRequest is NOT available
        in the PT Script Engine, only in the webview).
        """
        wrapped = (
            f"try {{ var __r = (function(){{ {js_code} }})(); "
            f"reportResult(String(__r)); "
            f"}} catch(__e) {{ reportResult('ERROR:' + __e); }}"
        )
        self._queue.put(wrapped)
        try:
            return self._results.get(timeout=timeout)
        except Empty:
            return None

    def bootstrap_script(self) -> str:
        """
        Generate the one-time bootstrap JavaScript for Builder Code Editor.

        Uses webViewManager.createWebView to load the bridge UI from our local
        HTTP server. The new webview runs in QWebEngine (has XMLHttpRequest + $se)
        and works on macOS where window.webview.evaluateJavaScriptAsync does not.
        """
        return (
            f'/* PT-MCP Bridge - paste in Builder Code Editor and click Run */\n'
            f'webViewManager.createWebView("MCP Bridge","http://127.0.0.1:{self.port}/ui",220,60);\n'
        )


def generate_topology_js(
    devices: list[dict],
    links: list[dict],
    configs: list[dict] | None = None,
) -> str:
    """
    Generate JavaScript commands compatible with PTBuilder's userfunctions.js.

    devices: [{"name": "R1", "model": "2911", "x": 100, "y": 100}, ...]
    links: [{"dev1": "R1", "port1": "Gig0/0", "dev2": "S1", "port2": "Gig0/1", "type": "straight"}, ...]
    configs: [{"name": "R1", "commands": "hostname R1\\ninterface gig0/0\\n..."}, ...]
    """
    lines = []

    for d in devices:
        name = json.dumps(d["name"])
        model = json.dumps(d["model"])
        x = d.get("x", 100)
        y = d.get("y", 100)
        lines.append(f"addDevice({name}, {model}, {x}, {y});")

    for lnk in links:
        d1 = json.dumps(lnk["dev1"])
        p1 = json.dumps(lnk["port1"])
        d2 = json.dumps(lnk["dev2"])
        p2 = json.dumps(lnk["port2"])
        lt = json.dumps(lnk.get("type", "straight"))
        lines.append(f"addLink({d1}, {p1}, {d2}, {p2}, {lt});")

    if configs:
        for cfg in configs:
            name = json.dumps(cfg["name"])
            cmds = json.dumps(cfg["commands"])
            lines.append(f"configureIosDevice({name}, {cmds});")

    return "\n".join(lines)
