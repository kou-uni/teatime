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
import os
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
:root{color-scheme:light dark;--paper:#f4f1ea;--ink:#23201c;--muted:#6f6a60;--rule:#ded8c9;--red:#9b3b2f;--read:"Hiragino Mincho ProN","Yu Mincho",YuMincho,"Noto Serif JP",serif;--ui:-apple-system,"Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif}
@media(prefers-color-scheme:dark){:root{--paper:#14130f;--ink:#e9e4d8;--muted:#948d80;--rule:#2e2a23;--red:#d08477}}
*{box-sizing:border-box;border-radius:0!important;letter-spacing:normal}
*::before,*::after,input::file-selector-button{border-radius:0!important}
body,h1,h2,h3,h4,p,ul,ol,dl,dd,blockquote,pre,fieldset{margin:0}
*+*{margin-top:16px}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 var(--ui);overflow-wrap:anywhere;-webkit-text-size-adjust:100%}
body>header,main{width:100%;max-width:704px;margin-inline:auto;padding:32px}
body>header{padding-bottom:16px;color:var(--muted);font-size:12px;border-bottom:1px solid var(--rule)}
main{margin-top:0;padding-bottom:64px}
body{padding-bottom:64px}
h1{font:400 32px/1.3 var(--read)}
h2,.big{font-size:24px;font-weight:650;line-height:1.5}
h3{font-size:20px}h4{font-size:17px}
strong,b{font-weight:650}
main>:is(div,section,article,form)+:is(div,section,article,form){margin-top:64px}
.card,blockquote{background:none;border:0;padding:0}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:16px}
.col{display:flex;flex-direction:column;gap:16px}
.row>*,.col>*{margin-top:0;min-width:0;max-width:100%}
.row>input:not([type=radio]):not([type=checkbox]){flex:1 1 100%}
.row>.btn{flex:1 1 100%}
.row>.btn2{flex:0 1 auto}
.mut,.tag{color:var(--muted);font-size:14px}.tag{font-size:12px}
ul,ol{padding-left:32px}li+li{margin-top:8px}
dt{font-weight:650}dd{margin-top:4px}
fieldset{min-width:0;padding:0;border:0}legend{padding:0;font-weight:650}
label{display:block}label>input,label>select,label>textarea{margin-top:8px}
pre{white-space:pre-wrap;overflow-wrap:anywhere}pre,code,kbd,samp{font-family:var(--ui);font-size:14px}
img,video,canvas,svg{max-width:100%;height:auto}
table{width:100%;table-layout:fixed;border-collapse:collapse;font:14px/1.6 var(--ui)}
th,td{padding:8px;text-align:left;vertical-align:top;border-bottom:1px solid var(--rule)}
th{font-weight:650}caption{text-align:left;margin-bottom:8px}
a{display:inline-flex;align-items:center;min-width:44px;min-height:44px;padding:8px 0;color:inherit;text-underline-offset:4px;touch-action:manipulation}
/* 入力は薄い沈み。新しい色や影は増やさない。 */
input,textarea,select,.field{display:block;width:100%;max-width:100%;min-width:44px;min-height:44px;font:inherit;color:var(--ink);padding:8px 16px;border:0;border-bottom:1px solid var(--muted);background:color-mix(in srgb,var(--ink) 4%,var(--paper))}
textarea{resize:vertical}input::placeholder,textarea::placeholder{color:var(--muted);opacity:1}
input:is([type=radio],[type=checkbox]){appearance:none;display:inline-block;width:44px;height:44px;padding:8px;margin:0;vertical-align:middle;border:1px solid var(--ink);background:var(--paper);flex-shrink:0;cursor:pointer}
input[type=radio]:checked::before,input[type=checkbox]:checked::before{content:"✓";display:block;text-align:center;color:var(--ink);font:650 20px/1.3 var(--ui)}
/* 押すものは墨の面。副操作は下罫、選ぶものは囲み。 */
button,[role=button],input[type=submit],input[type=button],input[type=reset],.btn,.btn2,input::file-selector-button{display:inline-flex;align-items:center;justify-content:center;width:auto;min-width:44px;min-height:44px;max-width:100%;padding:8px 16px;border:1px solid var(--ink);background:var(--ink);color:var(--paper);font:inherit;cursor:pointer;text-decoration:none;text-align:center;touch-action:manipulation;white-space:normal}
.btn2{background:none;color:var(--ink);border:0;border-bottom:2px solid var(--ink);padding:8px 0}
label:has(input[type=radio]),label:has(input[type=checkbox]),select,summary,[role=option],.row:has(>.btn2~.btn2)>.btn2,label.btn2{min-width:44px;min-height:44px;padding:8px 16px;border:1px solid var(--ink);background:var(--paper);color:var(--ink);cursor:pointer}
label:has(input[type=radio]),label:has(input[type=checkbox]){display:flex;align-items:center;gap:8px}
label:has(input[type=radio])>*,label:has(input[type=checkbox])>*{margin-top:0}
summary{display:list-item}option{background:var(--paper);color:var(--ink)}
.row:has(>.btn2~.btn2)>.btn2{flex:1 1 100%;justify-content:flex-start;text-align:left}
:where(button,input,textarea,select,a,summary,[tabindex],[role=button]):focus-visible{outline:2px solid var(--ink);outline-offset:4px}
:disabled,[aria-disabled=true]{cursor:not-allowed;text-decoration:line-through}
/* 状態名が変わっても反転は同じ。sheet の on は開閉専用。 */
:is(.active,.on,.selected,.is-active,[aria-pressed="true"],[aria-selected="true"],[data-selected],input:checked+*,label:has(input:checked)):not(#sheet){background:var(--ink);color:var(--paper);border-color:var(--ink)}
:where(p,li,td) a{display:inline!important;min-width:0!important;min-height:0!important;padding:0!important}
/* 空の操作部品や入力欄は消さず、空の入れ物だけ潰す。 */
:where(div,section,article,aside,nav,header,footer,main,p,ul,ol,dl,pre,blockquote,fieldset,output):empty:not([role]):not([contenteditable]){display:none!important}
[hidden],input[type=hidden]{display:none!important}
.filepick{display:inline-flex;align-items:center;gap:12px;min-height:44px;padding:10px 20px;background:var(--ink);color:var(--paper);font-size:14px;cursor:pointer}
.filepick input[type=file]{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
.filepick .filename{color:var(--paper);font-size:13px}
#fab{position:fixed;left:0;right:0;bottom:0;z-index:9;margin:0;width:100%;min-height:56px;padding:16px 32px;text-align:left;background:var(--paper);color:var(--ink);border:0;border-top:1px solid var(--rule);font-size:14px}
#fab::after{content:"▸";float:right;color:var(--muted)}
main{padding-bottom:88px}
#sheet{display:none;position:fixed;inset:0;z-index:10;margin:0;background:color-mix(in srgb,var(--ink) 32%,transparent);color:var(--ink)}
#sheet.on{display:block}body:has(#sheet.on){overflow:hidden}
#sheet>div{position:absolute;right:0;top:0;bottom:0;width:min(704px,100%);margin:0;padding:0 32px 32px;overflow-y:auto;overscroll-behavior:contain;background:var(--paper);border-left:1px solid var(--rule)}
#sheet .sheet-head{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:16px;margin:0;padding:16px 0;background:var(--paper);border-bottom:1px solid var(--rule)}
#sheet .sheet-head>*{margin:0}#sheet h2{font-family:var(--read);font-weight:400}
#sclose{border:0;border-bottom:2px solid var(--ink);background:none;color:var(--ink);padding:8px 0;flex-shrink:0}
.as{margin-top:32px}.as>b{display:block;font:400 22px/1.6 var(--read)}
.as .why{color:var(--muted);font-size:14px}
.hi,.risk,.blank{color:var(--red)}.hi{font-family:var(--ui);font-size:14px;font-variant-emoji:text}
@media(max-width:640px){body>header,main{padding:16px}main{padding-bottom:88px}h1{font-size:28px}.big{font-size:24px}#sheet>div{padding:0 16px 32px}}
"""

SHEET_JS = """
document.getElementById('fab').onclick=()=>document.getElementById('sheet').classList.add('on');
document.getElementById('sheet').onclick=e=>{if(e.target.id==='sheet'||e.target.id==='sclose')
document.getElementById('sheet').classList.remove('on')};
/* 選んだファイル名を出す。出さないと押した結果が分からない。 */
document.querySelectorAll('.filepick input[type=file]').forEach(i=>i.onchange=()=>{
const n=i.parentNode.querySelector('.filename');if(n)n.textContent=i.files[0]?i.files[0].name:'';});
"""


def _sheet(assumptions):
    # **外れると作り直す前提から読む。** 元の一覧は変更しない。
    ordered = sorted(assumptions, key=lambda a: a.get("risk") != "high")
    rows = []
    for a in ordered:
        hi = a.get("risk") == "high"
        rows.append(
            '<div class="as">'
            + ('<p class="hi">&#9873;&#65038; 高リスク</p>' if hi else '')
            + f'<b>{_h.escape(str(a.get("gap", "")))}</b>'
            f'<div>→ {_h.escape(str(a.get("assumption", "")))}</div>'
            f'<div class="why">なぜ: {_h.escape(str(a.get("why", "")))}'
            f'<br>確かめ方: {_h.escape(str(a.get("how_to_check", "")))}</div></div>')
    n = len(ordered)
    return (
        f'<button id="fab" type="button" aria-controls="sheet">仮置き {n}</button>'
        '<div id="sheet"><div role="region" aria-labelledby="sheet-title">'
        '<div class="sheet-head"><h2 id="sheet-title">仮置き</h2>'
        '<button id="sclose" class="btn2" type="button">閉じる</button></div>'
        '<p class="mut">議論で決まっていないこと。作るために、いまは仮にこうしてあります。'
        '<span class="hi">&#9873;&#65038; 高リスク</span> は外れると作り直しになるもの。</p>'
        + "".join(rows) + '</div></div>')


def _clean(text, drop_tags=True):
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t).rsplit("```", 1)[0]
    if drop_tags:
        t = re.sub(r"</?(?:script|style)[^>]*>", "", t)
    return t.strip()


def _jp_file(markup):
    """**ファイル選択の「Choose File」はCSSで変えられない。** 素の input を隠し、
    label をこちら側で書いて日本語のボタンにする。モデルの書き方に依存しない。"""
    def wrap(m):
        tag = m.group(0)
        if 'data-jp' in tag:
            return tag
        label = "写真を選ぶ" if re.search(r'accept=["\']?image', tag) else "ファイルを選ぶ"
        return (f'<label class="filepick">{label}'
                f'{tag[:-1]} data-jp>'
                f'<span class="filename"></span></label>')
    return re.sub(r'<input\b[^>]*type=["\']?file["\']?[^>]*>', wrap, markup, flags=re.I)


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


FIX_PROMPT = """この画面は、機械の試験に落ちました。**落ちた所だけを直してください。**

## 落ちた観点
{failures}

## いまの画面
```html
{markup}
```

## 直し方の規則
- **構造で直す。** 「追加」「登録」「保存」「足す」のどれかを**文字として含むボタン**を置く。
  一覧は `<ul>` `<ol>` `<tbody>` のどれかにする。日付が要るなら `<input type="date">`。
- **押して何も起きないボタンを作らない。** 押したら一覧か文言が**目に見えて変わる**こと。
- 画面の目的（{mvp}）を変えない。**落ちた所だけ**を直す。
- 使ってよい class は card row col btn btn2 mut tag big field のみ。

**HTML（画面の中身）だけ**を2500字以内で。説明を書かない。
"""


def _score(report):
    """**試験の良し悪しを1つの数にする。** skip は「その構造が無い」なので減点。"""
    s = (report or {}).get("summary") or {}
    return s.get("pass", 0) * 2 - s.get("fail", 0) * 3 - s.get("skip", 0)


def _failures(report):
    """落ちた観点と理由を、モデルに渡せる形にする。**pass は渡さない。**"""
    from . import uxcheck
    lines = []
    for key in uxcheck.IDS:
        c = (report.get("checks") or {}).get(key)
        if c and c["status"] in ("fail", "skip"):
            lines.append(f'- {uxcheck.LABELS[key]}（{c["status"]}）: '
                         + " ".join(c["reason"].split())[:160])
    return "\n".join(lines)


def _rounds():
    """**既定は1回だけ直す。** 直すたびに生成が1本増えるので、際限なく回さない。"""
    try:
        return max(0, min(3, int(os.environ.get("TEATIME_REFINE", "1"))))
    except ValueError:
        return 1


def refine(report, markup, mvp, assemble, on_step=None):
    """**作って終わりにしない。** 落ちた観点をモデルに返して作り直し、また測る。
    **良くなったときだけ採る**ので、直そうとして悪くなることが無い。"""
    from . import uxcheck
    best = {"markup": markup, "report": report, "score": _score(report)}
    history = [{"round": 0, "score": best["score"],
                "summary": dict((report or {}).get("summary") or {})}]
    for i in range(1, _rounds() + 1):
        failures = _failures(best["report"])
        if not failures:
            break  # **落ちていないなら触らない**
        if on_step:
            on_step(f"refine{i}")
        try:
            new_markup = _jp_file(_clean(model.ask(
                MARKUP_SYS, FIX_PROMPT.format(
                    failures=failures, markup=best["markup"], mvp=mvp))))
            new_page = assemble(new_markup)
            new_report = uxcheck.check(new_page)
        except Exception as error:
            history.append({"round": i, "error": type(error).__name__})
            break
        new_score = _score(new_report)
        history.append({"round": i, "score": new_score,
                        "summary": dict(new_report.get("summary") or {}),
                        "採用": new_score > best["score"]})
        if new_score > best["score"]:
            best = {"markup": new_markup, "report": new_report, "score": new_score}
        else:
            break  # **良くならなかったら、そこで止める**
    return best, history


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
    markup = _jp_file(markup)

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

    def assemble(body):
        # **組み立ては1か所。** refine が同じ手で作り直せるようにする
        return (
            '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_h.escape(mvp)[:40]}</title><style>{CSS}</style></head><body>"
            f'<header>プロトタイプ ・ 議論「{_h.escape(topic)}」から生成</header>'
            f"<main>{body}</main>"
            + _sheet(assumptions)
            + f"<script>{js}\n{SHEET_JS}</script></body></html>")

    page = assemble(markup)
    if on_step:
        on_step("uxcheck")
    try:
        from . import uxcheck
        report = uxcheck.check(page)
    except Exception as error:
        # **成果物は出す。試験の障害は隠さない。**
        report = {"checks": {}, "summary": {"fail": 0, "pass": 0, "skip": 0},
                  "execution": {"complete": False, "障害": type(error).__name__}}
    # **落ちたまま出さない。** 落ちた観点を返して作り直し、良くなったときだけ採る
    best, history = refine(report, markup, mvp, assemble, on_step)
    markup, report, page = best["markup"], best["report"], assemble(best["markup"])

    return {"mvp": mvp, "assumptions": assumptions, "html": page,
            "markup_chars": len(markup), "js_chars": len(js),
            "js_check": js_check, "ux": report, "refine": history}
