"""5つ目の成果物 — **動くプロトタイプそのもの。**

仕様書ではなく、ブラウザで開けば動く1枚の HTML を出す。

**ここだけ「空白を埋めない」規則を外す。**
文書（pitch/product/project/feedback）は議論に無いことを埋めない。
**作るものは、埋めないと存在できない。** だから仮置きして前に進み、
**どこを仮置きしたかをプロトタイプ自身が表示する。**

## 作り方（2026-10-28 に変更）
以前は「1枚の HTML を丸ごと LLM に書かせる」ことにしていたが、
**長い出力は応答側の長さガードに引っかかって返ってこない。**
いまは **枠（doctype/CSS/ヘッダ/仮置きシート）を Python が決め打ちし、
LLM には中身だけを短く2回に分けて書かせる。**
仮置きの表示が LLM の気分で消えないのも、この分け方の利点。
"""
import html as _h
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

from . import model

ASSUME_SYS = (
    "あなたは、議論の記録と抽出結果を渡されて、**作り始めるために必要な仮置き**を決める人です。"
    "議論で決まっていないことを、**決めたことにしない。** "
    "『いまは仮にこうしておく』を、理由つきで置くのが仕事です。出力は JSON のみ。"
)

ASSUME_PROMPT = """次の議論から**プロトタイプを1本作る**ために、
決まっていないことへ**仮置き**を置いてください。

規則
- **採った案と成り立つ条件は動かさない。** 仮置きはその外側だけ
- 仮置きは**最大7つ**。多く置かない。置くほど、確かめる相手が減ります
- 各仮置きに `risk` を付ける: `high` = これが外れると作り直し / `low` = 後から変えられる
- **議論で既に決まっていることを仮置きに入れない**

出力:
{{"mvp":"プロトタイプで実際に動かす一本（1文）",
"assumptions":[{{"gap":"決まっていないこと","assumption":"仮にこうする",
"why":"そう置いた理由","risk":"high|low","how_to_check":"これを確かめる一番安い方法"}}]}}

---
{core}
"""

# --- 1回目: 画面の中身（マークアップだけ） ---------------------------------

MARKUP_SYS = (
    "あなたは、動くプロトタイプの**画面の中身だけ**を書く実装者です。\n"
    "- 出力は `<main>` の中に入る HTML 断片のみ。"
    "doctype・html・head・style・script は**書かない**（別で用意されます）。\n"
    "- class は `card` `row` `col` `btn` `btn2` `mut` `tag` `big` `field` だけ使う。"
    "自前の style 属性は最小限。\n"
    "- **読むだけの画面にしない。** 入力欄・ボタン・一覧など、指で触れるものを置く。\n"
    "- 空の画面は出さない。ただし**例の行は2件まで**。行の頭に `<span class=\"tag\">例</span>` を付け、"
    "議論の記録か仮置きに出てくる言葉だけで書く（作り話を本物に見せない）。\n"
    "- **議論で後回しにしたもの（次回やると決めたこと）は、画面に出さない。**\n"
    "- `<main>` タグ自体は書かない（中身だけ）。\n"
    "- 操作に必要な要素には `id` を付ける（JS から触ります）。\n"
    "- 絵文字を使わない。日本語。\n"
    "- **2500字以内。** 前置き・後書き・コードフェンスを書かない。"
)

MARKUP_PROMPT = """## 作るもの
{mvp}

## 守ること（議論で決まっている。動かさない）
- 採った案: {adopted}
- 成り立つ条件: {condition}
- 手放した価値: {sacrificed}
  → **手放したものを作り足さないこと。** これを守るのが、この画面の仕事です

## 仮置き（議論では決まっていない前提。これに沿って作る）
{assumptions}

## 議論の記録（抜粋）
{transcript}

---
`<main>` の中身を 2500字以内で出してください。
"""

# --- 2回目: 動き（JS だけ） ------------------------------------------------

JS_SYS = (
    "あなたは、与えられた HTML を**実際に動かす JavaScript だけ**を書く実装者です。\n"
    "- 出力は素の JS のみ。`<script>` タグもコードフェンスも書かない。\n"
    "- 外部ライブラリを使わない。保存が要るなら localStorage。\n"
    "- 渡された HTML に**実在する id/class だけ**を触る。無いものを作らない。\n"
    "- 主要な操作が1つでも実際に効くこと（増える・消える・絞られる・計算される）。\n"
    "- **押したら必ず目に見えて何か変わる。** 空のまま押されたら、その場で一言出す。\n"
    "- 日付の既定値は今日。\n"
    "- **2000字以内。** 説明文を書かない。"
)

