"""外に出す — **アカウント無しで開く1枚だけを、別のサーバから出す。**

teatime 本体（8777）は tailnet 専用のまま触らない。あれは録音を受け、
文字起こしも議事も全部置いてある。**公開していいのは、選んで置いた回だけ。**
ここは別プロセス・別ポート・読むだけで、`public/` の下しか見えない。

- 回ごとに推測しづらいトークンのフォルダを切る。一覧は出さない
- 置くのは4種類だけ（index.html / mp4 / poster.png / proto.html）。
  **文字起こしと議事は、置き場所にそもそも入らない**
- mp4 は Range を返す（iOS Safari はこれが無いと再生しない）

    .venv/bin/python -m teatime.publish out/<stem>     # 公開して URL を出す
    .venv/bin/python -m teatime.publish --serve 8780   # 読むだけのサーバ
"""
import http.server
import json
import pathlib
import re
import secrets
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
INDEX = PUB / ".index.json"
BASE = "https://mac-studio.taila649e1.ts.net:8443"

# **置けるものの一覧。** ここに無い拡張子は、公開フォルダに入る経路が無い
COPY = [("share.html", "index.html"), ("mp4", "{b}.mp4"),
        ("poster.png", "{b}.poster.png"), ("proto.html", "{b}.proto.html")]
CTYPE = {".html": "text/html; charset=utf-8", ".mp4": "video/mp4",
         ".png": "image/png"}


def _index():
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}


def publish(stem):
    """`<stem>.share.html` とその添え物を `public/<token>/` に置き、URL を返す。"""
    stem = pathlib.Path(stem)
    out, b = stem.parent, stem.name
    src = out / f"{b}.share.html"
    if not src.exists():
        raise FileNotFoundError(f"{src} がありません。先に teatime.share を通してください")

    idx = _index()
    token = idx.get(b) or secrets.token_urlsafe(9)
    dest = PUB / token
    dest.mkdir(parents=True, exist_ok=True)
    for suffix, name in COPY:
        f = out / f"{b}.{suffix}"
        if f.exists():
            shutil.copyfile(f, dest / name.format(b=b))

    idx[b] = token
    PUB.mkdir(exist_ok=True)
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"{BASE}/{token}/"


def unpublish(stem):
    b = pathlib.Path(stem).name
    idx = _index()
    token = idx.pop(b, None)
    if token:
        shutil.rmtree(PUB / token, ignore_errors=True)
        INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return token


class Reader(http.server.BaseHTTPRequestHandler):
    """**読むだけ。** POST も一覧も無い。public/ の外は解決した時点で捨てる。"""

    server_version = "teatime-public"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))

    def _text(self, code, body):
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._text(200, "teatime — 公開しているのは、渡した URL の回だけです。")
        rel = path.lstrip("/")
        if rel.endswith("/"):
            rel += "index.html"
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", rel):
            return self._text(404, "ありません")
        f = (PUB / rel).resolve()
        if f.suffix not in CTYPE or not f.is_file() or PUB.resolve() not in f.parents:
            return self._text(404, "ありません")
        self._send(f, CTYPE[f.suffix])

    def _send(self, f, ctype):
        """**Range を返す。** iOS Safari は mp4 を必ず Range で取りに来る。"""
        size = f.stat().st_size
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        head = [("Content-Type", ctype), ("Accept-Ranges", "bytes"),
                ("Referrer-Policy", "no-referrer"),
                ("X-Robots-Tag", "noindex, nofollow")]
        if not m:
            self.send_response(200)
            for k, v in head + [("Content-Length", str(size))]:
                self.send_header(k, v)
            self.end_headers()
            with f.open("rb") as fh:
                shutil.copyfileobj(fh, self.wfile)
            return
        a, b = m.group(1), m.group(2)
        start, end = ((max(0, size - int(b or 0)), size - 1) if a == ""
                      else (int(a), min(int(b), size - 1) if b else size - 1))
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        self.send_response(206)
        for k, v in head + [("Content-Range", f"bytes {start}-{end}/{size}"),
                            ("Content-Length", str(end - start + 1))]:
            self.send_header(k, v)
        self.end_headers()
        with f.open("rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(262144, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


def serve(port):
    PUB.mkdir(exist_ok=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Reader)
    print(f"public: http://127.0.0.1:{port}  ←  {BASE}")
    srv.serve_forever()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--serve"]:
        serve(int(args[1]) if len(args) > 1 else 8780)
    elif args[:1] == ["--remove"]:
        print(unpublish(args[1]) or "公開していません")
    else:
        print(publish(args[0]))
