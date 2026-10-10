"""Public API replica and crash fixtures, with isolated synthetic roots."""
import copy
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / '.agents/skills/artifact-bookkeeping/scripts'))

import artifact_ledger as ledger_module
from artifact_ledger import Ledger, reference
import test_artifact_ledger as fixtures


class LedgerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ArtifactLedgerTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def replica(self, name='replica', *, copy_catalogue=True):
        f = self.f
        root = f.work / name
        shutil.copytree(f.data, root)
        if not copy_catalogue and (root / 'catalogue').exists():
            shutil.rmtree(root / 'catalogue')
        config = copy.deepcopy(f.config)
        config['paths']['data_root'] = str(root)
        config['bookkeeping']['host_id'] = str(uuid4())
        ledger = Ledger(config)
        if copy_catalogue:
            ledger.rebuild(view=True)
        return ledger

    def synchronize(self, source, target):
        # Merge immutable records only; each machine keeps its private projection journal.
        for directory in ('ledger', 'history'):
            for path in (source.root / directory).rglob('*'):
                if not path.is_file():
                    continue
                dest = target.root / path.relative_to(source.root)
                if dest.exists():
                    self.assertEqual(dest.read_bytes(), path.read_bytes())
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)

    def write_outputs(self, ledger, intent, payload=b'output'):
        for output in intent['outputs']:
            for file in output['contract']['files']:
                path = ledger.root / intent['workspace'] / output['output_slot'] / file['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

    def test_replica_revision_conflict_keeps_exact_history_until_resolution(self):
        f = self.f
        base, _, _ = f.publish(f.spec('xml'))
        other = self.replica()
        spec = f.spec('xml', action='revise', base=base)
        left = f.prepare([spec])
        right = other.prepare('fixture', [spec], copy.deepcopy(f.producer))
        self.write_outputs(f.ledger, left, b'left correction')
        self.write_outputs(other, right, b'right correction')
        left_done = f.ledger.finalize(left['run_id'])
        right_done = other.finalize(right['run_id'])
        self.synchronize(other, f.ledger)
        state = f.ledger.state()
        key = f'artifact/{base["artifact_id"]}/revision'
        self.assertEqual(state['heads'][key], sorted([left_done['event_id'], right_done['event_id']]))
        with self.assertRaisesRegex(ValueError, 'conflict'):
            f.ledger.resolve(base['artifact_id'])
        left_ref = reference(left_done['data']['updates'][0])
        right_ref = reference(right_done['data']['updates'][0])
        self.assertTrue(f.ledger.resolve(**left_ref)['available'])
        self.assertTrue(f.ledger.resolve(**right_ref)['available'])
        f.ledger.resolve_conflict([{'key': key, 'heads': state['heads'][key], 'chosen_head': right_done['event_id']}], 'Choose reviewed right correction')
        f.ledger.rebuild(view=True)
        self.assertEqual(f.view_file(right_ref, 'xml.txt').read_bytes(), b'right correction')
        self.assertEqual(f.history_file(left_ref, 'xml.txt').read_bytes(), b'left correction')
        self.assertEqual(f.history_file(base, 'xml.txt').read_bytes(), b'xml.txt')

    def test_fresh_host_revision_initializes_view_without_overwriting_local_edits(self):
        f = self.f
        base, _, _ = f.publish(f.spec('xml'))
        child, _, _ = f.publish(f.spec('render', [f.dep(base, 'xml.txt')], parent=base['artifact_id']))
        other = self.replica(copy_catalogue=False)
        child_record = other.resolve(**child)
        child_file = other.root / child_record['path'] / 'render.txt'
        child_file.write_bytes(b'child edit outside parent ownership')
        spec = f.spec('xml', action='revise', base=base)
        intent = other.prepare('fixture', [spec], copy.deepcopy(f.producer))
        self.write_outputs(other, intent, b'fresh host correction')
        completed = other.finalize(intent['run_id'])
        record = other.resolve(**reference(completed['data']['updates'][0]))
        self.assertEqual((other.root / record['path'] / 'xml.txt').read_bytes(), b'fresh host correction')
        old = other.resolve(**base)
        self.assertEqual((other.root / old['history_path'] / 'xml.txt').read_bytes(), b'xml.txt')
        self.assertEqual(child_file.read_bytes(), b'child edit outside parent ownership')
        self.assertEqual(other.resolve(**child)['dependencies'], child_record['dependencies'])

        edited = self.replica('edited', copy_catalogue=False)
        visible = edited.root / edited.resolve(**base)['path'] / 'xml.txt'
        visible.write_bytes(b'unexpected user edit')
        events = {p.name: p.read_bytes() for p in (edited.root / 'ledger').glob('*.json')}
        with self.assertRaisesRegex(ValueError, 'Unexpected local edit'):
            edited.prepare('fixture', [spec], copy.deepcopy(f.producer))
        self.assertEqual(visible.read_bytes(), b'unexpected user edit')
        self.assertEqual({p.name: p.read_bytes() for p in (edited.root / 'ledger').glob('*.json')}, events)

    def test_replica_selection_conflict_never_chooses_timestamp_winner(self):
        f = self.f
        first, _, _ = f.publish(f.spec('render'))
        second, _, _ = f.publish(f.spec('render'))
        other = self.replica()
        scope = 'song:' + f.song['song_id']
        left = f.ledger.select(scope, 'render', 'backing', first)
        right = other.select(scope, 'render', 'backing', second)
        self.synchronize(other, f.ledger)
        key = f'selection/{scope}/render/backing'
        state = f.ledger.state()
        self.assertEqual(state['conflicts'][key], sorted([left['event_id'], right['event_id']]))
        self.assertNotIn(key, state['values'])
        self.assertEqual(f.ledger.list(kind='render', selected=True)['artifacts'], [])
        f.ledger.resolve_conflict([{'key': key, 'heads': state['heads'][key], 'chosen_head': left['event_id']}], 'Explicit selection')
        selected = f.ledger.list(kind='render', selected=True)['artifacts']
        self.assertEqual([row['revision_id'] for row in selected], [first['revision_id']])
        self.assertTrue(f.ledger.resolve(**second)['available'])

    def test_terminal_conflict_blocks_recovery_claim_but_preserves_completed_bytes(self):
        f = self.f
        intent = f.prepare([f.spec('render')])
        other = self.replica()
        self.write_outputs(f.ledger, intent, b'completed bytes')
        done = f.ledger.finalize(intent['run_id'])
        failed = other.fail(intent['run_id'], 'offline-error', 'Other collaborator recorded failure')
        self.synchronize(other, f.ledger)
        key = f'run/{intent["run_id"]}/state'
        state = f.ledger.state()
        self.assertEqual(state['heads'][key], sorted([done['event_id'], failed['event_id']]))
        with self.assertRaisesRegex(ValueError, 'conflict|terminal'):
            f.ledger.recover(intent['run_id'])
        ref = reference(done['data']['updates'][0])
        self.assertEqual(f.history_file(ref, 'render.txt').read_bytes(), b'completed bytes')
        f.ledger.resolve_conflict([{'key': key, 'heads': state['heads'][key], 'chosen_head': done['event_id']}], 'Completed bytes verified')
        self.assertEqual(f.ledger.recover(intent['run_id']), done)

    def test_fresh_host_unknown_destination_survives_after_completion_crash(self):
        f = self.f
        intent = f.prepare([f.spec('xml')])
        self.write_outputs(f.ledger, intent, b'published')
        with patch.object(f.ledger, '_materialize', side_effect=OSError('projection crash')):
            with self.assertRaises(OSError):
                f.ledger.finalize(intent['run_id'])
        other = self.replica(copy_catalogue=False)
        location = intent['outputs'][0]['identity']['path']
        unknown = other.root / location / 'unmanaged.txt'
        unknown.parent.mkdir(parents=True, exist_ok=True)
        unknown.write_bytes(b'local notes are not publication authority')
        before = {path.name: path.read_bytes() for path in (other.root / 'ledger').glob('*.json')}
        with self.assertRaisesRegex(ValueError, 'Unknown|unknown|Unmanaged|unmanaged'):
            other.recover(intent['run_id'])
        self.assertEqual(unknown.read_bytes(), b'local notes are not publication authority')
        self.assertEqual({path.name: path.read_bytes() for path in (other.root / 'ledger').glob('*.json')}, before)
        unknown.unlink()
        event = other.recover(intent['run_id'])
        self.assertEqual((other.root / location / 'xml.txt').read_bytes(), b'published')
        self.assertEqual(other.recover(intent['run_id']), event)

    def test_missing_retired_history_preserves_last_old_visible_bytes(self):
        f = self.f
        base, _, _ = f.publish(f.spec('xml', files=['keep.txt', 'retire.txt']))
        retired = f.view_file(base, 'retire.txt')
        intent = f.prepare([f.spec('xml', action='revise', base=base, files=['keep.txt'])])
        self.write_outputs(f.ledger, intent, b'new current content')
        f.history_file(base, 'retire.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'preserv|histor|Histor'):
            f.ledger.finalize(intent['run_id'])
        self.assertEqual(retired.read_bytes(), b'retire.txt')
        self.assertEqual(f.view_file(base, 'keep.txt').read_bytes(), b'keep.txt')

    def test_crash_at_each_publication_boundary_reuses_prepared_revision_ids(self):
        for boundary in ('journal-before', 'journal-after', 'history-after', 'event-after', 'view-after', 'projection-after'):
            with self.subTest(boundary=boundary):
                f = self.f
                intent = f.prepare([f.spec('bundle', files=['one.txt', 'two.txt'])])
                self.write_outputs(f.ledger, intent, b'complete bundle')
                expected_revisions = {o['revision_id'] for o in intent['outputs']}
                actual_atomic = ledger_module.atomic
                triggered = False
                projection_writes = 0

                def crash(path, content, **kwargs):
                    nonlocal triggered, projection_writes
                    relative = path.relative_to(f.data).as_posix()
                    is_journal = relative == intent['workspace'] + '/publication.json'
                    is_history = relative.startswith('history/') and intent['outputs'][0]['revision_id'] in relative
                    is_event = relative.startswith('ledger/')
                    is_view = relative.startswith(intent['outputs'][0]['identity']['path'] + '/')
                    is_projection = relative == f'catalogue/{f.ledger.host}/projection.json'
                    if is_projection:
                        projection_writes += 1
                    matched = ((boundary.startswith('journal-') and is_journal)
                               or (boundary == 'history-after' and is_history)
                               or (boundary == 'event-after' and is_event)
                               or (boundary == 'view-after' and is_view)
                               or (boundary == 'projection-after' and is_projection and projection_writes == 2))
                    if matched and not triggered:
                        triggered = True
                        if boundary != 'journal-before':
                            actual_atomic(path, content, **kwargs)
                        raise OSError('fixture crash at ' + boundary)
                    return actual_atomic(path, content, **kwargs)

                with patch.object(ledger_module, 'atomic', side_effect=crash):
                    with self.assertRaisesRegex(OSError, 'fixture crash'):
                        f.ledger.finalize(intent['run_id'])
                self.assertTrue(triggered)
                journal = f.data / intent['workspace'] / 'publication.json'
                saved = journal.read_bytes() if journal.exists() else None
                completion = f.ledger.recover(intent['run_id'])
                self.assertEqual({u['revision']['revision_id'] for u in completion['data']['updates']}, expected_revisions)
                if saved is not None:
                    self.assertEqual(journal.read_bytes(), saved)
                before = {p.name: p.read_bytes() for p in (f.data / 'ledger').glob('*.json')}
                self.assertEqual(f.ledger.recover(intent['run_id']), completion)
                self.assertEqual({p.name: p.read_bytes() for p in (f.data / 'ledger').glob('*.json')}, before)
                ref = reference(completion['data']['updates'][0])
                self.assertEqual(f.view_file(ref, 'one.txt').read_bytes(), b'complete bundle')
                self.assertEqual(f.view_file(ref, 'two.txt').read_bytes(), b'complete bundle')

    def test_concurrent_parent_move_new_child_is_repaired_without_reparenting(self):
        f = self.f
        parent, _, _ = f.publish(f.spec('source'))
        other = self.replica()
        f.ledger.move(parent['artifact_id'], 'moved-source', 'Offline parent move')
        spec = f.spec('xml', [f.dep(parent, 'source.txt')], parent=parent['artifact_id'])
        intent = other.prepare('fixture', [spec], copy.deepcopy(f.producer))
        self.write_outputs(other, intent, b'offline child')
        done = other.finalize(intent['run_id'])
        child = reference(done['data']['updates'][0])
        self.synchronize(other, f.ledger)
        state = f.ledger.state()
        self.assertIn(parent['artifact_id'], state['blocked_artifacts'])
        with self.assertRaisesRegex(ValueError, 'conflict'):
            f.ledger.rebuild(view=True)
        f.ledger.move(child['artifact_id'], 'repaired-child', 'Retain same storage parent at its current location')
        self.assertEqual(f.ledger.state()['blocked_artifacts'], [])
        self.assertEqual(f.ledger.state()['artifacts'][child['artifact_id']]['storage_parent'], parent['artifact_id'])
        self.assertEqual(f.view_file(child, 'xml.txt').read_bytes(), b'offline child')
        self.assertIn('/moved-source/repaired-child', f.ledger.resolve(**child)['path'])

    def test_resource_cache_container_and_undeclared_directory_symlinks_are_rejected(self):
        f = self.f
        installation = f.work / 'installed-resource'
        installation.mkdir()
        (installation / 'sample.bin').write_bytes(b'known sample')
        f.config['paths']['resource_cache'] = str(f.work / 'cache')
        f.config['resources'] = {'samples': str(installation)}
        resource = reference(f.ledger.register_resource('resources.samples', ['sample.bin'], label='sample',
                                                        version='fixture', source='synthetic')['data']['updates'][0])
        producer = copy.deepcopy(f.producer)
        producer['resources'] = [resource]
        for container in (False, True):
            with self.subTest(container=container):
                intent = f.ledger.prepare('fixture', [f.spec('render')], producer)
                self.write_outputs(f.ledger, intent)
                cache = next(iter(f.ledger.resource_paths(intent['run_id']).values()))
                if container:
                    shutil.rmtree(cache)
                    cache.symlink_to(installation, target_is_directory=True)
                else:
                    (cache / 'undeclared').symlink_to(installation, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'symlink|Symlink'):
                    f.ledger.finalize(intent['run_id'])
                self.assertNotIn(intent['outputs'][0]['artifact_id'], f.ledger.state()['artifacts'])
                self.assertEqual((installation / 'sample.bin').read_bytes(), b'known sample')

    def test_input_symlink_directory_is_rejected_before_completion(self):
        f = self.f
        source, _, _ = f.publish(f.spec('source'))
        intent = f.prepare([f.spec('xml', [f.dep(source, 'source.txt')], parent=source['artifact_id'])])
        self.write_outputs(f.ledger, intent)
        slot = f.data / intent['workspace'] / intent['input_slots'][0]['slot']
        external = f.work / 'undeclared-inputs'
        external.mkdir()
        (external / 'hidden.txt').write_bytes(b'not declared')
        (slot / 'hidden').symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink|Symlink|snapshot'):
            f.ledger.finalize(intent['run_id'])
        self.assertNotIn(intent['outputs'][0]['artifact_id'], f.ledger.state()['artifacts'])


if __name__ == '__main__':
    unittest.main()
