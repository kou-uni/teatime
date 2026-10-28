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
:root{color-scheme:light dark;--paper:#f4f1ea;--ink:#23201c;--muted:#6f6a60;--rule:#ded8c9;--red:#9b3b2f;--read:"Hiragino Mincho ProN","Yu Mincho",YuMincho,"Noto Serif JP",serif;--ui:-apple-system,"Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif}
@media(prefers-color-scheme:dark){:root{--paper:#14130f;--ink:#e9e4d8;--muted:#948d80;--rule:#2e2a23;--red:#d08477}}
*{box-sizing:border-box;border-radius:0;box-shadow:none}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--ui);font-size:16px;line-height:1.6;letter-spacing:normal;-webkit-text-size-adjust:100%;overflow-wrap:anywhere}
h1,h2,h3,h4,p,ul,ol,dl,dd,blockquote{margin:0}
h1,.adopted,blockquote{font-family:var(--read)}
h1{font-size:32px;font-weight:400;line-height:1.3}
a{color:inherit;text-underline-offset:4px;touch-action:manipulation}
a:focus-visible,.tw:focus-visible{outline:2px solid var(--ink);outline-offset:4px}
.wrap{width:100%;max-width:704px;margin:0 auto;padding:32px}
.masthead{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding-bottom:8px;border-bottom:1px solid var(--rule);color:var(--muted);font-size:12px}
.brand{color:var(--ink);font-size:24px;letter-spacing:.04em}
.core{margin-top:16px}
.k{font-size:12px;color:var(--muted)}
.adopted{margin-top:4px}
.condition{margin-top:16px}
.c{margin-top:4px}
.choices{margin-top:16px}
.pair{margin-top:8px;font-size:15px;line-height:1.6}
.pair p{display:flex;align-items:baseline;gap:8px}
.pair .take{color:var(--ink);font-weight:650}
.pair .give{color:var(--muted)}
.pair .label{flex:0 0 48px;font-size:12px}
.strip{margin-top:16px;font-size:14px;color:var(--muted)}
.toc{margin-top:32px}
.toc ul{list-style:none;margin:0;padding:0}
.toc a{display:flex;align-items:center;width:fit-content;max-width:100%;min-width:44px;min-height:44px;padding:8px 0}
section{display:block;margin-top:64px;scroll-margin-top:16px}
.section-title{font-size:20px;font-weight:650;margin-bottom:32px}
h2{font-size:20px;line-height:1.6;margin:32px 0 16px;font-weight:650}
h3{font-size:17px;margin:16px 0 8px;font-weight:650}
h4{font-size:16px;margin:16px 0 8px;font-weight:650}
section>h2:first-child{margin-top:0}
section p+p{margin-top:16px}
section ul,section ol{margin:16px 0;padding-left:32px}
section li+li{margin-top:8px}
strong,b{font-weight:650}
blockquote{margin:16px 0}
code{font-family:var(--ui);font-size:14px;padding:0 4px}
.tw{overflow-x:auto;margin:16px 0}
table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.6}
th,td{padding:8px;text-align:left;vertical-align:top;border-bottom:1px solid var(--rule);overflow-wrap:anywhere}
th{font-weight:650;color:var(--muted)}
.blank,.risk{color:var(--red);font-weight:650}
.risk{font-variant-emoji:text}
.assume{font-weight:650}
.guess,.status{color:var(--muted);font-size:14px}
a.btn{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;padding:8px 16px;background:var(--ink);color:var(--paper);font-weight:650;text-decoration:none}
hr.slide{border:0;border-top:1px solid var(--rule);margin:32px 0}
footer{margin-top:64px;border-top:1px solid var(--rule);padding-top:16px;color:var(--muted);font-size:12px}
footer p+p{margin-top:16px}
@media(max-width:640px){.wrap{padding:16px}h1,.adopted{font-size:28px}.c{font-size:14px;line-height:1.5}.tw table{min-width:560px}}
@media print{
:root{color-scheme:light;--paper:#f4f1ea;--ink:#23201c;--muted:#6f6a60;--rule:#ded8c9;--red:#9b3b2f}
@page{margin:16px}
body{font-size:11pt}.wrap{max-width:none;padding:0}
section{display:block;break-before:page;margin-top:32px}
h2,h3,h4{break-after:avoid}.pair,tr,blockquote{break-inside:avoid}
.tw{overflow:visible}.tw table{min-width:0}thead{display:table-header-group}
a.btn{background:none;color:var(--ink);padding:0;text-decoration:underline}
}
"""

PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title><style>{css}</style></head>
<body><div class="wrap">
<header class="masthead"><span class="brand">teatime</span><span>議論の成果物</span></header>
<main>
<div class="core">
<p class="k">採用した一行</p>
<h1 class="adopted">{adopted}</h1>
<div class="condition"><p class="k">成り立つ条件</p><p class="c">{condition}</p></div>
<div class="choices" aria-label="取るものと手放すもの">{pairs}</div>
</div>
<p class="strip">{strip}</p>
<div class="toc" role="navigation" aria-label="成果物の目次"><ul>{toc_items}</ul></div>
{sections}
</main>
<footer>
<p>teatime — 席を外している間に、議論を事業の形へ起こす。<br>
この頁は議論の記録だけから作られています。<br>
<strong>記録に無いことは埋めず「<span class="blank">未入力</span>」と出しています。</strong>仮置きは議論の決定と分けて記しています。</p>
<p>{src}<br>{stamp} · {model}</p>
</footer>
</div></body></html>"""

STUCK = {"action": "取りうる手", "outcome": "どうなるか",
         "causation": "何が何を起こすか", "value": "どちらに価値があるか"}


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
    return "\n".join(rows)


def render(title, source, model_label, docs, structured, proto=None):
    m = structured.get("metrics", {})
    st = (structured.get("stuck") or {}).get("type")
    count = m.get("unverbalized")
    rate = m.get("unverbalized_rate")
    if count is not None:
        reason = f"うち{count}件は、なぜ捨てたかが議論で言葉になっていない。"
    elif rate is not None:
        reason = f"うち{int(rate * 100)}%は、なぜ捨てたかが議論で言葉になっていない。"
    else:
        reason = "理由が言葉になっていない件数は未入力。"
    strip = _inline(
        f'捨てた案 {m.get("abandonments", 0)}件。{reason}'
        f'空白{len(structured.get("gaps", []))}件。'
        f'詰まっている所：{STUCK.get(st, "未入力")}。')
    # **抽出順の先頭3対。議論にない価値を補わない。**
    pairs = "".join(
        '<div class="pair"><p class="take"><span class="label">取る</span>'
        f'<strong>{_inline(a.get("gained_value") or "未入力")}</strong></p>'
        '<p class="give"><span class="label">手放す</span>'
        f'<span>{_inline(a.get("sacrificed_value") or "未入力")}</span></p></div>'
        for a in structured.get("abandonments", [])[:3])
    if proto:
        docs = list(docs) + [{"key": "proto", "title": "プロトタイプ",
                              "text": assumptions_md(proto)}]
    toc_items = "".join(
        f'<li><a href="#doc-{i}">{html.escape(doc["title"])}</a></li>'
        for i, doc in enumerate(docs))
    sections = []
    for i, doc in enumerate(docs):
        # **本文の見出しと文言は保ち、目次と同じ文書名で識別する。**
        body = md(doc["text"]).replace(
            "⚑", '<span class="risk" aria-label="高リスク">⚑&#xfe0e;</span>')
        sections.append(
            f'<section id="doc-{i}" aria-labelledby="doc-title-{i}">'
            f'<p class="section-title" id="doc-title-{i}">{html.escape(doc["title"])}</p>'
            f'{body}</section>')
    d = structured.get("decision") or {}
    return PAGE.format(
        title=html.escape(title), css=CSS, src=html.escape(source),
        stamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        model=html.escape(model_label),
        adopted=_inline(d.get("adopted") or "まだ決まっていません"),
        condition=_inline(d.get("condition") or "未入力（議論で出ていない）"),
        pairs=pairs, strip=strip, toc_items=toc_items, sections="".join(sections))
