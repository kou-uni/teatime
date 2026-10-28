"""5つ目の成果物 — 音声解説つきの動画。

スライド（Pillow）＋ ElevenLabs の読み上げ ＋ ffmpeg で1本にする。
**見る人は、その議論に出ていなかった人。** だから中身は「何を手放したか」から始める。

    .venv/bin/python -m teatime.narrate out/<stem>
"""
import json
import os
import pathlib
import subprocess
import sys
import textwrap
import urllib.request

from PIL import Image, ImageDraw, ImageFont

from . import model

W, H = 1920, 1080
BG, FG, MUT, ACC = (251, 250, 247), (29, 27, 23), (109, 103, 93), (138, 106, 59)
FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_L = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
VOICE = os.environ.get("TEATIME_VOICE_ID", "SAz9YHcvj6GT2YYXdXww")
TTS_MODEL = os.environ.get("TEATIME_TTS_MODEL", "eleven_multilingual_v2")

SYSTEM = (
    "あなたは、議論に出ていなかった人へ向けた短い解説動画の構成作家です。"
    "**話し言葉で書くこと。** 読み上げられます。"
    "議論に出ていないことを足さない。空白は空白として読み上げる。"
    "出力は JSON のみ。"
)

PROMPT = """次の分析から、**5〜7枚**の解説動画の台本を作ってください。

並び（この順を守る）
1. この議論は何だったか（1枚）
2. **採った案と、それが成り立つ条件**（1枚。ここが山）
3. **手放したもの**（1〜2枚）
4. **埋めるべき空白**（1枚。未入力のまま読み上げる）
5. 次の一手（1枚）

各スライド
- `title` … 10〜18文字。体言止め
- `lines` … 画面に出す行。**3行以内、1行24文字以内**。多く書かない
- `narration` … 読み上げ。**60〜110文字**。話し言葉。
  箇条書きを読み上げない（画面に出ているものをなぞらない）

出力: {{"slides":[{{"title":"","lines":[],"narration":""}}]}}

---
{core}
"""


def script(structured, docs):
    core = json.dumps({"structured": structured,
                       "feedback": next((d["text"] for d in docs
                                         if d["key"] == "feedback"), "")},
                      ensure_ascii=False)
    return model.ask_json(SYSTEM, PROMPT.format(core=core))["slides"]


def slide_png(s, idx, total, dest):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_t, f_b, f_s = (ImageFont.truetype(FONT, 86),
                     ImageFont.truetype(FONT_L, 52),
                     ImageFont.truetype(FONT_L, 30))
    d.line([(150, 196), (260, 196)], fill=ACC, width=4)
    d.text((150, 100), s["title"], font=f_t, fill=FG)
    y = 310
    for line in s.get("lines", [])[:3]:
        for part in textwrap.wrap(line, 24) or [""]:
            d.text((150, y), part, font=f_b, fill=FG)
            y += 86
        y += 18
    d.text((150, H - 92), f"teatime — 議論の記録だけから作っています", font=f_s, fill=MUT)
    d.text((W - 230, H - 92), f"{idx}/{total}", font=f_s, fill=MUT)
    img.save(dest)


SAY_VOICE = os.environ.get("TEATIME_SAY_VOICE", "Kyoko")


def _key():
    """ElevenLabs の鍵。**無ければ無いと言う（黙って別物に差し替えない）。**"""
    k = os.environ.get("ELEVENLABS_API_KEY")
    if k:
        return k
    env = pathlib.Path.home() / ".hermes" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):   # コメント行は拾わない
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def tts(text, dest):
    """読み上げ。鍵があれば ElevenLabs、無ければ macOS の say に落ちる。

    **どちらを使ったかを返す。** 黙って落ちると、出来上がりの声が違う理由が分からなくなる。
    """
    if not _key():
        aiff = dest.with_suffix(".aiff")
        subprocess.run(["say", "-v", SAY_VOICE, "-o", str(aiff), text], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(aiff), str(dest)], check=True)
        aiff.unlink(missing_ok=True)
        return "say"
    key = _key()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}",
        data=json.dumps({"text": text, "model_id": TTS_MODEL,
                         "voice_settings": {"stability": 0.5,
                                            "similarity_boost": 0.75}}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        dest.write_bytes(r.read())
    return "elevenlabs"


def build(stem_dir, structured, docs):
    out = pathlib.Path(stem_dir)
    work = out.parent / f"{out.name}.video"
    work.mkdir(exist_ok=True)
    slides = script(structured, docs)
    (work / "script.json").write_text(
        json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")

    parts = []
    for i, s in enumerate(slides, 1):
        png, mp3, mp4 = work / f"{i:02d}.png", work / f"{i:02d}.mp3", work / f"{i:02d}.mp4"
        slide_png(s, i, len(slides), png)
        voice = tts(s["narration"], mp3)
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-loop", "1", "-i", str(png), "-i", str(mp3),
             "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-shortest",
             "-vf", "fps=12", str(mp4)], check=True)
        parts.append(mp4)

    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    dest = out.parent / f"{out.name}.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(dest)], check=True)
    (work / "voice.txt").write_text(voice, encoding="utf-8")
    print(f"読み上げ: {voice}（ElevenLabs を使うには ELEVENLABS_API_KEY が要ります）"
          if voice == "say" else "読み上げ: elevenlabs")
    return dest


if __name__ == "__main__":
    stem = pathlib.Path(sys.argv[1])
    base = stem.parent / stem.name
    structured = json.loads((base.with_suffix(".extract.json")).read_text(encoding="utf-8"))
    docs = [{"key": k, "title": k,
             "text": (base.parent / f"{base.name}.{k}.md").read_text(encoding="utf-8")}
            for k in ("pitch", "product", "project", "feedback")
            if (base.parent / f"{base.name}.{k}.md").exists()]
    print(build(base, structured, docs))
