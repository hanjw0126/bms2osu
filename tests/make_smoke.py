"""Create a tiny BMS song folder for the frozen-binary smoke test in CI."""
import sys
import wave
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "smoke") / "song"
root.mkdir(parents=True, exist_ok=True)
(root / "a.bme").write_text(
    "#TITLE Smoke\n#ARTIST CI\n#BPM 120\n#WAV01 tone.ogg\n#00011:01010101\n#00101:01\n",
    encoding="utf-8",
)
with wave.open(str(root / "tone.wav"), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(44100)
    w.writeframes((4000).to_bytes(2, "little", signed=True) * 22050)
print(root)
