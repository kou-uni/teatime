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
/* 1書体・2ウェイト。明朝は全廃した。
   ウマ娘はロダンわんぱく EB の1ウェイトだけで、強弱をサイズ・色・地の色で付ける。
   teatime は本文が長いので 1書体・2ウェイトにした（本文400 / 見出し・数値800）。
   iOS のヒラギノは W3/W6 しか出ないので、実機では 400→W3・800→W6。
   数字だけ ui-rounded（SF Pro Rounded・標準搭載）に分ける＝和文と数字で丸みが別。 */
:root{color-scheme:light dark;--paper:#f4f1ea;--ink:#23201c;--muted:#6f6a60;--rule:#ded8c9;--red:#9b3b2f;--main:#3f6b26;--on-main:#f4f1ea;--ui:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic Medium",sans-serif;--num:ui-rounded,-apple-system,"SF Pro Rounded","Hiragino Sans","Noto Sans JP",sans-serif}
@media(prefers-color-scheme:dark){:root{--paper:#14130f;--ink:#e9e4d8;--muted:#948d80;--rule:#2e2a23;--red:#d08477;--main:#7fb34a;--on-main:#14130f}}
/* 角丸は「指で触れるもの」の印。読むものは0のまま。装飾としては足さない。 */
*{box-sizing:border-box;border-radius:0;box-shadow:none}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--ui);font-size:16px;line-height:1.75;font-weight:400;-webkit-text-size-adjust:100%;overflow-wrap:anywhere}
h1,h2,h3,h4,p,ul,ol,dl,dd,blockquote{margin:0}
h1{font-size:32px;font-weight:800;line-height:1.4;letter-spacing:.005em}
a{color:inherit;text-underline-offset:4px;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
a:focus-visible,summary:focus-visible,.tw:focus-visible{outline:3px solid var(--ink);outline-offset:3px}
.wrap{width:100%;max-width:704px;margin:0 auto;padding:32px}
.masthead{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding-bottom:8px;border-bottom:1px solid var(--rule);color:var(--muted);font-size:12px}
.brand{color:var(--ink);font-size:24px;font-weight:800;letter-spacing:.04em}
.core{margin-top:20px}
.k{font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.04em}
.adopted{margin-top:6px}
.condition{margin-top:20px}
.c{margin-top:4px;line-height:1.7}

/* ===== 取る / 手放す ==========================================================
   この製品で一番価値のある情報。ゲームのステータスバーの機構をそのまま当てた:
   **形も色相も位置も変えず、充填と彩度だけを変える**（ポケモンGO が戦闘中HP #03FF69
   と一覧HP #6DEDB7 を同じピル型で出し分けているのと同じ手）。
   上が満ちていて下が空いている＝1つのメーターとして読める。
   ラベルは値の 65%（11px / 17px）。ポケモンGO の実測は 48% だが、
   「手放す」という3文字を 8px にすると読めない。**48% は固定値ではなく、
   下限はラベルの字数で決まる。** 退かせる仕事は色とウェイトが引き継いでいる。 */
.choices{margin-top:24px}
.pair{margin-top:16px}
.pair p{display:flex;align-items:baseline;gap:12px;min-height:44px;margin:0;padding:11px 14px;font-size:17px;line-height:1.5}
.pair .label{flex:0 0 52px;font-size:11px;font-weight:700;line-height:1.9;letter-spacing:.04em}
.pair .take{background:var(--main);color:var(--on-main);font-weight:800}
.pair .take .label{color:var(--on-main);opacity:.70}
.pair .take strong{font-weight:800}
.pair .give{background:transparent;color:var(--muted);border:1px solid var(--main);border-top:0}
.pair .give .label{color:var(--muted)}

/* ===== 横串の1数値 ============================================================
   モンスト: 一番大きい活字は見出しではなく「いま起きたこと」。
   ポケモンGO: ラベルは数字の 48%・明度で大きく引き離す（L* で 1.72 倍）。
   teatime の 墨 L*12.4 / muted L*45.0 は 3.62 倍で、既にもっと開いている。
   足りなかったのは**サイズ比のほう**だったので、数字を 28px / ラベルを 11px にした。 */
.stats{display:flex;margin-top:24px;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.stat{flex:1 1 0;min-width:0;padding:14px 0}
.stat+.stat{border-left:1px solid var(--rule);padding-left:14px}
.sv{display:block;font-family:var(--num);font-size:28px;font-weight:900;line-height:1;font-variant-numeric:tabular-nums}
.sl{display:block;margin-top:6px;font-size:11px;font-weight:700;color:var(--muted);line-height:1.45}
.stuck{margin-top:12px;font-size:13px;color:var(--muted)}
.stuck strong{color:var(--ink);font-weight:800}

section{display:block;margin-top:56px;scroll-margin-top:16px}
.section-title{font-size:19px;font-weight:800;margin-bottom:32px}
h2{font-size:20px;line-height:1.6;margin:32px 0 16px;font-weight:800}
h3{font-size:17px;margin:20px 0 8px;font-weight:800}
h4{font-size:16px;margin:16px 0 8px;font-weight:800}
section>h2:first-child{margin-top:0}
section p+p{margin-top:16px}
section ul,section ol{margin:16px 0;padding-left:28px}
section li+li{margin-top:8px}
strong,b{font-weight:800}
blockquote{margin:20px 0;padding-left:14px;border-left:3px solid var(--rule);color:var(--muted)}
code{font-family:var(--num);font-size:14px;padding:0 4px}
.tw{overflow-x:auto;margin:16px 0}
table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.6}
th,td{padding:10px 8px;text-align:left;vertical-align:top;border-bottom:1px solid var(--rule);overflow-wrap:anywhere}
th{font-weight:800;color:var(--muted);font-size:12px}
/* 警告は文字と帯だけ。面にしない（ウマ娘には赤い危険ボタンが無い）。 */
.blank,.risk{color:var(--red);font-weight:800}
.risk{font-variant-emoji:text}
.assume{font-weight:800}
.guess{color:var(--muted);font-size:14px}
/* 唯一の「進む」ボタン。色はこの1か所と .take だけに出る。
   押下 scale(.94)/70ms は4本の分解で全部一致した値。
   戻りは cubic-bezier(.34,1.56,.64,1)（3本一致）。読み物なので JS は足さない＝
   押し返しの行き過ぎは出ない。**縮んで戻るところまで**が、JS 無しで出せる限界。 */
a.btn{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:48px;padding:10px 20px;border-radius:10px;background:var(--main);color:var(--on-main);font-weight:800;text-decoration:none;transition:transform 180ms cubic-bezier(.34,1.56,.64,1),filter 180ms ease-out}
a.btn:active{transform:scale(.94);filter:brightness(.93);transition-duration:70ms;transition-timing-function:cubic-bezier(.4,0,1,1)}
hr.slide{border:0;border-top:1px solid var(--rule);margin:32px 0}
/* 次の一手（また開く理由）。ウマ娘の仕掛けは「閉じる直前に次の約束を見せる」で、
   報酬の大きさではなく**次に来る理由が今この画面に見えている**ことが効く。
   ここは既に文言が入っているので、枠だけ与える——帯も色も付けない。
   成果物に報酬演出を足すと、議論の結論がゲームの進捗に見える。 */
.next{margin-top:56px;border-top:1px solid var(--rule);padding-top:24px}
.next .k{color:var(--muted)}
.next p.n{margin-top:8px;font-size:15px;line-height:1.75}
.next strong{font-weight:800}
.next a{color:inherit;text-underline-offset:4px}
footer{margin-top:56px;border-top:1px solid var(--rule);padding-top:16px;color:var(--muted);font-size:12px;line-height:1.7}
footer p+p{margin-top:16px}
@media(max-width:640px){.wrap{padding:16px}h1,.adopted{font-size:27px}.c{font-size:15px;line-height:1.65}.tw table{min-width:560px}.sv{font-size:25px}.pair p{font-size:16px}}

/* ===== 畳んだ節を開く ==========================================================
   ウマ娘:「出だしは元気よく、閉じるときは目立たせずすっと消える」。
   人は「出た」は見たいが「消えた」は見たくない。だから**開くときだけ動かす**。
   details の高さアニメは移さない——iOS Safari には interpolate-size も
   transition-behavior:allow-discrete も無く、JS 無しでは動かない。
   成果物は依存ゼロの単一 HTML で JS を1行も持っていない。読み物に JS を
   足してまで移す価値は無い。中身が 240ms で入ってくるだけで、因果は足りている。 */
.doc{border-top:1px solid var(--rule);padding:0}
.doc>summary{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:56px;padding:16px 0;cursor:pointer;list-style:none;font-size:16px;-webkit-tap-highlight-color:transparent;transition:background 180ms ease-out}
.doc>summary::-webkit-details-marker{display:none}
.doc>summary:active{background:color-mix(in srgb,var(--ink) 7%,transparent)}
/* 右端の小さい丸チップが「ここは触れる」を言う。
   ポケモンGO 実測の逆転（一覧カード 19pt ／ 詳細シート 5.7pt）＝
   **小さい板はつまめるモノ、大きい板は下敷き。** 幅いっぱいの summary は丸めない。 */
.doc>summary::after{content:"読む";flex:0 0 auto;min-height:32px;padding:6px 14px;border-radius:10px;border:1px solid var(--main);color:var(--main);font-size:12px;font-weight:800;line-height:1.6}
.doc[open]>summary::after{content:"閉じる";border-color:var(--rule);color:var(--muted)}
.doc[open]>summary{border-bottom:1px solid var(--rule)}
.doc[open]>*:not(summary){animation:enter 240ms cubic-bezier(.2,.9,.3,1) both}
@keyframes enter{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.doc>*:last-child{margin-bottom:32px}
h1.adopted.long{font-size:27px}
h1.adopted.xlong{font-size:22px;line-height:1.6}

@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important}}

@media print{
:root{color-scheme:light;--paper:#f4f1ea;--ink:#23201c;--muted:#6f6a60;--rule:#ded8c9;--red:#9b3b2f;--main:#3f6b26;--on-main:#f4f1ea}
@page{margin:16px}
body{font-size:11pt;line-height:1.65}.wrap{max-width:none;padding:0}
section{display:block;break-before:page;margin-top:32px}
h2,h3,h4{break-after:avoid}.pair,.stats,tr,blockquote{break-inside:avoid}
.tw{overflow:visible}.tw table{min-width:0}thead{display:table-header-group}
/* 白黒で刷っても対比が残るように、取る側を面から左の太い罫に落とす。 */
.pair .take{background:none;color:var(--ink);border-left:6px solid var(--main);padding-left:10px}
.pair .take .label{color:var(--muted);opacity:1}
.pair .give{border:0;border-left:1px solid var(--main);padding-left:15px}
.doc[open]>*:not(summary){animation:none}
.doc>summary::after{border:0;padding:0}
a.btn{background:none;color:var(--ink);border:1px solid var(--ink);padding:4px 10px}
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
<h1 class="adopted {adopted_class}">{adopted}</h1>
<div class="condition"><p class="k">成り立つ条件</p><p class="c">{condition}</p></div>
<div class="choices" aria-label="取るものと手放すもの">{pairs}</div>
</div>
{stats}

{sections}
{next_up}
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
    # **横串の1数値を3つ、数字だけ大きく出す。** 文章に埋めると数字が飛び込まない。
    if count is not None:
        un = str(count)
    elif rate is not None:
        un = f"{int(rate * 100)}%"
    else:
        un = "—"
    stats = (
        '<div class="stats" aria-label="この議論の数">'
        f'<div class="stat"><span class="sv">{m.get("abandonments", 0)}</span>'
        '<span class="sl">捨てた案</span></div>'
        f'<div class="stat"><span class="sv">{un}</span>'
        '<span class="sl">理由が言葉に<br>なっていない</span></div>'
        f'<div class="stat"><span class="sv">{len(structured.get("gaps", []))}</span>'
        '<span class="sl">埋めるべき空白</span></div>'
        '</div>'
        f'<p class="stuck">詰まっている所：<strong>{STUCK.get(st, "未入力")}</strong></p>')
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
    sections = []
    for i, doc in enumerate(docs):
        # **本文の見出しと文言は保ち、目次と同じ文書名で識別する。**
        body = md(doc["text"]).replace(
            "⚑", '<span class="risk" aria-label="高リスク">⚑&#xfe0e;</span>')
        # **4文書を全部ぶちまけない。** 開いた人だけが読む。
        # プロトタイプだけは開いておく（触る導線なので畳むと死ぬ）。
        openness = " open" if doc["key"] == "proto" else ""
        sections.append(
            f'<details class="doc" id="doc-{i}"{openness}>'
            f'<summary class="section-title">{html.escape(doc["title"])}</summary>'
            f'{body}</details>')
    # **次に何が見られるかを、1行だけ予告する。** 架空の希少性で戻らせない。
    # 手放した価値が1つも無ければ、何も出さない（予告を作文しない）。
    first = next((a for a in structured.get("abandonments", [])
                  if a.get("sacrificed_value")), None)
    next_up = ""
    if first:
        next_up = ('<section class="next"><p class="k">次の一手</p>'
                   f'<p class="n">もう1本録ると、今日手放した'
                   f'<strong>{_inline(first["sacrificed_value"])}</strong>が'
                   '次も手放されるか、順位が入れ替わるかが見られます。'
                   '<br><a href="/archive">これまでの議論を見る</a></p></section>')
    d = structured.get("decision") or {}
    # **長い一行は、大きい活字で出すと6行の壁になる。** 字数で級数を落とす
    adopted_text = d.get("adopted") or "まだ決まっていません"
    adopted_class = "lead" + ("" if len(adopted_text) <= 40 else " long" if len(adopted_text) <= 80 else " xlong")
    return PAGE.format(
        title=html.escape(title), css=CSS, src=html.escape(source),
        stamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        model=html.escape(model_label),
        adopted=_inline(adopted_text), adopted_class=adopted_class,
        condition=_inline(d.get("condition") or "未入力（議論で出ていない）"),
        pairs=pairs, stats=stats, sections="".join(sections), next_up=next_up)
