"""Real ELF closure execution and missing-dependency rejection; no media tools."""
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from uuid import uuid4

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / '.agents/skills/artifact-bookkeeping/scripts'))

from artifact_ledger import Ledger, LedgerError, reference
from ledger_tools import elf_dependencies, validate_execution, tool_argv, tool_environment


class NativeToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lt-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / 'native'; self.bundle.mkdir()
        sources = {'true': Path('/usr/bin/true').resolve(),
                   'libc.so.6': Path('/usr/lib/x86_64-linux-gnu/libc.so.6'),
                   'ld-linux-x86-64.so.2': Path('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')}
        if not all(path.exists() for path in sources.values()):
            self.skipTest('Linux x86_64 ELF fixture unavailable')
        for name, path in sources.items():
            shutil.copy2(path, self.bundle / name)
        self.execution = {'mode': 'dynamic-elf', 'entrypoint': 'true',
                          'loader': 'ld-linux-x86-64.so.2', 'library_dirs': ['.']}
        self.descriptor = {'source': {'execution': self.execution},
                           'files': [{'path': name} for name in sources]}

    def test_real_loader_runs_exact_private_closure(self):
        self.execution['arguments'] = ['--version']
        config = {'paths': {'data_root': str(self.root / 'data'), 'resource_cache': str(self.root / 'cache')},
                  'bookkeeping': {'actor_id': 'fixture', 'host_id': str(uuid4())},
                  'resources': {'native': str(self.bundle)}}
        (self.root / 'data').mkdir()
        ledger = Ledger(config)
        event = ledger.register_resource('resources.native', [f['path'] for f in self.descriptor['files']],
            label='Native fixture', version='observed-system-true', source=self.descriptor['source'])
        ref = reference(event['data']['updates'][0])
        producer = ledger.producer('native-fixture', 'artifact-bookkeeping', 'test')
        producer['resources'] = [ref]
        intent = ledger.prepare('native-fixture', [{'kind': 'report', 'label': 'Native fixture',
            'contract': {'files': [{'path': 'result.txt', 'role': 'result'}]}}], producer)
        argv = tool_argv(ledger, intent['run_id'], ref)
        self.assertTrue(argv[0].startswith(str(self.root / 'cache')))
        self.assertEqual(argv[-1], '--version')
        shutil.rmtree(self.bundle)
        result = subprocess.run(argv, env=tool_environment(self.root / 'scratch'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'coreutils', result.stdout)
        output = ledger.path(intent['workspace'] + '/' + intent['outputs'][0]['output_slot'] + '/result.txt')
        output.write_text('native execution passed\n')
        ledger.finalize(intent['run_id'])

    def test_missing_transitive_library_and_unsafe_search_directory_rejected(self):
        self.assertEqual(elf_dependencies(self.bundle / 'true')['needed'], ['libc.so.6'])
        validate_execution(self.bundle, self.descriptor)
        bad = copy.deepcopy(self.descriptor)
        bad['files'] = [file for file in bad['files'] if file['path'] != 'libc.so.6']
        with self.assertRaisesRegex(LedgerError, 'missing or ambiguous'):
            validate_execution(self.bundle, bad)
        bad = copy.deepcopy(self.descriptor)
        bad['source']['execution']['library_dirs'] = ['../native']
        with self.assertRaises(ValueError):
            validate_execution(self.bundle, bad)

    def test_malformed_elf_fails_without_execution(self):
        target = self.bundle / 'bad'
        target.write_bytes(b'\x7fELF' + b'\0' * 70)
        with self.assertRaises(LedgerError):
            elf_dependencies(target)

    def test_compiler_module_prefix_and_no_external_prefix_paths(self):
        self.execution['arguments'] = ['-m', 'jdk.compiler/com.sun.tools.javac.Main']
        validate_execution(self.bundle, self.descriptor)
        for arguments in [['/external/file'], ['-Dconfig=/external/file'], ['../file'], 'not-an-argv-list']:
            self.execution['arguments'] = arguments
            with self.assertRaisesRegex(LedgerError, 'prefix arguments'):
                validate_execution(self.bundle, self.descriptor)
        self.execution['arguments'] = ['--share-folder', '{resource}/libc.so.6']
        validate_execution(self.bundle, self.descriptor)
        self.execution['arguments'] = ['--share-folder', '{resource}/missing']
        with self.assertRaisesRegex(LedgerError, 'outside the resource manifest'):
            validate_execution(self.bundle, self.descriptor)

    def test_embedded_library_paths_cannot_escape_private_snapshot(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('C compiler unavailable for ELF RPATH fixture')
        source = self.root / 'fixture.c'
        source.write_text('int main(void) { return 0; }\n')
        for search, allowed in [('$ORIGIN', True), ('$ORIGIN/../outside', False), ('/usr/lib', False)]:
            subprocess.run([compiler, str(source), '-o', str(self.bundle / 'true'), '-Wl,-rpath,' + search],
                           check=True, capture_output=True)
            self.assertEqual(elf_dependencies(self.bundle / 'true')['search_paths'], [search])
            if allowed:
                validate_execution(self.bundle, self.descriptor)
            else:
                with self.assertRaisesRegex(LedgerError, 'RPATH/RUNPATH'):
                    validate_execution(self.bundle, self.descriptor)


if __name__ == '__main__':
    unittest.main()
