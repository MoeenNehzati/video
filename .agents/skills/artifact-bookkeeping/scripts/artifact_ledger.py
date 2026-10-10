"""Append-only artifact bookkeeping, immutable storage and recoverable local views."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import sysconfig
import tempfile
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.read_config import ROOT, load_config
from ledger_replay import canonical_json, casefold_paths, portable_path, replay, replay_events, resource_relative, validate_event


class LedgerError(ValueError):
    """A refused mutation; existing evidence is retained."""


def new_id():
    return str(uuid.uuid4())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise LedgerError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(LedgerError(f'Non-finite JSON: {value}')))


def encoded(value):
    return (canonical_json(value) + '\n').encode('utf-8')


def atomic(path, content, *, replace=False):
    """Publish complete bytes; never clobber a conflicting immutable record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        if path.read_bytes() != content:
            raise LedgerError(f'Integrity failure: different bytes already exist at {path}')
        return
    fd, temporary = tempfile.mkstemp(prefix='.publish-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise LedgerError(f'Integrity failure: concurrent publication at {path}')
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def resource_file(directory, name):
    resource_relative(name)
    directory = Path(directory)
    if directory.absolute() != directory.resolve() or directory.is_symlink():
        raise LedgerError('Resource cache or installation container contains a symlink')
    path = directory / name
    if len(str(path).encode('utf-16-le')) // 2 > 240:
        raise LedgerError('Resource snapshot path exceeds 240 UTF-16 units; shorten resource_cache')
    for part in [path, *path.parents]:
        if part == directory:
            break
        if part.is_symlink():
            raise LedgerError('Resource symlinks require a dedicated safe adapter')
    return path


def reference(update):
    return {'artifact_id': update['artifact_id'], 'revision_id': update['revision']['revision_id']}


def _slug(label):
    return re.sub('[^a-z0-9]', '', label.lower())[:8] or 'artifact'


def _directory(label, identity):
    return f'{_slug(label)}--{identity.replace("-", "")[:12]}'


def _keys(output):
    aid, rid = output['artifact_id'], output['revision_id']
    keys = [f'artifact/{aid}/revision', f'revision/{rid}/provenance_notes']
    if output['action'] == 'create':
        keys.extend(f'artifact/{aid}/{field}' for field in
                    ('identity', 'location', 'label', 'song_ids', 'withdrawn'))
    return keys


class Ledger:
    def __init__(self, config, *, frontier=None):
        self.config = config
        self.frontier = frontier
        self.root = Path(config['paths']['data_root']).resolve(strict=True)
        if self.root.is_relative_to(ROOT) or ROOT.is_relative_to(self.root):
            raise LedgerError('data_root must be separate from the repository')
        bookkeeping = config.get('bookkeeping', {})
        actor, host = bookkeeping.get('actor_id'), bookkeeping.get('host_id')
        if not isinstance(actor, str) or not actor.strip():
            raise LedgerError('Set bookkeeping.actor_id in config.local.toml')
        try:
            valid_host = str(uuid.UUID(host, version=4)) == host and uuid.UUID(host).version == 4
        except (ValueError, TypeError, AttributeError):
            valid_host = False
        if not valid_host:
            raise LedgerError('Set bookkeeping.host_id to a machine-stable UUIDv4 in config.local.toml')
        self.actor = {'id': actor, 'host_id': host}
        self.host = host
        self.path(f'catalogue/{host}/projection.json')

    def path(self, relative):
        portable_path(relative, self.root)
        result = self.root / relative
        # Reject all symlink components, even when currently pointing inside the root.
        for component in [result, *result.parents]:
            if component == self.root:
                break
            if component.is_symlink():
                raise LedgerError(f'Symlink is not a managed path: {relative}')
            if component != result and component.exists() and not component.is_dir():
                raise LedgerError(f'Managed path ancestor is not a directory: {relative}')
        if not result.resolve().is_relative_to(self.root):
            raise LedgerError(f'Path escapes data root: {relative}')
        return result

    @contextmanager
    def lock(self):
        # OS locks are machine-local; a synchronized lockfile is not a distributed lease.
        name = hashlib.sha256(os.fsencode(self.root)).hexdigest()
        path = Path(tempfile.gettempdir()) / f'music-ledger-{name}.lock'
        with path.open('a+b') as stream:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0)
                stream.write(b'0')
                stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def state(self, frontier=None):
        return replay(self.root, frontier=self.frontier if frontier is None else frontier)

    def _clean(self):
        if self.frontier is not None:
            raise LedgerError('Historical frontier queries are read-only')
        state = self.state()
        fatal = [issue for issue in state['issues'] if issue['status'] not in ('unavailable', 'conflict')]
        if fatal:
            raise LedgerError(f'Incomplete ledger; resolve issues before mutation: {fatal}')
        return state

    def _event(self, kind, data, keys, state, expected=None):
        predecessors = set(state['events'])
        for event in state['events'].values():
            predecessors.difference_update(event['previous_events'])
        return {'schema_version': 1, 'event_id': new_id(), 'event_type': kind,
                'recorded_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'actor': self.actor, 'previous_events': sorted(predecessors),
                'expected_heads': expected if expected is not None else
                    {key: state['heads'].get(key, []) for key in sorted(keys)}, 'data': data}

    def _append(self, event, state=None):
        state = self._clean() if state is None else state
        validate_event(event)
        if event['event_id'] in state['events']:
            if state['events'][event['event_id']] != event:
                raise LedgerError('Integrity failure: reused event ID')
            return event
        trial = replay_events([*state['events'].values(), event])
        problems = [issue for issue in trial['issues'] if issue.get('event_id') == event['event_id']]
        if problems or event['event_id'] not in trial['events']:
            raise LedgerError(f'Invalid event: {problems}')
        for key, heads in event['expected_heads'].items():
            if heads != state['heads'].get(key, []):
                raise LedgerError(f'Stale or conflicted base for {key}')
        destination = self.path(f'ledger/{event["event_id"]}.json')
        if destination.exists() and read_json(destination) == event:
            return event
        atomic(destination, encoded(event))
        return event

    def create_song(self, label):
        with self.lock():
            state = self._clean()
            sid = new_id()
            data = {'song_id': sid, 'label': label, 'path': f'songs/{_directory(label, sid)}'}
            if self.path(data['path']).exists():
                raise LedgerError('Generated song location already exists; preserve it and retry with a new identity')
            event = self._event('song.created', data, [f'song/{sid}', f'song/{sid}/label'], state)
            self._append(event, state)
            self.path(data['path']).mkdir(parents=True, exist_ok=True)
            return data

    def resolve(self, artifact_id, revision_id=None):
        state = self.state()
        if artifact_id not in state['artifacts']:
            # Only exact registered paths resolve; labels may be ambiguous.
            matches = [aid for aid, artifact in state['artifacts'].items()
                       if artifact.get('path') == str(artifact_id)]
            if len(matches) != 1:
                raise LedgerError(f'Unknown or ambiguous artifact: {artifact_id}; issues={state["issues"]}')
            artifact_id = matches[0]
        artifact = state['artifacts'][artifact_id]
        if revision_id is None:
            key = f'artifact/{artifact_id}/revision'
            if len(state['heads'].get(key, [])) != 1:
                raise LedgerError(f'Current revision is conflicted or missing: {artifact_id}')
            revision_id = state['values'][key]
            if isinstance(revision_id, dict):
                revision_id = revision_id.get('revision_id')
        if revision_id not in state['revisions']:
            raise LedgerError(f'Unknown revision: {revision_id}')
        revision = state['revisions'][revision_id]
        if revision.get('artifact_id', artifact_id) != artifact_id:
            raise LedgerError('Revision belongs to another artifact')
        result = {**revision, 'artifact_id': artifact_id, 'path': artifact.get('path')}
        result['issues'] = state['issues']
        result['conflicts'] = state['conflicts']
        result['available'] = all(self._file_matches(self.path(f'{revision["history_path"]}/{f["path"]}'), f)
                                  for f in revision['files'])
        return result

    @staticmethod
    def _file_matches(path, file):
        return path.is_file() and not path.is_symlink() and path.stat().st_size == file['size_bytes'] and sha(path) == file['sha256']

    def _dependency(self, dependency, allocated=None):
        allocated = allocated or {}
        dep = dict(dependency)
        rid = dep['revision_id']
        if rid in allocated:
            return dep
        record = self.resolve(dep['artifact_id'], rid)
        if not record['available']:
            raise LedgerError(f'Historical input unavailable: {rid}')
        files = {file['path']: file for file in record['files']}
        if 'roles' in dep:
            roles = dep.pop('roles')
            dep['files'] = sorted(f['path'] for f in files.values() if f['role'] in roles)
        if not dep.get('files') or not set(dep['files']) <= files.keys():
            raise LedgerError('Dependency requires explicit existing files or roles')
        dep['files'] = sorted(set(dep['files']))
        if not dep.get('purpose'):
            raise LedgerError('Dependency purpose is required')
        return dep

    def producer(self, operation, skill, entrypoint, command=None, settings=None, code_paths=None):
        code_paths = list(dict.fromkeys([*sorted((ROOT / 'scripts').glob('*.py')),
                    *sorted((ROOT / '.agents/skills/artifact-bookkeeping/scripts').glob('*.py')),
                    ROOT / '.agents/skills/artifact-bookkeeping/schema/event.schema.json',
                    *(code_paths or [])]))
        snapshot = self.code_snapshot(code_paths)
        code = {'snapshot': snapshot, 'files': self._code_files(code_paths)}
        unknowns = {'origin': 'Locally produced; no external acquisition'}
        if command is None:
            unknowns['command'] = 'Portable invocation argv was not supplied; entrypoint and settings are recorded'
        return {'run_id': None, 'operation': operation, 'skill': skill, 'entrypoint': entrypoint,
                'command': command, 'settings': settings or {}, 'code': code, 'resources': [],
                'origin': None, 'unknowns': unknowns}

    @staticmethod
    def _code_files(paths):
        records = []
        for path in paths:
            path = Path(path).resolve(strict=True)
            name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
            records.append({'path': name, 'sha256': sha(path)})
        return records

    def code_snapshot(self, paths):
        paths = list(dict.fromkeys([Path(__file__), ROOT / '.agents/skills/artifact-bookkeeping/scripts/ledger_replay.py',
                                   ROOT / 'scripts/read_config.py',
                                   ROOT / '.agents/skills/artifact-bookkeeping/schema/event.schema.json', *paths]))
        files = {f'f{i:04d}{Path(path).suffix}': Path(path) for i, path in enumerate(paths, 1)}
        producer = {'run_id': None, 'operation': 'code-snapshot', 'skill': 'artifact-bookkeeping',
                    'entrypoint': 'artifact_ledger', 'command': None, 'settings': {},
                    'code': {'files': self._code_files(paths), 'snapshot': None}, 'resources': [],
                    'origin': None, 'unknowns': {'code.snapshot': 'Bootstrap code capture',
                    'command': 'In-process code capture', 'origin': 'Executed working-copy source files'}}
        result = self.import_files(files, kind='code', label='Code snapshot', producer=producer)
        return reference(result['data']['updates'][0])

    def prepare(self, operation, outputs, producer, *, inputs=None):
        with self.lock():
            state = self._clean()
            run_id = new_id()
            workspace = f'work/{run_id}'
            if not outputs:
                raise LedgerError('A complete output contract is required')
            outputs = [dict(spec, artifact_id=spec.get('artifact_id', new_id()),
                            revision_id=spec.get('revision_id', new_id())) for spec in outputs]
            creates = {spec['artifact_id']: spec for spec in outputs if spec.get('action', 'create') == 'create'}
            def placement(spec, visiting=()):
                aid = spec['artifact_id']
                if aid in visiting:
                    raise LedgerError('Cyclic storage parents')
                parent = spec.get('storage_parent')
                songs = sorted(set(spec.get('song_ids', [])))
                if parent in creates:
                    location = placement(creates[parent], (*visiting, aid))
                elif parent:
                    if parent in state.get('blocked_artifacts', []):
                        raise LedgerError('Resolve primary-parent structural conflicts before production')
                    location = state['artifacts'].get(parent, {}).get('path')
                    if not location:
                        raise LedgerError('Unknown or conflicted primary dependency')
                elif len(songs) == 1 and songs[0] in state['songs']:
                    location = state['songs'][songs[0]]['path']
                else:
                    location = 'shared'
                return f'{location}/{_directory(spec["kind"], aid)}'
            allocated = []
            for number, spec in enumerate(outputs, 1):
                action = spec.get('action', 'create')
                aid, rid = spec['artifact_id'], spec['revision_id']
                base = spec.get('base')
                identity = None
                if action == 'revise':
                    if not base:
                        raise LedgerError('Revise requires an exact current base')
                    aid = base['artifact_id']
                    if aid in state.get('blocked_artifacts', []):
                        raise LedgerError('Resolve artifact structural conflicts before revising')
                    current = self.resolve(aid)
                    if current['revision_id'] != base['revision_id']:
                        raise LedgerError('Revise base is not the current revision; create a branch')
                elif action == 'create':
                    aid = spec.get('artifact_id', aid)
                    rid = spec.get('revision_id', rid)
                    parent = spec.get('storage_parent')
                    songs = sorted(set(spec.get('song_ids', [])))
                    if not set(songs) <= state['songs'].keys():
                        raise LedgerError('Unknown song association')
                    identity = {'artifact_id': aid, 'kind': spec['kind'], 'label': spec['label'],
                                'song_ids': songs, 'storage_parent': parent, 'path': placement(spec)}
                    if self.path(identity['path']).exists():
                        raise LedgerError('Generated artifact location already exists; preserve it and use a new identity')
                else:
                    raise LedgerError('action must be create or revise')
                slot = f'outputs/o{number:04d}'
                output = {'action': action, 'artifact_id': aid, 'revision_id': rid,
                          'identity': identity, 'base': base if action == 'revise' else None,
                          'branched_from': spec.get('branched_from') if action == 'create' else None,
                          'output_slot': slot, 'dependencies': spec.get('dependencies', []),
                          'contract': spec['contract']}
                for file in output['contract'].get('files', []):
                    self.path(f'{workspace}/{slot}/{file["path"]}')
                    self.path(f'history/{aid}/{rid}/{file["path"]}')
                    location = identity['path'] if identity else state['artifacts'][aid]['path']
                    self.path(f'{location}/{file["path"]}')
                allocated.append(output)
            locations = {aid: record['path'] for aid, record in state['artifacts'].items() if record.get('path')}
            locations.update({out['artifact_id']: out['identity']['path'] for out in allocated if out['identity']})
            for output in allocated:
                location = locations[output['artifact_id']]
                for file in output['contract'].get('files', []):
                    owned = (location + '/' + file['path']).casefold()
                    for aid, path in locations.items():
                        if aid == output['artifact_id']:
                            continue
                        child = path.casefold()
                        if child.startswith(location.casefold() + '/') and (
                                owned == child or owned.startswith(child + '/') or child.startswith(owned + '/')):
                            raise LedgerError('Output ownership overlaps a descendant artifact')
            by_revision = {output['revision_id']: output for output in allocated}
            dependencies = []
            for output in allocated:
                output['dependencies'] = [self._dependency(dep, by_revision) for dep in output['dependencies']]
                parent = output['identity']['storage_parent'] if output['identity'] else None
                if parent and not any(dep['artifact_id'] == parent for dep in output['dependencies']):
                    raise LedgerError('Primary storage parent must be an actual declared input')
                dependencies.extend(dep for dep in output['dependencies'] if dep['revision_id'] not in by_revision)
            # Inputs collect the union of consumed files, independent of output-specific purpose labels.
            external = {}
            for dep in dependencies:
                key = (dep['artifact_id'], dep['revision_id'])
                if key not in external:
                    external[key] = dict(dep, files=[])
                external[key]['files'] = sorted(set(external[key]['files'] + dep['files']))
            union = sorted(external.values(), key=lambda dep: (dep['artifact_id'], dep['revision_id']))
            if inputs is not None:
                supplied = {(d['artifact_id'], d['revision_id'], tuple(sorted(d['files']))) for d in inputs}
                actual = {(d['artifact_id'], d['revision_id'], tuple(d['files'])) for d in union}
                if supplied != actual:
                    raise LedgerError('Start inputs must equal output dependency union')
            slots = [dict(dep, slot=f'inputs/i{number:04d}') for number, dep in enumerate(union, 1)]
            for slot in slots:
                slot.pop('purpose', None)
                for filename in slot['files']:
                    self.path(f'{workspace}/{slot["slot"]}/{filename}')
            producer = dict(producer, run_id=run_id, operation=operation)
            resource_slots = self._prepare_resources(producer, run_id, dry_run=True)
            publication = {key: state['heads'].get(key, []) for output in allocated for key in _keys(output)}
            if any(len(heads) > 1 for heads in publication.values()):
                raise LedgerError('Resolve output state conflicts before preparing')
            data = {'run_id': run_id, 'operation': operation, 'inputs': union, 'outputs': allocated,
                    'publication_heads': publication, 'producer': producer, 'workspace': workspace,
                    'input_slots': slots, 'resource_slots': resource_slots}
            event = self._event('operation.started', data, [f'run/{run_id}/state'], state)
            validate_event(event)
            trial = replay_events([*state['events'].values(), event])
            if event['event_id'] not in trial['events']:
                raise LedgerError(f'Invalid intent: {trial["issues"]}')
            # Establish this host's verified base before a revision changes the current target.
            revised = {output['artifact_id'] for output in allocated if output['action'] == 'revise'}
            if revised:
                self._materialize(state, revised)
            # Validation precedes all workspace writes.
            for folder in ('inputs', 'outputs', 'scratch'):
                self.path(f'{workspace}/{folder}').mkdir(parents=True, exist_ok=False)
            atomic(self.path(f'{workspace}/intent.json'), encoded(data))
            self._append(event, state)
            for slot in slots:
                record = self.resolve(slot['artifact_id'], slot['revision_id'])
                manifest = {f['path']: f for f in record['files']}
                for filename in slot['files']:
                    src = self.path(f'{record["history_path"]}/{filename}')
                    dst = self.path(f'{workspace}/{slot["slot"]}/{filename}')
                    atomic(dst, src.read_bytes())
                    if not self._file_matches(dst, manifest[filename]):
                        raise LedgerError('Input changed while preparing')
            for output in allocated:
                self.path(f'{workspace}/{output["output_slot"]}').mkdir(parents=True, exist_ok=True)
            self._prepare_resources(producer, run_id, dry_run=False)
            return data

    def _intent(self, run_id):
        if str(uuid.UUID(run_id)) != run_id:
            raise LedgerError('Invalid run ID')
        intent = read_json(self.path(f'work/{run_id}/intent.json'))
        starts = [event for event in self.state()['events'].values()
                  if event['event_type'] == 'operation.started' and event['data']['run_id'] == run_id]
        if len(starts) != 1 or intent != starts[0]['data']:
            raise LedgerError('Intent differs from immutable start event')
        return intent, starts[0]

    def _manifest(self, directory, contract):
        actual = []
        if not directory.is_dir() or directory.is_symlink():
            raise LedgerError(f'Missing or unsafe output slot: {directory}')
        for path in directory.rglob('*'):
            if path.is_symlink():
                raise LedgerError(f'Output symlink is forbidden: {path}')
            if path.is_file():
                relative = path.relative_to(directory).as_posix()
                portable_path(relative)
                actual.append(relative)
        if len(actual) != len({name.casefold() for name in actual}):
            raise LedgerError('Case-insensitive output collision')
        roles = {}
        if 'files' in contract:
            roles = {f['path']: f['role'] for f in contract['files']}
            if len(roles) != len(contract['files']) or set(actual) != roles.keys():
                raise LedgerError(f'Output contract mismatch: expected {sorted(roles)}, found {sorted(actual)}')
        else:
            for rule in contract.get('discovery', []):
                matches = [name for name in actual if fnmatch.fnmatchcase(name, rule['glob'])]
                if not rule['min_count'] <= len(matches) <= rule['max_count']:
                    raise LedgerError(f'Discovery count outside contract: {rule["glob"]}')
                for name in matches:
                    if name in roles:
                        raise LedgerError('Overlapping discovery rules')
                    roles[name] = rule['role']
            if set(actual) != roles.keys():
                raise LedgerError('Unexpected publishable output')
        if not roles:
            raise LedgerError('An artifact must own at least one file')
        return [{'path': name, 'role': roles[name], 'sha256': sha(directory / name),
                 'size_bytes': (directory / name).stat().st_size} for name in sorted(roles)]

    def _verify_inputs(self, intent):
        for slot in intent['input_slots']:
            revision = self.resolve(slot['artifact_id'], slot['revision_id'])
            manifest = {f['path']: f for f in revision['files']}
            directory = self.path(f'{intent["workspace"]}/{slot["slot"]}')
            entries = list(directory.rglob('*'))
            if any(p.is_symlink() for p in entries):
                raise LedgerError('Input snapshot contains a symlink')
            actual = {p.relative_to(directory).as_posix() for p in entries if p.is_file()}
            if actual != set(slot['files']):
                raise LedgerError('Input snapshot file set changed')
            for name in slot['files']:
                if not self._file_matches(directory / name, manifest[name]):
                    raise LedgerError(f'Input snapshot altered: {name}')
        self._verify_resources(intent)

    def finalize(self, run_id):
        with self.lock():
            intent, start = self._intent(run_id)
            state = self._clean()
            complete = [e for e in state['events'].values() if e['event_type'] == 'operation.completed'
                        and e['data']['run_id'] == run_id]
            if complete:
                if len(complete) != 1 or state['runs'].get(run_id, {}).get('status') != 'completed':
                    raise LedgerError('Run has conflicting terminal outcomes or was resolved as failed')
                self._materialize(state, {u['artifact_id'] for u in complete[0]['data']['updates']})
                return complete[0]
            if state['heads'].get(f'run/{run_id}/state') != [start['event_id']]:
                raise LedgerError('Run is terminal or conflicted; create a fresh attempt')
            for key, heads in intent['publication_heads'].items():
                if state['heads'].get(key, []) != heads:
                    raise LedgerError(f'Stale-base publication: {key}')
            self._verify_inputs(intent)
            updates = []
            for output in intent['outputs']:
                aid, rid = output['artifact_id'], output['revision_id']
                manifest = self._manifest(self.path(f'{intent["workspace"]}/{output["output_slot"]}'), output['contract'])
                # Imported spelling is evidence, never the authority for a managed path.
                original_names = (intent['producer']['settings'] or {}).get('original_names', {})
                for f in manifest:
                    if f['path'] in original_names:
                        f['original_name'] = original_names[f['path']]
                    self.path(f'history/{aid}/{rid}/{f["path"]}')
                    location = output['identity']['path'] if output['identity'] else state['artifacts'][aid]['path']
                    self.path(f'{location}/{f["path"]}')
                revision = {'revision_id': rid, 'history_path': f'history/{aid}/{rid}', 'files': manifest,
                            'dependencies': output['dependencies'], 'producer': intent['producer'],
                            'previous_revision_id': output['base']['revision_id'] if output['base'] else None,
                            'branched_from': output['branched_from']}
                updates.append({'action': output['action'], 'artifact_id': aid,
                                'identity': output['identity'], 'revision': revision})
            by_revision = {u['revision']['revision_id']: u['revision'] for u in updates}
            for update in updates:
                for dep in update['revision']['dependencies']:
                    if 'roles' in dep:
                        roles = dep.pop('roles')
                        dep['files'] = sorted(f['path'] for f in by_revision[dep['revision_id']]['files'] if f['role'] in roles)
            expected = {**intent['publication_heads'], f'run/{run_id}/state': [start['event_id']]}
            event = self._event('operation.completed', {'run_id': run_id, 'updates': updates}, expected, state, expected)
            journal = self.path(f'{intent["workspace"]}/publication.json')
            if journal.exists():
                saved = read_json(journal)
                if saved['data'] != event['data'] or saved['expected_heads'] != expected:
                    raise LedgerError('Prepared publication bytes changed; cannot recover as the same attempt')
                event = saved
            else:
                validate_event(event)
                trial = replay_events([*state['events'].values(), event])
                if event['event_id'] not in trial['events']:
                    raise LedgerError(f'Invalid completion: {trial["issues"]}')
                atomic(journal, encoded(event))
            for output, update in zip(intent['outputs'], updates):
                revision = update['revision']
                for file in revision['files']:
                    source = self.path(f'{intent["workspace"]}/{output["output_slot"]}/{file["path"]}')
                    target = self.path(f'{revision["history_path"]}/{file["path"]}')
                    atomic(target, source.read_bytes())
                    target.chmod(0o700 if source.stat().st_mode & 0o111 else 0o600)
                    if not self._file_matches(target, file):
                        raise LedgerError('Historical bytes differ from publication manifest')
            self._verify_inputs(intent)
            self._append(event, state)
            self._materialize(self._clean(), {u['artifact_id'] for u in updates})
            return event

    recover = finalize

    def fail(self, run_id, code, message, details=None):
        with self.lock():
            self._intent(run_id)
            state = self._clean()
            data = {'run_id': run_id, 'error': {'code': code, 'message': message, 'details': details or {}}}
            return self._append(self._event('operation.failed', data, [f'run/{run_id}/state'], state), state)

    def abandon(self, run_id, reason):
        with self.lock():
            self._intent(run_id)
            state = self._clean()
            return self._append(self._event('operation.abandoned', {'run_id': run_id, 'reason': reason},
                                           [f'run/{run_id}/state'], state), state)

    def import_files(self, files, *, kind, label, song_ids=None, storage_parent=None,
                     dependencies=None, origin=None, producer=None, branched_from=None):
        sources = {name: Path(path).resolve(strict=True) for name, path in files.items()}
        for name, path in sources.items():
            portable_path(name)
            if not path.is_file():
                raise LedgerError('Imports require explicit files')
        if producer is None:
            producer = self.producer('import', 'artifact-bookkeeping', 'artifact_ledger')
        producer = json.loads(json.dumps(producer))
        producer['origin'] = origin
        if origin is None:
            producer['unknowns']['origin'] = 'Origin/source/license not supplied; imported bytes only'
        else:
            producer['unknowns'].pop('origin', None)
        producer['settings'] = producer['settings'] or {}
        producer['settings']['original_names'] = {name: source.name for name, source in sources.items()}
        producer['settings']['original_paths'] = {name: str(source) for name, source in sources.items()}
        spec = {'kind': kind, 'label': label, 'song_ids': song_ids or [], 'storage_parent': storage_parent,
                'dependencies': dependencies or [], 'branched_from': branched_from,
                'contract': {'files': [{'path': name, 'role': kind} for name in sources]}}
        intent = self.prepare(producer['operation'], [spec], producer)
        for name, path in sources.items():
            destination = self.path(f'{intent["workspace"]}/{intent["outputs"][0]["output_slot"]}/{name}')
            atomic(destination, path.read_bytes())
        return self.finalize(intent['run_id'])

    def _projection_path(self):
        return self.path(f'catalogue/{self.host}/projection.json')

    def _materialize(self, state, artifact_ids=None):
        structural = [key for key in state['conflicts'] if key.endswith(('/identity', '/location', '/revision'))
                      and (artifact_ids is None or key.split('/')[1] in artifact_ids)]
        blocked = set(state.get('blocked_artifacts', []))
        if artifact_ids is not None:
            blocked &= artifact_ids
        if structural or blocked:
            raise LedgerError(f'Resolve current view conflicts before materialization: {structural or sorted(blocked)}')
        journal_path = self._projection_path()
        journal = read_json(journal_path) if journal_path.exists() else {'files': {}}
        previous = journal['files']
        desired = {name: entry for name, entry in previous.items()
                   if artifact_ids is not None and entry['artifact_id'] not in artifact_ids}
        active_paths = set()
        for aid, artifact in state['artifacts'].items():
            if artifact_ids is not None and aid not in artifact_ids:
                continue
            record = self.resolve(aid)
            if not record['available']:
                raise LedgerError(f'History unavailable; cannot materialize {aid}')
            location = artifact['path']
            for file in record['files']:
                path = f'{location}/{file["path"]}'
                self.path(path)
                folded = path.casefold()
                if any(existing.casefold() == folded for existing in desired):
                    raise LedgerError(f'Overlapping owned path: {path}')
                active_paths.add(path)
                desired[path] = {'sha256': file['sha256'], 'size_bytes': file['size_bytes'],
                                 'history': f'{record["history_path"]}/{file["path"]}', 'artifact_id': aid}
        for aid, artifact in state['artifacts'].items():
            if artifact_ids is not None and aid not in artifact_ids:
                continue
            if any(entry['artifact_id'] == aid for entry in previous.values()):
                continue
            location = self.path(artifact['path'])
            descendants = [self.path(child['path']) for child_id, child in state['artifacts'].items()
                           if artifact_ids is not None and child_id not in artifact_ids
                           and child['path'].startswith(artifact['path'] + '/')]
            for entry in location.rglob('*'):
                if any(entry.is_relative_to(child) for child in descendants):
                    continue
                if entry.is_symlink() or (entry.is_file() and entry.relative_to(self.root).as_posix() not in desired):
                    raise LedgerError(f'Unknown destination file; preserved: {entry}')
        paths = sorted(desired, key=str.casefold)
        for first, second in zip(paths, paths[1:]):
            if second.casefold().startswith(first.casefold() + '/'):
                raise LedgerError(f'File/directory ownership collision: {first}')
        # Preflight the entire projection before changing the first owned file.
        for name, wanted in desired.items():
            if name not in active_paths:
                continue
            target = self.path(name)
            for parent in target.parents:
                if parent == self.root:
                    break
                if parent.exists() and not parent.is_dir():
                    raise LedgerError(f'Projection ancestor is a file: {parent}')
            if target.exists() and not self._file_matches(target, wanted):
                old = previous.get(name)
                if not old or not self._file_matches(target, old):
                    raise LedgerError(f'Unexpected local edit; preserved: {name}')
                if not self._file_matches(self.path(old['history']), old):
                    raise LedgerError(f'Old history unavailable; refusing replacement: {name}')
            if target.parent.exists():
                for sibling in target.parent.iterdir():
                    if sibling.name.casefold() == target.name.casefold() and sibling.name != target.name:
                        raise LedgerError(f'Case-insensitive destination collision: {name}')
        retired = set(previous) - set(desired)
        for name in retired:
            target = self.path(name)
            if target.exists() and not self._file_matches(target, previous[name]):
                raise LedgerError(f'Unexpected edit to retired owned file; preserved: {name}')
            if target.exists() and not self._file_matches(self.path(previous[name]['history']), previous[name]):
                raise LedgerError(f'Old history unavailable; refusing removal: {name}')
        atomic(journal_path, encoded({'files': previous, 'intended': desired}), replace=True)
        for name, wanted in desired.items():
            if name not in active_paths:
                continue
            target = self.path(name)
            if not self._file_matches(target, wanted):
                atomic(target, self.path(wanted['history']).read_bytes(), replace=True)
            if not self._file_matches(target, wanted):
                raise LedgerError(f'Projection verification failed: {name}')
        for name in retired:
            self.path(name).unlink(missing_ok=True)
        atomic(journal_path, encoded({'files': desired}), replace=True)
        return {'files': len(desired), 'retired': len(retired)}

    def _resource_cache(self):
        value = self.config['paths'].get('resource_cache')
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise LedgerError('Configure paths.resource_cache outside the repo and synchronized data root')
        path = Path(value).resolve()
        for forbidden in (ROOT, self.root):
            if path.is_relative_to(forbidden) or forbidden.is_relative_to(path):
                raise LedgerError('Resource cache must be separate from repository and data root')
        return path

    def _descriptor(self, ref):
        record = self.resolve(ref['artifact_id'], ref['revision_id'])
        if not record['available'] or len(record['files']) != 1:
            raise LedgerError('Resource descriptor unavailable or not a single file')
        descriptor = read_json(self.path(f'{record["history_path"]}/{record["files"][0]["path"]}'))
        if set(descriptor) != {'config_key', 'version', 'source', 'files'} or not descriptor['files']:
            raise LedgerError('Invalid resource descriptor')
        folded = set()
        casefold_paths(file['path'] for file in descriptor['files'])
        directories = set()
        for file in descriptor['files']:
            if set(file) != {'path', 'sha256', 'size_bytes'}:
                raise LedgerError('Invalid resource manifest')
            resource_relative(file['path'])
            parts = file['path'].split('/')
            parents = {'/'.join(parts[:length]).casefold() for length in range(1, len(parts))}
            if file['path'].casefold() in directories or parents & folded:
                raise LedgerError('Resource file/directory collision')
            directories.update(parents)
            if file['path'].casefold() in folded:
                raise LedgerError('Case-insensitive resource collision')
            folded.add(file['path'].casefold())
        return descriptor

    def _resource_installation(self, key):
        parts = key.split('.')
        if len(parts) < 2 or parts[0] not in ('resources', 'tools'):
            raise LedgerError('Resource config_key must name tools or resources')
        value = self.config
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                raise LedgerError(f'Resource unavailable: configure {key}')
            value = value[part]
        if isinstance(value, list):
            value = value[0] if value else None
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise LedgerError(f'{key} must resolve to an absolute resource path')
        installation = Path(value).resolve(strict=True)
        if installation.is_relative_to(ROOT) and installation != Path(sysconfig.get_path('purelib')).resolve():
            raise LedgerError('Installed resources must remain outside repository (except the active Python environment)')
        return installation if installation.is_dir() else installation.parent

    def _prepare_resources(self, producer, run_id, *, dry_run):
        slots = []
        for index, ref in enumerate(producer['resources'], 1):
            descriptor = self._descriptor(ref)
            cache = self._resource_cache() / self.host / run_id / ref['revision_id']
            installation = None
            for file in descriptor['files']:
                target = resource_file(cache, file['path'])
                if not target.exists():
                    installation = installation or self._resource_installation(descriptor['config_key'])
                    source = resource_file(installation, file['path'])
                if target.exists():
                    if not self._file_matches(target, file):
                        raise LedgerError('Resource snapshot integrity failure')
                elif not self._file_matches(source, file):
                    raise LedgerError(f'Historical resource bytes unavailable: {descriptor["config_key"]}/{file["path"]}')
                elif not dry_run:
                    atomic(target, source.read_bytes())
                    target.chmod(0o700 if source.stat().st_mode & 0o111 else 0o600)
                    if not self._file_matches(target, file):
                        raise LedgerError('Resource changed during snapshot')
            slots.append({**ref, 'slot': f'resources/r{index:04d}',
                          'files': sorted(f['path'] for f in descriptor['files'])})
        return slots

    def resource_paths(self, run_id):
        intent, _ = self._intent(run_id)
        return {slot['slot']: self._resource_cache() / self.host / run_id / slot['revision_id']
                for slot in intent['resource_slots']}

    def _verify_resources(self, intent):
        for slot in intent['resource_slots']:
            descriptor = self._descriptor(slot)
            directory = self._resource_cache() / self.host / intent['run_id'] / slot['revision_id']
            entries = list(directory.rglob('*'))
            if any(p.is_symlink() for p in entries):
                raise LedgerError('Resource snapshot contains a symlink')
            actual = {p.relative_to(directory).as_posix() for p in entries if p.is_file()}
            if actual != set(slot['files']):
                raise LedgerError('Resource snapshot file set changed')
            for file in descriptor['files']:
                if not self._file_matches(resource_file(directory, file['path']), file):
                    raise LedgerError('Resource snapshot altered')

    def register_resource(self, config_key, filenames, *, label, version, source):
        installation = self._resource_installation(config_key)
        files = []
        for name in filenames:
            path = resource_file(installation, name)
            if path.is_symlink() or not path.resolve().is_relative_to(installation):
                raise LedgerError('Unsafe resource file')
            files.append({'path': name, 'sha256': sha(path), 'size_bytes': path.stat().st_size})
        descriptor = {'config_key': config_key, 'version': version, 'source': source, 'files': files}
        producer = self.producer('resource-descriptor', 'artifact-bookkeeping', 'artifact_ledger')
        intent = self.prepare('resource-descriptor', [{'kind': 'resource', 'label': label,
                              'contract': {'files': [{'path': 'resource.json', 'role': 'descriptor'}]}}], producer)
        atomic(self.path(f'{intent["workspace"]}/{intent["outputs"][0]["output_slot"]}/resource.json'), encoded(descriptor))
        return self.finalize(intent['run_id'])

    def _mutate(self, kind, data, keys):
        with self.lock():
            state = self._clean()
            if any(len(state['heads'].get(key, [])) > 1 for key in keys):
                raise LedgerError('Resolve conflicting heads before mutation')
            return self._append(self._event(kind, data, keys, state), state)

    def metadata(self, target, changes, reason):
        kind, identity = target['type'], target['id']
        keys = [f'{kind}/{identity}/{field}' for field in changes]
        return self._mutate('metadata.corrected', {'target': target, 'changes': changes, 'reason': reason}, keys)

    def review(self, target, stage, purpose, verdict, notes='', evidence=None, supersedes=None):
        rid = new_id()
        return self._mutate('review.recorded', {'review_id': rid, 'target': target, 'stage': stage,
                            'purpose': purpose, 'verdict': verdict, 'notes': notes,
                            'evidence': evidence or [], 'supersedes': supersedes}, [f'review/{rid}'])

    def select(self, scope, stage, purpose, target):
        return self._mutate('selection.set', {'scope': scope, 'stage': stage, 'purpose': purpose,
                            'target': target}, [f'selection/{scope}/{stage}/{purpose}'])

    def withdraw(self, artifact_id, withdrawn=True, reason=''):
        return self._mutate('artifact.withdrawal_set', {'artifact_id': artifact_id,
                            'withdrawn': withdrawn, 'reason': reason}, [f'artifact/{artifact_id}/withdrawn'])

    def resolve_conflict(self, resolutions, reason):
        with self.lock():
            state = self._clean()
            keys = [item['key'] for item in resolutions]
            for item in resolutions:
                if item['heads'] != state['heads'].get(item['key']) or len(item['heads']) < 2:
                    raise LedgerError('Resolution must name every current competing head')
            event = self._event('conflict.resolved', {'resolutions': resolutions, 'reason': reason}, keys, state)
            self._append(event, state)
            return event

    def move(self, artifact_id, name, reason):
        portable_path(name)
        if '/' in name:
            raise LedgerError('V1 moves rename one subtree; reparenting is unsupported')
        with self.lock():
            state = self._clean()
            artifact = state['artifacts'].get(artifact_id)
            if not artifact or not artifact.get('path'):
                raise LedgerError('Unknown or conflicted artifact location')
            old = artifact['path']
            parent = artifact['storage_parent']
            parent_path = state['artifacts'][parent].get('path') if parent else old.rsplit('/', 1)[0]
            if not parent_path:
                raise LedgerError('Resolve storage parent location before moving its child')
            new = parent_path + '/' + name
            targets = {artifact_id: new}
            while True:
                children = {aid: targets[child['storage_parent']] + '/' + child['path'].rsplit('/', 1)[1]
                            for aid, child in state['artifacts'].items()
                            if aid not in targets and child['storage_parent'] in targets and child.get('path')}
                if not children:
                    break
                targets.update(children)
            mapping = []
            for aid, target in targets.items():
                self.path(target)
                mapping.append({'artifact_id': aid, 'from': state['artifacts'][aid]['path'], 'to': target})
            mapping.sort(key=lambda item: item['artifact_id'])
            owned = set()
            for item in mapping:
                revision = self.resolve(item['artifact_id'])
                for file in revision['files']:
                    owned.add(f'{item["from"]}/{file["path"]}')
                    self.path(f'{item["to"]}/{file["path"]}')
            for item in mapping:
                for path in self.path(item['from']).rglob('*'):
                    if path.is_symlink() or (path.is_file() and path.relative_to(self.root).as_posix() not in owned):
                        raise LedgerError('Unknown descendant files block a managed move')
            if self.path(new).exists():
                raise LedgerError('Move destination already exists')
            keys = [f'artifact/{item["artifact_id"]}/location' for item in mapping]
            event = self._event('artifacts.moved', {'mapping': mapping, 'reason': reason}, keys, state)
            atomic(self.path(f'catalogue/{self.host}/move-{event["event_id"]}.json'), encoded(event))
            self._append(event, state)
            self._materialize(self._clean(), {item['artifact_id'] for item in mapping})
            return event

    def history(self, artifact_id):
        state = self.state()
        return [revision for revision in state['revisions'].values() if revision['artifact_id'] == artifact_id]

    def inputs(self, artifact_id, revision_id=None, transitive=False):
        start = self.resolve(artifact_id, revision_id)
        results, seen = [], set()
        def visit(record):
            for dep in record['dependencies']:
                key = (dep['artifact_id'], dep['revision_id'], tuple(dep['files']))
                if key in seen:
                    continue
                seen.add(key)
                results.append(dep)
                if transitive:
                    visit(self.resolve(dep['artifact_id'], dep['revision_id']))
        visit(start)
        return results

    def consumers(self, artifact_id, revision_id=None, transitive=False):
        revision = self.resolve(artifact_id, revision_id)
        wanted = {(artifact_id, revision['revision_id'])}
        state = self.state()
        result = []
        while True:
            found = []
            for rid, record in state['revisions'].items():
                ref = (record['artifact_id'], rid)
                if ref in wanted:
                    continue
                if any((dep['artifact_id'], dep['revision_id']) in wanted for dep in record['dependencies']):
                    found.append(ref)
                    result.append({'artifact_id': ref[0], 'revision_id': ref[1]})
            if not transitive or not found:
                return result
            wanted.update(found)

    def list(self, *, song_id=None, kind=None, label=None, role=None, review=None,
             selected=None, available=None):
        state = self.state()
        records = []
        for aid, artifact in state['artifacts'].items():
            if song_id and song_id not in artifact.get('song_ids', []):
                continue
            if kind and artifact['kind'] != kind:
                continue
            if label and label.casefold() not in artifact.get('label', '').casefold():
                continue
            for revision in self.history(aid):
                rid = revision['revision_id']
                reviews = [r for r in state['reviews'].values() if r['target']['revision_id'] == rid]
                selections = [key for key, value in state['selections'].items()
                              if value and value.get('revision_id') == rid]
                record = self.resolve(aid, rid)
                if role and role not in [f['role'] for f in record['files']]:
                    continue
                if review and review not in [r['verdict'] for r in reviews]:
                    continue
                if selected is not None and bool(selections) != selected:
                    continue
                if available is not None and record['available'] != available:
                    continue
                records.append({**artifact, **record, 'registered': True,
                                'current': artifact.get('revision') == rid,
                                'reviews': reviews, 'selections': selections,
                                'conflicted': any(key.startswith(f'artifact/{aid}/') for key in state['conflicts'])})
        return {'artifacts': records, 'issues': state['issues'], 'conflicts': state['conflicts']}

    def reconcile(self):
        state = self.state()
        expected = {}
        for aid, artifact in state['artifacts'].items():
            if not artifact.get('path') or f'artifact/{aid}/revision' in state['conflicts']:
                continue
            record = self.resolve(aid)
            for file in record['files']:
                expected[f'{artifact["path"]}/{file["path"]}'] = file
        missing, altered, unmanaged = [], [], []
        for name, file in expected.items():
            path = self.path(name)
            if not path.exists():
                missing.append(name)
            elif not self._file_matches(path, file):
                altered.append(name)
        for path in self.root.rglob('*'):
            relative = path.relative_to(self.root).as_posix()
            if relative.split('/')[0] in {'ledger', 'history', 'work', 'catalogue'}:
                continue
            if (path.is_file() or path.is_symlink()) and relative not in expected:
                unmanaged.append(relative)
        return {'missing': sorted(missing), 'altered': sorted(altered), 'unmanaged': sorted(unmanaged),
                'issues': state['issues'], 'conflicts': state['conflicts']}

    def rebuild(self, *, view=False):
        with self.lock():
            state = self._clean()
            result = self.list()
            result['frontier'] = sorted(set(state['events']) - {parent for e in state['events'].values() for parent in e['previous_events']})
            atomic(self.path(f'catalogue/{self.host}/index.json'), encoded(result), replace=True)
            if view:
                result['materialization'] = self._materialize(state)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-root', type=Path, default=ROOT)
    parser.add_argument('--json', action='store_true', help='Emit JSON (also accepted after command)')
    parser.add_argument('--frontier', help='Read-only causal state at comma-separated event IDs')
    sub = parser.add_subparsers(dest='command', required=True)
    song = sub.add_parser('song'); song.add_argument('label')
    prepare = sub.add_parser('prepare'); prepare.add_argument('request', type=Path)
    for command in ('finalize', 'recover', 'abandon', 'fail'):
        p = sub.add_parser(command); p.add_argument('run_id')
        if command in ('fail', 'abandon'):
            p.add_argument('--reason', required=True)
    imp = sub.add_parser('import'); imp.add_argument('request', type=Path)
    for command in ('resolve', 'history', 'inputs', 'consumers'):
        p = sub.add_parser(command); p.add_argument('artifact_id'); p.add_argument('--revision-id')
        if command in ('inputs', 'consumers'):
            p.add_argument('--transitive', action='store_true')
    ls = sub.add_parser('list')
    for option in ('song-id', 'kind', 'label', 'role', 'review'):
        ls.add_argument('--' + option)
    ls.add_argument('--selected', action='store_true', default=None)
    ls.add_argument('--available', action='store_true', default=None)
    for command in ('review', 'select', 'metadata', 'resolve-conflict', 'resource'):
        p = sub.add_parser(command); p.add_argument('request', type=Path)
    move = sub.add_parser('move'); move.add_argument('artifact_id'); move.add_argument('name'); move.add_argument('--reason', required=True)
    wd = sub.add_parser('withdraw'); wd.add_argument('artifact_id'); wd.add_argument('--reason', required=True); wd.add_argument('--restore', action='store_true')
    sub.add_parser('reconcile')
    sub.add_parser('discover')
    rb = sub.add_parser('rebuild'); rb.add_argument('--view', action='store_true')
    sub.add_parser('status')
    # Global output/config switches may also follow a subcommand.
    raw = list(sys.argv[1:] if argv is None else argv)
    if '--json' in raw:
        raw.remove('--json'); raw.insert(0, '--json')
    if '--config-root' in raw:
        pos = raw.index('--config-root')
        option = raw[pos:pos + 2]; del raw[pos:pos + 2]; raw = option + raw
    args = parser.parse_args(raw)
    try:
        ledger = Ledger(load_config(args.config_root), frontier=args.frontier.split(',') if args.frontier else None)
        cmd = args.command
        if cmd == 'song': result = ledger.create_song(args.label)
        elif cmd == 'prepare':
            request = read_json(args.request)
            if 'producer' not in request:
                request['producer'] = ledger.producer(request['operation'], 'artifact-bookkeeping', 'manual', settings=request.pop('settings', {}))
            result = ledger.prepare(**request)
        elif cmd in ('finalize', 'recover'): result = ledger.finalize(args.run_id)
        elif cmd == 'fail': result = ledger.fail(args.run_id, 'producer-failed', args.reason)
        elif cmd == 'abandon': result = ledger.abandon(args.run_id, args.reason)
        elif cmd == 'import': result = ledger.import_files(**read_json(args.request))
        elif cmd == 'list':
            result = ledger.list(**{name: getattr(args, name) for name in ('song_id', 'kind', 'label', 'role', 'review', 'selected', 'available')})
        elif cmd == 'resolve': result = ledger.resolve(args.artifact_id, args.revision_id)
        elif cmd == 'history': result = ledger.history(args.artifact_id)
        elif cmd in ('inputs', 'consumers'):
            result = getattr(ledger, cmd)(args.artifact_id, args.revision_id, args.transitive)
        elif cmd in ('review', 'select', 'metadata', 'resolve-conflict'):
            result = getattr(ledger, cmd.replace('-', '_'))(**read_json(args.request))
        elif cmd == 'resource': result = ledger.register_resource(**read_json(args.request))
        elif cmd == 'move': result = ledger.move(args.artifact_id, args.name, args.reason)
        elif cmd == 'withdraw': result = ledger.withdraw(args.artifact_id, not args.restore, args.reason)
        elif cmd in ('reconcile', 'discover'): result = ledger.reconcile()
        elif cmd == 'rebuild': result = ledger.rebuild(view=args.view)
        else:
            state = ledger.state()
            result = {'events': len(state['events']), 'songs': state['songs'], 'runs': state['runs'],
                      'frontier': state['frontier'], 'issues': state['issues'], 'conflicts': state['conflicts']}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'Bookkeeping error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
