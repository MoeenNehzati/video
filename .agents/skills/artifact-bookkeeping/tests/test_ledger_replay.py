"""Synthetic causal histories: no production assets or external resources."""
import copy
import hashlib
import json
import random
import tempfile
import unittest
import uuid
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / '.agents/skills/artifact-bookkeeping/scripts'))

from ledger_replay import (LedgerValidationError, canonical_json, event_writes,
                               mutation_keys, portable_path, replay, replay_events,
                               validate_event, resource_relative)


def uid():
    return str(uuid.uuid4())


class Fixture:
    def __init__(self):
        self.events = []
        self.actor = {'id': 'tester', 'host_id': uid()}

    def event(self, kind, data, previous=None, expected=None, append=True):
        state = replay_events(self.events)
        event = {'schema_version': 1, 'event_id': uid(), 'event_type': kind,
                 'recorded_at': '2026-10-08T01:00:00Z', 'actor': self.actor,
                 'previous_events': state['frontier'] if previous is None else sorted(previous),
                 'expected_heads': {}, 'data': data}
        event['expected_heads'] = expected if expected is not None else {k: state['heads'].get(k, []) for k in mutation_keys(event)}
        if append:
            self.events.append(event)
        return event

    def song(self):
        sid = uid()
        return self.event('song.created', {'song_id': sid, 'label': 'Example', 'path': f'songs/song--{sid[:8]}'})

    def start(self, label='source', deps=None, base=None, parent=None, song=None, branch=None, outputs=None):
        run, aid, rid = uid(), base['artifact_id'] if base else uid(), uid()
        state = replay_events(self.events)
        path = state['artifacts'][parent]['path'] if parent else state['songs'][song]['path'] if song else 'shared'
        identity = None if base else {'artifact_id': aid, 'kind': label, 'label': label, 'song_ids': [song] if song else [], 'path': f'{path}/{label}--{aid[:8]}', 'storage_parent': parent}
        output = {'action': 'revise' if base else 'create', 'artifact_id': aid, 'revision_id': rid,
                  'identity': identity, 'base': base, 'branched_from': branch,
                  'output_slot': 'outputs/o0001', 'dependencies': deps or [],
                  'contract': {'files': [{'path': 'data.txt', 'role': 'data'}]}}
        outputs = outputs or [output]
        producer = {'run_id': run, 'operation': 'code-snapshot', 'skill': 'artifact-bookkeeping', 'entrypoint': 'fixture', 'command': None, 'settings': {}, 'code': {'files': [{'path': 'fixture.py', 'sha256': '0' * 64}], 'snapshot': None}, 'resources': [], 'origin': None, 'unknowns': {'command': 'Synthetic fixture', 'origin': 'Synthetic fixture', 'code.snapshot': 'Bootstrap code capture'}}
        keys = []
        for item in outputs:
            prefix = f'artifact/{item["artifact_id"]}'
            keys += [prefix + '/revision', f'revision/{item["revision_id"]}/provenance_notes']
            if item['action'] == 'create':
                keys += [prefix + '/' + f for f in ('identity', 'location', 'label', 'song_ids', 'withdrawn')]
        allocated = {item['revision_id'] for item in outputs}
        external = {}
        for item in outputs:
            for dep in item['dependencies']:
                if dep['revision_id'] not in allocated:
                    key = (dep['artifact_id'], dep['revision_id'])
                    external.setdefault(key, dict(dep, files=[]))['files'].extend(dep['files'])
        inputs = [dict(dep, files=sorted(set(dep['files']))) for dep in external.values()]
        return self.event('operation.started', {'run_id': run, 'operation': 'code-snapshot', 'inputs': inputs, 'outputs': outputs, 'publication_heads': {k: state['heads'].get(k, []) for k in keys}, 'producer': producer, 'workspace': f'work/{run}', 'input_slots': [dict(artifact_id=d['artifact_id'], revision_id=d['revision_id'], files=d['files'], slot=f'inputs/i{i:04d}') for i, d in enumerate(inputs, 1)], 'resource_slots': []})

    def complete(self, start, content=b'fixture', previous=None, append=True):
        updates = []
        for output in start['data']['outputs']:
            aid, rid = output['artifact_id'], output['revision_id']
            files = [{'path': f['path'], 'role': f['role'], 'sha256': hashlib.sha256(content).hexdigest(), 'size_bytes': len(content)} for f in output['contract']['files']]
            revision = {'revision_id': rid, 'history_path': f'history/{aid}/{rid}', 'files': files,
                        'dependencies': output['dependencies'], 'producer': start['data']['producer'],
                        'previous_revision_id': output['base']['revision_id'] if output['base'] else None,
                        'branched_from': output['branched_from']}
            updates.append({'action': output['action'], 'artifact_id': aid, 'identity': output['identity'], 'revision': revision})
        expected = dict(start['data']['publication_heads'])
        expected[f'run/{start["data"]["run_id"]}/state'] = [start['event_id']]
        return self.event('operation.completed', {'run_id': start['data']['run_id'], 'updates': updates}, previous=previous, expected=expected, append=append)

    def artifact(self, **kwargs):
        start = self.start(**kwargs)
        done = self.complete(start)
        update = done['data']['updates'][0]
        return {'artifact_id': update['artifact_id'], 'revision_id': update['revision']['revision_id']}

    @staticmethod
    def dep(ref, purpose='input'):
        return {**ref, 'files': ['data.txt'], 'purpose': purpose}


