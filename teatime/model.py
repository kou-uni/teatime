"""モデルの呼び出し口。**宛先を直書きしない。**

**行き先は役で決める。** 頭を使う工程（抽出・4文書・仮置き）は Claude CLI、
言われたとおりに作る工程（HTML / JS）はローカルの Qwen。
**私的な対話は `TEATIME_BACKEND=ollama` で全部を裏方に落とす。**
切替点はこの1ファイルだけ。
"""
import json
import os
import pathlib
import subprocess
import threading
import urllib.request

BACKEND = os.environ.get("TEATIME_BACKEND", "claude")
CODE_BACKEND = os.environ.get("TEATIME_CODE_BACKEND", "ollama")

OLLAMA_CANDIDATES = [
    os.environ.get("TEATIME_OLLAMA"),
    "http://10.10.10.2:11434",   # 裏方
    "http://127.0.0.1:11434",    # 母艦（退避先）
]
OLLAMA_MODEL = os.environ.get("TEATIME_OLLAMA_MODEL", "qwen2.5:32b")
CODE_MODEL = os.environ.get("TEATIME_CODE_MODEL", "qwen2.5-coder:32b")
NUM_PREDICT = int(os.environ.get("TEATIME_NUM_PREDICT", "8000"))

_endpoint = None

# **黙って退避しない。** 実際にどこへ出したかをスレッドごとに積む（処理の頭で reset_usage）。
_usage = threading.local()


def route(role="think"):
    """**行き先を決めるのはここ1か所。** 考える工程は Claude、作る工程はローカル。"""
    if BACKEND == "ollama":  # 私的な議論用。何より先に効かせる
        return "ollama"
    if role == "check":  # **検査は外へ逃がさない。**
        return "ollama"
    if role == "code" and CODE_BACKEND != "claude":
        return "ollama"
    return "claude"


def _model_for(role):
    return CODE_MODEL if role == "code" else OLLAMA_MODEL


def reset_usage():
    """1回の処理の頭で数え直す。**前の回の退避を次の回に引きずらない。**"""
    _usage.log = []


def _record(role, backend, model, fallback=False):
    if not hasattr(_usage, "log"):
        _usage.log = []
    _usage.log.append({"role": role, "backend": backend,
                       "model": model, "fallback": fallback})


def _ollama_endpoint(timeout=8):
    global _endpoint
    if _endpoint:
        return _endpoint
    tried = []
    for ep in [c for c in OLLAMA_CANDIDATES if c]:
        try:
            with urllib.request.urlopen(f"{ep}/api/tags", timeout=timeout) as r:
                json.load(r)
            _endpoint = ep
            return ep
        except Exception as e:  # noqa: BLE001
            tried.append(f"{ep} ({type(e).__name__})")
    raise RuntimeError("Ollama の宛先が見つかりません: " + ", ".join(tried))


def _ask_ollama(system, user, timeout=900, model=None):
    body = {
        "model": model or OLLAMA_MODEL,
        "stream": False,
        "options": {"num_predict": NUM_PREDICT, "temperature": 0.3},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{_ollama_endpoint()}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["message"]["content"]


# **道具を取り上げる。** 既定の claude は Code のエージェントなので、
# 長い HTML を頼むと「ファイルに書こうとして、書けないと報告する」側に回る
# （2026-10-28、プロトタイプが 436 バイトの弁明文になった）。
NO_TOOLS = ["--disallowedTools", "Bash", "Read", "Write", "Edit", "Glob",
            "Grep", "WebFetch", "WebSearch", "TodoWrite", "Task"]

# **呼ぶ側のフックを子に継がせない。** 母艦の Stop フック（返答の長さの番人）が
# 子プロセスにも効いて、長い HTML が「長すぎます」の弁明文に化けた（2026-10-28）。
SETTINGS = str(pathlib.Path(__file__).resolve().parent.parent / ".claude-settings.json")


def _ask_claude(system, user, timeout=900):
    # プロンプトは stdin で渡す（--disallowedTools が可変長で引数を飲み込む）
    out = subprocess.run(
        ["claude", "-p", "--settings", SETTINGS, "--system-prompt", system] + NO_TOOLS,
        input=user, capture_output=True, text=True, timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError(f"claude CLI 失敗 rc={out.returncode}: {out.stderr[:400]}")
    return out.stdout.strip()


def ask(system, user, timeout=900, role="think"):
    """1往復。返るのは本文の文字列。**role で行き先が変わる（既定は think）。**"""
    if route(role) == "ollama":
        m = _model_for(role)
        try:
            out = _ask_ollama(system, user, timeout, m)
            _record(role, "ollama", m)
            return out
        except Exception:  # noqa: BLE001
            # **作る工程だけ逃がす。** ローカルが落ちても仕事は止めない。ただし記録に残す
            # **私的モードでは逃がさない。** 逃がした先が外の Claude になり、議論が手元から出る
            if role != "code" or BACKEND == "ollama":
                raise
            out = _ask_claude(system, user, timeout)
            _record(role, "claude", "claude-cli", fallback=True)
            return out
    out = _ask_claude(system, user, timeout)
    _record(role, "claude", "claude-cli")
    return out


def ask_json(system, user, timeout=900, role="think"):
    """JSON だけを期待する呼び出し。コードフェンスと前置きを剥がす。"""
    raw = ask(system + "\n出力は JSON のみ。前置き・後書き・コードフェンスを書かない。",
              user, timeout, role)
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("JSON が見つかりません: " + raw[:300])
    return json.loads(t[i:j + 1])


def _label_one(role, backend, model, fallback=False):
    # **未知の役で落とさない。** think 以外の従来表示も残す
    head = {"think": "考える: ", "check": "確かめる: "}.get(role, "作る: ")
    name = "claude-cli" if backend == "claude" else model
    return head + name + ("（退避あり）" if fallback else "")


def label():
    """**実際に使ったもの**を返す。退避したなら、そう書く。"""
    log = getattr(_usage, "log", [])
    parts = []
    roles = ("think", "code")
    if any(r["role"] == "check" for r in log):  # **呼んだときだけ出す。**
        roles += ("check",)
    for role in roles:
        rec = next((r for r in reversed(log) if r["role"] == role), None)
        if rec:
            parts.append(_label_one(role, rec["backend"], rec["model"], rec["fallback"]))
        else:  # まだ呼んでいない役は設定から組み立てる
            parts.append(_label_one(role, route(role), _model_for(role)))
    return " / ".join(parts)

