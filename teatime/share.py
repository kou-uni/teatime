"""外から見る1枚 — **その場にいなかった人と、投資家が開くページ。**

成果物は全部「ファイル」で、転送できなかった。これは転送できる単位を作る。
設計の根拠は `docs/outputs-for-whom.md`。

- **最大の活字は、採った案と、その成り立つ条件。** これだけ読んで閉じてよい
- 動作は2つだけ（見る／触る）。並べない
- **「理由は言われていません」を隠さない。** ここだけが他では見られないもの
- **「未入力」を誇って出す。** 空欄は、作文していないことの証拠
- OGP を入れる。Slack や LINE に貼った時点で、1行が相手に届く

    .venv/bin/python -m teatime.share out/<stem>
"""
import datetime
import html as _h
import json
import pathlib
import shutil
import sys

CSS = """
:root{color-scheme:light dark;
--paper:#f4f1ea;--ink:#23201c;--mut:#6f6a60;--rule:#ded8c9;--ac:#8a6a3b;--warn:#9b3b2f;
--ui:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif;
--num:ui-rounded,-apple-system,"SF Pro Rounded","Hiragino Sans",sans-serif}
@media(prefers-color-scheme:dark){:root{--paper:#14130f;--ink:#e9e4d8;--mut:#948d80;
--rule:#2e2a23;--ac:#c9a46a;--warn:#d08477}}
*{box-sizing:border-box;border-radius:0}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--ui);
font-size:17px;line-height:1.7;font-weight:500;-webkit-text-size-adjust:100%}
.page{max-width:680px;margin:0 auto;padding:28px 20px 80px}
.mast{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
padding-bottom:14px;border-bottom:1px solid var(--rule);color:var(--mut);font-size:12px}
.brand{color:var(--ink);font-size:20px;font-weight:650;letter-spacing:.04em}
.topic{color:var(--mut);font-size:13px;margin:22px 0 10px}
h1{font-size:31px;line-height:1.42;font-weight:650;margin:0;letter-spacing:.01em}
.cond{margin:14px 0 0;font-size:18px;font-weight:650;color:var(--ac);line-height:1.6}
.cond small{display:block;color:var(--mut);font-weight:500;font-size:12px;margin-bottom:2px}
/* 動作は2つだけ。角丸があるもの＝触れるもの、を一意にする */
.acts{display:flex;flex-direction:column;gap:12px;margin:28px 0 8px}
a.go,button.go{display:block;width:100%;padding:16px;border:0;border-radius:10px;
background:var(--ink);color:var(--paper);font:inherit;font-weight:650;font-size:16px;
text-align:center;text-decoration:none;cursor:pointer;
transition:transform .18s cubic-bezier(.34,1.56,.64,1)}
a.go2,button.go2{background:transparent;color:var(--ink);border:1px solid var(--rule)}
a.go:active,button.go:active{transform:scale(.97);transition-duration:70ms}
video{width:100%;display:block;margin:24px 0 0;background:#000}
h2{font-size:13px;font-weight:700;color:var(--mut);letter-spacing:.08em;
margin:44px 0 0;padding-bottom:10px;border-bottom:1px solid var(--rule)}
.row{padding:16px 0;border-bottom:1px solid var(--rule)}
.swap{font-size:17px;font-weight:650;line-height:1.55}
.swap s{color:var(--mut);font-weight:500;text-decoration-thickness:1px}
.trade{font-size:14px;color:var(--ac);font-weight:650;margin-top:4px}
.quote{font-size:14px;color:var(--mut);margin-top:6px;line-height:1.65}
.tag{display:inline-block;margin-top:8px;padding:3px 8px;border:1px solid var(--warn);
color:var(--warn);font-size:11.5px;font-weight:700;letter-spacing:.04em}
.gaps{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 0}
.gaps span{padding:6px 11px;border:1px dashed var(--rule);color:var(--mut);font-size:14px}
.note{color:var(--mut);font-size:13.5px;margin-top:14px;line-height:1.7}
.stuck{margin-top:18px;font-size:19px;font-weight:650;line-height:1.6}
.big{font-family:var(--num);font-size:40px;font-weight:900;line-height:1;
font-variant-numeric:tabular-nums}
.nums{display:flex;gap:28px;margin:20px 0 0;flex-wrap:wrap}
.n span{display:block;color:var(--mut);font-size:12px;margin-top:6px}
footer{margin-top:52px;padding-top:16px;border-top:1px solid var(--rule);
color:var(--mut);font-size:12.5px;line-height:1.8}
#copied{color:var(--ac);font-size:13px;font-weight:650;min-height:20px;margin-top:4px}
"""


def _stuck_line(stuck):
    t = (stuck or {}).get("type")
    return {
        "value": "**価値**で止まっています。これは調べても出ません。決める話です。",
        "action": "**何をするか**で止まっています。ここは動けば分かります。",
        "outcome": "**結果の読み**で止まっています。小さく試せば分かります。",
        "causal": "**因果**で止まっています。切り分ければ分かります。",
    }.get(t, "止まっている場所は、議論からは分かりませんでした。")


