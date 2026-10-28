"""一次資料の抽出。**人には見せない層。**

teatime が独自に持つのはここ。議事録でも要約でもなく、
**どの価値が、どの価値のために手放されたか**を録音から取り出す。
→ ~/Obsidian/ThoughtLog/concepts/teatime-what-to-measure.md
"""
import json

from . import model

SYSTEM = (
    "あなたは、議論の録音の文字起こしを渡された分析者です。"
    "文字起こしは言い間違い・重複・誤変換・句読点なしを含みます。"
    "**誤変換を直すことに時間を使わず、話者が言おうとしたことを取ってください。**"
    "最重要の規則: **無いものを作らない。**"
    "議論に出ていないことを、もっともらしく補わないでください。"
    "出ていなければ空配列を返し、`gaps` に『議論に出ていない』として挙げてください。"
)

PROMPT = """次の議論の記録から、**採択ではなく放棄**を取り出してください。

ふつうの議事録は「Aにしよう」で終わります。teatime が取るのはその先、
**「だからBは諦める」**の側です。

## 取るもの

1. `abandonments` — **放棄点**。議論の中で選択肢が落ちた瞬間。
   - `dropped` 落ちた案 / `kept` 代わりに残った案
   - `sacrificed_value` 手放した価値 / `gained_value` 取った価値
     （抽象名詞1語〜数語で。例: 速さ / 網羅 / 低コスト / 一貫性 / 自由度 / 確実性 / 範囲の広さ）
   - `verbalized` その場で**理由が言葉になっていたか** true/false
   - `evidence` 根拠になった発言の引用（文字起こしのまま。短く）
   - **理由が言葉になっていない放棄ほど重要です。落とさないでください。**

2. `ranking` — 発言から**復元できる価値の順位**。`higher` / `lower` / `evidence`。
   事実や因果ではなく、**何を上に置いたか**だけ。

3. `ranking_source` — その順位の出どころ。各項目 `value` と `type`。
   - `borrowed` 外から借りた順位。合図「普通は」「一般的に」「他社では」「標準」「ベストプラクティス」
   - `rebuilt` その場で作り直した順位。合図「そもそも」「本当に要る？」「前提がおかしい」「逆では」
   - `cue` 実際にあった合図の語。無ければ null
   - **rebuilt はめったに起きません。無ければ空で構いません。**

4. `stuck` — この議論が止まっている場所。`type` は次の4つから1つ。
   `action`（取りうる手がわからない）/ `outcome`（どうなるかがわからない）/
   `causation`（何が何を起こすかわからない）/ `value`（どちらに価値があるかが決まらない）
   - `evidence` と、`misdirected` （value で詰まっているのに調査や実験の話をしているなら true）

5. `decision` — **成果物の核**。`adopted`（採った案）と
   `condition`（それが成り立つ条件 = 何を取り、何をやらないか。1行）。
   決まっていなければ両方 null。**決まっていないのに決まったことにしない。**

6. `open_questions` — 戻ってきた人に**聞き返すべき問い**。
   理由が言葉になっていない放棄（`verbalized: false`）から作ります。
   「Bを落としたのは、速さのためですか、それとも別の理由ですか」の形。最大5個。

7. `gaps` — **議論に一度も出てこなかった論点**。
   事業の話なら例えば: 誰が金を払うか / いくらか / 誰と競合するか / 最初の1人は誰か /
   いつ失敗と判断するか。**出ていないものだけ**を挙げること。

8. `topic` 一行の主題 / `participants` 話者の数か呼び名（わからなければ null）/
   `care_signal` 対象そのものへの関心の強さ 0〜3（誰にも頼まれていないのに
   具体を語った時間が長いほど高い）と `evidence`

## 出力（この JSON だけ）

{{"topic":"","participants":null,"abandonments":[],"ranking":[],"ranking_source":[],
"stuck":{{"type":"","evidence":"","misdirected":false}},
"decision":{{"adopted":null,"condition":null}},
"open_questions":[],"gaps":[],"care_signal":{{"score":0,"evidence":""}}}}

---
{transcript}
"""


def extract(transcript):
    data = model.ask_json(SYSTEM, PROMPT.format(transcript=transcript))
    data.setdefault("abandonments", [])
    data.setdefault("gaps", [])
    a = data["abandonments"]
    unverb = [x for x in a if not x.get("verbalized")]
    data["metrics"] = {
        "abandonments": len(a),
        "unverbalized": len(unverb),
        # ②非言語化率。これが 0 に近いなら teatime は要らない
        "unverbalized_rate": round(len(unverb) / len(a), 2) if a else None,
        "rebuilt": sum(1 for r in data.get("ranking_source", [])
                       if r.get("type") == "rebuilt"),
    }
    return data


if __name__ == "__main__":
    import pathlib
    import sys
    src = pathlib.Path(sys.argv[1])
    out = extract(src.read_text(encoding="utf-8"))
    print(json.dumps(out, ensure_ascii=False, indent=2))
