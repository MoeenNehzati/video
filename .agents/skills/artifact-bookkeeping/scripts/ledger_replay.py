"""Read-only schema validation and causal replay of immutable artifact events."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'schema/event.schema.json'


class LedgerValidationError(ValueError):
    pass


class PendingReference(LedgerValidationError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def portable_path(value: str, root: Path | None = None, *, check_links: bool = True) -> str:
    if not isinstance(value, str) or not value or len(value) > 200 or '\\' in value:
        raise LedgerValidationError(f'Invalid portable path: {value!r}')
    parts = value.split('/')
    for part in parts:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', part) or part.endswith('.'):
            raise LedgerValidationError(f'Invalid path component: {part!r}')
        if part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            raise LedgerValidationError(f'Reserved device path: {part}')
    if root is not None:
        full = root.absolute().joinpath(*parts)
        if len(str(full).encode('utf-16-le')) // 2 > 240:
            raise LedgerValidationError(f'Absolute path exceeds 240 UTF-16 units: {full}')
        cursor = root.absolute()
        for part in parts:
            cursor /= part
            if check_links and cursor.is_symlink():
                raise LedgerValidationError(f'Symlink in managed path: {cursor}')
    return value


def resource_relative(value: str) -> str:
    """Keep installed resource spelling while rejecting unsafe portable paths."""
    if not isinstance(value, str) or not value or value.startswith('/') or '\\' in value:
        raise LedgerValidationError('Invalid resource relative path')
    for part in value.split('/'):
        if part in ('', '.', '..') or part.endswith(('.', ' ')) or any(ord(c) < 32 or c in '<>:"|?*' for c in part):
            raise LedgerValidationError('Unsafe resource path component')
        if part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            raise LedgerValidationError('Reserved resource device path')
    return value


def _schema(value: Any, spec: dict, schema: dict, at: str = '$') -> None:
    if '$ref' in spec:
        spec = schema['$defs'][spec['$ref'].rsplit('/', 1)[1]]
    if 'const' in spec and (value != spec['const'] or type(value) is not type(spec['const'])):
        raise LedgerValidationError(f'{at}: expected constant {spec["const"]!r}')
    if 'enum' in spec and value not in spec['enum']:
        raise LedgerValidationError(f'{at}: unsupported value {value!r}')
    for combiner in ('anyOf', 'oneOf'):
        if combiner in spec:
            count = 0
            for option in spec[combiner]:
                try:
                    _schema(value, option, schema, at)
                    count += 1
                except LedgerValidationError:
                    pass
            if not count or (combiner == 'oneOf' and count != 1):
                raise LedgerValidationError(f'{at}: does not match {combiner}')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool, 'null': type(None)}
    kind = spec.get('type')
    if kind and type(value) is not types[kind]:
        raise LedgerValidationError(f'{at}: expected {kind}')
    if kind == 'object':
        props = spec.get('properties', {})
        if set(spec.get('required', [])) - value.keys():
            raise LedgerValidationError(f'{at}: missing fields {sorted(set(spec["required"]) - value.keys())}')
        for key, item in value.items():
            if key in props:
                _schema(item, props[key], schema, f'{at}.{key}')
            elif spec.get('additionalProperties') is False:
                raise LedgerValidationError(f'{at}: unknown field {key}')
            elif isinstance(spec.get('additionalProperties'), dict):
                _schema(item, spec['additionalProperties'], schema, f'{at}.{key}')
    elif kind == 'array':
        if len(value) < spec.get('minItems', 0):
            raise LedgerValidationError(f'{at}: too few items')
        if spec.get('uniqueItems') and len({canonical_json(v) for v in value}) != len(value):
            raise LedgerValidationError(f'{at}: duplicate items')
        for index, item in enumerate(value):
            _schema(item, spec['items'], schema, f'{at}[{index}]')
    elif kind == 'string':
        if len(value) < spec.get('minLength', 0) or ('pattern' in spec and not re.search(spec['pattern'], value)):
            raise LedgerValidationError(f'{at}: invalid string {value!r}')
    elif kind == 'integer' and value < spec.get('minimum', value):
        raise LedgerValidationError(f'{at}: integer below minimum')
    for condition in spec.get('allOf', []):
        try:
            _schema(value, condition['if'], schema, at)
        except LedgerValidationError:
            continue
        _schema(value, condition['then'], schema, at)
    # Conditional schemas omit type but still constrain their named properties.
    if kind is None and 'properties' in spec and isinstance(value, dict):
        for key, child in spec['properties'].items():
            if key in value:
                _schema(value[key], child, schema, f'{at}.{key}')


def _walk(value: Any) -> None:
    if value is not None and type(value) not in (str, bool, int, float, dict, list):
        raise LedgerValidationError('Value is not a JSON type')
    if isinstance(value, float) and not math.isfinite(value):
        raise LedgerValidationError('Non-finite JSON number')
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise LedgerValidationError('JSON object keys must be strings')
        for item in value.values():
            _walk(item)
    elif isinstance(value, list):
        for item in value:
            _walk(item)


@lru_cache(maxsize=1)
def _event_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_event(event: dict) -> None:
    _walk(event)
    schema = _event_schema()
    _schema(event, schema, schema)
    try:
        datetime.fromisoformat(event['recorded_at'].replace('Z', '+00:00'))
    except ValueError as exc:
        raise LedgerValidationError('Invalid UTC event timestamp') from exc
    for heads in [event['previous_events'], *event['expected_heads'].values()]:
        if heads != sorted(set(heads)):
            raise LedgerValidationError('Event IDs and head sets must be sorted and unique')
    if event['event_id'] in event['previous_events']:
        raise LedgerValidationError('Event is its own predecessor')


def selection_key(data: dict) -> str:
    return f'selection/{data["scope"]}/{data["stage"]}/{data["purpose"]}'


def event_writes(event: dict, values: dict | None = None) -> dict:
    values = values or {}
    kind, data = event['event_type'], event['data']
    writes = {}
    if kind == 'song.created':
        key = f'song/{data["song_id"]}'
        writes.update({key: {'song_id': data['song_id'], 'path': data['path']}, key + '/label': data['label']})
    elif kind.startswith('operation.'):
        writes[f'run/{data["run_id"]}/state'] = {'status': kind.split('.')[1], **data}
        if kind == 'operation.completed':
            for update in data['updates']:
                aid, rev = update['artifact_id'], update['revision']
                key = f'artifact/{aid}'
                if update['action'] == 'create':
                    identity = update['identity']
                    writes[key + '/identity'] = {k: identity[k] for k in ('artifact_id', 'kind', 'storage_parent')}
                    for field in ('label', 'path', 'song_ids'):
                        writes[key + ('/location' if field == 'path' else '/' + field)] = identity[field]
                    writes[key + '/withdrawn'] = False
                writes[key + '/revision'] = rev['revision_id']
                writes[f'revision/{rev["revision_id"]}/provenance_notes'] = None
    elif kind == 'metadata.corrected':
        target = data['target']
        prefix = f'{target["type"]}/{target["id"]}'
        for field, value in data['changes'].items():
            key = prefix + '/' + field
            writes[key] = (values.get(key) or []) + [{'event_id': event['event_id'], 'notes': value, 'reason': data['reason']}] if field == 'provenance_notes' else value
    elif kind == 'artifacts.moved':
        writes = {f'artifact/{item["artifact_id"]}/location': item['to'] for item in data['mapping']}
    elif kind == 'review.recorded':
        writes[f'review/{data["review_id"]}'] = {**data, 'actor': event['actor']}
    elif kind == 'selection.set':
        writes[selection_key(data)] = data['target']
    elif kind == 'artifact.withdrawal_set':
        writes[f'artifact/{data["artifact_id"]}/withdrawn'] = data['withdrawn']
    elif kind == 'conflict.resolved':
        writes = {item['key']: None for item in data['resolutions']}
    return writes


def mutation_keys(event: dict) -> list[str]:
    return sorted(event_writes(event))


def _heads(ids: set[str], writes: dict, ancestors: dict) -> dict:
    by_key = {}
    for eid in ids:
        for key in writes[eid]:
            by_key.setdefault(key, set()).add(eid)
    return {key: sorted(e for e in writers if not any(e in ancestors[other] for other in writers)) for key, writers in by_key.items()}


def _values(heads: dict, writes: dict) -> dict:
    return {key: writes[eids[0]][key] for key, eids in heads.items() if len(eids) == 1}


def casefold_paths(paths) -> None:
    spellings = {}
    for path in paths:
        parts = path.split('/')
        for length in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:length])
            previous = spellings.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                raise LedgerValidationError('Case-insensitive directory or file spelling collision')


def _unique_files(files: list[dict]) -> None:
    casefold_paths(file['path'] for file in files)
    paths = []
    for item in files:
        portable_path(item['path'])
        path = item['path'].casefold()
        if path in paths or any(path.startswith(old + '/') or old.startswith(path + '/') for old in paths):
            raise LedgerValidationError('Overlapping or case-colliding owned files')
        paths.append(path)


def _dependency_key(dep: dict) -> str:
    return canonical_json(dep)


def _semantic(event: dict, values: dict, heads: dict, events: dict, closure: set[str]) -> None:
    kind, data = event['event_type'], event['data']
    revisions, identities, reviews = {}, {}, {}
    for eid in closure:
        old = events[eid]
        if old['event_type'] == 'operation.completed':
            for update in old['data']['updates']:
                rid = update['revision']['revision_id']
                revisions[rid] = {**update['revision'], 'artifact_id': update['artifact_id']}
                if update['identity'] is not None:
                    identities[update['artifact_id']] = update['identity']
        elif old['event_type'] == 'review.recorded':
            reviews[old['data']['review_id']] = old
    local = {}
    if kind == 'operation.completed':
        for update in data['updates']:
            rid = update['revision']['revision_id']
            if rid in revisions or rid in local:
                raise LedgerValidationError('Revision identity reused')
            local[rid] = {**update['revision'], 'artifact_id': update['artifact_id']}
            if update['identity'] is not None:
                identities[update['artifact_id']] = update['identity']

    def exact(ref: dict) -> dict:
        record = local.get(ref['revision_id'], revisions.get(ref['revision_id']))
        if record is None:
            raise PendingReference(f'Referenced revision absent from causal history: {ref["revision_id"]}')
        if record['artifact_id'] != ref['artifact_id']:
            raise LedgerValidationError('Revision belongs to a different artifact')
        return record

    def dependency(dep: dict, *, intent=False, allocated=None) -> None:
        if intent and dep['revision_id'] in (allocated or {}):
            output = allocated[dep['revision_id']]
            if output['artifact_id'] != dep['artifact_id']:
                raise LedgerValidationError('Allocated dependency artifact mismatch')
            if ('files' in dep) == ('roles' in dep):
                raise LedgerValidationError('Intent dependency needs files or roles, exclusively')
            if 'files' in output['contract'] and 'files' in dep:
                available = {f['path'] for f in output['contract']['files']}
                if not set(dep['files']) <= available:
                    raise LedgerValidationError('Dependency file missing from allocated output')
            return
        record = exact(dep)
        if 'roles' in dep or not set(dep['files']) <= {f['path'] for f in record['files']}:
            raise LedgerValidationError('Dependency names files absent from manifest')

    def song(sid: str) -> None:
        if f'song/{sid}' not in values:
            raise PendingReference(f'Unknown or conflicted song {sid}')

    def identity(record: dict, dependencies: list[dict]) -> None:
        aid, path, parent = record['artifact_id'], record['path'], record['storage_parent']
        portable_path(path)
        if record['song_ids'] != sorted(set(record['song_ids'])):
            raise LedgerValidationError('Song IDs must be sorted and unique')
        for sid in record['song_ids']:
            song(sid)
        if parent:
            if parent == aid or parent not in identities:
                raise PendingReference('Storage parent is unavailable')
            parent_path = values.get(f'artifact/{parent}/location', identities[parent]['path'])
            if str(PurePosixPath(path).parent) != parent_path:
                raise LedgerValidationError('Artifact must nest directly under storage parent')
            if parent not in {dep['artifact_id'] for dep in dependencies}:
                raise LedgerValidationError('Storage parent must be a declared dependency')
        elif path.startswith('shared/'):
            if len(path.split('/')) != 2:
                raise LedgerValidationError('Shared root artifact must be directly under shared/')
        else:
            if len(record['song_ids']) != 1 or str(PurePosixPath(path).parent) != values[f'song/{record["song_ids"][0]}']['path']:
                raise LedgerValidationError('Source artifact must be directly under its song')
        for key, value in values.items():
            if key.endswith('/location') and value.casefold() == path.casefold():
                raise LedgerValidationError('Artifact location already occupied')

    def producer(record: dict) -> None:
        if not record['code']['files']:
            raise LedgerValidationError('Producer must capture executed code file hashes')
        if record['run_id'] != data['run_id']:
            raise LedgerValidationError('Producer run does not match operation')
        for field in ('skill', 'entrypoint', 'command', 'settings', 'origin'):
            if record[field] is None and not record['unknowns'].get(field):
                raise LedgerValidationError(f'Missing unknown provenance reason: {field}')
        if record['code']['snapshot'] is None:
            if not record['unknowns'].get('code.snapshot'):
                raise LedgerValidationError('Missing code snapshot reason')
            if record['operation'] != 'code-snapshot':
                raise LedgerValidationError('Only code-snapshot permits hash-only code provenance')
        else:
            snapshot = record['code']['snapshot']
            exact(snapshot)
            if identities[snapshot['artifact_id']]['kind'] != 'code':
                raise LedgerValidationError('Producer code snapshot must reference a code artifact')
        for resource in record['resources']:
            exact(resource)
            if identities[resource['artifact_id']]['kind'] != 'resource':
                raise LedgerValidationError('Producer resources must reference resource descriptors')
        for item in record['code']['files']:
            path = item['path']
            if path.startswith('/') or '\\' in path or ':' in path or any(p in ('', '.', '..') for p in path.split('/')):
                raise LedgerValidationError('Unsafe source code provenance path')

    if kind == 'song.created':
        portable_path(data['path'])
        if len(data['path'].split('/')) != 2 or not data['path'].startswith('songs/'):
            raise LedgerValidationError('Song location must be directly under songs/')
        if any(key.startswith('song/') and key.count('/') == 1 and value['path'].casefold() == data['path'].casefold() for key, value in values.items()):
            raise LedgerValidationError('Song location already occupied')
    elif kind == 'operation.started':
        if data['workspace'] != f'work/{data["run_id"]}':
            raise LedgerValidationError('Workspace does not match run identity')
        producer(data['producer'])
        if data['producer']['operation'] != data['operation']:
            raise LedgerValidationError('Producer operation differs from intent')
        allocated = {output['revision_id']: output for output in data['outputs']}
        if len(allocated) != len(data['outputs']) or len({o['artifact_id'] for o in data['outputs']}) != len(data['outputs']):
            raise LedgerValidationError('Duplicate allocated artifact or revision')
        for output in data['outputs']:
            if output['action'] == 'create' and output['identity'] is not None:
                identities[output['artifact_id']] = output['identity']
        publication = {}
        external = {}
        output_slots = set()
        for output in data['outputs']:
            aid, rid = output['artifact_id'], output['revision_id']
            if rid in revisions:
                raise LedgerValidationError('Revision identity already exists')
            portable_path(output['output_slot'])
            if not output['output_slot'].startswith('outputs/') or output['output_slot'] in output_slots:
                raise LedgerValidationError('Invalid or duplicate output slot')
            output_slots.add(output['output_slot'])
            contract = output['contract']
            if 'files' in contract:
                _unique_files(contract['files'])
            else:
                patterns = []
                for discovery in contract['discovery']:
                    pattern = discovery['glob']
                    portable_path(pattern.replace('*', 'x').replace('?', 'x'))
                    if '**' in pattern or '[' in pattern or discovery['min_count'] > discovery['max_count']:
                        raise LedgerValidationError('Invalid bounded discovery pattern')
                    if any(_glob_overlap(pattern, old) for old in patterns):
                        raise LedgerValidationError('Overlapping discovery patterns')
                    patterns.append(pattern)
            if output['action'] == 'create':
                if output['identity'] is None or output['identity']['artifact_id'] != aid or output['base'] is not None:
                    raise LedgerValidationError('Invalid create intent')
                identity(output['identity'], output['dependencies'])
                for field in ('identity', 'revision', 'location', 'label', 'song_ids', 'withdrawn'):
                    publication[f'artifact/{aid}/{field}'] = []
                if output['branched_from']:
                    exact(output['branched_from'])
            else:
                if output['identity'] is not None or output['base'] is None or output['branched_from'] is not None:
                    raise LedgerValidationError('Invalid revise intent')
                exact(output['base'])
                key = f'artifact/{aid}/revision'
                if output['base']['artifact_id'] != aid or values.get(key) != output['base']['revision_id']:
                    raise LedgerValidationError('Revise base is not the single current revision')
                publication[key] = heads[key]
            publication[f'revision/{rid}/provenance_notes'] = []
            for dep in output['dependencies']:
                dependency(dep, intent=True, allocated=allocated)
                if dep['revision_id'] not in allocated:
                    external.setdefault((dep['artifact_id'], dep['revision_id']), set()).update(dep['files'])
        _unique_files([{'path': slot} for slot in output_slots])
        _check_cycles({rid: [d['revision_id'] for d in o['dependencies'] if d['revision_id'] in allocated] for rid, o in allocated.items()})
        actual_inputs = {(d['artifact_id'], d['revision_id']): set(d['files']) for d in data['inputs']}
        if len(actual_inputs) != len(data['inputs']) or actual_inputs != external:
            raise LedgerValidationError('Start inputs differ from union of external dependencies')
        if data['publication_heads'] != publication:
            raise LedgerValidationError('Publication heads differ from intended output state')
        for key, expected in publication.items():
            if expected != heads.get(key, []):
                raise LedgerValidationError('Publication head is stale or identity exists')
        for slots, prefix in ((data['input_slots'], 'inputs/'), (data['resource_slots'], 'resources/')):
            names = set()
            for slot in slots:
                portable_path(slot['slot'])
                if not slot['slot'].startswith(prefix) or slot['slot'] in names:
                    raise LedgerValidationError('Invalid or duplicate input/resource slot')
                names.add(slot['slot'])
                record = exact(slot)
                if prefix == 'inputs/' and not set(slot.get('files', [])) <= {f['path'] for f in record['files']}:
                    raise LedgerValidationError('Slot names files absent from manifest')
                casefold_paths(slot.get('files', []))
                for filename in slot.get('files', []):
                    (portable_path if prefix == 'inputs/' else resource_relative)(filename)
            _unique_files([{'path': slot['slot']} for slot in slots])
        slot_inputs = {(s['artifact_id'], s['revision_id']): set(s.get('files', [])) for s in data['input_slots']}
        if len(slot_inputs) != len(data['input_slots']) or slot_inputs != external:
            raise LedgerValidationError('Input slots must cover exact external dependency union')
        if sorted((s['artifact_id'], s['revision_id']) for s in data['resource_slots']) != sorted((s['artifact_id'], s['revision_id']) for s in data['producer']['resources']):
            raise LedgerValidationError('Resource slots must cover producer resources')
    elif kind.startswith('operation.'):
        key = f'run/{data["run_id"]}/state'
        start = values.get(key)
        if start is None:
            raise PendingReference('Operation start unavailable or conflicted')
        if start['status'] != 'started':
            raise LedgerValidationError('Operation is already terminal')
        if kind == 'operation.completed':
            intents = {o['artifact_id']: o for o in start['outputs']}
            if len(data['updates']) != len(intents) or {u['artifact_id'] for u in data['updates']} != set(intents):
                raise LedgerValidationError('Completion does not contain complete output set')
            for update in data['updates']:
                aid, rev = update['artifact_id'], update['revision']
                intent = intents[aid]
                if update['action'] != intent['action'] or update['identity'] != intent['identity'] or rev['revision_id'] != intent['revision_id']:
                    raise LedgerValidationError('Completion changed allocated output identity')
                if rev['history_path'] != f'history/{aid}/{rev["revision_id"]}':
                    raise LedgerValidationError('Wrong revision history path')
                portable_path(rev['history_path'])
                if rev['previous_revision_id'] != (intent['base']['revision_id'] if intent['base'] else None) or rev['branched_from'] != intent['branched_from']:
                    raise LedgerValidationError('Completion changed revision ancestry')
                if rev['producer'] != start['producer']:
                    raise LedgerValidationError('Completion changed producer provenance')
                _unique_files(rev['files'])
                for dep in rev['dependencies']:
                    dependency(dep)
                expected_dependencies = []
                for dep in intent['dependencies']:
                    resolved = dict(dep)
                    if 'roles' in resolved:
                        manifest = exact(dep)['files']
                        roles = resolved.pop('roles')
                        resolved['files'] = sorted(f['path'] for f in manifest if f['role'] in roles)
                        if not resolved['files'] or not set(roles) <= {f['role'] for f in manifest}:
                            raise LedgerValidationError('Declared output role unavailable')
                    expected_dependencies.append(resolved)
                if sorted(map(_dependency_key, rev['dependencies'])) != sorted(map(_dependency_key, expected_dependencies)):
                    raise LedgerValidationError('Completion changed dependency edges')
                contract = intent['contract']
                actual = [{'path': f['path'], 'role': f['role']} for f in rev['files']]
                if 'files' in contract:
                    if sorted(map(canonical_json, actual)) != sorted(map(canonical_json, contract['files'])):
                        raise LedgerValidationError('Completion violates file contract')
                else:
                    counts = [0] * len(contract['discovery'])
                    for item in actual:
                        matches = [i for i, rule in enumerate(contract['discovery']) if fnmatch.fnmatchcase(item['path'], rule['glob'])]
                        if len(matches) != 1 or item['role'] != contract['discovery'][matches[0]]['role']:
                            raise LedgerValidationError('Unexpected output or overlapping discovery')
                        counts[matches[0]] += 1
                    if any(not rule['min_count'] <= counts[i] <= rule['max_count'] for i, rule in enumerate(contract['discovery'])):
                        raise LedgerValidationError('Discovery count outside contract')
            for key, expected in start['publication_heads'].items():
                if event['expected_heads'].get(key) != expected:
                    raise LedgerValidationError('Completion must reuse frozen publication heads')
            _check_cycles({rid: [d['revision_id'] for d in r['dependencies'] if d['revision_id'] in local] for rid, r in local.items()})
    elif kind == 'metadata.corrected':
        target = data['target']
        allowed = {'song': {'label'}, 'artifact': {'label', 'song_ids'}, 'revision': {'provenance_notes'}}[target['type']]
        if not data['changes'] or not set(data['changes']) <= allowed:
            raise LedgerValidationError('Metadata correction changes immutable or unknown fields')
        for field, value in data['changes'].items():
            if field == 'song_ids':
                if not isinstance(value, list) or value != sorted(set(value)):
                    raise LedgerValidationError('Invalid song associations')
                for sid in value:
                    song(sid)
            elif not isinstance(value, str) or not value:
                raise LedgerValidationError('Metadata text must be nonempty')
            if f'{target["type"]}/{target["id"]}/{field}' not in values:
                raise PendingReference('Metadata target unavailable or conflicted')
    elif kind == 'artifact.withdrawal_set':
        if f'artifact/{data["artifact_id"]}/identity' not in values:
            raise PendingReference('Withdrawal artifact unavailable')
    elif kind == 'selection.set':
        scope = data['scope']
        if scope != 'shared' and not re.fullmatch(r'(song|artifact):[0-9a-f-]{36}', scope):
            raise LedgerValidationError('Invalid selection scope')
        if scope.startswith('song:'):
            song(scope[5:])
        elif scope.startswith('artifact:') and scope[9:] not in identities:
            raise PendingReference('Selection scope artifact unavailable')
        if data['target'] is not None:
            exact(data['target'])
            aid = data['target']['artifact_id']
            location = values.get(f'artifact/{aid}/location', identities[aid]['path'])
            if location.startswith('shared/'):
                if scope != 'shared':
                    raise LedgerValidationError('Shared target requires shared scope')
            elif scope.startswith('song:'):
                if scope[5:] not in values.get(f'artifact/{aid}/song_ids', identities[aid]['song_ids']):
                    raise LedgerValidationError('Selection song scope mismatch')
            elif scope.startswith('artifact:'):
                lineage = {aid}
                cursor = identities[aid]['storage_parent']
                while cursor:
                    if cursor in lineage:
                        raise LedgerValidationError('Storage ancestry cycle')
                    lineage.add(cursor)
                    cursor = identities[cursor]['storage_parent']
                if scope[9:] not in lineage:
                    raise LedgerValidationError('Selection artifact scope mismatch')
            else:
                raise LedgerValidationError('Song target cannot use shared scope')
    elif kind == 'review.recorded':
        exact(data['target'])
        for ref in data['evidence']:
            exact(ref)
        if data['supersedes']:
            old = reviews.get(data['supersedes'])
            if old is None:
                raise PendingReference('Superseded review unavailable')
            if old['actor']['id'] != event['actor']['id'] or any(old['data'][field] != data[field] for field in ('target', 'stage', 'purpose')):
                raise LedgerValidationError('Review supersedes unrelated actor or target')
    elif kind == 'artifacts.moved':
        mapping = {item['artifact_id']: item for item in data['mapping']}
        if len(mapping) != len(data['mapping']):
            raise LedgerValidationError('Duplicate move identity')
        roots = [aid for aid in mapping if identities.get(aid, {}).get('storage_parent') not in mapping]
        if len(roots) != 1:
            raise LedgerValidationError('Move must cover one complete subtree')
        moved_root = roots[0]
        if moved_root not in identities:
            raise PendingReference('Moved artifact unavailable')
        old, new = mapping[moved_root]['from'], mapping[moved_root]['to']
        storage_parent = identities[moved_root]['storage_parent']
        parent_location = values.get(f'artifact/{storage_parent}/location') if storage_parent else str(PurePosixPath(old).parent)
        if parent_location is None or str(PurePosixPath(new).parent) != parent_location:
            raise LedgerValidationError('Reparenting is unsupported; move must retain its storage parent identity')
        descendants = {moved_root}
        while True:
            expanded = descendants | {aid for aid, record in identities.items() if record['storage_parent'] in descendants}
            if expanded == descendants:
                break
            descendants = expanded
        if descendants != set(mapping):
            raise LedgerValidationError('Move mapping omits or invents descendants')
        destinations = set()
        for aid, item in mapping.items():
            portable_path(item['to'])
            parent = identities[aid]['storage_parent']
            expected_location = new if aid == moved_root else mapping[parent]['to'] + '/' + PurePosixPath(item['from']).name
            if values.get(f'artifact/{aid}/location') != item['from'] or item['to'] != expected_location:
                raise LedgerValidationError('Move mapping disagrees with subtree identities or locations')
            if item['to'].casefold() in destinations:
                raise LedgerValidationError('Move destination collision')
            destinations.add(item['to'].casefold())
        for aid in identities.keys() - mapping.keys():
            if values.get(f'artifact/{aid}/location', '').casefold() in destinations:
                raise LedgerValidationError('Move collides with another artifact')
    elif kind == 'conflict.resolved':
        resolutions = {item['key']: item for item in data['resolutions']}
        if len(resolutions) != len(data['resolutions']):
            raise LedgerValidationError('Duplicate resolution key')
        for key, item in resolutions.items():
            if len(item['heads']) < 2 or item['heads'] != heads.get(key) or item['chosen_head'] not in item['heads']:
                raise LedgerValidationError('Resolution must choose among all observed competing heads')
            for eid in item['heads']:
                old = events[eid]
                if old['event_type'] == 'artifacts.moved':
                    grouped = set(mutation_keys(old))
                    if not grouped <= resolutions.keys() or any(resolutions[k]['chosen_head'] != item['chosen_head'] for k in grouped):
                        raise LedgerValidationError('Resolution must preserve complete grouped move')


def _glob_overlap(left: str, right: str) -> bool:
    """Intersect two bounded glob automata without guessing sample filenames."""
    seen, pending = set(), [(0, 0)]
    while pending:
        i, j = pending.pop()
        if (i, j) in seen:
            continue
        seen.add((i, j))
        if i == len(left) and j == len(right):
            return True
        if i < len(left) and left[i] == '*':
            pending.append((i + 1, j))
        if j < len(right) and right[j] == '*':
            pending.append((i, j + 1))
        if i < len(left) and j < len(right):
            a, b = left[i], right[j]
            if a == b or a in '*?' or b in '*?':
                pending.append((i if a == '*' else i + 1, j if b == '*' else j + 1))
    return False


def _check_cycles(graph: dict) -> None:
    done, visiting = set(), set()
    def visit(node):
        if node in visiting:
            raise LedgerValidationError('Causal or dependency cycle')
        if node in done:
            return
        visiting.add(node)
        for child in graph.get(node, []):
            visit(child)
        visiting.remove(node)
        done.add(node)
    for node in graph:
        visit(node)


def _root_paths(event: dict, root: Path) -> None:
    data, kind = event['data'], event['event_type']
    if kind == 'song.created':
        portable_path(data['path'], root, check_links=False)
    elif kind == 'operation.started':
        portable_path(data['workspace'], root, check_links=False)
        for slot in data['input_slots']:
            for filename in slot.get('files', []):
                portable_path(data['workspace'] + '/' + slot['slot'] + '/' + filename, root, check_links=False)
        for output in data['outputs']:
            if output['identity']:
                portable_path(output['identity']['path'], root, check_links=False)
            for file in output['contract'].get('files', []):
                portable_path(data['workspace'] + '/' + output['output_slot'] + '/' + file['path'], root, check_links=False)
                portable_path(f'history/{output["artifact_id"]}/{output["revision_id"]}/{file["path"]}', root, check_links=False)
                if output['identity']:
                    portable_path(output['identity']['path'] + '/' + file['path'], root, check_links=False)
    elif kind == 'operation.completed':
        for update in data['updates']:
            revision = update['revision']
            for file in revision['files']:
                portable_path(revision['history_path'] + '/' + file['path'], root, check_links=False)
    elif kind == 'artifacts.moved':
        for item in data['mapping']:
            portable_path(item['from'], root, check_links=False)
            portable_path(item['to'], root, check_links=False)


def replay_events(records, root: Path | None = None, frontier: list[str] | None = None) -> dict:
    events, issues, bad = {}, [], set()
    def issue(status, eid, reason):
        issues.append({'status': status, 'event_id': eid, 'reason': reason})
    for event in records:
        eid = event.get('event_id') if isinstance(event, dict) and isinstance(event.get('event_id'), str) else None
        if isinstance(event, dict) and type(event.get('schema_version')) is int and event['schema_version'] != 1:
            issue('unsupported', eid, 'Unsupported schema version')
            bad.add(eid)
            continue
        try:
            validate_event(event)
            if eid in events and canonical_json(events[eid]) != canonical_json(event):
                issue('integrity', eid, 'Different logical content under one event ID')
                bad.add(eid)
            else:
                events[eid] = event
        except (LedgerValidationError, TypeError, ValueError) as exc:
            issue('invalid', eid, str(exc))
            bad.add(eid)
    for eid in bad:
        events.pop(eid, None)
    if frontier is not None:
        included, queue = set(), list(frontier)
        while queue:
            eid = queue.pop()
            if eid in included:
                continue
            included.add(eid)
            if eid in events:
                queue.extend(events[eid]['previous_events'])
            else:
                issue('pending', eid, 'Requested frontier or predecessor missing')
        events = {eid: event for eid, event in events.items() if eid in included}
    identities = {}
    for eid, event in events.items():
        claims = []
        if event['event_type'] == 'song.created':
            claims.append(('song', event['data']['song_id']))
        elif event['event_type'] == 'operation.started':
            claims.append(('run', event['data']['run_id']))
        elif event['event_type'] == 'review.recorded':
            claims.append(('review', event['data']['review_id']))
        elif event['event_type'] == 'operation.completed':
            for update in event['data']['updates']:
                claims.append(('revision', update['revision']['revision_id']))
                if update['action'] == 'create':
                    claims.append(('artifact', update['artifact_id']))
        for claim in claims:
            if claim in identities and identities[claim] != eid:
                other = identities[claim]
                issue('integrity', eid, f'Identity reused by different events: {claim[0]}/{claim[1]}')
                bad.update((eid, other))
            identities[claim] = eid
    for eid in bad:
        events.pop(eid, None)
    remaining, valid, ancestors, writes = dict(events), {}, {}, {}
    while remaining:
        progress = False
        for eid in sorted(remaining):
            event = remaining[eid]
            previous = set(event['previous_events'])
            if not previous <= valid.keys():
                continue
            progress = True
            del remaining[eid]
            closure = previous | set().union(*(ancestors[p] for p in previous))
            local_heads = _heads(closure, writes, ancestors)
            local_values = _values(local_heads, writes)
            try:
                expected = event['expected_heads']
                keys = mutation_keys(event)
                if set(expected) != set(keys):
                    raise LedgerValidationError('Expected heads must cover exactly mutated keys')
                create_keys = set()
                if event['event_type'] in ('song.created', 'operation.started', 'review.recorded'):
                    create_keys.update(keys)
                if event['event_type'] == 'operation.completed':
                    for update in event['data']['updates']:
                        create_keys.add(f'revision/{update["revision"]["revision_id"]}/provenance_notes')
                        if update['action'] == 'create':
                            create_keys.update(k for k in keys if k.startswith(f'artifact/{update["artifact_id"]}/'))
                if any(expected[key] for key in create_keys):
                    raise LedgerValidationError('Creation cannot overwrite an existing identity or initial key')
                for key, observed in expected.items():
                    if observed != local_heads.get(key, []):
                        raise LedgerValidationError(f'Expected heads do not match causal ancestor state: {key}')
                    if event['event_type'] != 'conflict.resolved' and len(observed) > 1:
                        raise LedgerValidationError(f'Ordinary mutation of conflicted key: {key}')
                _semantic(event, local_values, local_heads, valid, closure)
                if root is not None:
                    _root_paths(event, root)
                produced = event_writes(event, local_values)
                if event['event_type'] == 'conflict.resolved':
                    produced = {r['key']: writes[r['chosen_head']][r['key']] for r in event['data']['resolutions']}
                valid[eid], ancestors[eid], writes[eid] = event, closure, produced
            except PendingReference as exc:
                issue('pending', eid, str(exc))
            except (LedgerValidationError, KeyError, TypeError, ValueError) as exc:
                issue('invalid', eid, str(exc))
        if not progress:
            for eid, event in remaining.items():
                reachable, stack = set(), list(event['previous_events'])
                while stack:
                    predecessor = stack.pop()
                    if predecessor in reachable:
                        continue
                    reachable.add(predecessor)
                    if predecessor in remaining:
                        stack.extend(remaining[predecessor]['previous_events'])
                issue('invalid' if eid in reachable else 'pending', eid, 'Causal cycle' if eid in reachable else 'Missing or invalid causal predecessor')
            break
    heads = _heads(set(valid), writes, ancestors)
    values = _values(heads, writes)
    state = {'events': valid, 'heads': heads, 'values': values, 'writes': writes, 'ancestors': {k: sorted(v) for k, v in ancestors.items()}, 'issues': issues, 'conflicts': {k: v for k, v in heads.items() if len(v) > 1}, 'songs': {}, 'artifacts': {}, 'revisions': {}, 'revision_events': {}, 'runs': {}, 'reviews': {}, 'selections': {}, 'blocked_artifacts': []}
    for key, value in values.items():
        parts = key.split('/')
        if parts[0] == 'song' and len(parts) == 2:
            state['songs'][parts[1]] = {**value, 'label': values.get(key + '/label')}
        elif parts[0] == 'artifact' and parts[2] == 'identity':
            prefix = '/'.join(parts[:2])
            state['artifacts'][parts[1]] = {**value, **{name: values.get(prefix + '/' + field) for name, field in [('path', 'location'), ('label', 'label'), ('song_ids', 'song_ids'), ('withdrawn', 'withdrawn'), ('revision', 'revision')]}}
        elif parts[0] == 'run':
            state['runs'][parts[1]] = value
        elif parts[0] == 'review':
            state['reviews'][parts[1]] = value
        elif parts[0] == 'selection':
            state['selections'][key] = value
    for eid, event in valid.items():
        if event['event_type'] == 'operation.completed':
            for update in event['data']['updates']:
                rev = update['revision']
                rid = rev['revision_id']
                state['revisions'][rid] = {**rev, 'artifact_id': update['artifact_id'], 'available': None}
                state['revision_events'][rid] = eid
                if root is not None:
                    available = True
                    for file in rev['files']:
                        relative = rev['history_path'] + '/' + file['path']
                        try:
                            portable_path(relative, root)
                            path = root / relative
                            if not path.is_file():
                                issue('unavailable', eid, f'Missing history file: {relative}')
                                available = False
                            elif path.stat().st_size != file['size_bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != file['sha256']:
                                issue('integrity', eid, f'History hash mismatch: {relative}')
                                available = False
                        except (OSError, LedgerValidationError) as exc:
                            issue('integrity', eid, str(exc))
                            available = False
                    directory = root / rev['history_path']
                    try:
                        if directory.exists() and not directory.is_symlink():
                            expected_files = {file['path'] for file in rev['files']}
                            for path in directory.rglob('*'):
                                relative = path.relative_to(directory).as_posix()
                                if path.is_symlink() or (path.is_file() and relative not in expected_files):
                                    issue('integrity', eid, f'Unexpected history entry: {rev["history_path"]}/{relative}')
                                    available = False
                    except OSError as exc:
                        issue('unavailable', eid, str(exc))
                        available = False
                    state['revisions'][rid]['available'] = available
    _combined_locations(state, root)
    state['complete'] = not issues and not state['conflicts']
    state['frontier'] = sorted(eid for eid in valid if not any(eid in ancestor for ancestor in ancestors.values()))
    return state


def _combined_locations(state: dict, root: Path | None) -> None:
    artifacts, blocked = state['artifacts'], set()
    locations = {}
    for aid, artifact in artifacts.items():
        path = artifact['path']
        if path is None:
            blocked.add(aid)
            continue
        try:
            portable_path(path, root)
        except LedgerValidationError as exc:
            state['issues'].append({'status': 'invalid', 'event_id': None, 'reason': str(exc)})
            blocked.add(aid)
        folded = path.casefold()
        if folded in locations:
            other = locations[folded]
            blocked.update((aid, other))
            state['issues'].append({'status': 'conflict', 'event_id': None, 'reason': f'Casefold artifact location collision: {aid}, {other}'})
        locations[folded] = aid
        parent = artifact['storage_parent']
        if parent and (parent not in artifacts or artifacts[parent]['path'] is None or str(PurePosixPath(path).parent) != artifacts[parent]['path']):
            blocked.update((aid, parent))
            # A concurrent new descendant must block the complete structural move, not half its view.
            for eid in state['heads'].get(f'artifact/{parent}/location', []):
                blocked.update(key.split('/')[1] for key in state['writes'][eid]
                               if key.startswith('artifact/') and key.endswith('/location'))
            state['issues'].append({'status': 'conflict', 'event_id': None, 'reason': f'Inconsistent storage subtree: {aid}'})
    for aid, artifact in artifacts.items():
        ref = artifact['revision']
        if ref is None:
            blocked.add(aid)
            continue
        revision = state['revisions'][ref]
        if artifact['path']:
            for file in revision['files']:
                owned = artifact['path'] + '/' + file['path']
                for other, record in artifacts.items():
                    if other != aid and record['path'] and record['path'].casefold().startswith(artifact['path'].casefold() + '/') and (owned.casefold() == record['path'].casefold() or owned.casefold().startswith(record['path'].casefold() + '/') or record['path'].casefold().startswith(owned.casefold() + '/')):
                        blocked.update((aid, other))
                        state['issues'].append({'status': 'conflict', 'event_id': None, 'reason': f'Owned file overlaps child artifact: {owned}'})
    changed = True
    while changed:
        old = set(blocked)
        blocked.update(aid for aid, record in artifacts.items() if record['storage_parent'] in blocked)
        changed = old != blocked
    state['blocked_artifacts'] = sorted(blocked)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LedgerValidationError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def replay(root: Path, frontier: list[str] | None = None) -> dict:
    root = Path(root)
    records, read_issues = [], []
    ledger = root / 'ledger'
    if ledger.is_symlink():
        return replay_events([], root=root) | {'complete': False, 'issues': [{'status': 'integrity', 'event_id': None, 'reason': 'Ledger directory is a symlink'}]}
    for path in sorted(ledger.glob('*.json')):
        try:
            if path.is_symlink():
                raise LedgerValidationError('Event file is a symlink')
            event = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_object_pairs, parse_constant=lambda v: (_ for _ in ()).throw(LedgerValidationError(f'Non-finite JSON value {v}')))
            if not isinstance(event, dict):
                raise LedgerValidationError('Event must be a JSON object')
            records.append(event)
        except (OSError, ValueError) as exc:
            read_issues.append({'status': 'invalid', 'event_id': path.stem, 'reason': str(exc)})
    state = replay_events(records, root, frontier)
    state['issues'].extend(read_issues)
    state['complete'] = state['complete'] and not read_issues
    return state
