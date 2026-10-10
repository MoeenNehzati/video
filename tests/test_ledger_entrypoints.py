"""The generic execution boundary and dependency-free production interface."""
import ast
import copy
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / '.agents/skills'
sys.path.insert(0, str(SKILLS / 'artifact-bookkeeping/scripts'))
from artifact_ledger import Ledger, reference
from ledger_execution import prepare, execute, finish, status, handoff


class CommandFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='command å ')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.data = self.directory / 'data ö'; self.data.mkdir()
        self.config = {'paths': {'data_root': str(self.data), 'resource_cache': str(self.directory / 'cache')},
                       'bookkeeping': {'actor_id': 'fixture', 'host_id': str(uuid4())}}
        self.ledger = Ledger(self.config)
        self.original = self.data / 'input å.txt'; self.original.write_text('Twin-kle star\n')
        self.dep = self.register(self.original)

    def register(self, path):
        name = 'input.txt' if path == self.original else path.name
        event = self.ledger.import_files({name: path}, kind='source', label=path.name)
        return {**reference(event['data']['updates'][0]), 'files': [name], 'purpose': 'fixture input'}

    def request(self, mode='ok'):
        return {'operation': 'text-fixture', 'skill': 'test-fixture',
                'declaration': '.agents/skills/syllabify_lyrics/SKILL.md', 'code': ['tests/command_fixture.py'],
                'inputs': {'text': copy.deepcopy(self.dep)},
                'outputs': {'result': {'kind': 'report', 'label': 'Fixture', 'dependencies': ['text'],
                                      'contract': {'files': [{'path': 'result.txt', 'role': 'report'}]}}},
                'command': ['{python}', '{code:tests/command_fixture.py}', '{input:text}',
                            '{output:result/result.txt}', '--mode', mode]}

    def run_operation(self, request=None):
        intent = prepare(self.ledger, request or self.request())
        execute(self.ledger, intent['run_id'])
        event = finish(self.ledger, intent['run_id'])
        return intent, event


