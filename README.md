# teatime

**席を外している間に、議論を事業の形へ起こす。**

スマホでタップ → 録音 → 議論が終わったらもう一度タップ → 席を外す → 戻ると資料ができている。

## これが他と違うところ

議事録でも要約でもない。**採択ではなく放棄を測る。**

ふつうの議事録は「Aにしよう」で終わる。teatime が取るのは**「だからBは諦める」**の側。
理由は3つ:

- **トレードオフを書かない決定は実行できない。** その場にいなかった人が、黙って捨てたものを足し戻す
- **好み（状態）は機械が推定できて、貯めるほど過去の重心に腐る。放棄（出来事）は推定できない**
- **★評価や承認ボタンのUIでは「捨てた」という出来事がそもそも発生しない。** だから複製されない

→ 設計の根拠: `~/Obsidian/ThoughtLog/concepts/teatime-what-to-measure.md`

## 3つの層を混ぜない

| 層 | 中身 | 人が見るか |
|---|---|---|
| 一次資料 | 放棄点・序列・詰まりの型（`*.extract.json`） | **見せない** |
| 成果物 | 採った案 ＋ 成り立つ条件 ＋ 4つの文書 | **これだけ見る** |
| 蓄積 | 手放した価値、序列の反転 | 本人が見たいときだけ |

**記録に無いことは埋めない。**「未入力（議論で出ていない）」と赤で出す。
リーンキャンバスは「埋まった欄 N / 9」が出る。**その赤が、次に話すことになる。**

## 使う

```bash
cd ~/projects/teatime

# 文字起こしから
python3 -m teatime.cli tea samples/20261007-taiwa-dictation.txt

# 録音から（uni2 の mlx-whisper を使う）
python3 -m teatime.cli tea ~/Downloads/会議.m4a

# 動画つき（Pillow が要るので .venv で）
.venv/bin/python -m teatime.cli tea samples/kensho.m4a --video

# スマホから（タップで録音）
.venv/bin/python -m teatime.server --tailnet     # https://mac-studio.taila649e1.ts.net:8777/
TEATIME_VIDEO=1 .venv/bin/python -m teatime.server --tailnet   # 動画も作る
```

**スマホのマイクは https でないと開かない。** `--tailnet` は tailscale の証明書を取って
**別ポート(8777)で待つだけ**で、Funnel の向き先（443 → 8402 / yohaku）には一切触れない。

## 出るもの（5つ）

| ファイル | 中身 |
|---|---|
| `out/<名前>.html` | **スマホ前提の1枚。** 下の4つをタブで。印刷でA4に展開 |
| `.pitch.md` | 投資家向け — エレベーターピッチ / 構想 / 独自性 / マネタイズ / リーンキャンバス |
| `.product.md` | プロダクト仕様 — **受け入れ条件は「手放した価値」から作る** |
| `.project.md` | 次のアクション / 課題 / **埋めるべき空白** / 聞き返すこと |
| `.feedback.md` | 参加者へ返すスライド。**評価も採点もしない。観測だけ返す** |
| `.mp4` | 上記をまとめた解説動画（`--video`） |

## 中身

```
teatime/model.py       呼び出し口。既定は Claude CLI。TEATIME_BACKEND=ollama で裏方の Qwen
teatime/transcribe.py  録音 → 文字起こし（uni2 の mlx-whisper を借りる）
teatime/extract.py     一次資料。**ここが急所**
teatime/deliver.py     4つの文書
teatime/render.py      スマホ前提の1枚
teatime/narrate.py     スライド + 読み上げ + 動画
teatime/server.py      スマホの口
web/record.html        タップで録音する画面
```

## 測り方（この設計自体が当たっているかの検証）

**言い当てテスト**: 10ラウンドぶんの放棄ログから、その部屋が手放し続けている価値を
1行で言い当て、本人に○×させる。当たらなければ、貯まっているのは taste ではなくただのログ。

補助:
- **非言語化率が 0 に近い** → その部屋に teatime は要らない
- **序列の反転が長期間 0** → 丸まっている。出す膳の分散を上げる側に倒す

## 確かめたこと / まだのこと

**確かめた（2026-10-28、実際に通した）**
- 文字起こし（`samples/20261007-taiwa-dictation.txt`）→ 4文書 + HTML。187秒
- 音声（m4a）→ uni2 で文字起こし → 抽出 → 4文書 → HTML → 動画(2分05秒)
- 抽出が借用（「普通は」）と作り直し（「そもそも本当に全部いるのか」）を**撃ち分けた**
- リーンキャンバスが9欄中3欄だけ埋め、残りを「未入力」と出した（**作文で埋めなかった**）
- サーバ: アップロード → 文字起こし → 分析 → レポートURL

**まだ**
- **スマホの実機で録音していない。** `web/record.html` はブラウザ実機未検証
- **ElevenLabs の鍵がこの Mac に無い。** いまの読み上げは macOS の `say`（Kyoko）。
  `ELEVENLABS_API_KEY` を入れれば自動で切り替わる（`narrate.py` の `_key()`）
- **実際の会議で1回も使っていない**
- リアルタイム版は未着手
