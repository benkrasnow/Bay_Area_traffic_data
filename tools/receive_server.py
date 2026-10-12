"""Tiny localhost-only receiver: the browser page POSTs a downloaded PeMS file here and it is saved
into the project folder.  Only accepts names like d04_text_station_5min_YYYY_MM_DD.txt.gz.

    python tools/receive_server.py        # listens on 127.0.0.1:8765
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

DEST = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
NAME = re.compile(r"^d04_text_station_(5min|hour)_\d{4}_\d{2}(_\d{2})?\.txt\.gz$")


def pending():
    """Extra-lean files of sampling_plan.csv not yet on disk: [[ [year, month0, filename], ...backups ], ...]"""
    import csv
    items = []
    with open(os.path.join(DEST, "sampling_plan.csv"), newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("xlean") == "1"]
    for r in sorted(rows, key=lambda r: r["date"]):
        if os.path.exists(os.path.join(DEST, r["filename"])):
            continue
        names = [r["filename"]] + ["d04_text_station_5min_%s.txt.gz" % r[b].replace("-", "_") for b in ("backup1", "backup2") if r[b]]
        items.append([[int(x[22:26]), int(x[27:29]) - 1, x] for x in names])
    return items


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        body = b"ok"
        if self.path.startswith("/queue"):
            body = json.dumps(pending()).encode()
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("name") or [""])[0]
        if not NAME.match(name):
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(b"bad name")
            return
        n = int(self.headers.get("Content-Length", 0))
        tmp = os.path.join(DEST, name + ".part")
        got = 0
        with open(tmp, "wb") as f:
            while got < n:
                chunk = self.rfile.read(min(1 << 20, n - got))
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
        if got != n:
            os.remove(tmp)
            self.send_response(400)
            self._cors()
            self.end_headers()
            return
        os.replace(tmp, os.path.join(DEST, name))
        print("saved", name, got, flush=True)
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(str(got).encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("saving into", DEST, flush=True)
    HTTPServer(("127.0.0.1", 8765), H).serve_forever()