def build(stem):
    """`<stem>.share.html` を書いて、そのパスを返す。"""
    stem = pathlib.Path(stem)
    out, base = stem.parent, stem.name
    d = json.loads((out / f"{base}.extract.json").read_text(encoding="utf-8"))
    dec = d.get("decision") or {}
    adopted = dec.get("adopted") or "この議論では、採る案は決まっていません"
    cond = dec.get("condition") or "成り立つ条件は、まだ言葉になっていません"
    m = d.get("metrics") or {}
    e = _h.escape
    has = lambda n: (out / f"{base}.{n}").exists()  # noqa: E731
    when = datetime.datetime.fromtimestamp(
        (out / f"{base}.extract.json").stat().st_mtime).strftime("%Y-%m-%d")

    acts = []
    if has("mp4"):
        acts.append(f'<a class="go" href="#v">解説を見る（音声つき）</a>')
    if has("proto.html"):
        acts.append(f'<a class="go go2" href="{e(base)}.proto.html">触ってみる</a>')
    acts.append('<button class="go go2" id="c" type="button">この1行をコピー</button>')

    rows = []
    for a in d.get("abandonments") or []:
        tag = ('<div class="tag">理由は言われていません</div>'
               if a.get("verbalized") is False else "")
        q = (f'<div class="quote">「{e(a.get("evidence",""))}」</div>'
             if a.get("evidence") else "")
        rows.append(
            f'<div class="row"><div class="swap"><s>{e(a.get("dropped",""))}</s>'
            f' → {e(a.get("kept",""))}</div>'
            f'<div class="trade">{e(a.get("sacrificed_value") or "？")}を手放して、'
            f'{e(a.get("gained_value") or "？")}を取る</div>{q}{tag}</div>')
    swaps = "".join(rows) or '<p class="note">落ちた案は見つかりませんでした。</p>'

    gaps = "".join(f"<span>{e(g)}</span>" for g in d.get("gaps") or [])
    stuck = _stuck_line(d.get("stuck")).replace("**", "")
    sq = (d.get("stuck") or {}).get("evidence") or ""
    rate = m.get("unverbalized_rate")
    rate_s = "—" if rate is None else f'{round(rate * 100)}%'

    # **黒い箱を先頭に置かない。** 1枚目のスライドを静止画として出しておく
    poster = ""
    first = out / f"{base}.video" / "01.png"
    if first.exists():
        shutil.copyfile(first, out / f"{base}.poster.png")
        poster = f' poster="{e(base)}.poster.png"'
    video = (f'<video id="v" controls playsinline preload="metadata"{poster} '
             f'src="{e(base)}.mp4"></video>' if has("mp4") else "")
    adopted_js = json.dumps(adopted, ensure_ascii=False)
    cond_js = json.dumps(cond, ensure_ascii=False)

    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>{e(adopted)}</title>
<meta property="og:type" content="article">
<meta property="og:title" content="{e(adopted)}">
<meta property="og:description" content="{e(cond)}">
<meta name="description" content="{e(cond)}">
<style>{CSS}</style></head><body>
<div class="page">
<header class="mast"><span class="brand">teatime</span><span>{when}</span></header>

<p class="topic">{e(d.get("topic") or "")}</p>
<h1>{e(adopted)}</h1>
<p class="cond"><small>これが成り立つ条件</small>{e(cond)}</p>

<div class="acts">{"".join(acts)}</div>
<div id="copied" role="status" aria-live="polite"></div>
{video}

<h2>手放したもの</h2>
{swaps}

<h2>まだ決まっていないこと</h2>
<div class="gaps">{gaps or '<span>なし</span>'}</div>
<p class="note">議論に出てこなかったので、埋めずに置いてあります。
<b>ここを埋めない限り、次は決まりません。</b></p>

<h2>今日、止まっていた場所</h2>
<p class="stuck">{e(stuck)}</p>
<p class="quote">「{e(sq)}」</p>

<h2>この部屋の数字</h2>
<div class="nums">
<div class="n"><b class="big">{m.get("abandonments", 0)}</b><span>捨てた案</span></div>
<div class="n"><b class="big">{rate_s}</b><span>理由が言われていない</span></div>
<div class="n"><b class="big">{len(d.get("gaps") or [])}</b><span>未入力</span></div>
</div>

<footer>このページは、議論の録音だけから作っています。<br>
議論に出ていないことは書かず、<b>「未入力」と出します。</b></footer>
</div>
<script>
document.getElementById('c').onclick=async()=>{{
  const t={adopted_js}+"\\n"+{cond_js}+"\\n"+location.href;
  try{{await navigator.clipboard.writeText(t);
    document.getElementById('copied').textContent='コピーしました。貼って送れます。';}}
  catch(e){{document.getElementById('copied').textContent='コピーできませんでした。';}}
}};
</script></body></html>"""


def write(stem):
    stem = pathlib.Path(stem)
    dest = stem.parent / f"{stem.name}.share.html"
    dest.write_text(build(stem), encoding="utf-8")
    return dest


if __name__ == "__main__":
    print(write(sys.argv[1]))
