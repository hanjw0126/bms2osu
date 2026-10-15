import tempfile
import unittest
import zipfile
from pathlib import Path

from bms2osu.batch import Options, process_group
from bms2osu.cli import collect
from bms2osu.converter import convert_chart
from bms2osu.osu import render_osu
from bms2osu.parser import parse_bms

SAMPLE = (
    "#TITLE Test Song\n#ARTIST Tester\n#BPM 120\n#PLAYLEVEL 5\n#LNOBJ ZZ\n"
    "#WAV01 bgm.wav\n#BPM01 240\n#STOP01 48\n"
    "#00011:01000000\n#00016:00010000\n#00012:0001\n"          # measure 0
    "#00113:01\n#00114:0001\n#00108:0001\n"                    # measure 1 (BPM->240 at 0.5)
    "#00211:01\n#00209:01\n"                                   # measure 2 (note, then STOP)
    "#00311:01\n#00352:0101\n"                                 # measure 3 (normal + LN ch52)
    "#00415:010000ZZ\n"                                        # measure 4 (LNOBJ)
    "#00502:0.5\n#00511:0001\n"                                # measure 5 (half length)
)


def notes_of(conv):
    return [(n.lane, n.time, n.end) for n in conv.notes]


class ConverterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.bms = self.dir / "test.bme"
        self.bms.write_text(SAMPLE, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_with_scratch_8k(self):
        conv = convert_chart(parse_bms(self.bms), remove_scratch=False)
        self.assertEqual(conv.keys, 8)
        self.assertEqual(
            notes_of(conv),
            [
                (1, 0, None),
                (0, 500, None),        # scratch -> lane 0
                (2, 1000, None),
                (3, 2000, None),
                (4, 3000, None),       # BPM change applies before the note
                (1, 3500, None),
                (1, 4750, None),       # shifted by 250ms STOP
                (2, 4750, 5250),       # LN via channel 52
                (5, 5750, 6500),       # LN via #LNOBJ
                (1, 7000, None),       # half-length measure
            ],
        )
        self.assertEqual(conv.timing, [(0, 120.0), (3000, 240.0)])

    def test_remove_scratch_7k(self):
        conv = convert_chart(parse_bms(self.bms), remove_scratch=True)
        self.assertEqual(conv.keys, 7)
        self.assertFalse(any(n.time == 500 for n in conv.notes))
        self.assertEqual(notes_of(conv)[0], (0, 0, None))
        self.assertTrue(all(0 <= n.lane < 7 for n in conv.notes))

    def test_double_play(self):
        p = self.dir / "dp.bme"
        p.write_text("#BPM 120\n#00011:01\n#00021:01\n#00026:01\n", encoding="utf-8")
        conv = convert_chart(parse_bms(p), remove_scratch=False)
        self.assertTrue(conv.double)
        self.assertEqual(conv.keys, 16)
        self.assertEqual(sorted(n.lane for n in conv.notes), [1, 8, 15])
        conv = convert_chart(parse_bms(p), remove_scratch=True)
        self.assertEqual(conv.keys, 14)

    def test_osu_output(self):
        chart = parse_bms(self.bms)
        conv = convert_chart(chart)
        text = render_osu(chart, conv, audio_name="a.ogg")
        self.assertIn("Mode: 3", text)
        self.assertIn("CircleSize:8", text)
        self.assertIn("0,500,4,1,0,100,1,0", text)
        self.assertIn("[HitObjects]", text)
        self.assertIn("224,192,2000,1,0,0:0:0:0:", text)          # lane 3 of 8 keys (center x)
        self.assertIn("5250:0:0:0:0:", text)

    def test_batch_osz(self):
        song = self.dir / "song"
        song.mkdir()
        (song / "a.bms").write_text(SAMPLE, encoding="utf-8")
        (song / "b.bme").write_text(SAMPLE, encoding="utf-8")
        (song / "bgm.ogg").write_bytes(b"fake")
        groups, _ = collect([str(self.dir)], True)
        self.assertEqual(len(groups), 2)  # tmp root (test.bme) and song/
        folder = song.resolve()
        res = process_group(str(folder), groups[folder], str(self.dir / "out"), "song", Options(remove_scratch=True))
        self.assertIsNone(res.error)
        self.assertEqual(res.charts, 2)
        with zipfile.ZipFile(res.output) as z:
            names = z.namelist()
        self.assertEqual(sum(n.endswith(".osu") for n in names), 2)
        self.assertIn("bgm.ogg", names)


if __name__ == "__main__":
    unittest.main()
