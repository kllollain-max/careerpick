"""Isolated CI preview. An optional flag simulates a temporary 503, not deleted files."""
import argparse
import functools
import json
from urllib.parse import urlsplit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("port", type=int)
parser.add_argument("directory")
args = parser.parse_args()
root = Path(args.directory).resolve()

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if (root / ".cp-audit-outage").exists():
            body = b"Synthetic temporary network outage"
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        version = root / ".cp-worker-version"
        if urlsplit(self.path).path.endswith("/careerpick/sw.js") and version.exists():
            marker = version.read_text().strip()
            original = (root / "careerpick" / "sw.js").read_text()
            body = (original + '\nself.addEventListener("message",e=>{if(e.data==="CP_RECORDS_AUDIT")e.source.postMessage(' + json.dumps(marker) + ');});\n').encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

ThreadingHTTPServer.request_queue_size = 128
ThreadingHTTPServer(("127.0.0.1", args.port), functools.partial(Handler, directory=str(root))).serve_forever()
