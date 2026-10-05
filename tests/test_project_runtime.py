"""Shared boundary checks used by every automated artifact-producing skill."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bin.project_runtime import data_path, load_project, resource_path, tool_command
from bin.read_config import ROOT


class RuntimeTests(unittest.TestCase):
    def test_paths_cannot_escape_root_and_validation_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            root = work / 'data with spaces'
            root.mkdir()
            config = {'paths': {'data_root': str(root)}}
            source = root / 'source.txt'
            source.write_text('original')
            self.assertEqual(data_path(config, 'source.txt', must_exist=True), source)
            self.assertEqual(data_path(config, root / 'nested/output.json'), root / 'nested/output.json')
            self.assertFalse((root / 'nested').exists())
            for value in ('../escape', work / 'outside', '.', 'source.txt/output'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    data_path(config, value)
            with self.assertRaises(ValueError):
                data_path(config, 'missing', must_exist=True)
            with self.assertRaises(ValueError):
                data_path(config, 'source.txt', must_exist=True, directory=True)
            try:
                (root / 'escape').symlink_to(work, target_is_directory=True)
            except (OSError, NotImplementedError):
                pass  # Windows can require privileges to create a symlink.
            else:
                with self.assertRaises(ValueError):
                    data_path(config, 'escape/outside')
            self.assertEqual(source.read_text(), 'original')
            with self.assertRaises(ValueError):
                data_path({'paths': {'data_root': str(ROOT.parent)}}, ROOT / 'README.md')

    def test_configured_argv_and_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'data'
            data.mkdir()
            resource = root / 'sample library.sf2'
            resource.write_bytes(b'fixture')
            (root / 'config.toml').write_text('[paths]\ndata_root = ""\n')
            (root / 'config.local.toml').write_text(
                '[paths]\ndata_root = ' + json.dumps(str(data)) + '\n'
                '[tools.example]\ncommand = ' + json.dumps([sys.executable, 'argument with spaces']) + '\n'
                '[resources]\nsamples = ' + json.dumps(str(resource)) + '\n')
            config = load_project(root)
            self.assertEqual(tool_command(config, 'example')[1:], ['argument with spaces'])
            self.assertEqual(resource_path(config, 'samples'), resource)
            for invalid in ('example --shell', [], ['missing-executable-029001'], [1]):
                config['tools']['example']['command'] = invalid
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    tool_command(config, 'example')
            for invalid in ('relative.sf2', str(root / 'missing'), str(data)):
                config['resources']['samples'] = invalid
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    resource_path(config, 'samples')


if __name__ == '__main__':
    unittest.main()
