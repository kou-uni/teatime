"""振り返り（品評）— **戻ってきた人が置いていくもの。**

7つの観測量のうち、⑥手放した価値の名前 と ⑦序列の反転 は議論からは取れない。
**人が資料を見て、戻ってきて置いていく。** ここはその口。

    .venv/bin/python -m teatime.review out/<stem> <品評の録音>
    .venv/bin/python -m teatime.review out/<stem>        # <stem>.review.txt が既にあるとき

出すもの: `<stem>.review.json` / `<stem>.review.md` / `<stem>.review.mp4`

**作文しない。** 言われていない判定は出さない。反転が無ければ「無い」と出す
（反転が0であること自体が、この部屋についての観測なので）。
**動画の台本はモデルに書かせない。** 文言はここで決め、モデルは抽出だけをする。
"""
import json
import pathlib
import sys

from . import model

SYSTEM = (
    "あなたは品評の記録係です。"
    "**判定も理由も創作しない。** 言われていないものは空配列で返す。"
    "`evidence` は文字起こしからの逐語引用。要約した引用を作らない。"
    "引用できないものは出さない。"
    "出力は JSON のみ。"
)

PROMPT = """戻ってきた人が、成果物を見ながら品評しました。その録音の文字起こしです。

**取り出すのは4つだけ。**

1. **判定（verdicts）** — どの成果物を「結構」（これでいく）、「もう一服」（出し直し）としたか。
   `target` は実際に触れられたものだけ。**触れられていない成果物を並べない。**

2. **手放した価値（released）** — 品評は「良い／悪い」では記録しない。
   **「◯◯を取るために、△△を手放す」**の形になったものだけ。
   その形になっていない感想は取らない（取らないのが正しい）。

3. **序列の反転（reversals）** — 議論のときの順位（下の before_ranking）と**逆**になったものだけ。
   **無理に見つけない。反転が無いことは、立派な観測です。**

4. **次の一手（next）** — 本人が口に出したものだけ。最大3件。

出力:
{{"verdicts":[{{"target":"","verdict":"結構","why":"","evidence":""}}],
 "released":[{{"released":"","taken":"","evidence":""}}],
 "reversals":[{{"higher":"","lower":"","was":"","evidence":""}}],
 "next":[""],
 "unsaid":""}}

`unsaid` は「品評されなかったが、判断が要るもの」を1行。無ければ空文字。

---
## 議論のときの順位（before_ranking）
{ranking}

## 採った案と、それが成り立つ条件
{decision}

## 品評の文字起こし
{review}
"""


def _ranking_text(structured):
    rows = structured.get("ranking") or []
    return "\n".join(f'- {r.get("higher")} ＞ {r.get("lower")}' for r in rows) or "（記録なし）"


def _decision_text(structured):
    d = structured.get("decision") or {}
    return (f'採った案: {d.get("adopted") or "決まっていない"}\n'
            f'成り立つ条件: {d.get("condition") or "決まっていない"}')


def analyze(structured, review_text):
    """品評の文字起こしから ⑥⑦と判定を取る。**ここだけがモデルを使う。**"""
    out = model.ask_json(SYSTEM, PROMPT.format(
        ranking=_ranking_text(structured),
        decision=_decision_text(structured),
        review=review_text))
    for k in ("verdicts", "released", "reversals", "next"):
        out[k] = out.get(k) or []
    out["unsaid"] = out.get("unsaid") or ""
    return out


def document(structured, a):
    """人が読む1枚。**空は空のまま出す。**"""
    d = structured.get("decision") or {}
    L = [f'# 振り返り — {structured.get("topic") or "（主題は記録されていない）"}', ""]
    L += [f'採った案: {d.get("adopted") or "**決まっていない**"}', ""]

    L += ["## 判定", ""]
    if a["verdicts"]:
        L += ["| 対象 | 判定 | 理由 | 本人の言葉 |", "|---|---|---|---|"]
        L += [f'| {v.get("target","")} | {v.get("verdict","")} | {v.get("why","")} '
              f'| {v.get("evidence","")} |' for v in a["verdicts"]]
    else:
        L += ["判定は言葉になっていません。"]

    L += ["", "## 手放した価値", ""]
    L += ([f'- **{r.get("released")}** を手放して、**{r.get("taken")}** を取る '
           f'— 「{r.get("evidence","")}」' for r in a["released"]]
          or ["トレードオフの形で言われたものはありません。",
              "（「良い／悪い」で話されたものは、ここには残りません）"])

    L += ["", "## 序列の反転", ""]
    L += ([f'- **{r.get("higher")} ＞ {r.get("lower")}**（議論のときは {r.get("was","逆")}）'
           f' — 「{r.get("evidence","")}」' for r in a["reversals"]]
          or ["**反転はありません。** この回では、順位は動いていません。"])

    L += ["", "## 次の一手", ""]
    L += ([f"- {n}" for n in a["next"]] or ["言われていません。"])
    if a["unsaid"]:
        L += ["", "## 品評されなかったが、判断が要るもの", "", a["unsaid"]]
    return "\n".join(L) + "\n"


