import tempfile
import unittest
import zipfile
from pathlib import Path

from bms2osu import difficulty as d
from bms2osu.batch import Options, process_group


class LabelTest(unittest.TestCase):
    def test_strip_tags(self):
        for raw in ("Song [ANOTHER]", "Song (SP HYPER)", "Song -NORMAL-", "Song [7keys LEGGENDARIA]",
                    "Song \u3010INSANE\u3011"):
            self.assertEqual(d.strip_tags(raw), "Song")
        self.assertEqual(d.strip_tags("Another Day"), "Another Day")
        self.assertEqual(d.strip_tags("Hyperion"), "Hyperion")

    def test_detect_label(self):
        cases = [
            ({"DIFFICULTY": "3"}, "x", d.HYPER),
            ({"TITLE": "Song [ANOTHER]"}, "x", d.ANOTHER),
            ({"SUBTITLE": "[SP NORMAL]"}, "x", d.NORMAL),
            ({}, "song_7a", d.ANOTHER),
            ({}, "song-hyper", d.HYPER),
            ({}, "7n", d.NORMAL),
            ({}, "song_l", d.LEGGENDARIA),
            ({}, "song_x", d.INSANE),
            ({"TITLE": "Another Day"}, "a", None),      # words inside a title are not tags
            ({"SUBTITLE": "Another Mix"}, "bgm", None),
        ]
        for headers, stem, want in cases:
            self.assertEqual(d.detect_label(headers, stem), want, (headers, stem))

    def test_versions_unique_and_level(self):
        infos = d.chart_infos([
            ({"PLAYLEVEL": "12", "DIFFICULTY": "4"}, "s_a", 1000),
            ({"PLAYLEVEL": "\u26053"}, "s_x", 1000),
            ({"PLAYLEVEL": "5"}, "p", 300),
            ({"PLAYLEVEL": "5"}, "q", 300),
        ])
        self.assertEqual([i.version for i in infos],
                         ["ANOTHER Lv.12", "INSANE \u26053", "Lv.5 (p)", "Lv.5 (q)"])

    def test_od_hp(self):
        self.assertEqual(d.estimate_od({}), 8.0)
        self.assertEqual(d.estimate_od({"RANK": "0"}), 9.0)
        self.assertEqual(d.estimate_od({"RANK": "3"}), 7.0)
        self.assertEqual(d.estimate_od({"DEFEXRANK": "100"}), 8.0)
        self.assertEqual(d.estimate_hp({}, 1000), 8.0)
        std = d.standard_total(1000)
        self.assertEqual(d.estimate_hp({"TOTAL": str(std)}, 1000), 8.0)
        self.assertLess(d.estimate_hp({"TOTAL": str(std * 2)}, 1000), 8.0)   # generous gauge
        self.assertGreater(d.estimate_hp({"TOTAL": str(std / 2)}, 1000), 8.0)

    def test_set_metadata(self):
        title, artist = d.set_metadata(
            [{"TITLE": "Song [HYPER]", "ARTIST": "A"}, {"TITLE": "Song", "SUBTITLE": "[ANOTHER]", "ARTIST": "A"}], "f")
        self.assertEqual((title, artist), ("Song", "A"))


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "song"
        self.dir.mkdir()
        body = "#BPM 120\n#00111:01010101\n"
        (self.dir / "x_7h.bme").write_text(
            "#TITLE Song [HYPER]\n#ARTIST A\n#PLAYLEVEL 6\n#RANK 3\n" + body, encoding="utf-8")
        (self.dir / "x_7a.bme").write_text(
            "#TITLE Song [ANOTHER]\n#ARTIST A\n#PLAYLEVEL 11\n#RANK 1\n" + body, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _osu_files(self, opts):
        res = process_group(str(self.dir), sorted(str(p) for p in self.dir.glob("*.bme")),
                            str(self.dir.parent / "out"), "song", opts)
        self.assertIsNone(res.error)
        with zipfile.ZipFile(res.output) as z:
            return [z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".osu")]

    def test_fixed(self):
        texts = self._osu_files(Options(render_keysounds=False))
        self.assertTrue(all("Title:Song\n" in t for t in texts))
        versions = sorted(t.split("Version:")[1].split("\n")[0] for t in texts)
        self.assertEqual(versions, ["ANOTHER Lv.11", "HYPER Lv.6"])
        hyper = [t for t in texts if "Version:HYPER" in t][0]
        another = [t for t in texts if "Version:ANOTHER" in t][0]
        self.assertIn("OverallDifficulty:7\n", hyper)
        self.assertIn("OverallDifficulty:8.5\n", another)

    def test_manual_od_overrides(self):
        texts = self._osu_files(Options(render_keysounds=False, od=6.5))
        self.assertTrue(all("OverallDifficulty:6.5\n" in t for t in texts))

    def test_disabled_keeps_old_names(self):
        texts = self._osu_files(Options(render_keysounds=False, fix_difficulty=False))
        self.assertTrue(any("Title:Song [HYPER]\n" in t for t in texts))
        self.assertTrue(all("OverallDifficulty:8\n" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
