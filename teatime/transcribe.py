"""録音 → 文字起こし。**宛先を直書きしない。**

裏方（uni2）の mlx-whisper を使う。居なければ、居ないと言って止まる。
音量をそろえる filter は omi-stackchan の実測済みのもの（割らずに持ち上げる）を借りている。
"""
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path.home() / "omi-stackchan" / "pipeline"))

MODEL = "mlx-community/whisper-large-v3-turbo"
CHUNK_SEC = 600          # 10分ごとに切って出す。落ちても最大10分ぶんのやり直し
AF = "dynaudnorm=f=200:g=15:p=0.9:m=10,alimiter=limit=0.89"


def to_wav(src, dst):
    """16kHz モノラルに揃え、音量を持ち上げる。**頭を叩かない。**"""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-af", AF, "-ar", "16000", "-ac", "1", str(dst)],
        check=True)


def split(wav, out_dir):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
         "-f", "segment", "-segment_time", str(CHUNK_SEC),
         "-c", "copy", str(out_dir / "part-%03d.wav")],
        check=True)
    return sorted(out_dir.glob("part-*.wav"))


def _local(part):
    """**裏方が落ちていても止まらない。** 母艦の mlx-whisper へ退避する。
    遅いが、終わる。**宛先は増やさない**（uni2 か、ここだけ）。"""
    import mlx_whisper
    out = mlx_whisper.transcribe(str(part), path_or_hf_repo=MODEL, language="ja")
    return out.get("segments", [])


def run(src, with_time=True):
    try:
        from remote_whisper import backyard_host, transcribe_remote
        host = backyard_host()
    except Exception:
        host = None
    if not host:
        print("裏方（uni2）に届きません。母艦で文字起こしします（遅くなります）。")

    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        wav = tmp / "all.wav"
        to_wav(src, wav)
        parts = split(wav, tmp)
        for i, p in enumerate(parts):
            segs = transcribe_remote(p, MODEL, host) if host else None
            if segs is None:
                # **途中で落ちても、その断片だけ母艦で引き取る**
                if host:
                    print(f"裏方が {p.name} で止まりました。母艦で続けます。")
                try:
                    segs = _local(p)
                except Exception as error:
                    sys.exit(f"文字起こしが止まりました（{p.name}）: {error}")
            base = i * CHUNK_SEC
            for s in segs:
                t = int(base + s.get("start", 0))
                txt = s["text"].strip()
                if not txt:
                    continue
                lines.append(f"[{t//60:02d}:{t%60:02d}] {txt}" if with_time else txt)
    return "\n".join(lines)


if __name__ == "__main__":
    print(run(pathlib.Path(sys.argv[1])))
