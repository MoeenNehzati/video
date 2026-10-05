import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "read_config.py"
SPEC = importlib.util.spec_from_file_location("read_config", SCRIPT)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)


class ReadConfigTests(unittest.TestCase):
    def test_layering_and_entry_points(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            root.mkdir()
            data = Path(directory) / "data with spaces"
            data.mkdir()
            (root / "bin").mkdir()
            shutil.copy(SCRIPT, root / "bin" / SCRIPT.name)
            shutil.copy(REPO / "bin" / "__init__.py", root / "bin" / "__init__.py")
            shared = root / "config.toml"
            local = root / "config.local.toml"
            shared.write_text(
                f'[paths]\ndata_root = {json.dumps(str(data))}\n'
                '[render]\nformats = ["wav", "flac"]\nnormalize = true\n'
                'recorded = 2026-09-25\n'
                '[render.audio]\nrate = 44100\ngain = 0.5\n', encoding="utf-8"
            )
            self.assertEqual(READER.load_config(root)["render"]["formats"], ["wav", "flac"])
            local.write_text(
                '[render]\nformats = ["mp3"]\nnormalize = false\n'
                '[render.audio]\nrate = 48000\n', encoding="utf-8"
            )
            before = (shared.read_bytes(), local.read_bytes())
            resolved = READER.load_config(root)
            self.assertEqual(resolved["render"]["audio"], {"rate": 48000, "gain": 0.5})
            self.assertEqual(resolved["render"]["formats"], ["mp3"])
            self.assertIs(resolved["render"]["normalize"], False)
            direct = subprocess.run(
                [sys.executable, str(root / "bin" / SCRIPT.name)],
                cwd=data, capture_output=True, text=True, check=True,
            )
            module = subprocess.run(
                [sys.executable, "-m", "bin.read_config"],
                cwd=root, capture_output=True, text=True, check=True,
            )
            imported = subprocess.run(
                [sys.executable, "-c", "from bin.read_config import load_config; "
                 "assert load_config()['render']['audio']['rate'] == 48000"],
                cwd=root, capture_output=True, text=True, check=True,
            )
            self.assertEqual(imported.stdout, "")
            self.assertEqual(json.loads(direct.stdout), json.loads(module.stdout))
            self.assertEqual(json.loads(direct.stdout)["render"]["recorded"], "2026-09-25")
            self.assertEqual((shared.read_bytes(), local.read_bytes()), before)

            # An invalid local value must override a valid shared value and fail.
            for value in ('""', '"relative/path"', '123', json.dumps(str(shared)),
                          json.dumps(str(root / "missing"))):
                local.write_text(f"[paths]\ndata_root = {value}\n", encoding="utf-8")
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "config.local.toml"):
                    READER.load_config(root)
            failed = subprocess.run(
                [sys.executable, "-m", "bin.read_config"],
                cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(failed.stdout, "")
            self.assertIn("config.local.toml", failed.stderr)

            local.write_text("[broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "config.local.toml"):
                READER.load_config(root)
            local.unlink()
            shared.write_text("[paths]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "config.local.toml"):
                READER.load_config(root)
            shared.unlink()
            with self.assertRaises(FileNotFoundError):
                READER.load_config(root)


if __name__ == "__main__":
    unittest.main()