class ManagedExecutionTests(CommandFixture):
    def test_fresh_attempts_revision_and_no_registration(self):
        first, done = self.run_operation()
        second, _ = self.run_operation()
        self.assertNotEqual(first['run_id'], second['run_id'])
        self.assertNotEqual(first['outputs'][0]['artifact_id'], second['outputs'][0]['artifact_id'])
        ref = reference(done['data']['updates'][0])
        request = self.request()
        request['outputs']['result'].update(action='revise', base=ref)
        revised, _ = self.run_operation(request)
        self.assertEqual(revised['outputs'][0]['artifact_id'], ref['artifact_id'])
        self.assertNotEqual(revised['outputs'][0]['revision_id'], ref['revision_id'])
        self.assertEqual(self.ledger.resolve(**ref)['dependencies'], [self.dep])
        self.assertEqual(self.original.read_text(), 'Twin-kle star\n')

    def test_standalone_and_managed_syllabification_match(self):
        script = '.agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py'
        config = self.directory / 'config.toml'
        config.write_text('[paths]\ndata_root=' + json.dumps(str(self.data)) + '\n')
        out = self.data / 'standalone.json'
        result = subprocess.run([sys.executable, str(REPO / script), str(self.original), '--out', str(out),
                                 '--config-root', str(self.directory)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        request = self.request()
        request['code'] = [script, '.agents/skills/syllabify_lyrics/scripts/lyrics_syllabify.py']
        request['command'] = ['{python}', '{code:' + script + '}', '{input:text}', '--out', '{output:result/result.txt}']
        intent, done = self.run_operation(request)
        record = self.ledger.resolve(**reference(done['data']['updates'][0]))
        self.assertEqual((self.data / record['history_path'] / 'result.txt').read_bytes(), out.read_bytes())
        self.assertIn('/cache/', status(self.ledger, intent['run_id'])['plan']['command'][1])

    def test_partial_extra_missing_outputs_do_not_publish(self):
        for mode in ['partial', 'extra']:
            with self.subTest(mode=mode):
                intent = prepare(self.ledger, self.request(mode))
                with self.assertRaises(ValueError):
                    execute(self.ledger, intent['run_id'])
                    finish(self.ledger, intent['run_id'])
                self.assertEqual(self.ledger.state()['runs'][intent['run_id']]['status'], 'failed')
                self.assertNotIn(intent['outputs'][0]['artifact_id'], self.ledger.state()['artifacts'])
                self.assertTrue(self.ledger.path(intent['workspace'] + '/stderr.txt').exists())
        intent = prepare(self.ledger, self.request())
        execute(self.ledger, intent['run_id'])
        Path(status(self.ledger, intent['run_id'])['plan']['bindings']['output:result']).joinpath('result.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'contract mismatch'):
            finish(self.ledger, intent['run_id'])

    def test_captured_source_not_live_source_and_no_repeat(self):
        intent = prepare(self.ledger, self.request())
        # The filesystem source no longer exists to the executor after preparation.
        with patch('ledger_execution.ROOT', self.directory / 'absent-checkout'):
            execute(self.ledger, intent['run_id'])
        with self.assertRaisesRegex(ValueError, 'already attempted'):
            execute(self.ledger, intent['run_id'])
        finish(self.ledger, intent['run_id'])

    def test_new_ordinary_script_uses_prepared_bytes_after_live_edit(self):
        checkout = self.directory / 'checkout'
        shutil.copytree(REPO / 'scripts', checkout / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(SKILLS / 'artifact-bookkeeping', checkout / '.agents/skills/artifact-bookkeeping',
                        ignore=shutil.ignore_patterns('__pycache__', 'tests'))
        skill = checkout / '.agents/skills/tiny'; skill.mkdir()
        (skill / 'SKILL.md').write_text('## Bookkeeping\nUse artifact-bookkeeping: text input, text output; no packages.\n')
        program = skill / 'summary.py'
        program.write_text('import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text("captured:"+Path(sys.argv[1]).read_text())\n')
        request = self.request()
        request['declaration'] = '.agents/skills/tiny/SKILL.md'
        request['skill'] = 'tiny'
        request['code'] = ['.agents/skills/tiny/summary.py']
        request['command'] = ['{python}', '{code:.agents/skills/tiny/summary.py}', '{input:text}', '{output:result/result.txt}']
        with patch('ledger_execution.ROOT', checkout), patch('artifact_ledger.ROOT', checkout):
            intent = prepare(self.ledger, request)
            program.write_text('raise SystemExit("changed live code must not execute")\n')
            execute(self.ledger, intent['run_id'])
            event = finish(self.ledger, intent['run_id'])
        record = self.ledger.resolve(**reference(event['data']['updates'][0]))
        self.assertEqual((self.data / record['history_path'] / 'result.txt').read_text(), 'captured:Twin-kle star\n')

    def test_successful_output_edit_is_preserved_and_blocks_finish(self):
        intent = prepare(self.ledger, self.request())
        execute(self.ledger, intent['run_id'])
        output = Path(status(self.ledger, intent['run_id'])['plan']['bindings']['output:result']) / 'result.txt'
        output.write_text('unexpected user edit')
        with self.assertRaisesRegex(ValueError, 'Successful output bytes changed'):
            finish(self.ledger, intent['run_id'])
        self.assertEqual(output.read_text(), 'unexpected user edit')
        self.assertNotIn(intent['outputs'][0]['artifact_id'], self.ledger.state()['artifacts'])

    def test_tampered_execution_plan_code_and_input_refuse(self):
        intent = prepare(self.ledger, self.request())
        work = self.ledger.path(intent['workspace'])
        original = (work / 'execution-plan.json').read_bytes()
        plan = json.loads(original); plan['command'][-1] = 'partial'
        (work / 'execution-plan.json').write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'immutable operation'):
            execute(self.ledger, intent['run_id'])
        (work / 'execution-plan.json').write_bytes(original)
        plan = json.loads(original)
        Path(plan['bindings']['input:text']).write_text('changed input')
        with self.assertRaisesRegex(ValueError, 'snapshot altered'):
            execute(self.ledger, intent['run_id'])
        self.assertFalse((work / 'execution.json').exists())
        other = prepare(self.ledger, self.request())
        plan = status(self.ledger, other['run_id'])['plan']
        Path(plan['command'][1]).write_text('raise SystemExit(99)')
        with self.assertRaises(ValueError):
            execute(self.ledger, other['run_id'])

    def test_indirect_binding_validated_before_prepare_and_original_preserved(self):
        manifest = self.data / 'map.json'; manifest.write_text(json.dumps({'file': self.original.name}))
        dep = self.register(manifest)
        request = self.request()
        request['inputs']['map'] = dep
        request['outputs']['result']['dependencies'].append('map')
        request['documents'] = {'map': {'input': 'map', 'bindings': {'/file': '{input:text}'}}}
        self.original.write_text('different')
        before = set((self.data / 'ledger').iterdir())
        with self.assertRaisesRegex(ValueError, 'Indirect input differs'):
            prepare(self.ledger, request)
        self.assertEqual(set((self.data / 'ledger').iterdir()), before)
        self.original.write_text('Twin-kle star\n')
        raw = manifest.read_bytes()
        intent, _ = self.run_operation(request)
        plan = status(self.ledger, intent['run_id'])['plan']
        self.assertEqual(json.loads(Path(plan['bindings']['document:map']).read_text())['file'], plan['bindings']['input:text'])
        self.assertEqual(manifest.read_bytes(), raw)

    def test_flow_instructions_bind_every_image_without_mutating_storyboard(self):
        image = self.data / 'pose.png'; image.write_bytes(b'formatting fixture')
        image_dep = self.register(image)
        story = self.data / 'story.json'
        story.write_text(json.dumps({'title': 'Fixture', 'context': 'Synthetic formatting test',
                                    'style': 'cartoon', 'video_model': 'fixture', 'aspect_ratio': '16:9',
                                    'images': [{'id': 'pose', 'file': image.name, 'description': 'A wave'}],
                                    'clips': [{'id': 'one', 'start_image': 'pose', 'duration_s': 2, 'action': 'Wave'}]}))
        before = story.read_bytes()
        script = '.agents/skills/barnsang-video/scripts/write_flow_instructions.py'
        request = self.request()
        request.update(skill='barnsang-video', declaration='.agents/skills/barnsang-video/SKILL.md', code=[script],
                       inputs={'story': self.register(story), 'image': image_dep},
                       documents={'story': {'input': 'story', 'bindings': {'/images/0/file': '{input:image}'}}},
                       command=['{python}', '{code:' + script + '}', '--storyboard', '{document:story}',
                                '--output', '{output:result/result.txt}'])
        request['outputs']['result']['dependencies'] = ['story', 'image']
        _, event = self.run_operation(request)
        record = self.ledger.resolve(**reference(event['data']['updates'][0]))
        self.assertEqual(len(record['dependencies']), 2)
        self.assertIn('START pose.png', (self.data / record['history_path'] / 'result.txt').read_text())
        self.assertEqual(story.read_bytes(), before)

    def test_published_json_references_history_and_recovers_without_production(self):
        request = self.request('paths'); request['publish_json'] = ['{output:result/result.txt}']
        intent = prepare(self.ledger, request)
        execute(self.ledger, intent['run_id'])
        with patch.object(self.ledger, '_materialize', side_effect=OSError('interrupted view')):
            with self.assertRaisesRegex(OSError, 'interrupted view'):
                finish(self.ledger, intent['run_id'])
        before = (self.ledger.path(intent['workspace']) / 'execution.json').read_bytes()
        event = finish(self.ledger, intent['run_id'])
        record = self.ledger.resolve(**reference(event['data']['updates'][0]))
        content = json.loads((self.data / record['history_path'] / 'result.txt').read_text())
        self.assertTrue(Path(content['source']).is_file())
        self.assertTrue(Path(content['output']).is_file())
        self.assertIn('/history/', content['source'])
        self.assertEqual(before, (self.ledger.path(intent['workspace']) / 'execution.json').read_bytes())
        self.assertEqual(finish(self.ledger, intent['run_id']), event)

    def test_handoff_uncertainty_refuses_duplicate_then_accepts_observed_receipt(self):
        request = self.request(); request['command'] = None; request['handoff'] = 'Write one reviewed note'
        intent = prepare(self.ledger, request)
        handoff(self.ledger, intent['run_id'])
        out = Path(status(self.ledger, intent['run_id'])['plan']['bindings']['output:result']) / 'result.txt'
        out.write_text('observed result')
        with self.assertRaisesRegex(ValueError, 'uncertainty'):
            finish(self.ledger, intent['run_id'])
        with self.assertRaisesRegex(ValueError, 'already started'):
            handoff(self.ledger, intent['run_id'])
        handoff(self.ledger, intent['run_id'], {'evidence': 'Observed one local result', 'result_sha256': hashlib.sha256(out.read_bytes()).hexdigest()})
        finish(self.ledger, intent['run_id'])

    def test_recovery_rejects_forged_transform_paths_and_content_before_writing(self):
        for change in ('external-path', 'changed-content'):
            with self.subTest(change=change):
                request = self.request('paths')
                request['publish_json'] = ['{output:result/result.txt}']
                intent = prepare(self.ledger, request)
                run_id = intent['run_id']
                execute(self.ledger, run_id)
                with patch.object(self.ledger, 'finalize', side_effect=OSError('publication interrupted')):
                    with self.assertRaisesRegex(OSError, 'publication interrupted'):
                        finish(self.ledger, run_id)
                work = self.ledger.path(intent['workspace'])
                journal = work / 'publication-transforms.json'
                transformations = json.loads(journal.read_text())
                output = Path(status(self.ledger, run_id)['plan']['bindings']['output:result']) / 'result.txt'
                before_output = output.read_bytes()
                unrelated = self.directory / 'unrelated.txt'
                unrelated.write_text('preserve unrelated data')
                if change == 'external-path':
                    content = 'undeclared replacement'
                    transformations[str(unrelated)] = {
                        'content': content, 'sha256': hashlib.sha256(content.encode()).hexdigest()}
                else:
                    transformations[str(output)]['content'] = '{"source":"fabricated"}\n'
                journal.write_text(json.dumps(transformations))
                with self.assertRaises(ValueError):
                    finish(self.ledger, run_id)
                self.assertEqual(unrelated.read_text(), 'preserve unrelated data')
                self.assertEqual(output.read_bytes(), before_output)
                self.assertNotIn(intent['outputs'][0]['artifact_id'], self.ledger.state()['artifacts'])

    def test_unbound_missing_input_and_conflicting_revision_refuse(self):
        request = self.request(); request['inputs']['text']['files'] = ['missing.txt']
        with self.assertRaises(ValueError): prepare(self.ledger, request)
        # A previous current base remains readable but is not silently revised again.
        _, event = self.run_operation()
        ref = reference(event['data']['updates'][0])
        request = self.request(); request['outputs']['result'].update(action='revise', base=ref)
        self.run_operation(request)
        with self.assertRaisesRegex(ValueError, 'not the current revision'):
            prepare(self.ledger, request)


class EntrypointInventoryTests(unittest.TestCase):
    def test_production_has_no_reverse_dependency(self):
        forbidden = ['ledger_producer', 'ledger_python', 'artifact_ledger', 'ledger_tools',
                     'ledger_execution', 'artifact-bookkeeping/scripts', '--ledger-request', 'require_workspace']
        for path in SKILLS.rglob('*.py'):
            if {'tests', '_build', 'artifact-bookkeeping'} & set(path.relative_to(REPO).parts):
                continue
            with self.subTest(path=str(path)):
                text = path.read_text()
                for name in forbidden:
                    self.assertNotIn(name, text)

    def test_inventory_covers_current_functions_and_owners(self):
        paths = {path.relative_to(REPO).as_posix() for folder in [SKILLS, REPO / 'scripts']
                 for path in folder.rglob('*') if path.suffix in {'.py', '.java', '.html'}
                 and not {'tests', '_build'} & set(path.relative_to(REPO).parts)}
        owners = {item['path']: item for item in json.loads((REPO / 'docs/skill-imports.json').read_text())['code_ownership']}
        self.assertEqual(paths, set(owners))
        records = []
        for relative in sorted(paths):
            record = {'path': relative, 'owner': owners[relative]['owner'],
                      'source_sha256': hashlib.sha256((REPO / relative).read_bytes()).hexdigest()}
            records.append(record)
            if not relative.endswith('.py'):
                continue
            tree = ast.parse((REPO / relative).read_text())
            functions = {}
            def walk(body, prefix=''):
                for node in body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        name = prefix + node.name
                        if not isinstance(node, ast.ClassDef):
                            functions[name] = sorted({ast.unparse(call.func) for call in ast.walk(node) if isinstance(call, ast.Call)})
                        walk(node.body, name + '.')
            walk(tree.body)
            record['functions'] = [{'name': name, 'callees': calls} for name, calls in functions.items()]
            record['argument_definitions'] = sorted(
                ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument')
        report = REPO / '_build/skill-entrypoints.json'
        report.parent.mkdir(exist_ok=True)
        report.write_text(json.dumps({
            'schema_version': 2,
            'note': 'Generated source inventory; route restrictions live in docs/artifact-ledger-entrypoints.md. Not runtime registration.',
            'entrypoints': records,
        }, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