class ReplayTests(unittest.TestCase):
    def assert_clean(self, fixture):
        state = replay_events(fixture.events)
        self.assertEqual(state['issues'], [])
        return state

    def test_example_alternatives_revision_and_pinned_consumers(self):
        f = Fixture()
        sid = f.song()['data']['song_id']
        source_a = f.artifact(label='source', song=sid)
        source_b = f.artifact(label='source', song=sid)
        deps = [f.dep(source_a), f.dep(source_b)]
        xml_a = f.artifact(label='xml', deps=deps, parent=source_a['artifact_id'], song=sid)
        xml_b = f.artifact(label='xml', deps=deps, parent=source_a['artifact_id'], song=sid)
        arrangements, renders = [], []
        for xml in (xml_a, xml_b):
            for _ in range(2):
                midi = f.artifact(label='midi', deps=[f.dep(xml)], parent=xml['artifact_id'], song=sid)
                arrangements.append(midi)
                for _ in range(2):
                    renders.append(f.artifact(label='render', deps=[f.dep(midi)], parent=midi['artifact_id'], song=sid))
        report = f.artifact(label='report', deps=[f.dep(xml_a)], parent=xml_a['artifact_id'], song=sid)
        revised = f.artifact(label='xml', deps=[f.dep(source_a)], base=xml_a)
        branch = f.artifact(label='xml', deps=[f.dep(xml_a), f.dep(source_a)], branch=xml_a, parent=source_a['artifact_id'], song=sid)
        state = self.assert_clean(f)
        self.assertEqual(state['values'][f'artifact/{xml_a["artifact_id"]}/revision'], revised['revision_id'])
        self.assertEqual(state['revisions'][report['revision_id']]['dependencies'][0]['revision_id'], xml_a['revision_id'])
        self.assertEqual(len(state['artifacts']), 18)
        baseline = state['values']
        random.Random(42).shuffle(f.events)
        self.assertEqual(self.assert_clean(f)['values'], baseline)

    def test_concurrent_revisions_and_resolution_reopening(self):
        f = Fixture()
        ref = f.artifact()
        baseline = copy.deepcopy(f.events)
        a_start = f.start(base=ref)
        a = f.complete(a_start, b'A')
        f.events = copy.deepcopy(baseline)
        b_start = f.start(base=ref)
        b = f.complete(b_start, b'B')
        f.events += [a_start, a]
        state = self.assert_clean(f)
        key = f'artifact/{ref["artifact_id"]}/revision'
        self.assertEqual(state['conflicts'][key], sorted([a['event_id'], b['event_id']]))
        self.assertEqual(len(state['revisions']), 3)
        f.event('conflict.resolved', {'resolutions': [{'key': key, 'heads': state['heads'][key], 'chosen_head': a['event_id']}], 'reason': 'choose A'})
        self.assertNotIn(key, self.assert_clean(f)['conflicts'])
        resolved = copy.deepcopy(f.events)
        f.events = baseline
        c_start = f.start(base=ref)
        c = f.complete(c_start, b'C')
        f.events = resolved + [c_start, c]
        self.assertIn(key, self.assert_clean(f)['conflicts'])

    def test_terminal_conflict_preserves_completed_outputs(self):
        f = Fixture()
        start = f.start()
        done = f.complete(start)
        failure = f.event('operation.failed', {'run_id': start['data']['run_id'], 'error': {'code': 'failed', 'message': 'failure', 'details': {}}}, previous=[start['event_id']], expected={f'run/{start["data"]["run_id"]}/state': [start['event_id']]})
        state = self.assert_clean(f)
        self.assertIn(f'run/{start["data"]["run_id"]}/state', state['conflicts'])
        self.assertEqual(len(state['revisions']), 1)
        self.assertIn(done['event_id'], state['events'])
        self.assertIn(failure['event_id'], state['events'])

    def test_missing_ancestors_cycles_duplicate_and_unsupported(self):
        f = Fixture()
        song = f.song()
        changed = f.event('metadata.corrected', {'target': {'type': 'song', 'id': song['data']['song_id']}, 'changes': {'label': 'new'}, 'reason': 'name'})
        self.assertEqual(replay_events([changed])['issues'][0]['status'], 'pending')
        duplicate = copy.deepcopy(song)
        duplicate['data']['label'] = 'different'
        self.assertEqual(replay_events([song, duplicate])['issues'][0]['status'], 'integrity')
        self.assertEqual(len(replay_events([song, copy.deepcopy(song)])['events']), 1)
        unsupported = dict(song, schema_version=9)
        self.assertEqual(replay_events([unsupported])['issues'][0]['status'], 'unsupported')
        song['previous_events'] = [changed['event_id']]
        self.assertTrue(all(i['status'] == 'invalid' for i in replay_events([song, changed])['issues']))

    def test_selection_reviews_withdrawal_remain_independent(self):
        f = Fixture()
        ref = f.artifact()
        review = f.event('review.recorded', {'review_id': uid(), 'target': ref, 'stage': 'source', 'purpose': 'accuracy', 'verdict': 'pass', 'notes': 'checked', 'evidence': [], 'supersedes': None})
        f.event('selection.set', {'scope': 'shared', 'stage': 'source', 'purpose': 'chosen', 'target': ref})
        f.event('artifact.withdrawal_set', {'artifact_id': ref['artifact_id'], 'withdrawn': True, 'reason': 'hide'})
        state = self.assert_clean(f)
        self.assertEqual(state['selections']['selection/shared/source/chosen'], ref)
        self.assertTrue(state['artifacts'][ref['artifact_id']]['withdrawn'])
        self.assertEqual(len(state['reviews']), 1)
        other = copy.deepcopy(review['data'])
        other.update(review_id=uid(), supersedes=review['data']['review_id'], stage='other')
        bad = f.event('review.recorded', other)
        self.assertEqual(replay_events(f.events)['issues'][-1]['status'], 'invalid')
        self.assertNotIn(bad['event_id'], replay_events(f.events)['events'])

    def test_multi_output_registration_and_partial_completion(self):
        f = Fixture()
        first = f.start()['data']['outputs'][0]
        f.events = []
        second = copy.deepcopy(first)
        second.update(artifact_id=uid(), revision_id=uid(), output_slot='outputs/o0002')
        second['identity'].update(artifact_id=second['artifact_id'], path=f'shared/report--{second["artifact_id"][:8]}')
        second['dependencies'] = [f.dep({'artifact_id': first['artifact_id'], 'revision_id': first['revision_id']})]
        start = f.start(outputs=[first, second])
        done = f.complete(start)
        self.assertEqual(len(self.assert_clean(f)['revisions']), 2)
        done['data']['updates'].pop()
        state = replay_events(f.events)
        self.assertEqual(len(state['revisions']), 0)
        self.assertEqual(state['issues'][-1]['status'], 'invalid')

    def test_grouped_move_preserves_history_and_requires_descendants(self):
        f = Fixture()
        parent = f.artifact()
        child = f.artifact(label='xml', deps=[f.dep(parent)], parent=parent['artifact_id'])
        state = self.assert_clean(f)
        old = state['artifacts'][parent['artifact_id']]['path']
        new = 'shared/renamed'
        mapping = [{'artifact_id': aid, 'from': artifact['path'], 'to': new + artifact['path'][len(old):]} for aid, artifact in state['artifacts'].items()]
        move = f.event('artifacts.moved', {'mapping': mapping, 'reason': 'rename'})
        state = self.assert_clean(f)
        self.assertEqual(state['artifacts'][parent['artifact_id']]['path'], new)
        self.assertEqual(state['revisions'][child['revision_id']]['dependencies'][0]['revision_id'], parent['revision_id'])
        move['data']['mapping'] = move['data']['mapping'][:1]
        move['expected_heads'] = {k: v for k, v in move['expected_heads'].items() if k in mutation_keys(move)}
        self.assertEqual(replay_events(f.events)['issues'][-1]['status'], 'invalid')

    def test_concurrent_child_creation_blocks_whole_parent_move_until_identity_repair(self):
        f = Fixture()
        parent = f.artifact()
        existing = f.artifact(label='xml', deps=[f.dep(parent)], parent=parent['artifact_id'])
        baseline = copy.deepcopy(f.events)
        before = replay_events(f.events)
        old = before['artifacts'][parent['artifact_id']]['path']
        move = f.event('artifacts.moved', {'mapping': [
            {'artifact_id': aid, 'from': record['path'], 'to': 'shared/moved' + record['path'][len(old):]}
            for aid, record in before['artifacts'].items()], 'reason': 'move existing subtree'})
        f.events = baseline
        new_child = f.artifact(label='render', deps=[f.dep(parent)], parent=parent['artifact_id'])
        f.events.append(move)
        combined = replay_events(f.events)
        self.assertEqual(set(combined['blocked_artifacts']), {parent['artifact_id'], existing['artifact_id'], new_child['artifact_id']})
        child_path = combined['artifacts'][new_child['artifact_id']]['path']
        f.event('artifacts.moved', {'mapping': [{'artifact_id': new_child['artifact_id'], 'from': child_path,
                                                'to': 'shared/moved/' + child_path.rsplit('/', 1)[1]}],
                                  'reason': 'Repair location under same storage parent'})
        repaired = self.assert_clean(f)
        self.assertEqual(repaired['blocked_artifacts'], [])
        self.assertEqual(repaired['artifacts'][new_child['artifact_id']]['storage_parent'], parent['artifact_id'])

    def test_history_bytes_missing_and_corrupt_are_registered(self):
        f = Fixture()
        ref = f.artifact()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'ledger').mkdir()
            for event in f.events:
                (root / 'ledger' / (event['event_id'] + '.json')).write_text(canonical_json(event))
            state = replay(root)
            self.assertIn(ref['revision_id'], state['revisions'])
            self.assertEqual(state['issues'][0]['status'], 'unavailable')
            path = root / state['revisions'][ref['revision_id']]['history_path'] / 'data.txt'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'fixture')
            self.assertTrue(replay(root)['revisions'][ref['revision_id']]['available'])
            path.write_bytes(b'corrupt')
            self.assertEqual(replay(root)['issues'][0]['status'], 'integrity')
            (root / 'ledger' / 'bad.json').write_text('{"schema_version":1,"schema_version":1}')
            self.assertIn('Duplicate JSON key', str(replay(root)['issues']))

    def test_multiple_visual_alternatives_and_old_kit_preserved(self):
        f = Fixture()
        sid = f.song()['data']['song_id']
        source = f.artifact(song=sid)
        audio = f.artifact(label='render', deps=[f.dep(source)], parent=source['artifact_id'], song=sid)
        character = f.artifact(label='character')
        films, kits = [], []
        for _ in range(2):
            story = f.artifact(label='storyboard', deps=[f.dep(source), f.dep(audio)], parent=source['artifact_id'], song=sid)
            for _ in range(2):
                image = f.artifact(label='image', deps=[f.dep(story), f.dep(character)], parent=story['artifact_id'], song=sid)
                kit = f.artifact(label='flow-kit', deps=[f.dep(image)], parent=image['artifact_id'], song=sid)
                kits.append(kit)
                for _ in range(2):
                    take = f.artifact(label='clip', deps=[f.dep(image), f.dep(kit)], parent=image['artifact_id'], song=sid)
                    f.event('selection.set', {'scope': 'artifact:' + image['artifact_id'], 'stage': 'clip', 'purpose': 'chosen', 'target': take})
                    films.append(f.artifact(label='video', deps=[f.dep(story), f.dep(audio), f.dep(take)], parent=story['artifact_id'], song=sid))
        replacement = f.artifact(label='flow-kit', base=kits[0], deps=[f.dep(character)])
        state = self.assert_clean(f)
        self.assertIn(kits[0]['revision_id'], state['revisions'])
        self.assertNotEqual(replacement['revision_id'], kits[0]['revision_id'])
        self.assertEqual(len(films), 8)
        self.assertTrue(all(state['revisions'][film['revision_id']]['dependencies'][1]['revision_id'] == audio['revision_id'] for film in films))

    def test_creation_cannot_overwrite_and_slots_cannot_omit_inputs(self):
        f = Fixture()
        song = f.song()
        overwrite = f.event('song.created', dict(song['data'], label='overwrite'))
        self.assertEqual(replay_events(f.events)['issues'][0]['status'], 'integrity')
        f.events.pop()
        ref = f.artifact()
        start = f.start(deps=[f.dep(ref)])
        start['data']['input_slots'] = []
        self.assertIn('Input slots must cover', str(replay_events(f.events)['issues']))

    def test_discovery_overlap_and_dependency_cycle_fail_before_production(self):
        f = Fixture()
        start = f.start()
        start['data']['outputs'][0]['contract'] = {'discovery': [
            {'glob': '*.txt', 'role': 'text', 'min_count': 1, 'max_count': 2},
            {'glob': 'data.*', 'role': 'data', 'min_count': 1, 'max_count': 2}]}
        self.assertIn('Overlapping discovery', str(replay_events(f.events)['issues']))
        output = start['data']['outputs'][0]
        output['contract'] = {'files': [{'path': 'data.txt', 'role': 'data'}]}
        output['dependencies'] = [f.dep({'artifact_id': output['artifact_id'], 'revision_id': output['revision_id']})]
        self.assertIn('dependency cycle', str(replay_events(f.events)['issues']))

    def test_reused_revision_id_and_historical_frontier(self):
        f = Fixture()
        ref = f.artifact()
        historical = f.events[-1]['event_id']
        first = copy.deepcopy(f.events)
        other = Fixture()
        start = other.start()
        start['data']['outputs'][0]['revision_id'] = ref['revision_id']
        old_revision_key = next(k for k in start['data']['publication_heads'] if k.startswith('revision/'))
        start['data']['publication_heads'].pop(old_revision_key)
        start['data']['publication_heads'][f'revision/{ref["revision_id"]}/provenance_notes'] = []
        other.complete(start)
        state = replay_events(first + other.events)
        self.assertEqual(state['issues'][0]['status'], 'integrity')
        historical_state = replay_events(first + other.events, frontier=[historical])
        self.assertEqual(historical_state['issues'], [])
        self.assertIn(ref['revision_id'], historical_state['revisions'])

    def test_identical_sync_conflict_filename_and_whitespace_are_idempotent(self):
        f = Fixture()
        song = f.song()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'ledger').mkdir()
            (root / 'ledger' / (song['event_id'] + '.json')).write_text(canonical_json(song))
            copy_path = root / 'ledger' / (song['event_id'] + ' (conflicted copy).json')
            copy_path.write_text(json.dumps(song, indent=4))
            state = replay(root)
            self.assertEqual(state['issues'], [])
            self.assertEqual(len(state['events']), 1)
            conflicting = copy.deepcopy(song)
            conflicting['data']['label'] = 'different bytes under same identity'
            copy_path.write_text(json.dumps(conflicting))
            self.assertEqual(replay(root)['issues'][0]['status'], 'integrity')

    def test_output_directory_case_spelling_collision_is_rejected(self):
        f = Fixture()
        start = f.start()
        start['data']['outputs'][0]['contract'] = {'files': [
            {'path': 'Foo/one.txt', 'role': 'data'}, {'path': 'foo/two.txt', 'role': 'data'}]}
        self.assertIn('spelling collision', str(replay_events(f.events)['issues']))

    def test_resource_original_spelling_and_root_relocation_limits(self):
        self.assertEqual(resource_relative('.config/Sample Library/échantillon.wav'), '.config/Sample Library/échantillon.wav')
        for path in ('../escape', 'C:/absolute', 'files/NUL.wav', 'ends. ', 'unsafe:stream'):
            with self.subTest(path=path), self.assertRaises(LedgerValidationError):
                resource_relative(path)
        f = Fixture()
        f.artifact()
        long_root = Path('/tmp') / ('long-root-' * 18)
        state = replay_events(f.events, root=long_root)
        self.assertIn('exceeds 240', str(state['issues']))

    def test_schema_and_portable_paths(self):
        f = Fixture()
        song = f.song()
        validate_event(song)
        song['data']['unknown'] = True
        with self.assertRaises(LedgerValidationError):
            validate_event(song)
        for path in ('../escape', '/absolute', 'C:/drive', 'foo//bar', 'NUL.txt', 'x.', 'a/b\\c'):
            with self.subTest(path=path), self.assertRaises(LedgerValidationError):
                portable_path(path)
        self.assertEqual(portable_path('files/PROMPT.md'), 'files/PROMPT.md')


if __name__ == '__main__':
    unittest.main()
