"""戻ってきた人が最初に見る1枚。**スマホ前提。依存ゼロの単一 HTML。**

一次資料は出さない。出すのは成果物と、議論が触れなかった空白。
"""
import datetime
import html
import re


def _inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = s.replace("未入力", '<span class="blank">未入力</span>')
    s = s.replace("仮置き", '<span class="assume">仮置き</span>')
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a class="btn" href="\2">\1</a>', s)
    s = s.replace("（推測）", '<span class="guess">（推測）</span>')
    return s


def md(text):
    """見出し・箇条書き・表・強調・段落・スライド区切り。"""
    out, ul, tbl = [], False, []

    def close_ul():
        nonlocal ul
        if ul:
            out.append("</ul>"); ul = False

    def close_tbl():
        nonlocal tbl
        if tbl:
            rows = [r for r in tbl if not re.match(r"^[\s|:-]+$", r)]
            cells = [[_inline(c.strip()) for c in r.strip().strip("|").split("|")]
                     for r in rows]
            if cells:
                head = "".join(f"<th>{c}</th>" for c in cells[0])
                body = "".join(
                    "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                    for r in cells[1:])
                out.append(f'<div class="tw"><table><thead><tr>{head}</tr>'
                           f"</thead><tbody>{body}</tbody></table></div>")
            tbl = []

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("|"):
            close_ul(); tbl.append(line); continue
        close_tbl()
        if re.match(r"^\s*---+\s*$", line):
            close_ul(); out.append('<hr class="slide">'); continue
        if m := re.match(r"^(#{1,4})\s+(.*)", line):
            close_ul()
            lv = min(max(len(m.group(1)), 2), 4)
            out.append(f"<h{lv}>{_inline(m.group(2))}</h{lv}>")
        elif m := re.match(r"^\s*(?:[-*]|\d+\.)\s+(.*)", line):
            if not ul:
                out.append("<ul>"); ul = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
        elif not line.strip():
            close_ul()
        else:
            close_ul()
            out.append(f"<p>{_inline(line)}</p>")
    close_ul(); close_tbl()
    return "\n".join(out)


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1b17;--mut:#6d675d;--line:#e2ddd2;--accent:#8a6a3b;
--card:#fff;--warn:#a63d33;--ok:#2f6b46}
@media (prefers-color-scheme:dark){:root{--bg:#16150f;--fg:#ece7dc;--mut:#9d968a;
--line:#322e26;--accent:#c9a46a;--card:#1e1c15;--warn:#d98b7f;--ok:#7fb894}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;
line-height:1.8;font-size:16px;-webkit-text-size-adjust:100%}
.wrap{max-width:740px;margin:0 auto;padding:28px 16px 90px}
header{border-bottom:1px solid var(--line);padding-bottom:18px}
h1{font-size:22px;margin:0 0 6px;letter-spacing:.01em}
.sub{color:var(--mut);font-size:12px}
.core{margin:22px 0 10px;padding:18px 20px;background:var(--card);
border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:4px}
.core .k{font-size:11px;letter-spacing:.14em;color:var(--accent)}
.core .v{font-size:18px;font-weight:650;margin:4px 0 10px;line-height:1.5}
.core .c{font-size:15px}
.strip{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}
.m{flex:1 1 110px;background:var(--card);border:1px solid var(--line);
border-radius:4px;padding:10px 12px}
.m b{display:block;font-size:21px;line-height:1.2}
.m span{font-size:11px;color:var(--mut)}
nav{display:flex;gap:6px;overflow-x:auto;margin:20px 0 0;
border-bottom:1px solid var(--line);-webkit-overflow-scrolling:touch}
nav button{flex:0 0 auto;background:none;border:0;border-bottom:2px solid transparent;
color:var(--mut);font:inherit;font-size:14px;padding:10px 12px;cursor:pointer}
nav button[aria-selected=true]{color:var(--fg);border-bottom-color:var(--accent);font-weight:650}
section{display:none;margin:22px 0}
section.on{display:block}
h2{font-size:18px;margin:26px 0 10px;font-weight:650}
h3{font-size:14px;margin:20px 0 4px;color:var(--accent);font-weight:650}
h4{font-size:13px;margin:14px 0 2px;font-weight:650}
p{margin:.6em 0}ul{margin:.5em 0;padding-left:1.1em}li{margin:.35em 0}
code{font-size:.9em;background:var(--card);border:1px solid var(--line);
border-radius:3px;padding:1px 4px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:460px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:var(--card);font-weight:650}
.blank{color:var(--warn);font-weight:650}
.assume{color:var(--accent);font-weight:650}
a.btn{display:inline-block;margin:10px 0;padding:11px 20px;border-radius:4px;
background:var(--accent);color:#fff;text-decoration:none;font-weight:650;font-size:15px}
.guess{color:var(--mut);font-size:.9em}
hr.slide{border:0;border-top:1px dashed var(--line);margin:26px 0}
footer{margin-top:60px;border-top:1px solid var(--line);padding-top:14px;
color:var(--mut);font-size:12px}
@media print{nav{display:none}section{display:block!important}
body{background:#fff;font-size:11pt}.wrap{max-width:none;padding:0}
section{page-break-before:always}}
"""

PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title><style>{css}</style></head><body><div class="wrap">
<header><h1>{title}</h1><div class="sub">{src} ・ {stamp} ・ {model}</div></header>

<div class="core"><div class="k">持ち帰る1行</div>
<div class="v">{adopted}</div>
<div class="k">成り立つ条件</div><div class="c">{condition}</div></div>

<div class="strip">{strip}</div>

<nav>{tabs}</nav>
{sections}
<footer>teatime — 席を外している間に、議論を事業の形へ起こす。<br>
この頁は議論の記録だけから作られています。
<b>記録に無いことは埋めず「未入力」と出しています。</b>その赤が、次に話すことです。</footer>
</div>
<script>
const b=[...document.querySelectorAll('nav button')],s=[...document.querySelectorAll('section')];
b.forEach((x,i)=>x.onclick=()=>{{b.forEach(y=>y.setAttribute('aria-selected',y===x));
s.forEach((y,j)=>y.classList.toggle('on',i===j));scrollTo({{top:0,behavior:'smooth'}});}});
</script></body></html>"""

STUCK = {"action": "取りうる手", "outcome": "どうなるか",
         "causation": "何が何を起こすか", "value": "どちらに価値があるか"}


def ux_error(proto):
    """**skip と試験障害を区別する。** HTML と端末で同じ理由を出す。"""
    report = (proto or {}).get("ux") or {}
    execution = report.get("execution", {})
    reason = execution.get("障害")
    if not reason:
        reason = next((c["障害"] for c in execution.get("coverage", [])
                       if c.get("check") == "browser" and c.get("障害")), None)
    if not reason and not report.get("checks"):
        reason = "試験結果なし"
    return " ".join(str(reason).split()).replace("|", "/") if reason else None


def assumptions_md(proto):
    """仮置きを、文書と同じ形で1枚にする。**どこを埋めたかを隠さない。**"""
    if not proto:
        return None
    rows = ["## 作ったもの", proto.get("mvp", ""), "",
            "## 仮置き（議論では決まっていません）",
            "| 決まっていないこと | 仮にこうした | 理由 | 確かめ方 |",
            "|---|---|---|---|"]
    for a in proto.get("assumptions", []):
        mark = " ⚑" if a.get("risk") == "high" else ""
        rows.append(f'| {a.get("gap","")}{mark} | {a.get("assumption","")} '
                    f'| {a.get("why","")} | {a.get("how_to_check","")} |')
    hi = sum(1 for a in proto.get("assumptions", []) if a.get("risk") == "high")
    rows += ["", f"⚑ は**外れると作り直しになるもの（{hi}件）**。先に確かめてください。", "",
             "## 触る", f'[プロトタイプを開く]({proto["url"]})',
             "", "**これは議論の記録＋上の仮置きだけから作られています。**"]
    rows += ["", "## UX 試験"]
    error = ux_error(proto)
    if error:
        rows.append(f"**試験できませんでした（{error}）。**")
    else:
        from . import uxcheck
        report = proto["ux"]
        counts = report["summary"]
        rows += [f'**fail {counts["fail"]}件 / pass {counts["pass"]}件 / skip {counts["skip"]}件。**', ""]
        if counts["fail"]:
            rows += [f'**この画面は {counts["fail"]} 件の試験に落ちています。**', ""]
        rows += ["| 観点 | 見るところ | 結果 | 理由 |", "|---|---|---|---|"]
        for key in uxcheck.IDS:
            check = report["checks"][key]
            status = check["status"]
            result = "**fail**" if status == "fail" else status
            reason = " ".join(check["reason"].split()).replace("|", "/")
            rows.append(f"| {key} | {uxcheck.LABELS[key]} | {result} | {reason} |")
    return "\n".join(rows)


def render(title, source, model_label, docs, structured, proto=None):
    m = structured.get("metrics", {})
    st = (structured.get("stuck") or {}).get("type")
    rate = m.get("unverbalized_rate")
    fail = "—" if ux_error(proto) else proto["ux"]["summary"]["fail"]
    strip = "".join([
        f'<div class="m"><b>{m.get("abandonments",0)}</b><span>放棄点</span></div>',
        f'<div class="m"><b>{"—" if rate is None else f"{int(rate*100)}%"}</b>'
        f"<span>理由が言葉になっていない</span></div>",
        f'<div class="m"><b>{len(structured.get("gaps",[]))}</b><span>埋めるべき空白</span></div>',
        f'<div class="m"><b>{STUCK.get(st,"—")}</b><span>詰まっている所</span></div>',
        f'<div class="m"><b>{fail}</b><span>UX 試験の fail</span></div>',
    ])
    if proto:
        docs = list(docs) + [{"key": "proto", "title": "プロトタイプ",
                              "text": assumptions_md(proto)}]
    tabs = "".join(
        f'<button aria-selected="{"true" if i==0 else "false"}">'
        f'{html.escape(d["title"])}</button>' for i, d in enumerate(docs))
    sections = "".join(
        f'<section class="{"on" if i==0 else ""}">{md(d["text"])}</section>'
        for i, d in enumerate(docs))
    d = structured.get("decision") or {}
    return PAGE.format(
        title=html.escape(title), css=CSS, src=html.escape(source),
        stamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        model=html.escape(model_label),
        adopted=_inline(d.get("adopted") or "まだ決まっていません"),
        condition=_inline(d.get("condition") or "未入力（議論で出ていない）"),
        strip=strip, tabs=tabs, sections=sections)
