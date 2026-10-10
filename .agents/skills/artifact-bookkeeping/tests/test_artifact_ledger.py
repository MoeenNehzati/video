"""Public lifecycle acceptance fixtures; all bytes are synthetic and disposable."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / '.agents/skills/artifact-bookkeeping/scripts'))

from artifact_ledger import Ledger, LedgerError, reference
from scripts.read_config import ROOT


class ArtifactLedgerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ledger ')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.data = self.work / 'data with spaces'
        self.data.mkdir()
        self.config = {'paths': {'data_root': str(self.data)},
                       'bookkeeping': {'actor_id': 'fixture', 'host_id': str(uuid4())}}
        self.ledger = Ledger(self.config)
        self.song = self.ledger.create_song('Synthetic song')
        self.producer = self.ledger.producer('fixture', 'artifact-bookkeeping', 'test',
                                             code_paths=[ROOT / 'scripts/__init__.py'])

    def spec(self, kind, deps=(), *, files=None, parent=None, **extra):
        return {'kind': kind, 'label': kind, 'song_ids': [self.song['song_id']],
                'storage_parent': parent, 'dependencies': list(deps),
                'contract': {'files': [{'path': name, 'role': kind}
                                       for name in (files or [kind + '.txt'])]}, **extra}

    def dep(self, ref, filename, purpose='fixture input'):
        return {**ref, 'files': [filename], 'purpose': purpose}

    def prepare(self, specs):
        return self.ledger.prepare('fixture', specs, copy.deepcopy(self.producer))

    def outputs(self, intent, number=0):
        return self.data / intent['workspace'] / intent['outputs'][number]['output_slot']

    def publish(self, spec, contents=None):
        intent = self.prepare([spec])
        contents = contents or {file['path']: file['path'].encode()
                                for file in spec['contract']['files']}
        for name, content in contents.items():
            destination = self.outputs(intent) / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        event = self.ledger.finalize(intent['run_id'])
        return reference(event['data']['updates'][0]), event, intent

    def history_file(self, ref, name):
        revision = self.ledger.resolve(**ref)
        return self.data / revision['history_path'] / name

    def view_file(self, ref, name):
        revision = self.ledger.resolve(**ref)
        return self.data / revision['path'] / name

    def test_experiments_revision_and_old_dependency_keep_all_bytes(self):
        source_a, _, _ = self.publish(self.spec('source'))
        source_b, _, _ = self.publish(self.spec('source'))
        deps = [self.dep(source_a, 'source.txt'), self.dep(source_b, 'source.txt')]
        xml_a, _, _ = self.publish(self.spec('xml', deps, parent=source_a['artifact_id']))
        xml_b, _, _ = self.publish(self.spec('xml', deps, parent=source_a['artifact_id']))
        report, _, _ = self.publish(self.spec('report', [self.dep(xml_a, 'xml.txt')],
                                               parent=xml_a['artifact_id']))
        arrangements = []
        for xml in (xml_a, xml_b):
            for _ in range(2):
                midi, _, _ = self.publish(self.spec('midi', [self.dep(xml, 'xml.txt')],
                                                      parent=xml['artifact_id']))
                arrangements.append(midi)
                for _ in range(2):
                    render, _, _ = self.publish(self.spec('render', [self.dep(midi, 'midi.txt')],
                                                          parent=midi['artifact_id'],
                                                          files=['full.wav', 'backing.wav']))
                    self.assertTrue(self.history_file(render, 'backing.wav').exists())
        original = self.view_file(xml_a, 'xml.txt').read_bytes()
        revised, _, _ = self.publish(self.spec('xml', deps, action='revise', base=xml_a),
                                     {'xml.txt': b'corrected source'})
        self.assertEqual(revised['artifact_id'], xml_a['artifact_id'])
        self.assertNotEqual(revised['revision_id'], xml_a['revision_id'])
        self.assertEqual(self.history_file(xml_a, 'xml.txt').read_bytes(), original)
        self.assertEqual(self.view_file(revised, 'xml.txt').read_bytes(), b'corrected source')
        for midi in arrangements[:2]:
            self.assertEqual(self.ledger.resolve(**midi)['dependencies'][0]['revision_id'],
                             xml_a['revision_id'])
            self.assertTrue(self.view_file(midi, 'midi.txt').exists())
        branch, _, _ = self.publish(self.spec('xml', deps, parent=source_a['artifact_id'],
                                              branched_from=xml_a))
        self.assertEqual(self.ledger.resolve(**branch)['branched_from'], xml_a)
        self.assertNotEqual(branch['artifact_id'], xml_a['artifact_id'])
        self.assertEqual(self.ledger.inputs(**report)[0]['revision_id'], xml_a['revision_id'])
        self.ledger.select('song:' + self.song['song_id'], 'xml', 'transcription', xml_a)
        chosen = self.ledger.list(kind='xml', selected=True)['artifacts']
        self.assertEqual([row['revision_id'] for row in chosen], [xml_a['revision_id']])
        self.assertFalse(chosen[0]['current'])
        self.assertEqual(self.ledger.resolve(xml_a['artifact_id'])['revision_id'], revised['revision_id'])

    def test_prepare_freezes_input_and_rejects_altered_snapshot(self):
        source, _, _ = self.publish(self.spec('source'), {'source.txt': b'original'})
        spec = self.spec('xml', [self.dep(source, 'source.txt')], parent=source['artifact_id'])
        intent = self.prepare([spec])
        slot = self.data / intent['workspace'] / intent['input_slots'][0]['slot'] / 'source.txt'
        self.view_file(source, 'source.txt').write_bytes(b'local edit')
        self.assertEqual(slot.read_bytes(), b'original')
        self.assertEqual(self.history_file(source, 'source.txt').read_bytes(), b'original')
        slot.write_bytes(b'mutated execution input')
        (self.outputs(intent) / 'xml.txt').write_bytes(b'output')
        with self.assertRaisesRegex(ValueError, 'snapshot|Input'):
            self.ledger.finalize(intent['run_id'])
        self.assertFalse(any(event['event_type'] == 'operation.completed'
                             and event['data']['run_id'] == intent['run_id']
                             for event in self.ledger.state()['events'].values()))

    def test_browsing_edit_after_prepare_does_not_change_consumed_input(self):
        source, _, _ = self.publish(self.spec('source'), {'source.txt': b'original'})
        intent = self.prepare([self.spec('xml', [self.dep(source, 'source.txt')],
                                         parent=source['artifact_id'])])
        self.view_file(source, 'source.txt').write_bytes(b'local browsing edit')
        slot = self.data / intent['workspace'] / intent['input_slots'][0]['slot'] / 'source.txt'
        (self.outputs(intent) / 'xml.txt').write_bytes(slot.read_bytes())
        event = self.ledger.finalize(intent['run_id'])
        derived = reference(event['data']['updates'][0])
        self.assertEqual(self.history_file(derived, 'xml.txt').read_bytes(), b'original')
        self.assertEqual(self.view_file(source, 'source.txt').read_bytes(), b'local browsing edit')
        self.assertEqual(self.ledger.inputs(**derived)[0]['revision_id'], source['revision_id'])

    def test_full_bundle_and_multiple_outputs_are_atomic(self):
        intent = self.prepare([self.spec('render', files=['full.wav', 'backing.wav']),
                               self.spec('report')])
        (self.outputs(intent) / 'full.wav').write_bytes(b'full')
        (self.outputs(intent, 1) / 'report.txt').write_bytes(b'report')
        with self.assertRaisesRegex(ValueError, 'contract'):
            self.ledger.finalize(intent['run_id'])
        for output in intent['outputs']:
            self.assertNotIn(output['artifact_id'], self.ledger.state()['artifacts'])
        (self.outputs(intent) / 'backing.wav').write_bytes(b'backing')
        (self.outputs(intent) / 'unexpected.txt').write_bytes(b'unknown')
        with self.assertRaisesRegex(ValueError, 'contract'):
            self.ledger.finalize(intent['run_id'])
        (self.outputs(intent) / 'unexpected.txt').unlink()
        event = self.ledger.finalize(intent['run_id'])
        self.assertEqual(len(event['data']['updates']), 2)
        for output in intent['outputs']:
            self.assertIn(output['artifact_id'], self.ledger.state()['artifacts'])

    def test_same_completion_report_pins_allocated_output_revision(self):
        aid, rid = str(uuid4()), str(uuid4())
        output_ref = {'artifact_id': aid, 'revision_id': rid}
        intent = self.prepare([
            self.spec('xml', artifact_id=aid, revision_id=rid),
            self.spec('report', [self.dep(output_ref, 'xml.txt', 'verified output')], parent=aid),
        ])
        self.assertEqual(intent['inputs'], [])
        (self.outputs(intent) / 'xml.txt').write_bytes(b'synthetic score')
        (self.outputs(intent, 1) / 'report.txt').write_bytes(b'synthetic check')
        event = self.ledger.finalize(intent['run_id'])
        xml, report = [reference(update) for update in event['data']['updates']]
        self.assertEqual(xml, output_ref)
        self.assertEqual(self.ledger.inputs(**report)[0]['revision_id'], rid)
        self.assertTrue(self.view_file(report, 'report.txt').is_relative_to(self.view_file(xml, 'xml.txt').parent))

    def test_recovery_after_completion_repairs_view_without_new_identity(self):
        intent = self.prepare([self.spec('xml')])
        (self.outputs(intent) / 'xml.txt').write_bytes(b'published')
        with patch.object(self.ledger, '_materialize', side_effect=OSError('simulated interruption')):
            with self.assertRaisesRegex(OSError, 'interruption'):
                self.ledger.finalize(intent['run_id'])
        before = {path.name: path.read_bytes() for path in (self.data / 'ledger').glob('*.json')}
        event = self.ledger.recover(intent['run_id'])
        ref = reference(event['data']['updates'][0])
        self.assertEqual(self.view_file(ref, 'xml.txt').read_bytes(), b'published')
        self.assertEqual({path.name: path.read_bytes() for path in (self.data / 'ledger').glob('*.json')}, before)
        self.assertEqual(self.ledger.recover(intent['run_id']), event)

    def test_recovery_before_event_reuses_saved_completion_and_history(self):
        intent = self.prepare([self.spec('xml')])
        (self.outputs(intent) / 'xml.txt').write_bytes(b'prepared')
        append = self.ledger._append

        def interrupted(event, state=None):
            if event['event_type'] == 'operation.completed':
                raise OSError('before completion publication')
            return append(event, state)

        with patch.object(self.ledger, '_append', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.ledger.finalize(intent['run_id'])
        journal = self.data / intent['workspace'] / 'publication.json'
        saved = journal.read_bytes()
        event = self.ledger.recover(intent['run_id'])
        self.assertEqual(json.loads(saved), event)
        self.assertEqual(journal.read_bytes(), saved)
        self.assertEqual(self.ledger.recover(intent['run_id']), event)

    def test_failed_attempt_is_terminal_and_new_attempt_is_distinct(self):
        intent = self.prepare([self.spec('render')])
        (self.outputs(intent) / 'render.txt').write_bytes(b'partial evidence')
        self.ledger.fail(intent['run_id'], 'fixture', 'simulated producer failure')
        with self.assertRaisesRegex(ValueError, 'terminal'):
            self.ledger.finalize(intent['run_id'])
        replacement, _, retry = self.publish(self.spec('render'))
        self.assertNotEqual(retry['run_id'], intent['run_id'])
        self.assertNotEqual(replacement['artifact_id'], intent['outputs'][0]['artifact_id'])
        self.assertNotIn(intent['outputs'][0]['artifact_id'], self.ledger.state()['artifacts'])

    def test_stale_revision_is_rejected_and_descendants_unknown_files_survive(self):
        source, _, _ = self.publish(self.spec('source', files=['keep.txt', 'retire.txt']))
        child, _, _ = self.publish(self.spec('xml', [self.dep(source, 'keep.txt')],
                                              parent=source['artifact_id']))
        unknown = self.view_file(source, 'keep.txt').parent / 'unknown.txt'
        unknown.write_bytes(b'not owned')
        stale = self.prepare([self.spec('source', action='revise', base=source, files=['keep.txt'])])
        (self.outputs(stale) / 'keep.txt').write_bytes(b'stale')
        current, _, _ = self.publish(self.spec('source', action='revise', base=source,
                                              files=['keep.txt']), {'keep.txt': b'current'})
        with self.assertRaisesRegex(ValueError, 'Stale|stale'):
            self.ledger.finalize(stale['run_id'])
        self.assertEqual(unknown.read_bytes(), b'not owned')
        self.assertTrue(self.view_file(child, 'xml.txt').exists())
        self.assertFalse(self.view_file(current, 'retire.txt').exists())
        self.assertTrue(self.history_file(source, 'retire.txt').exists())

    def test_unexpected_local_edit_is_preserved_during_revision_repair(self):
        source, _, _ = self.publish(self.spec('source'))
        intent = self.prepare([self.spec('source', action='revise', base=source)])
        (self.outputs(intent) / 'source.txt').write_bytes(b'new revision')
        visible = self.view_file(source, 'source.txt')
        visible.write_bytes(b'unexpected manual edit')
        with self.assertRaisesRegex(ValueError, 'edit|unexpected|Unexpected|overwrite'):
            self.ledger.finalize(intent['run_id'])
        self.assertEqual(visible.read_bytes(), b'unexpected manual edit')
        self.assertEqual(self.history_file(source, 'source.txt').read_bytes(), b'source.txt')

    def test_import_preserves_original_name_bytes_and_distinct_acquisitions(self):
        original = self.work / 'Original source sheet.txt'
        original.write_bytes(b'imported original')
        refs = []
        for _ in range(2):
            event = self.ledger.import_files({'sheet.txt': original}, kind='source', label='Source',
                                             song_ids=[self.song['song_id']], producer=self.producer)
            refs.append(reference(event['data']['updates'][0]))
        original.write_bytes(b'changed outside managed storage')
        self.assertNotEqual(refs[0], refs[1])
        for ref in refs:
            record = self.ledger.resolve(**ref)
            self.assertEqual(record['files'][0]['original_name'], original.name)
            self.assertEqual(self.history_file(ref, 'sheet.txt').read_bytes(), b'imported original')
            self.assertIn('origin', record['producer']['unknowns'])

    def test_paths_reject_unsafe_contracts_before_workspace_side_effects(self):
        unsafe = ('../outside.txt', '/absolute.txt', 'C:/drive.txt', 'CON.txt',
                  'bad name.txt', 'a' * 65, 'trailing.', 'sub/../../escape.txt')
        before = sorted(path.as_posix() for path in self.data.rglob('*'))
        for name in unsafe:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.prepare([self.spec('xml', files=[name])])
            self.assertEqual(sorted(path.as_posix() for path in self.data.rglob('*')), before)
        with self.assertRaises(ValueError):
            self.prepare([self.spec('xml', files=['PROMPT.md', 'prompt.md'])])

    def test_parent_revision_cannot_claim_descendant_files_at_prepare(self):
        source, _, _ = self.publish(self.spec('source'))
        child, _, _ = self.publish(self.spec('xml', [self.dep(source, 'source.txt')],
                                              parent=source['artifact_id']))
        child_directory = Path(self.ledger.resolve(**child)['path']).name
        before = sorted(path.as_posix() for path in self.data.rglob('*'))
        with self.assertRaises(ValueError):
            self.prepare([self.spec('source', action='revise', base=source,
                                     files=[child_directory + '/xml.txt'])])
        self.assertEqual(sorted(path.as_posix() for path in self.data.rglob('*')), before)
        self.assertEqual(self.view_file(child, 'xml.txt').read_bytes(), b'xml.txt')

    def test_generated_destination_collision_and_file_ancestor_fail_before_events(self):
        from unittest.mock import patch
        identifier = str(uuid4())
        destination = self.data / 'songs' / ('collision'[:8] + '--' + identifier.replace('-', '')[:12])
        destination.write_bytes(b'unknown user file')
        before = {p.name: p.read_bytes() for p in (self.data / 'ledger').glob('*.json')}
        with patch('artifact_ledger.new_id', return_value=identifier):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                self.ledger.create_song('collision')
        obstacle = self.data / 'work' / 'obstacle'
        obstacle.write_bytes(b'file, not folder')
        with self.assertRaisesRegex(ValueError, 'not a directory'):
            self.ledger.path('work/obstacle/output.txt')
        self.assertEqual({p.name: p.read_bytes() for p in (self.data / 'ledger').glob('*.json')}, before)
        self.assertEqual(destination.read_bytes(), b'unknown user file')

    def test_root_relocation_keeps_historical_dependencies(self):
        source, _, _ = self.publish(self.spec('source'))
        child, _, _ = self.publish(self.spec('xml', [self.dep(source, 'source.txt')],
                                              parent=source['artifact_id']))
        relocated = self.work / 'relocated root with spaces'
        shutil.copytree(self.data, relocated)
        config = copy.deepcopy(self.config)
        config['paths']['data_root'] = str(relocated)
        ledger = Ledger(config)
        resolved = ledger.resolve(**child)
        self.assertTrue(resolved['available'])
        self.assertEqual(resolved['dependencies'][0]['revision_id'], source['revision_id'])
        self.assertEqual((relocated / resolved['history_path'] / 'xml.txt').read_bytes(), b'xml.txt')

    def test_visual_alternatives_selection_and_transitive_shared_inputs(self):
        source, _, _ = self.publish(self.spec('source'))
        audio, _, _ = self.publish(self.spec('audio', [self.dep(source, 'source.txt')],
                                              parent=source['artifact_id']))
        character_spec = self.spec('character')
        character_spec['song_ids'] = []
        character, _, _ = self.publish(character_spec)
        films = []
        takes = []
        for _ in range(2):
            story, _, _ = self.publish(self.spec('story', [self.dep(source, 'source.txt'),
                                                          self.dep(audio, 'audio.txt')],
                                                  parent=source['artifact_id']))
            image, _, _ = self.publish(self.spec('image', [self.dep(story, 'story.txt'),
                                                          self.dep(character, 'character.txt')],
                                                  parent=story['artifact_id']))
            for _ in range(2):
                take, _, _ = self.publish(self.spec('clip', [self.dep(image, 'image.txt')],
                                                     parent=image['artifact_id']))
                takes.append(take)
                film, _, _ = self.publish(self.spec('film', [self.dep(story, 'story.txt'),
                                                            self.dep(audio, 'audio.txt'),
                                                            self.dep(take, 'clip.txt')],
                                                    parent=story['artifact_id']))
                films.append(film)
        scope = 'song:' + self.song['song_id']
        self.ledger.review(films[0], 'film', 'viewing', 'pass', notes='Synthetic fixture only')
        self.assertEqual(self.ledger.list(kind='film', selected=True)['artifacts'], [])
        self.ledger.select(scope, 'film', 'viewing', films[0])
        self.ledger.select(scope, 'film', 'viewing', films[-1])
        selected = self.ledger.list(kind='film', selected=True)['artifacts']
        self.assertEqual([record['revision_id'] for record in selected], [films[-1]['revision_id']])
        self.assertEqual(len(self.ledger.list(kind='film')['artifacts']), 4)
        self.assertIn(takes[0]['revision_id'],
                      [dep['revision_id'] for dep in self.ledger.inputs(**films[0])])
        ancestors = self.ledger.inputs(**films[-1], transitive=True)
        self.assertIn(character['revision_id'], [dep['revision_id'] for dep in ancestors])
        consumers = self.ledger.consumers(**character, transitive=True)
        self.assertTrue(set(ref['revision_id'] for ref in films)
                        <= {ref['revision_id'] for ref in consumers})
        self.ledger.withdraw(films[-1]['artifact_id'], reason='Fixture withdrawal')
        selected = self.ledger.list(kind='film', selected=True)['artifacts']
        self.assertTrue(selected[0]['withdrawn'])
        self.assertTrue(self.history_file(films[-1], 'film.txt').exists())

    def test_flow_kit_revision_preserves_old_images_and_clip_reference(self):
        kit, _, _ = self.publish(self.spec('flow-kit', files=['PROMPT.md', 'image.png']))
        clip, _, _ = self.publish(self.spec('clip', [self.dep(kit, 'image.png')],
                                             parent=kit['artifact_id']))
        replacement, _, _ = self.publish(self.spec('flow-kit', action='revise', base=kit,
                                                   files=['PROMPT.md', 'replacement.png']))
        self.assertTrue(self.history_file(kit, 'image.png').exists())
        self.assertFalse(self.view_file(replacement, 'image.png').exists())
        self.assertEqual(self.ledger.inputs(**clip)[0]['revision_id'], kit['revision_id'])
        self.assertTrue(self.view_file(clip, 'clip.txt').exists())

    def test_subtree_move_keeps_ids_history_and_blocks_unknown_files(self):
        source, _, _ = self.publish(self.spec('source'))
        child, _, _ = self.publish(self.spec('xml', [self.dep(source, 'source.txt')],
                                              parent=source['artifact_id']))
        old_history = self.ledger.resolve(**child)['history_path']
        unknown = self.view_file(child, 'xml.txt').parent / 'unknown.txt'
        unknown.write_bytes(b'preserve me')
        with self.assertRaisesRegex(ValueError, 'Unknown|unknown'):
            self.ledger.move(source['artifact_id'], 'renamed', 'fixture move')
        self.assertEqual(unknown.read_bytes(), b'preserve me')
        unknown.unlink()
        event = self.ledger.move(source['artifact_id'], 'renamed', 'fixture move')
        self.assertEqual(len(event['data']['mapping']), 2)
        self.assertEqual(self.ledger.resolve(**child)['history_path'], old_history)
        self.assertTrue(self.view_file(child, 'xml.txt').exists())
        self.assertIn('/renamed/', self.ledger.resolve(**child)['path'])
        self.assertEqual(self.ledger.inputs(**child)[0]['revision_id'], source['revision_id'])

    def test_resource_snapshot_is_private_pinned_and_checked_after_execution(self):
        installation = self.work / 'installed samples'
        installation.mkdir()
        sample = installation / 'sample.bin'
        sample.write_bytes(b'version one')
        self.config['paths']['resource_cache'] = str(self.work / 'resource cache')
        self.config['resources'] = {'samples': str(installation)}
        descriptor = self.ledger.register_resource('resources.samples', ['sample.bin'],
                                                  label='Fixture samples', version='one',
                                                  source='Synthetic test resource')
        resource = reference(descriptor['data']['updates'][0])
        producer = copy.deepcopy(self.producer)
        producer['resources'] = [resource]
        intent = self.ledger.prepare('fixture', [self.spec('render')], producer)
        snapshot = next(iter(self.ledger.resource_paths(intent['run_id']).values())) / 'sample.bin'
        self.assertEqual(snapshot.read_bytes(), b'version one')
        sample.write_bytes(b'version two')
        self.assertEqual(snapshot.read_bytes(), b'version one')
        (self.outputs(intent) / 'render.txt').write_bytes(b'rendered')
        self.ledger.finalize(intent['run_id'])
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.ledger.prepare('fixture', [self.spec('render')], producer)
        sample.write_bytes(b'version one')
        another = self.ledger.prepare('fixture', [self.spec('render')], producer)
        snapshot = next(iter(self.ledger.resource_paths(another['run_id']).values())) / 'sample.bin'
        snapshot.write_bytes(b'altered during use')
        (self.outputs(another) / 'render.txt').write_bytes(b'rendered')
        with self.assertRaisesRegex(ValueError, 'Resource snapshot'):
            self.ledger.finalize(another['run_id'])

    def test_reconciliation_distinguishes_missing_altered_and_unmanaged(self):
        source, _, _ = self.publish(self.spec('source', files=['one.txt', 'two.txt']))
        self.view_file(source, 'one.txt').unlink()
        self.view_file(source, 'two.txt').write_bytes(b'altered')
        (self.data / 'legacy.txt').write_bytes(b'unmanaged')
        report = self.ledger.reconcile()
        self.assertEqual(report['missing'], [self.view_file(source, 'one.txt').relative_to(self.data).as_posix()])
        self.assertEqual(report['altered'], [self.view_file(source, 'two.txt').relative_to(self.data).as_posix()])
        self.assertIn('legacy.txt', report['unmanaged'])

    def test_cli_from_another_working_directory_with_explicit_config(self):
        config_root = self.work / 'config with spaces'
        config_root.mkdir()
        (config_root / 'config.toml').write_text(
            '[paths]\ndata_root = ' + json.dumps(str(self.data)) + '\n'
            '[bookkeeping]\nactor_id = "fixture"\nhost_id = '
            + json.dumps(self.config['bookkeeping']['host_id']) + '\n')
        result = subprocess.run([sys.executable, str(ROOT / '.agents/skills/artifact-bookkeeping/scripts/artifact_ledger.py'),
                                 'list', '--json', '--config-root', str(config_root)],
                                cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['issues'], [])

    def test_historical_frontier_is_causal_and_read_only(self):
        original, event, _ = self.publish(self.spec('xml'), {'xml.txt': b'old'})
        latest, _, _ = self.publish(self.spec('xml', action='revise', base=original),
                                    {'xml.txt': b'new'})
        old = Ledger(self.config, frontier=[event['event_id']])
        self.assertEqual(old.resolve(original['artifact_id'])['revision_id'], original['revision_id'])
        self.assertEqual(self.ledger.resolve(original['artifact_id'])['revision_id'], latest['revision_id'])
        with self.assertRaisesRegex(ValueError, 'read-only'):
            old.create_song('cannot write historical state')


if __name__ == '__main__':
    unittest.main()
