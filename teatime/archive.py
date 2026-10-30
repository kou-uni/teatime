"""過去の議論を一覧する1枚 — **アーカイブのリンク集。**

`out/` に溜まった回を、新しい順に並べるだけ。検索も絞り込みも付けない。
**teatime で見たいのは「前にどんな回があったか」より「何を手放し続けているか」**
なので、各行に放棄点の数と非言語化率を出す。回が貯まったら、
この列が縦に読めることが、横断の一次資料になる。

いまはファイルを毎回読んで数えている。回が増えて重くなったら DB（Issue #1）。
"""
import datetime
import html as _h
import json
import pathlib

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1b17;--mut:#6d675d;--line:#e2ddd2;--ac:#8a6a3b;--card:#fff}
@media(prefers-color-scheme:dark){:root{
--bg:#16150f;--fg:#ece7dc;--mut:#9d968a;--line:#322e26;--ac:#c9a46a;--card:#1e1c15}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-size:16px;line-height:1.7;
font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
.wrap{max-width:620px;margin:0 auto;padding:22px 14px 90px}
h1{font-size:20px;margin:.1em 0 .2em}
.sub{color:var(--mut);font-size:12.5px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:14px 16px;margin:12px 0}
.topic{font-size:15.5px;font-weight:650;line-height:1.5}
.when{color:var(--mut);font-size:11.5px;letter-spacing:.06em;margin-bottom:4px}
.nums{display:flex;gap:16px;margin:10px 0 12px;flex-wrap:wrap}
.n b{font-size:19px;font-weight:650;display:block;line-height:1.25}
.n span{color:var(--mut);font-size:11px}
.hi b{color:var(--ac)}
.links{display:flex;gap:7px;flex-wrap:wrap}
a.btn{font-size:13px;text-decoration:none;background:var(--fg);color:var(--bg);
border-radius:5px;padding:7px 13px}
a.btn2{background:transparent;color:var(--fg);border:1px solid var(--line)}
.none{color:var(--mut);font-size:13px}
.back{display:inline-block;margin-top:26px;font-size:13px;color:var(--ac)}
footer{margin-top:34px;border-top:1px solid var(--line);padding-top:14px;
color:var(--mut);font-size:12px}
"""

# 何がどの名前で置かれるか。出す順。
PARTS = [
    ("{s}.html", "レポート", "btn"),
    ("{s}.proto.html", "プロトタイプ", "btn2"),
    ("{s}.mp4", "動画", "btn2"),
    ("{s}.review.md", "振り返り", "btn2"),
    ("{s}.review.mp4", "振り返りの動画", "btn2"),
    ("{s}.txt", "文字起こし", "btn2"),
    ("{s}.pitch.md", "投資家向け", "btn2"),
    ("{s}.product.md", "プロダクト", "btn2"),
    ("{s}.project.md", "プロジェクト", "btn2"),
    ("{s}.feedback.md", "フィードバック", "btn2"),
]


def runs(out):
    """out/ から回を集める。新しい順。"""
    rows = []
    for f in out.glob("*.extract.json"):
        stem = f.name[:-len(".extract.json")]
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        m = d.get("metrics") or {}
        rows.append({
            "stem": stem,
            "topic": d.get("topic") or "（主題は記録されていない）",
            "when": datetime.datetime.fromtimestamp(f.stat().st_mtime),
            "abandonments": m.get("abandonments", len(d.get("abandonments") or [])),
            "unverbalized_rate": m.get("unverbalized_rate"),
            "rebuilt": m.get("rebuilt", 0),
            "gaps": len(d.get("gaps") or []),
            "parts": [(p.format(s=stem), label, cls)
                      for p, label, cls in PARTS
                      if (out / p.format(s=stem)).exists()],
        })
    rows.sort(key=lambda r: r["when"], reverse=True)
    return rows


def _card(r):
    rate = r["unverbalized_rate"]
    rate_s = "—" if rate is None else f"{round(rate * 100)}%"
    links = "".join(
        f'<a class="{cls}" href="/out/{_h.escape(name)}">{label}</a>'
        for name, label, cls in r["parts"]) or '<span class="none">成果物がまだありません</span>'
    return (
        '<div class="card">'
        f'<div class="when">{r["when"].strftime("%Y-%m-%d %H:%M")}</div>'
        f'<div class="topic">{_h.escape(r["topic"])}</div>'
        '<div class="nums">'
        f'<div class="n hi"><b>{r["abandonments"]}</b><span>放棄点</span></div>'
        f'<div class="n"><b>{rate_s}</b><span>非言語化率</span></div>'
        f'<div class="n"><b>{r["rebuilt"]}</b><span>序列の作り直し</span></div>'
        f'<div class="n"><b>{r["gaps"]}</b><span>未入力</span></div>'
        '</div>'
        f'<div class="links">{links}</div></div>')


def page(out):
    rows = runs(out)
    total = sum(r["abandonments"] for r in rows)
    body = "".join(_card(r) for r in rows) or \
        '<p class="none">まだ1回も記録がありません。</p>'
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>これまでの議論</title><style>{CSS}</style></head><body>"
        '<div class="wrap"><h1>これまでの議論</h1>'
        f'<div class="sub">{len(rows)}回 ・ 放棄点 {total}件</div>'
        f"{body}"
        '<a class="back" href="/">← 新しく録る</a>'
        '<footer>放棄点＝捨てた案と採った案の組。'
        '非言語化率＝そのうち理由が言葉になっていなかった割合。'
        '<b>高いほど、その部屋はまだ自分の基準を言えていない。</b></footer>'
        "</div></body></html>")


if __name__ == "__main__":
    print(page(pathlib.Path(__file__).resolve().parent.parent / "out"))
