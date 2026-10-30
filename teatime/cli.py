"""teatime — 席を外している間に、議論を事業の形へ起こす。

    python3 -m teatime.cli tea <transcript.txt|audio.m4a>

**起動したら席を外してよい。** 進捗は細かく出さない（眺める時間を作らないため）。
"""
import json
import pathlib
import sys
import time

from . import deliver, extract, model, prototype, render, share

AUDIO = {".m4a", ".mp3", ".wav", ".mp4", ".aac", ".caf", ".webm", ".ogg"}


def tea(path, keys=None, video=False, out_dir=None):
    model.reset_usage()  # **頭で数え直す。** 前の回の退避を次の回に引きずらない
    src = pathlib.Path(path).expanduser()
    out_dir = (pathlib.Path(__file__).resolve().parent.parent / "out"
               if out_dir is None else pathlib.Path(out_dir).expanduser())
    out_dir.mkdir(parents=True, exist_ok=True)

    if src.suffix.lower() in AUDIO:
        from . import transcribe
        print("文字起こし中…")
        text = transcribe.run(src)
        (out_dir / f"{src.stem}.txt").write_text(text, encoding="utf-8")
    else:
        text = src.read_text(encoding="utf-8")
    text = text.strip()
    if len(text) < 80:
        sys.exit("記録が短すぎます。議論の記録を渡してください。")

    print(f"お茶をどうぞ。戻ってきたら見られるようにしておきます。（{model.label()}）")
    t0 = time.time()

    structured = extract.extract(text)
    (out_dir / f"{src.stem}.extract.json").write_text(
        json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")

    docs = deliver.build(text, structured, keys)
    for d in docs:
        (out_dir / f'{src.stem}.{d["key"]}.md').write_text(d["text"], encoding="utf-8")

    print("仮置きを決めて、プロトタイプを作っています…")
    proto = prototype.build(text, structured)
    proto_name = f"{src.stem}.proto.html"
    (out_dir / proto_name).write_text(proto["html"], encoding="utf-8")
    proto["url"] = proto_name
    (out_dir / f"{src.stem}.assumptions.json").write_text(
        json.dumps(proto["assumptions"], ensure_ascii=False, indent=2), encoding="utf-8")

    page = render.render(f"{src.stem} — お茶の間の仕事", src.name,
                         model.label(), docs, structured, proto)
    dest = out_dir / f"{src.stem}.html"
    dest.write_text(page, encoding="utf-8")

    if video:
        print("解説動画を作っています…")
        try:
            from . import narrate
            print(f"動画: {narrate.build(out_dir / src.stem, structured, docs)}")
        except Exception as error:  # noqa: BLE001
            # **資料は渡す。** 動画は5つ目の成果物で、これが無くても回は成立する
            print(f"動画は作れませんでした（{type(error).__name__}: {error}）")

    print(f"外に見せる1枚: {share.write(out_dir / src.stem)}")

    m = structured["metrics"]
    deterministic = sum(r.get("type") == "rebuilt" and r.get("source") == "taste"
                        for r in structured.get("ranking_source", []))
    ratio = m.get("taste_coverage_ratio")
    coverage = f"{ratio:.1%}" if ratio is not None else "未算出"
    print(f'できました（{int(time.time()-t0)}秒）: {dest}')
    print(f'放棄点 {m["abandonments"]} / 理由が言葉になっていない {m["unverbalized"]} '
          f'/ 空白 {len(structured.get("gaps", []))} / 仮置き {len(proto["assumptions"])} '
          f'/ 序列の作り直し {m["rebuilt"]}（うち決定論 {deterministic}） '
          f'/ taste被覆率 {coverage}')
    print(f'プロトタイプ: {out_dir / proto_name}')
    # **UX 試験は作る側が見るもの。** 成果物からは外したが、端末には出す
    counts = (proto.get("ux") or {}).get("summary")
    if counts:
        print(f'UX 試験: fail {counts["fail"]} / pass {counts["pass"]} / skip {counts["skip"]}')
    else:
        print("UX 試験: できませんでした")
    return dest


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "tea":
        sys.exit("使い方: python3 -m teatime.cli tea <transcript.txt|audio.m4a> [doc,doc] [--no-video]\n  解説動画まで作るので .venv/bin/python で実行してください（Pillow が要ります）")
    args = sys.argv[3:]
    video = "--no-video" not in args   # **既定で作る。** 切るのは --no-video
    only = next((a.split(",") for a in args if not a.startswith("--")), None)
    tea(sys.argv[2], only, video)
