"""スマホから使う口。**タップ → 録音 → 席を外す。**

    python3 -m teatime.server            # http://localhost:8777
    python3 -m teatime.server --tailnet  # tailnet に https で出す（Funnel は触らない）

**Funnel の向き先（443 → 8402 / yohaku）には一切触れない。** 別ポートで待つだけ。
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import ssl
import subprocess
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import archive

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
WEB = ROOT / "web"
JOBS = {}


STEPS = [
    ("transcribe", "文字起こし"),
    ("extract", "放棄点の抽出"),
    ("pitch", "投資家向け資料"),
    ("product", "プロダクト仕様"),
    ("project", "プロジェクト文書"),
    ("feedback", "参加者へのフィードバック"),
    ("assume", "仮置きを決める"),
    ("proto", "プロトタイプを作る"),
    ("uxcheck", "プロトタイプを試す"),
    ("render", "1枚にまとめる"),
]


# **振り返り（品評）の工程。** 本編とは別の山。戻ってきた人が置いていくものを取る。
REVIEW_STEPS = [
    ("rtranscribe", "品評の文字起こし"),
    ("rextract", "手放した価値と序列の反転"),
    ("rvideo", "振り返りの動画"),
]


class Cancelled(Exception):
    """「やっぱやめる」。走っている1歩は止められないので、**次の歩の手前で止まる。**"""


def _discard(audio):
    """その回の録音と途中の生成物を全部消す。**やめた回はアーカイブに残さない。**"""
    for f in OUT.glob(f"{audio.stem}.*"):
        f.unlink(missing_ok=True)


def _work(job_id, audio):
    """**進行を1歩ずつ外に出す。** 黙って動いているものは、止まっているのと見分けがつかない。"""
    from . import deliver, extract, model, prototype, render, transcribe
    model.reset_usage()  # **頭で数え直す。** 前の回の退避を次の回に引きずらない
    job = JOBS[job_id]
    steps = [{"key": k, "label": l, "state": "wait", "sec": 0} for k, l in STEPS]
    if os.environ.get("TEATIME_VIDEO") != "0":   # **既定で作る。** 切るのは TEATIME_VIDEO=0
        steps.append({"key": "video", "label": "解説動画", "state": "wait", "sec": 0})
    job["steps"] = steps
    clock = {"t": time.time()}

    def step(key):
        if job.get("cancel"):
            raise Cancelled()
        now = time.time()
        for s_ in steps:
            if s_["state"] == "run":
                s_["state"] = "done"
                s_["sec"] = int(now - clock["t"])
        for s_ in steps:
            if s_["key"] == key:
                s_["state"] = "run"
                clock["t"] = now
                job["state"] = key
                return

    def finish():
        now = time.time()
        for s_ in steps:
            if s_["state"] == "run":
                s_["state"] = "done"
                s_["sec"] = int(now - clock["t"])

    try:
        step("transcribe")
        text = transcribe.run(audio)
        (OUT / f"{audio.stem}.txt").write_text(text, encoding="utf-8")
        if len(text.strip()) < 80:
            raise ValueError("記録が短すぎます（話が拾えていません）")
        job["chars"] = len(text)

        step("extract")
        structured = extract.extract(text)
        (OUT / f"{audio.stem}.extract.json").write_text(
            json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
        m = structured["metrics"]
        job.update(abandonments=m["abandonments"], unverbalized=m["unverbalized"],
                   gaps=len(structured.get("gaps", [])),
                   topic=structured.get("topic", ""))

        docs = deliver.build(text, structured, on_step=step)
        for d in docs:
            (OUT / f'{audio.stem}.{d["key"]}.md').write_text(d["text"], encoding="utf-8")

        proto = prototype.build(text, structured, on_step=step)
        proto_name = f"{audio.stem}.proto.html"
        (OUT / proto_name).write_text(proto["html"], encoding="utf-8")
        proto["url"] = f"/out/{proto_name}"
        (OUT / f"{audio.stem}.assumptions.json").write_text(
            json.dumps(proto["assumptions"], ensure_ascii=False, indent=2), encoding="utf-8")

        step("render")
        page = render.render(f"{audio.stem} — お茶の間の仕事", audio.name,
                             model.label(), docs, structured, proto)
        (OUT / f"{audio.stem}.html").write_text(page, encoding="utf-8")

        mp4 = None
        if os.environ.get("TEATIME_VIDEO") != "0":
            step("video")
            # **動画で落ちても、できた資料は渡す。** ここだけ例外を飲む
            try:
                from . import narrate
                mp4 = f"/out/{narrate.build(OUT / audio.stem, structured, docs).name}"
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                for s_ in steps:
                    if s_["key"] == "video":
                        s_["state"] = "fail"

        if job.get("cancel"):
            raise Cancelled()
        finish()
        job.update(state="done", url=f"/out/{audio.stem}.html",
                   proto=proto["url"], video=mp4, stem=audio.stem,
                   assumptions=len(proto["assumptions"]))
    except Cancelled:
        _discard(audio)
        for s_ in steps:
            if s_["state"] in ("run", "wait"):
                s_["state"] = "cancel"
        job.update(state="cancelled")
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        for s_ in steps:
            if s_["state"] == "run":
                s_["state"] = "fail"
        job.update(state="error", error=f"{type(exc).__name__}: {exc}")


def _review_work(job_id, stem, audio):
    """**品評は本編と同じ画面に積む。** 別の数にしない（横串の1数値）。"""
    from . import model, review
    model.reset_usage()
    job = JOBS[job_id]
    steps = [{"key": k, "label": l, "state": "wait", "sec": 0} for k, l in REVIEW_STEPS]
    job["steps"] = steps
    clock = {"t": time.time()}

    def step(key):
        now = time.time()
        for s_ in steps:
            if s_["state"] == "run":
                s_["state"] = "done"
                s_["sec"] = int(now - clock["t"])
        for s_ in steps:
            if s_["key"] == key:
                s_["state"] = "run"
                clock["t"] = now
                job["state"] = key
                return

    try:
        r = review.run(OUT / stem, audio, on_step=step)
        now = time.time()
        for s_ in steps:
            if s_["state"] == "run":
                s_["state"] = "done"
                s_["sec"] = int(now - clock["t"])
        job.update(state="done", url=f"/out/{stem}.review.md", stem=stem,
                   video=f"/out/{r['mp4'].name}" if r["mp4"] else None,
                   verdicts=r["verdicts"], released=r["released"],
                   reversals=r["reversals"])
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        for s_ in steps:
            if s_["state"] == "run":
                s_["state"] = "fail"
        job.update(state="error", error=f"{type(exc).__name__}: {exc}")


def parse_multipart_file(body, content_type):
    """multipart から最初のファイル部だけ取る。**cgi は 3.13 で消えた。**

    凝ったことはしない（間違えたときに気づけないので）。
    返すのは (ファイル名, 中身) か (None, None)。
    """
    m = re.search(r"boundary=\"?([^\";]+)", content_type or "")
    if not m:
        return None, None
    sep = b"--" + m.group(1).encode()
    for part in body.split(sep):
        head, _, data = part.partition(b"\r\n\r\n")
        if b"filename=" not in head:
            continue
        fn = re.search(rb'filename="([^"]*)"', head)
        return (fn.group(1).decode() if fn else "rec.m4a"), data.rstrip(b"\r\n--")
    return None, None


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _send_file(self, f, ctype):
        """**スマホで動画を見るには Range が要る。**

        iOS Safari は mp4 を必ず Range で取りに来る。206 を返せない相手の動画は、
        全部まとめて送っても再生されない（黒いまま、あるいは再生ボタンが死ぬ）。
        ここが無いと「動画はできているのに、スマホでだけ見られない」になる。
        """
        size = f.stat().st_size
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if not m:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with f.open("rb") as fh:
                shutil.copyfileobj(fh, self.wfile)
            return
        a, b = m.group(1), m.group(2)
        if a == "":                      # bytes=-N → 末尾 N バイト
            start, end = max(0, size - int(b or 0)), size - 1
        else:
            start = int(a)
            end = min(int(b), size - 1) if b else size - 1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
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

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (WEB / "record.html").read_bytes(),
                              "text/html; charset=utf-8")
        if path in ("/archive", "/archive.html"):
            return self._send(200, archive.page(OUT), "text/html; charset=utf-8")
        if path == "/status":
            q = dict(p.split("=", 1) for p in self.path.split("?", 1)[-1].split("&") if "=" in p)
            return self._send(200, json.dumps(JOBS.get(q.get("id"), {"state": "unknown"})))
        if path.startswith("/out/"):
            f = OUT / path[5:]
            if f.exists() and f.parent == OUT:
                ctype = {".html": "text/html; charset=utf-8",
                         ".mp4": "video/mp4",
                         ".m4a": "audio/mp4",
                         ".json": "application/json; charset=utf-8"
                         }.get(f.suffix, "text/plain; charset=utf-8")
                return self._send_file(f, ctype)
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path == "/cancel":
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            job_id = json.loads(body or b"{}").get("id")
            job = JOBS.get(job_id)
            if not job:
                return self._send(404, json.dumps({"error": "その回はありません"}))
            if job.get("state") in ("done", "error"):  # 間に合わなかった。できた分を消す
                for f in OUT.glob(f"rec-{job_id}.*"):
                    f.unlink(missing_ok=True)
                job["state"] = "cancelled"
            elif job.get("state") != "cancelled":
                job["cancel"] = True
            return self._send(200, json.dumps({"state": job.get("state")}))
        path = self.path.split("?")[0]
        if path == "/review":
            q = dict(p.split("=", 1) for p in self.path.split("?", 1)[-1].split("&") if "=" in p)
            stem = re.sub(r"[^A-Za-z0-9_.-]", "", q.get("stem", ""))
            if not stem or not (OUT / f"{stem}.extract.json").exists():
                return self._send(404, json.dumps({"error": "その回がありません"}))
            filename, blob = parse_multipart_file(
                self.rfile.read(int(self.headers["Content-Length"])),
                self.headers["Content-Type"])
            if blob is None:
                return self._send(400, json.dumps({"error": "音声がありません"}))
            ext = pathlib.Path(filename or "rec.m4a").suffix or ".m4a"
            dest = OUT / f"{stem}.review{ext}"
            dest.write_bytes(blob)
            job_id = f"{stem}.review"
            JOBS[job_id] = {"state": "queued"}
            threading.Thread(target=_review_work, args=(job_id, stem, dest),
                             daemon=True).start()
            return self._send(200, json.dumps({"id": job_id, "file": dest.name}))
        if path != "/upload":
            return self._send(404, json.dumps({"error": "not found"}))
        filename, blob = parse_multipart_file(
            self.rfile.read(int(self.headers["Content-Length"])),
            self.headers["Content-Type"])
        if blob is None:
            return self._send(400, json.dumps({"error": "音声がありません"}))
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        ext = pathlib.Path(filename or "rec.m4a").suffix or ".m4a"
        OUT.mkdir(exist_ok=True)
        dest = OUT / f"rec-{stamp}{ext}"
        dest.write_bytes(blob)

        JOBS[stamp] = {"state": "queued"}
        threading.Thread(target=_work, args=(stamp, dest), daemon=True).start()
        self._send(200, json.dumps({"id": stamp, "file": dest.name}))

    def log_message(self, *a):  # 静かに
        pass


def tailnet_cert():
    """tailscale のドメイン証明書。**Funnel/Serve の設定は読むだけで変えない。**"""
    name = subprocess.run(["tailscale", "status", "--json"],
                          capture_output=True, text=True).stdout
    dns = json.loads(name)["Self"]["DNSName"].rstrip(".")
    d = ROOT / ".certs"
    d.mkdir(exist_ok=True)
    crt, key = d / f"{dns}.crt", d / f"{dns}.key"
    if not crt.exists():
        subprocess.run(["tailscale", "cert", "--cert-file", str(crt),
                        "--key-file", str(key), dns], check=True)
    return dns, crt, key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--tailnet", action="store_true",
                    help="tailnet に https で出す（スマホのマイクに必要）")
    a = ap.parse_args()

    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    if a.tailnet:
        dns, crt, key = tailnet_cert()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        print(f"https://{dns}:{a.port}/  ← スマホでこれを開く")
    else:
        print(f"http://localhost:{a.port}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
