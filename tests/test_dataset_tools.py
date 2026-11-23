"""Folder -> manifest -> features -> train, on a mock tree shaped like the one in GUIDE.md. Writes only to a temp dir."""
import json, os, random, shutil, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "train"))
import gen_data as G          # noqa: E402
import check_ocr, analyze_times  # noqa: E402,F401
import import_aiforge as IA   # noqa: E402
import make_manifest as MM    # noqa: E402
from PIL import Image         # noqa: E402


def put(dirpath, name, data):
    os.makedirs(dirpath, exist_ok=True)
    open(os.path.join(dirpath, name), "wb").write(data)


def make_tree(raw, n=12):
    r = random.Random(5)
    def scr():
        im, box, fb = G.screen(r); return im, box, fb, G.jpeg(im, r.randrange(80, 96))
    for i in range(n):
        im, b, fb, base = scr(); put(f"{raw}/genuine_gpay_original", f"{i}.jpg", base)
        im, b, fb, base = scr(); put(f"{raw}/genuine_gpay_whatsapp", f"{i}.jpg", G.forward(base, r))
        im, b, fb, base = scr(); put(f"{raw}/fake_text_edit", f"{i}.jpg", G.jpeg(G.edit_text(base, b, fb, r, True), 88))
        im, b, fb, base = scr(); im2, _, _ = G.screen(r)
        put(f"{raw}/fake_paste", f"{i}.jpg", G.jpeg(G.paste_region(base, G.jpeg(im2, 80), r), 88))
        im, b, fb, base = scr(); put(f"{raw}/novel_fake_blur", f"{i}.jpg", G.jpeg(G.blur_retype(base, b, fb, r), 88))
        im, b, fb, base = scr(); put(f"{raw}/aux_genuine_docs", f"{i}.jpg", base)
        im, b, fb, base = scr(); put(f"{raw}/aux_fake_docs", f"{i}.jpg", G.jpeg(G.edit_text(base, b, fb, r, True), 88))


class Tools(unittest.TestCase):
    def test_labels_and_errors(self):
        self.assertEqual(MM.label_for("genuine_gpay"), 0)
        self.assertEqual(MM.label_for("novel_fake_blur"), 1)
        self.assertEqual(MM.label_for("aux_genuine_docs"), 0)
        self.assertEqual(MM.label_for("fake_paste"), 1)
        self.assertIsNone(MM.label_for("misc"))

    def test_duplicates_and_conflicts(self):
        d = tempfile.mkdtemp()
        try:
            r = random.Random(1); data = G.jpeg(G.screen(r)[0], 90)
            put(f"{d}/genuine_a", "1.jpg", data); put(f"{d}/genuine_b", "1.jpg", data)       # same label twice -> skipped
            put(f"{d}/fake_c", "1.jpg", data)                                                  # conflicting label -> error
            put(f"{d}/misc", "1.jpg", data)                                                    # bad folder name -> error
            put(f"{d}/genuine_a", "broken.jpg", b"not an image")
            rows, errors, warnings = MM.build(d)
            self.assertEqual(len(rows), 1)
            self.assertTrue(any("both genuine and fake" in e for e in errors))
            self.assertTrue(any("misc" in e for e in errors))
            self.assertTrue(any("unreadable" in w for w in warnings))
        finally:
            shutil.rmtree(d)

    def test_aiforge_import_mock_layout(self):
        d = tempfile.mkdtemp()
        try:
            r = random.Random(2)
            for i in range(6):
                put(f"{d}/TrainingSet/images", f"{i+1:09d}.png", b"x"); put(f"{d}/TrainingSet/masks", f"{i+1:09d}.png", b"x")
            with open(f"{d}/metadata.jsonl", "w") as f:
                for i in range(6):
                    f.write(json.dumps({"new_id": f"{i+1:09d}", "assigned_tool": "gemini-nano" if i < 4 else "qwen-inpaint"}) + "\n")
            with self.assertRaises(SystemExit):
                IA.build(d)                                              # refuses forged-only without opt-in
            rows = IA.build(d, forged_only=True)
            self.assertEqual(len(rows), 6)                              # masks excluded
            self.assertEqual({x["g"] for x in rows}, {"aux_aiforge_fake_gemini_nano", "aux_aiforge_fake_qwen_inpaint"})
            self.assertTrue(all(x["y"] == 1 for x in rows))
        finally:
            shutil.rmtree(d)

    def test_check_ocr_and_analyze_times(self):
        import check_ocr, analyze_times
        d = tempfile.mkdtemp()
        try:
            sys.path.insert(0, HERE)
            from make_samples import make_screen, to_jpeg
            put(d, "a.jpg", to_jpeg(make_screen("500", "412345678901", "26 Oct 2026, 02:38 PM")))
            open(f"{d}/ans.csv", "w").write("file,amount,utr,upi_id\na.jpg,500,412345678901,shopkeeper@okbank\n")
            ok, tot = check_ocr.main(d, f"{d}/ans.csv")
            self.assertEqual(ok, tot)
            open(f"{d}/t.csv", "w").write("screenshot_time,alert_time\n2026-11-24 14:00,2026-11-24 14:01\n2026-11-24 14:10,2026-11-24 14:14\n")
            v = analyze_times.gaps_minutes(f"{d}/t.csv")
            self.assertEqual(v, [1.0, 4.0])
        finally:
            shutil.rmtree(d)

    def test_pipeline_end_to_end(self):
        d = tempfile.mkdtemp()
        try:
            make_tree(f"{d}/raw")
            py = [sys.executable, "-I"]
            run = lambda *a: subprocess.run(py + list(a), capture_output=True, text=True, cwd=d)
            r1 = run(os.path.join(ROOT, "train/make_manifest.py"), "raw", "manifest.json"); self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            r2 = run(os.path.join(ROOT, "train/build_features.py"), "manifest.json", "feat.json"); self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            out = f"{d}/model.joblib"
            r3 = run(os.path.join(ROOT, "train/train.py"), "feat.json", "--out", out); self.assertEqual(r3.returncode, 0, r3.stdout + r3.stderr)
            self.assertTrue(os.path.exists(out))
            self.assertIn("novel_fake_blur", r3.stdout); self.assertIn("NEVER TRAINED", r3.stdout)
            self.assertIn("aux data", r3.stdout)
            print("\n" + r3.stdout)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
