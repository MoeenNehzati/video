import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "read_config.py"
SPEC = importlib.util.spec_from_file_location("read_config", SCRIPT)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)


class ReadConfigTests(unittest.TestCase):
    def environment_fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="command config ")
        self.addCleanup(temporary.cleanup)
        work = Path(temporary.name)
        root = work / "configuration with spaces"
        data = work / "data with spaces"
        root.mkdir()
        data.mkdir()
        (root / "config.toml").write_text(
            '[paths]\ndata_root = ' + json.dumps(str(data)) + '\n'
            '[render]\nformats = ["wav", "flac"]\nnormalize = true\n'
            'recorded = 2026-09-25\nrate = 44100\n'
            '[tools.example]\ncommand = ["tool with spaces", "--fixed-argument"]\n',
            encoding="utf-8",
        )
        return root, data, work

    def test_run_environment_is_fresh_and_arguments_are_literal(self):
        root, data, work = self.environment_fixture()
        local = root / "config.local.toml"
        code = (
            "import json, os, subprocess, sys; "
            "print(json.dumps({'root': os.environ['MUSIC_VIDEO_CONFIG_ROOT'], "
            "'data': os.environ['MUSIC_VIDEO_DATA_ROOT'], "
            "'config': json.loads(os.environ['MUSIC_VIDEO_CONFIG_JSON']), "
            "'inherited': os.environ['VIDEO_TEST_INHERITED'], 'args': sys.argv[1:], "
            "'grandchild': subprocess.check_output([sys.executable, '-c', "
            "'import os; print(os.environ[\"MUSIC_VIDEO_DATA_ROOT\"])'], text=True).strip()}))"
        )
        literal = "spaces; $(do-not-execute) `literal` $HOME"
        inherited = dict(os.environ, VIDEO_TEST_INHERITED="keep me",
                         MUSIC_VIDEO_DATA_ROOT="stale", MUSIC_VIDEO_CONFIG_ROOT="stale",
                         MUSIC_VIDEO_CONFIG_JSON="stale")
        shared_before = (root / "config.toml").read_bytes()
        for rate in (48000, 96000):
            with self.subTest(rate=rate):
                local.write_text(f"[render]\nrate = {rate}\nnormalize = false\n", encoding="utf-8")
                local_before = local.read_bytes()
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--config-root", str(root),
                     "--run", sys.executable, "-c", code, literal, "--config-root", "literal"],
                    cwd=work, env=inherited, capture_output=True, text=True, check=True,
                )
                output = json.loads(result.stdout)
                self.assertEqual(output["root"], str(root.resolve()))
                self.assertEqual(output["data"], str(data.resolve()))
                self.assertEqual(output["grandchild"], str(data.resolve()))
                self.assertEqual(output["inherited"], "keep me")
                self.assertEqual(output["args"], [literal, "--config-root", "literal"])
                self.assertEqual(output["config"]["render"], {
                    "rate": rate, "normalize": False, "formats": ["wav", "flac"],
                    "recorded": "2026-09-25",
                })
                self.assertEqual(output["config"]["tools"]["example"]["command"],
                                 ["tool with spaces", "--fixed-argument"])
                self.assertEqual(local.read_bytes(), local_before)
                self.assertEqual((root / "config.toml").read_bytes(), shared_before)

    def test_run_preserves_parent_environment_and_child_exit_status(self):
        root, data, _ = self.environment_fixture()
        with patch.dict(os.environ, {"MUSIC_VIDEO_DATA_ROOT": "parent value"}):
            before = dict(os.environ)
            status = READER.main([
                "--config-root", str(root), "--run", sys.executable, "-c",
                "import os, sys; assert os.environ['MUSIC_VIDEO_DATA_ROOT'] == sys.argv[1]; "
                "sys.exit(7)", str(data.resolve()),
            ])
            self.assertEqual(status, 7)
            self.assertEqual(dict(os.environ), before)

    def test_run_rejects_invalid_configuration_and_missing_command(self):
        root, _, work = self.environment_fixture()
        prefix = [sys.executable, str(SCRIPT), "--config-root", str(root), "--run"]
        for tail, status, message in (([], 2, "requires a command"),
                                      ([str(work / "no-such-executable")], 127, "Command error")):
            with self.subTest(tail=tail):
                result = subprocess.run(prefix + tail, capture_output=True, text=True)
                self.assertEqual(result.returncode, status)
                self.assertIn(message, result.stderr)
                self.assertEqual(result.stdout, "")
        (root / "config.local.toml").write_text('[paths]\ndata_root = "missing"\n', encoding="utf-8")
        marker = work / "must-not-exist"
        result = subprocess.run(
            prefix + [sys.executable, "-c", "import pathlib, sys; pathlib.Path(sys.argv[1]).touch()", str(marker)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Configuration error", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(marker.exists())

    def test_layering_and_entry_points(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            root.mkdir()
            data = Path(directory) / "data with spaces"
            data.mkdir()
            (root / "scripts").mkdir()
            shutil.copy(SCRIPT, root / "scripts" / SCRIPT.name)
            shutil.copy(REPO / "scripts" / "__init__.py", root / "scripts" / "__init__.py")
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
                [sys.executable, str(root / "scripts" / SCRIPT.name)],
                cwd=data, capture_output=True, text=True, check=True,
            )
            module = subprocess.run(
                [sys.executable, "-m", "scripts.read_config"],
                cwd=root, capture_output=True, text=True, check=True,
            )
            imported = subprocess.run(
                [sys.executable, "-c", "from scripts.read_config import load_config; "
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
                [sys.executable, "-m", "scripts.read_config"],
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