JS_PROMPT = """この画面を動かしてください。作っているもの: {mvp}

```html
{markup}
```

---
JS だけを 2000字以内で。
"""

JS_FIX_PROMPT = """
前回の JS は構文エラーで動きませんでした。**エラーを直した JS 全体**を、もう一度出してください。
{err}
"""

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1b17;--mut:#6d675d;--line:#e2ddd2;--ac:#8a6a3b;--card:#fff}
@media(prefers-color-scheme:dark){:root{
--bg:#16150f;--fg:#ece7dc;--mut:#9d968a;--line:#322e26;--ac:#c9a46a;--card:#1e1c15}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-size:16px;line-height:1.7;
font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:560px;margin:0 auto;padding:14px 14px 110px}
header{max-width:560px;margin:0 auto;padding:16px 14px 6px;color:var(--mut);font-size:11.5px;
letter-spacing:.1em}
h1{font-size:20px;margin:.2em 0 .5em}h2{font-size:16px;margin:1.2em 0 .4em}
h3{font-size:14px;margin:1em 0 .3em;color:var(--ac)}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:14px 16px;margin:12px 0}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.col{display:flex;flex-direction:column;gap:6px}
.mut{color:var(--mut);font-size:13px}.big{font-size:26px;font-weight:650}
.tag{display:inline-block;font-size:11px;letter-spacing:.1em;color:var(--ac);
border:1px solid var(--line);border-radius:2px;padding:2px 7px}
input,textarea,select,.field{font:inherit;color:var(--fg);background:var(--bg);
border:1px solid var(--line);border-radius:5px;padding:9px 11px;width:100%}
button,.btn{font:inherit;background:var(--fg);color:var(--bg);border:0;border-radius:5px;
padding:10px 16px;cursor:pointer}
.btn2{background:transparent;color:var(--fg);border:1px solid var(--line)}
ul{padding-left:1.1em}li{margin:.3em 0}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
#fab{position:fixed;right:14px;bottom:18px;z-index:9;background:var(--ac);color:#fff;
border-radius:999px;padding:12px 18px;font-size:13.5px;border:0;
box-shadow:0 2px 10px rgba(0,0,0,.18);cursor:pointer}
#sheet{position:fixed;inset:0;z-index:10;background:rgba(0,0,0,.35);display:none}
#sheet.on{display:block}
#sheet>div{position:absolute;left:0;right:0;bottom:0;max-height:86vh;overflow:auto;
background:var(--bg);border-top:1px solid var(--line);
border-radius:14px 14px 0 0;padding:18px 16px 28px}
#sheet h2{margin:0 0 4px}
.as{border-top:1px solid var(--line);padding:11px 0}
.as b{font-weight:650}.as .why{color:var(--mut);font-size:13px}
.hi{color:#b3261e}@media(prefers-color-scheme:dark){.hi{color:#f2b8b5}}
"""

SHEET_JS = """
document.getElementById('fab').onclick=()=>document.getElementById('sheet').classList.add('on');
document.getElementById('sheet').onclick=e=>{if(e.target.id==='sheet'||e.target.id==='sclose')
document.getElementById('sheet').classList.remove('on')};
"""


def _sheet(assumptions):
    rows = []
    for a in assumptions:
        hi = (a.get("risk") == "high")
        rows.append(
            '<div class="as">'
            f'<b>{"<span class=hi>⚑ </span>" if hi else ""}'
            f'{_h.escape(str(a.get("gap", "")))}</b>'
            f'<div>→ {_h.escape(str(a.get("assumption", "")))}</div>'
            f'<div class="why">なぜ: {_h.escape(str(a.get("why", "")))}'
            f'<br>確かめ方: {_h.escape(str(a.get("how_to_check", "")))}</div></div>')
    n = len(assumptions)
    return (
        f'<button id="fab">仮置き {n}</button>'
        '<div id="sheet"><div><h2>仮置き</h2>'
        '<p class="mut">議論で決まっていないこと。作るために、いまは仮にこうしてあります。'
        '<span class="hi">⚑</span> は外れると作り直しになるもの。</p>'
        + "".join(rows)
        + '<p style="margin-top:18px"><button id="sclose" class="btn2">閉じる</button></p>'
          '</div></div>')


def _clean(text, drop_tags=True):
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t).rsplit("```", 1)[0]
    if drop_tags:
        t = re.sub(r"</?(?:script|style)[^>]*>", "", t)
    return t.strip()


def _node():
    """node の居場所。**PATH に無くても、よくある置き場だけは見る。**"""
    for p in (shutil.which("node"), "~/.local/bin/node",
              "/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if p:
            path = pathlib.Path(p).expanduser()
            if path.exists():
                return str(path)
    return None


def _js_check(js):
    """構文だけは機械に見させる。返すのは (状態, エラー文)。"""
    node = _node()
    if not node:
        return "skipped", ""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(js)
        path = pathlib.Path(f.name)
    try:
        out = subprocess.run([node, "--check", str(path)],
                             capture_output=True, text=True, timeout=60)
    finally:
        path.unlink(missing_ok=True)
    if out.returncode == 0:
        return "ok", ""
    return "ng", (out.stderr or out.stdout).strip()[:800]


def build(transcript, structured, on_step=None):
    d = structured.get("decision") or {}
    sacrificed = "、".join(
        f'{a.get("sacrificed_value") or "?"}→{a.get("gained_value") or "?"}'
        for a in structured.get("abandonments", [])) or "（放棄は記録されていない）"
    core = json.dumps({"structured": structured, "transcript": transcript},
                      ensure_ascii=False)

    if on_step:
        on_step("assume")
    plan = model.ask_json(ASSUME_SYS, ASSUME_PROMPT.format(core=core))
    assumptions = plan.get("assumptions", [])
    mvp = plan.get("mvp") or "議論で出た一番小さい一本"

    if on_step:
        on_step("proto")
    markup = _clean(model.ask(MARKUP_SYS, MARKUP_PROMPT.format(
        mvp=mvp,
        adopted=d.get("adopted") or "（決まっていない。仮置きで進める）",
        condition=d.get("condition") or "（決まっていない。仮置きで進める）",
        sacrificed=sacrificed,
        assumptions=json.dumps(assumptions, ensure_ascii=False, indent=1),
        transcript=transcript[:6000])))  # **画面は考える工程**（決めたことを画面に訳す）。ローカルでは決定を落とした（2026-10-28）

    def ask_js(role, err=""):
        prompt = JS_PROMPT.format(mvp=mvp, markup=markup)
        if err:
            prompt += JS_FIX_PROMPT.format(err=err)
        return _clean(model.ask(JS_SYS, prompt, role=role), drop_tags=True)

    js = ask_js("code")
    js_check, err = _js_check(js)
    if js_check == "ng":  # **直させる。** まず作る側、それでも駄目なら考える側
        js = ask_js("code", err)
        js_check, err = _js_check(js)
        if js_check == "ok":
            js_check = "retried"
    if js_check == "ng":
        js = ask_js("think", err)
        js_check, err = _js_check(js)
        if js_check == "ok":
            js_check = "claude"
    if js_check == "ng":
        # **壊れた JS はページに載せない。** 仮置きのボタンは別の JS なので生きる
        js, js_check = "", "failed"

    topic = structured.get("topic", "")
    page = (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_h.escape(mvp)[:40]}</title><style>{CSS}</style></head><body>"
        f'<header>プロトタイプ ・ 議論「{_h.escape(topic)}」から生成</header>'
        f"<main>{markup}</main>"
        + _sheet(assumptions)
        + f"<script>{js}\n{SHEET_JS}</script></body></html>")
    if on_step:
        on_step("uxcheck")
    try:
        from . import uxcheck
        report = uxcheck.check(page)
    except Exception as error:
        # **成果物は出す。試験の障害は隠さない。**
        report = {"checks": {}, "summary": {"fail": 0, "pass": 0, "skip": 0},
                  "execution": {"complete": False, "障害": type(error).__name__}}
    return {"mvp": mvp, "assumptions": assumptions, "html": page,
            "markup_chars": len(markup), "js_chars": len(js),
            "js_check": js_check, "ux": report}