def _cut(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[:n - 1] + "…"


def slides(structured, a):
    """**台本はここで決める。** モデルに書かせない（議論に無いことが混ざるため）。"""
    topic = structured.get("topic") or "この議論"
    out = [{
        "title": "この回の振り返り",
        "lines": [_cut(topic, 22)],
        "narration": f"{_cut(topic, 40)}。その成果物を見て、戻ってきた人が置いていった判断です。",
    }]

    ok = [v for v in a["verdicts"] if v.get("verdict") == "結構"]
    ng = [v for v in a["verdicts"] if v.get("verdict") != "結構"]
    if a["verdicts"]:
        out.append({
            "title": "判定",
            "lines": ([f'結構: {_cut("、".join(v.get("target","") for v in ok), 18)}'] if ok else [])
                     + ([f'もう一服: {_cut("、".join(v.get("target","") for v in ng), 16)}'] if ng else []),
            "narration": (f'結構としたのが{len(ok)}件、もう一服が{len(ng)}件です。'
                          + (f'出し直すのは、{_cut(ng[0].get("target",""), 20)}。'
                             f'{_cut(ng[0].get("why",""), 50)}' if ng else "")),
        })
    else:
        out.append({"title": "判定", "lines": ["言葉になっていません"],
                    "narration": "どれを採るかは、この品評では言葉になりませんでした。"})

    if a["released"]:
        r = a["released"][0]
        out.append({
            "title": "手放した価値",
            "lines": [_cut(f'{x.get("released")} → {x.get("taken")}', 22)
                      for x in a["released"][:3]],
            "narration": (f'{_cut(r.get("released"), 20)}を手放して、'
                          f'{_cut(r.get("taken"), 20)}を取りました。'
                          'これが、次に作るものの受け入れ条件になります。'),
        })
    else:
        out.append({
            "title": "手放した価値", "lines": ["記録なし"],
            "narration": "トレードオフの形で言われたものはありませんでした。"
                         "良い悪いの感想は、ここには残りません。",
        })

    if a["reversals"]:
        r = a["reversals"][0]
        out.append({
            "title": "序列の反転",
            "lines": [_cut(f'{x.get("higher")} ＞ {x.get("lower")}', 22)
                      for x in a["reversals"][:3]],
            "narration": (f'{_cut(r.get("higher"), 16)}が、{_cut(r.get("lower"), 16)}の上に来ました。'
                          '議論のときとは逆です。この部屋の基準が動いた証拠です。'),
        })
    else:
        out.append({
            "title": "序列の反転", "lines": ["反転なし"],
            "narration": "順位は議論のときのままで、入れ替わりはありません。"
                         "動かないことも、この部屋についての記録です。",
        })

    out.append({
        "title": "次の一手",
        "lines": [_cut(n, 22) for n in a["next"][:3]] or ["言われていません"],
        "narration": (f'次は、{_cut(a["next"][0], 50)}。' if a["next"]
                      else "次の一手は、この品評では言われませんでした。"),
    })
    return out


def run(stem, audio=None, on_step=None, make_video=True):
    """品評の録音 → 文字起こし → ⑥⑦と判定 → 1枚 → 動画。"""
    stem = pathlib.Path(stem)
    base, out_dir = stem.name, stem.parent
    structured = json.loads(
        (out_dir / f"{base}.extract.json").read_text(encoding="utf-8"))

    txt = out_dir / f"{base}.review.txt"
    if audio:
        if on_step:
            on_step("rtranscribe")
        from . import transcribe
        txt.write_text(transcribe.run(pathlib.Path(audio)), encoding="utf-8")
    if not txt.exists():
        sys.exit(f"品評の記録がありません: {txt}")
    review_text = txt.read_text(encoding="utf-8").strip()
    if len(review_text) < 40:
        raise ValueError("品評が短すぎます（話が拾えていません）")

    if on_step:
        on_step("rextract")
    a = analyze(structured, review_text)
    (out_dir / f"{base}.review.json").write_text(
        json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    md = out_dir / f"{base}.review.md"
    md.write_text(document(structured, a), encoding="utf-8")

    mp4 = None
    if make_video:
        if on_step:
            on_step("rvideo")
        from . import narrate
        mp4 = out_dir / f"{base}.review.mp4"
        narrate.assemble(slides(structured, a), out_dir / f"{base}.review.video", mp4,
                         foot="teatime — 品評の記録だけから作っています")
    return {"analysis": a, "md": md, "mp4": mp4,
            "released": len(a["released"]), "reversals": len(a["reversals"]),
            "verdicts": len(a["verdicts"])}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("使い方: python3 -m teatime.review out/<stem> [品評の録音] [--no-video]")
    r = run(sys.argv[1],
            next((x for x in sys.argv[2:] if not x.startswith("--")), None),
            make_video="--no-video" not in sys.argv)
    print(f'判定 {r["verdicts"]} / 手放した価値 {r["released"]} / 序列の反転 {r["reversals"]}')
    print(r["md"])
    if r["mp4"]:
        print(r["mp4"])
