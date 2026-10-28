"""モデルの呼び出し口。**宛先を直書きしない。**

既定は Claude CLI（抽出に推論の質が要るため）。
**私的な対話は `TEATIME_BACKEND=ollama` で裏方の Qwen に落とす。**
切替点はこの1ファイルだけ。
"""
import json
import os
import pathlib
import subprocess
import urllib.request

BACKEND = os.environ.get("TEATIME_BACKEND", "claude")

OLLAMA_CANDIDATES = [
    os.environ.get("TEATIME_OLLAMA"),
    "http://10.10.10.2:11434",   # 裏方
    "http://127.0.0.1:11434",    # 母艦（退避先）
]
OLLAMA_MODEL = os.environ.get("TEATIME_OLLAMA_MODEL", "qwen2.5:32b")
NUM_PREDICT = int(os.environ.get("TEATIME_NUM_PREDICT", "8000"))

_endpoint = None


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


def _ask_ollama(system, user, timeout=900):
    body = {
        "model": OLLAMA_MODEL,
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


def ask(system, user, timeout=900):
    """1往復。返るのは本文の文字列。"""
    if BACKEND == "ollama":
        return _ask_ollama(system, user, timeout)
    return _ask_claude(system, user, timeout)


def ask_json(system, user, timeout=900):
    """JSON だけを期待する呼び出し。コードフェンスと前置きを剥がす。"""
    raw = ask(system + "\n出力は JSON のみ。前置き・後書き・コードフェンスを書かない。",
              user, timeout)
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("JSON が見つかりません: " + raw[:300])
    return json.loads(t[i:j + 1])


def label():
    return "claude-cli" if BACKEND != "ollama" else f"{OLLAMA_MODEL}@{_ollama_endpoint()}"
