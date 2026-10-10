"""Isolated Python package snapshots with synthetic installed distributions."""
import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import sys
import sysconfig
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / '.agents/skills/artifact-bookkeeping/scripts'))

from artifact_ledger import Ledger, reference
from ledger_python import capture_python_runtime, distribution_manifest
from ledger_execution import prepare, execute, finish, status
from ledger_replay import SCHEMA_PATH
from scripts.read_config import ROOT


class LedgerPythonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ledger-py-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.packages = self.work / 'site-packages'
        self.packages.mkdir()
        self.distributions = {}
        self.make_distribution('fixturepkg', 'fixturepkg', '1.0', 'VALUE = "captured package"\n',
                               requires=['fixture-dep>=2; python_version >= "3.11"'])
        self.make_distribution('fixture-dep', 'fixture_dep', '2.0', 'VALUE = 2\n')
        root = self.work / 'data'
        root.mkdir()
        self.config = {'paths': {'data_root': str(root), 'resource_cache': str(self.work / 'cache')},
                       'resources': {'python_packages': str(self.packages)},
                       'bookkeeping': {'actor_id': 'fixture', 'host_id': '11111111-1111-4111-8111-111111111111'}}
        self.ledger = Ledger(self.config)

    def make_distribution(self, name, package, version, source, requires=(), extra_records=(), entry_points=None):
        directory = self.packages / package
        directory.mkdir(exist_ok=True)
        (directory / '__init__.py').write_text(source)
        metadata = self.packages / f'{name.replace("-", "_")}-{version}.dist-info'
        metadata.mkdir(exist_ok=True)
        text = f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n'
        text += ''.join('Requires-Dist: ' + requirement + '\n' for requirement in requires)
        (metadata / 'METADATA').write_text(text)
        files = [f'{package}/__init__.py', metadata.name + '/METADATA', metadata.name + '/RECORD']
        if entry_points:
            (metadata / 'entry_points.txt').write_text(entry_points)
            files.append(metadata.name + '/entry_points.txt')
        (metadata / 'RECORD').write_text(''.join(filename + ',,\n' for filename in [*files, *extra_records]))
        self.distributions[name] = importlib.metadata.Distribution.at(metadata)

    def metadata(self):
        return patch('ledger_python.importlib.metadata.distribution', side_effect=lambda name: self.distributions[name])

    def prepare(self):
        src = self.ledger.root / 'input.txt'; src.write_text('original')
        event = self.ledger.import_files({'input.txt': src}, kind='source', label='Input')
        dep = {**reference(event['data']['updates'][0]), 'files': ['input.txt'], 'purpose': 'fixture'}
        request = {'operation': 'package-fixture', 'skill': 'test',
                   'declaration': '.agents/skills/syllabify_lyrics/SKILL.md',
                   'code': ['tests/command_fixture.py'], 'inputs': {'source': dep},
                   'outputs': {'result': {'kind': 'report', 'label': 'Package result', 'dependencies': ['source'],
                               'contract': {'files': [{'path': 'result.txt', 'role': 'report'}]}}},
                   'packages': ['fixturepkg'],
                   'command': ['{python}', '{code:tests/command_fixture.py}', '{input:source}',
                               '{output:result/result.txt}', '--mode', 'package']}
        with self.metadata():
            intent = prepare(self.ledger, request)
        output = Path(status(self.ledger, intent['run_id'])['plan']['bindings']['output:result']) / 'result.txt'
        return intent, output

    def test_dependency_closure_includes_metadata_and_enforces_installed_versions(self):
        with self.metadata():
            manifest = distribution_manifest(['fixturepkg'], self.packages)
            self.assertEqual(manifest['versions'], {'fixture-dep': '2.0', 'fixturepkg': '1.0'})
            self.assertIn('fixture_dep/__init__.py', manifest['files'])
            self.assertIn('fixturepkg-1.0.dist-info/METADATA', manifest['files'])
            with self.assertRaisesRegex(ValueError, 'does not satisfy'):
                distribution_manifest(['fixturepkg>=9'], self.packages)

    def test_unsafe_records_and_symlinks_fail_closed(self):
        self.make_distribution('unsafe', 'unsafe', '1.0', '', extra_records=['../../../unrelated.txt'])
        with self.metadata(), self.assertRaisesRegex(ValueError, 'Unsafe external'):
            distribution_manifest(['unsafe'], self.packages)
        source = self.packages / 'fixture_dep/__init__.py'
        source.unlink()
        outside = self.work / 'outside.py'
        outside.write_text('VALUE = 3\n')
        source.symlink_to(outside)
        with self.metadata(), self.assertRaisesRegex(ValueError, 'Unsafe external|symlink'):
            distribution_manifest(['fixture-dep'], self.packages)

    def test_only_declared_unused_console_wrapper_is_excluded(self):
        scripts = self.work / 'bin'
        scripts.mkdir()
        (scripts / 'fixture-tool').write_text('#!fixture\n')
        self.make_distribution('console-fixture', 'console_fixture', '1.0', '',
                               extra_records=['../bin/fixture-tool'],
                               entry_points='[console_scripts]\nfixture-tool = console_fixture:main\n')
        with self.metadata(), patch('ledger_python.sysconfig.get_path', return_value=str(scripts)):
            manifest = distribution_manifest(['console-fixture'], self.packages)
        self.assertEqual(len(manifest['exclusions']), 1)
        self.assertEqual(manifest['exclusions'][0]['path'], '../bin/fixture-tool')
        self.assertNotIn('../bin/fixture-tool', manifest['files'])

    def test_isolated_child_uses_snapshots_and_refuses_repeat_execution(self):
        intent, output = self.prepare()
        (self.packages / 'fixturepkg/__init__.py').write_text('VALUE = "changed installation"\n')
        execute(self.ledger, intent['run_id'])
        self.assertEqual(output.read_text(), 'captured package')
        with self.assertRaisesRegex(ValueError, 'already attempted'):
            execute(self.ledger, intent['run_id'])
        event = finish(self.ledger, intent['run_id'])
        self.assertTrue(self.ledger.resolve(**reference(event['data']['updates'][0]))['available'])

    def test_tampered_package_snapshot_fails_before_spawn(self):
        intent, output = self.prepare()
        cache = next(iter(self.ledger.resource_paths(intent['run_id']).values()))
        (cache / 'fixturepkg/__init__.py').write_text('VALUE = "tampered cache"\n')
        with self.assertRaisesRegex(ValueError, 'snapshot altered|snapshot.*integrity'):
            execute(self.ledger, intent['run_id'])
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
