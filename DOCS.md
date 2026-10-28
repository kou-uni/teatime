# teatime ドキュメント一覧

> 2026-10-28 作成。**散らばっている検討物の索引。** 中身はここに写さない（写すと二重管理になる）。
> 現在地と状態は vault のハブ `~/Obsidian/ThoughtLog/projects/teatime.md` に上書きする。

## 1. 現在地（まずこれを読む）

| 置き場 | 中身 |
|---|---|
| `~/Obsidian/ThoughtLog/projects/teatime.md` | **ハブ。** いまの形・確かめたこと・未確認・次の一手 |
| `~/projects/teatime/README.md` | プロダクト説明。「採択ではなく放棄を測る」「3つの層を混ぜない」 |
| https://github.com/kou-uni/teatime | コード（public）。Issue の `backlog` ラベルがバックログ |
| https://mac-studio.taila649e1.ts.net:8777/ | スマホからの録音入口。`/archive` が過去の回 |

## 2. 設計の根拠（vault・なぜそう作るか）

| ノート | 中身 |
|---|---|
| `concepts/teatime-what-to-measure.md` | **中核。** 議論から測る7つの観測量と、独自性の在り処 |
| `concepts/taste.md` | taste を4成分に分解し、観測できる形にする |
| `decisions/teatime-as-the-product-name.md` | 名前は teatime。taiwa は1拍目に降格 |
| `insights/20261027-taste-is-extracted-as-a-tradeoff.md` | 評点では出ない。「何を手放したか」で出る |
| `insights/20261027-four-kinds-of-subjective-judgment.md` | 意味づけ4種類。4つ目だけがイノベーションを生む |
| `insights/20261027-value-uncertainty-has-only-deliberation.md` | 価値の不確実性だけ、手が「議論」しかない |
| `insights/20261020-scaling-removes-taste.md` | スケールは taste を取り除く。だから小さい規模で作る |
| `insights/20261020-finishing-is-going-to-production.md` | 終わらせる＝本番に出して人を巻き込む |
| `insights/20261028-dont-let-the-model-write-the-whole-page.md` | 1枚丸ごとをモデルに書かせない。枠を決め打ちする |
| `questions/can-taste-log-filter-the-course.md` | **未解決。** taste ログを選別に使ってよいか |
| `interests/taiwa.md` | 前身の関心ハブ |
| `interests/startup-training-notes-analysis.md` | 起業家研修のメモ分析 |

（vault のルートは `~/Obsidian/ThoughtLog/`）

## 3. 研修（授業）側 — `~/projects/Entrepreneurship-and-Getting-Things-Done`

ハブ: `~/Obsidian/ThoughtLog/projects/entrepreneurship-course.md` ／ 入口: `~/ch/entrepreneurship`

| ファイル | 中身 | teatime との関係 |
|---|---|---|
| `final/product-taiwa.md` | Taiwa — the human only talks; the AI builds the business | **提出物。名前が taiwa のまま** |
| `final/business-model.md` | ビジネスモデル | 同上 |
| `final/competitive-analysis-and-mvp.md` | 競合分析と MVP 設計 | 同上 |
| `final/week5-submission-form.md` | Week 5 提出フォームの記入内容 | 提出済みの文面 |
| `final/README.md` | ファイナルプロジェクト（評価50%）の要件 | 締切と採点軸 |
| `interviews/README.md` | インタビュープロジェクト（評価50%） | **インタビュー5人がまだ** |
| `sessions/05-20261020-harper-reed-agentic-coding.md` | 第5回 Harper Reed | 「本番に出す」の出所 |
| `sessions/01-…` `02-…` | 第1〜2回のメモ | |
| `readings/w01-02-vaughn-tan-innovation-and-not-knowing.md` | Vaughn Tan | **4種類の不確実性の出所** |
| `readings/w01-01-joi-ito-ted2014-now-ist.md` | Joi Ito now-ist | |
| `readings/w02-assessment-reflection.md` | 診断レポートへのリフレクション | **未回答** |
| `labs/02-personality-pairing.md` | ラボ W2 | **未実施** |
| `HANDOFF.md` | 引き継ぎメモ（10-19） | 授業側の現在地 |
| `AI-UPDATE.md` / `README.md` / `english-track.md` | 授業の枠組み | |

**セッションノートは 01・02・05 だけ。** 03・04・06 が欠番。
第6回（10-27 Vaughn Tan）は vault の insights 3本に入っているが、`sessions/` には無い。

## 4. コードと生成物 — `~/projects/teatime`

| 置き場 | 中身 |
|---|---|
| `teatime/extract.py` | 一次資料の抽出（放棄点・序列・詰まり） |
| `teatime/render.py` / `deliver.py` | 4文書 → HTML1枚 |
| `teatime/prototype.py` | 動くプロトタイプ＋仮置き一覧 |
| `teatime/server.py` / `archive.py` / `web/record.html` | スマホの録音入口とアーカイブ |
| `teatime/transcribe.py` / `narrate.py` / `model.py` / `cli.py` | 文字起こし・読み上げ・配線 |
| `out/` | 生成物（**git に入れない**）。10-28 の `seisaku` `rec-20261028-170026` `kensho` が最新 |
| `samples/seisaku.txt` `samples/20261007-taiwa-dictation.txt` | 手元のサンプル入力 |

## 5. 前身 — `~/projects/taiwa`（10-07。3役の要約器）

`out/*.summary.md` / `*.questions.md` / `*.canvas.md`。**要約・論点整理をやめた**ので、
いまは「何をやめたかの証拠」としてだけ残す。

## 6. 過去の会話ログ（重い。必要なときだけ grep する）

`grep -rl teatime ~/.claude/projects/*/*.jsonl` で約50本。大きいものだけ:

- `-Users-uni/67458353-926a-….jsonl`（38MB・起業とやることの科学）
- `-Users-uni/ed5d45d7-bb2a-….jsonl`（6MB）
- `-Users-uni/4a116a15-4e4b-….jsonl`（5MB）
- `-Users-uni-ch-seeds/f5a642e0-0c33-….jsonl`（4MB）
- `-Users-uni-projects-teatime/` 配下に 10-28 の作業ログ40本ほど

蒸留済みの切片は `~/Obsidian/ThoughtLog/_meta/inbox/slices/`。

## 7. 気づいたずれ

- **授業の提出物は `taiwa` 名のまま。** リネームするか、taiwa を1拍目として残すかは未決
- **セッションノート 03・04・06 が無い**（第6回は insights だけある）
- **まだ無い文書:** 決めた「作らないもの4件」の Issue 本文、言い当てテストの手順、実会議での1回目の記録
