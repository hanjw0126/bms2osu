import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from bms2osu import keysound
from bms2osu.batch import Options, process_group
from bms2osu.converter import convert_chart
from bms2osu.parser import parse_bms

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


def write_tone(path: Path, seconds: float, rate: int = 44100, channels: int = 1, amp: int = 8000):
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frame = int(amp).to_bytes(2, "little", signed=True) * channels
        w.writeframes(frame * n)


# 120 BPM -> one measure = 2000 ms
CHART = (
    "#TITLE Key\n#ARTIST Sound\n#BPM 120\n#LNOBJ ZZ\n"
    "#WAV01 kick.ogg\n#WAV02 Snare.WAV\n#WAV03 pad.wav\n#WAVZZ kick.wav\n"
    "#00101:03\n"            # BGM pad at 2000 ms
    "#00111:01010000\n"      # kick at 2000, 2500 (2nd cuts the 1st: same id)
    "#00116:00000200\n"      # scratch snare at 3000 (still audible when scratch removed)
    "#00152:0101\n"          # LN 52: start 2000 plays, end 3000 silent
    "#00213:01ZZ\n"          # note + LNOBJ end (silent) at 4000/5000
)


@unittest.skipIf(np is None, "numpy not installed")
class KeysoundTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "song"
        self.dir.mkdir()
        (self.dir / "a.bme").write_text(CHART, encoding="utf-8")
        write_tone(self.dir / "kick.wav", 1.0)                 # referenced as kick.ogg
        write_tone(self.dir / "snare.wav", 0.1, rate=22050)    # case + resample
        write_tone(self.dir / "pad.wav", 0.2, channels=2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sound_events(self):
        conv = convert_chart(parse_bms(self.dir / "a.bme"), remove_scratch=True)
        got = [(round(t), v) for t, v in conv.sounds]
        self.assertEqual(got, [(2000, "01"), (2000, "01"), (2000, "03"),
                               (2500, "01"), (3000, "02"), (4000, "01")])

    def test_mix_positions_and_cutoff(self):
        chart = parse_bms(self.dir / "a.bme")
        conv = convert_chart(chart)
        index = keysound.build_index(self.dir)
        events, missing = keysound.resolve_events(conv.sounds, chart.wav_table, index)
        self.assertEqual(missing, [])
        out = keysound.mix(events, {})
        sr = keysound.SAMPLE_RATE
        self.assertEqual(out.shape[1], 2)
        self.assertTrue(np.all(out[: 2 * sr - 1] == 0))          # silence before 2.0 s
        self.assertGreater(abs(out[2 * sr + 10, 0]), 0)           # sound at 2.0 s
        self.assertGreater(abs(out[int(3.02 * sr), 0]), 0)        # resampled snare at 3.0 s
        # kick at 4.0 s lasts 1 s; the silent LNOBJ end must not add a 2nd kick at 5.0 s
        self.assertTrue(np.all(out[int(5.05 * sr): int(5.4 * sr)] == 0))
        self.assertLessEqual(float(np.abs(out).max()), keysound.PEAK + 1e-6)

    def test_osz_contains_rendered_audio(self):
        res = process_group(str(self.dir), [str(self.dir / "a.bme")], str(self.dir.parent / "out"),
                            "song", Options())
        self.assertIsNone(res.error, res.warnings)
        ext = keysound.output_extension()
        with zipfile.ZipFile(res.output) as z:
            names = z.namelist()
            osu = [n for n in names if n.endswith(".osu")][0]
            text = z.read(osu).decode("utf-8")
            self.assertIn("audio" + ext, names)
            self.assertIn(f"AudioFilename: audio{ext}", text)
            data = z.read("audio" + ext)
        if keysound.sf is not None:
            import io
            audio, sr = keysound.sf.read(io.BytesIO(data))
            self.assertEqual(sr, keysound.SAMPLE_RATE)
            self.assertGreater(len(audio) / sr, 5.0)  # last kick ends at ~5.0 s (+ tail)

    def test_disabled_uses_folder_audio(self):
        res = process_group(str(self.dir), [str(self.dir / "a.bme")], str(self.dir.parent / "out"),
                            "song", Options(render_keysounds=False))
        with zipfile.ZipFile(res.output) as z:
            self.assertNotIn("audio" + keysound.output_extension(), z.namelist())


if __name__ == "__main__":
    unittest.main()
