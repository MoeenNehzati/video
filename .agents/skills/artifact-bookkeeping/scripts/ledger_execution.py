"""Prepare and execute ordinary commands using immutable declared dependencies."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from artifact_ledger import Ledger, LedgerError, atomic, encoded, new_id, read_json, resource_file, sha
from ledger_python import _captured_code, capture_python_runtime, PYTHON_RESOURCE_KEY
from ledger_tools import tool_argv, validate_tools, native_library_paths, conversion_environment
from ledger_replay import portable_path
from scripts.project_runtime import load_project, data_path
from scripts.read_config import ROOT


TOKEN = re.compile(r'^\{(input|output|resource|code|document|layout|scratch|tool):([^{}]+)\}$')
CHILD = '''import json, runpy, sys
from pathlib import Path
r=json.load(sys.stdin)
sys.path[:0]=[r['code'], *r['packages']]
sys.path.insert(0,str(Path(r['argv'][0]).parent))
sys.argv=r['argv']
runpy.run_path(sys.argv[0],run_name='__main__')
'''


def pointer(document, value):
    if not isinstance(value, str) or not value.startswith('/'):
        raise LedgerError('JSON binding requires an absolute JSON pointer')
    parts = [part.replace('~1', '/').replace('~0', '~') for part in value[1:].split('/')]
    current = document
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    key = int(parts[-1]) if isinstance(current, list) else parts[-1]
    return current, key


def source(ledger, dep, filename=None):
    record = ledger.resolve(dep['artifact_id'], dep['revision_id'])
    directory = ledger.path(record['history_path'])
    if filename is None:
        return directory
    if filename not in dep['files']:
        raise LedgerError('Binding must select a declared input file')
    return directory / filename


def input_token(ledger, request, token):
    match = TOKEN.fullmatch(token)
    if match and match[1] == 'document':
        dep = request['inputs'][request['documents'][match[2]]['input']]
        if len(dep['files']) != 1:
            raise LedgerError('Document layout entry must name one file')
        return source(ledger, dep, dep['files'][0])
    if not match or match[1] != 'input':
        raise LedgerError('Expected an exact input binding')
    name, _, relative = match[2].partition('/')
    dep = request['inputs'][name]
    filename = relative or (dep['files'][0] if len(dep['files']) == 1 else '')
    return source(ledger, dep, filename)


def check_request(ledger, request):
    required = {'operation', 'skill', 'declaration', 'code', 'inputs', 'outputs', 'command'}
    optional = {'resources', 'packages', 'settings', 'config', 'environment', 'documents',
                'layouts', 'relations', 'publish_json', 'publish_text', 'publish_hashes', 'collect', 'path_aliases', 'handoff'}
    if not isinstance(request, dict) or not required <= request.keys() or request.keys() - required - optional:
        raise LedgerError('Operation has missing or unknown fields')
    if not request['outputs'] or not isinstance(request['inputs'], dict):
        raise LedgerError('Declare named inputs and at least one output')
    for group in ('inputs', 'outputs', 'resources', 'documents', 'layouts'):
        for name in request.get(group, {}):
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', name):
                raise LedgerError('Binding names must be simple identifiers')
    declaration = resource_file(ROOT, request['declaration'])
    if not declaration.is_file() or declaration.name != 'SKILL.md':
        raise LedgerError('Record the production SKILL.md declaration source')
    code = [resource_file(ROOT, name) for name in request['code']]
    if any(not path.is_file() for path in code):
        raise LedgerError('Capture every executed project script/helper')
    if request['command'] is not None and (not isinstance(request['command'], list) or not request['command']
            or any(not isinstance(arg, str) or not arg for arg in request['command'])):
        raise LedgerError('Command must be a nonempty argument vector, or null for a handoff')
    if request['command'] is None and not request.get('handoff'):
        raise LedgerError('Manual/external preparation requires a handoff description')
    for dep in request['inputs'].values():
        if set(dep) != {'artifact_id', 'revision_id', 'files', 'purpose'}:
            raise LedgerError('Inputs must pin exact revision files and their purpose')
        ledger._dependency(dep)
    for relation in request.get('relations', []):
        if set(relation) != {'input', 'depends_on'}:
            raise LedgerError('Relation requires input and depends_on binding names')
        parent, target = (request['inputs'][relation[key]] for key in ('input', 'depends_on'))
        if not any(dep['artifact_id'] == target['artifact_id'] and dep['revision_id'] == target['revision_id']
                   and set(target['files']) <= set(dep['files'])
                   for dep in ledger.inputs(parent['artifact_id'], parent['revision_id'])):
            raise LedgerError('Declared input relationship is not present in exact provenance')
    for ref in request.get('resources', {}).values():
        ledger._descriptor(ref)
    for value in request.get('config', {}).get('resources', {}).values():
        if not isinstance(value, str) or not TOKEN.fullmatch(value) or not value.startswith('{resource:'):
            raise LedgerError('Configured resource paths must use pinned resource bindings')
    for value in request.get('config', {}).get('tools', {}).values():
        if not isinstance(value, dict) or not isinstance(value.get('command'), str) or not value['command'].startswith('{tool:'):
            raise LedgerError('Configured commands must use pinned tool bindings')
    for arg in request['command'] or []:
        if arg == '--config-root' or arg.startswith('--config-root=') or Path(arg).is_absolute():
            raise LedgerError('Command paths/configuration must use prepared bindings')
    for layout in request.get('layouts', {}).values():
        for filename, token in layout.items():
            portable_path(filename)
            input_token(ledger, request, token)
    for document in request.get('documents', {}).values():
        dep = request['inputs'][document['input']]
        if len(dep['files']) != 1:
            raise LedgerError('JSON document input must select one file')
        original = read_json(source(ledger, dep, dep['files'][0]))
        for location, token in document['bindings'].items():
            container, key = pointer(original, location)
            old = container[key]
            match = TOKEN.fullmatch(token)
            if not match or match[1] not in {'input', 'layout', 'resource'}:
                raise LedgerError('Document paths must bind exact inputs, layouts or resources')
            kind, binding = match.groups()
            name, _, relative = binding.partition('/')
            if kind == 'input':
                supplied = data_path(ledger.config, old, must_exist=True)
                if sha(supplied) != sha(input_token(ledger, request, token)):
                    raise LedgerError('Indirect input differs from its exact declared revision')
            elif kind == 'layout':
                if relative:
                    raise LedgerError('Document directory binding must name the entire layout')
                for filename, source_token in request['layouts'][name].items():
                    supplied = data_path(ledger.config, str(Path(old) / filename), must_exist=True)
                    if sha(supplied) != sha(input_token(ledger, request, source_token)):
                        raise LedgerError('Indirect layout differs from its declared revision')
            else:
                descriptor = ledger._descriptor(request['resources'][name])
                installation = ledger._resource_installation(descriptor['config_key'])
                expected = resource_file(installation, relative) if relative else installation
                if Path(old).resolve() != expected.resolve():
                    raise LedgerError('Indirect resource differs from the configured descriptor')
    return code, declaration


def prepare(ledger, request):
    """Persist a generic operation; no per-skill adapters or inventory lookup."""
    request = copy.deepcopy(request)
    code, declaration = check_request(ledger, request)
    outputs = {}
    for name, spec in request['outputs'].items():
        spec = copy.deepcopy(spec)
        spec['artifact_id'] = spec['base']['artifact_id'] if spec.get('action') == 'revise' else new_id()
        spec['revision_id'] = new_id()
        outputs[name] = spec
    used = set()
    for spec in outputs.values():
        dependencies = []
        for item in spec['dependencies']:
            if isinstance(item, str):
                dependencies.append(request['inputs'][item])
                used.add(item)
            elif isinstance(item, dict) and set(item) == {'output', 'files', 'purpose'}:
                target = outputs[item['output']]
                dependencies.append({key: target[key] for key in ('artifact_id', 'revision_id')} |
                                    {'files': item['files'], 'purpose': item['purpose']})
            else:
                raise LedgerError('Dependencies must name inputs or exact sibling output files')
        spec['dependencies'] = dependencies
        if isinstance(spec.get('storage_parent'), dict):
            spec['storage_parent'] = outputs[spec['storage_parent']['output']]['artifact_id']
    if used != set(request['inputs']):
        raise LedgerError('Every consumed input must belong to an output dependency contract')
    request['output_order'] = list(outputs)
    resources = dict(request.get('resources', {}))
    if request.get('packages'):
        resources['_python'] = capture_python_runtime(ledger, request['packages'])
    for name, ref in resources.items():
        descriptor = ledger._descriptor(ref)
        if (descriptor.get('source') or {}).get('execution'):
            validate_tools(ledger, {name: ref}, [name])
    request['resources'] = resources
    request['platform_environment'] = {key: value for key, value in os.environ.items()
                                       if key in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'LANG', 'LC_ALL', 'LC_CTYPE'}}
    request['runtime'] = {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()}
    producer = ledger.producer(request['operation'], request['skill'], request['declaration'],
                               request['command'], {'command_operation': request}, [*code, declaration])
    producer['resources'] = list(resources.values())
    producer['unknowns']['platform'] = 'Interpreter, standard library and OS are boundaries, not a hermetic machine'
    intent = ledger.prepare(request['operation'], list(outputs.values()), producer)
    try:
        plan = build_plan(ledger, intent)
        atomic(ledger.path(intent['workspace'] + '/execution-plan.json'), encoded(plan))
    except Exception as exc:
        ledger.fail(intent['run_id'], 'preparation-failed', str(exc))
        raise
    return intent


def build_plan(ledger, intent):
    request = intent['producer']['settings']['command_operation']
    work = ledger.path(intent['workspace'])
    code = ledger._resource_cache() / ledger.host / intent['run_id'] / 'command-code'
    expected = _captured_code(ledger, intent, code)
    resources = ledger.resource_paths(intent['run_id'])
    bindings, published = {}, {}
    for name, dep in request['inputs'].items():
        slot = next(slot for slot in intent['input_slots'] if slot['artifact_id'] == dep['artifact_id'] and slot['revision_id'] == dep['revision_id'])
        directory = work / slot['slot']
        bindings['input:' + name] = str(directory / dep['files'][0]) if len(dep['files']) == 1 else str(directory)
        for filename in dep['files']:
            bindings['input:' + name + '/' + filename] = str(directory / filename)
            published[str(directory / filename)] = str(source(ledger, dep, filename))
        published[str(directory)] = str(source(ledger, dep))
    for name, spec in zip(request['output_order'], intent['outputs']):
        bindings['output:' + name] = str(work / spec['output_slot'])
        published[str(work / spec['output_slot'])] = str(ledger.path(f'history/{spec["artifact_id"]}/{spec["revision_id"]}'))
    packages = []
    for name, ref in request.get('resources', {}).items():
        slot = next(slot for slot in intent['resource_slots'] if slot['revision_id'] == ref['revision_id'])
        directory = resources[slot['slot']]
        descriptor = ledger._descriptor(ref)
        bindings['resource:' + name] = str(directory)
        if descriptor['config_key'] == PYTHON_RESOURCE_KEY:
            packages.append(str(directory))
        execution = (descriptor.get('source') or {}).get('execution')
        if execution and execution['mode'] != 'dynamic-library':
            bindings['tool:' + name] = tool_argv(ledger, intent['run_id'], ref)
    bindings['code:'] = str(code)
    bindings['scratch:'] = str(work / 'scratch')
    for name in request.get('documents', {}):
        bindings['document:' + name] = str(work / 'scratch' / ('document-' + name + '.json'))
    for name in request.get('layouts', {}):
        bindings['layout:' + name] = str(work / 'scratch' / ('layout-' + name))

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        if not isinstance(value, str):
            return value
        if value == '{python}':
            return sys.executable
        match = TOKEN.fullmatch(value)
        if not match:
            if '{' in value or '}' in value:
                raise LedgerError('Bindings must occupy an entire argument/value')
            return value
        kind, name = match.groups()
        key = kind + ':' + name
        if key in bindings:
            return bindings[key]
        head, _, relative = name.partition('/')
        base = bindings.get(kind + ':' + ('' if kind in {'code', 'scratch'} else head))
        suffix = name if kind in {'code', 'scratch'} else relative
        if base is None or not suffix:
            raise LedgerError('Unknown path binding: ' + value)
        if kind != 'code':
            portable_path(suffix)
        path = resource_file(base, suffix)
        if kind == 'code' and suffix not in expected:
            raise LedgerError('Command references uncaptured code')
        if kind == 'input':
            raise LedgerError('Command references an undeclared input file')
        if kind == 'resource':
            descriptor = ledger._descriptor(request['resources'][head])
            if suffix not in {f['path'] for f in descriptor['files']} and not any(f['path'].startswith(suffix + '/') for f in descriptor['files']):
                raise LedgerError('Command references an undeclared resource file')
        if kind == 'output':
            spec = intent['outputs'][request['output_order'].index(head)]
            if 'files' in spec['contract'] and suffix not in {f['path'] for f in spec['contract']['files']} and not any(f['path'].startswith(suffix + '/') for f in spec['contract']['files']):
                raise LedgerError('Command references an undeclared output file')
        return str(path)

    controlled = {}
    for name, document in request.get('documents', {}).items():
        src = Path(bindings['input:' + document['input']])
        payload = read_json(src)
        for location, token in document['bindings'].items():
            container, key = pointer(payload, location)
            container[key] = expand(token)
        target = Path(bindings['document:' + name])
        atomic(target, encoded(payload))
        controlled[str(target)] = sha(target)
        published[str(target)] = published[str(src)]
    for name, layout in request.get('layouts', {}).items():
        destination = Path(bindings['layout:' + name])
        roots = set()
        for filename, token in layout.items():
            src = Path(expand(token))
            target = resource_file(destination, filename)
            atomic(target, src.read_bytes())
            controlled[str(target)] = sha(target)
            published[str(target)] = published[str(src)]
            original = Path(published[str(src)])
            if original.as_posix().endswith('/' + filename):
                roots.add(str(original)[:-len(filename)-1])
            else:
                roots.add(None)
        if len(roots) == 1 and None not in roots:
            published[str(destination)] = roots.pop()
    config = expand(request.get('config', {}))
    config['paths'] = {'data_root': str(ledger.root)}
    profile = work / 'scratch' / 'profile'
    profile.mkdir(parents=True, exist_ok=True)
    environment = dict(request['platform_environment'], PATH='')
    environment.update({key: str(profile) for key in ('HOME', 'USERPROFILE', 'APPDATA',
                        'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_RUNTIME_DIR',
                        'TMPDIR', 'TEMP', 'TMP')})
    supplied = expand(request.get('environment', {}))
    if any(key.startswith(('PYTHON', 'LD_', 'DYLD_')) or key in {'PATH', 'MUSIC_VIDEO_CONFIG_JSON', 'MUSIC_VIDEO_CONFIG_ROOT', 'MUSIC_VIDEO_DATA_ROOT'} for key in supplied):
        raise LedgerError('Environment cannot override isolation controls')
    environment.update(supplied)
    environment.update(MUSIC_VIDEO_CONFIG_JSON=json.dumps(config, sort_keys=True), MUSIC_VIDEO_DATA_ROOT=str(ledger.root),
                       MUSIC_VIDEO_CONFIG_ROOT=str(code), PYTHONDONTWRITEBYTECODE='1',
                       MPLCONFIGDIR=str(work / 'scratch' / 'profile'))
    native = []
    for ref in request.get('resources', {}).values():
        descriptor = ledger._descriptor(ref)
        if (descriptor.get('source') or {}).get('conversion'):
            slot = next(slot for slot in intent['resource_slots'] if slot['revision_id'] == ref['revision_id'])
            environment.update(conversion_environment(resources[slot['slot']], descriptor))
        if (descriptor.get('source') or {}).get('execution', {}).get('mode') == 'dynamic-library':
            native.extend(native_library_paths(ledger, intent['run_id'], ref))
    if native:
        environment['LD_LIBRARY_PATH'] = os.pathsep.join(dict.fromkeys(native))
    command = None
    if request['command'] is not None:
        command = []
        for item in request['command']:
            value = expand(item)
            command.extend(value if isinstance(value, list) else [value])
        if request['command'][0] == '{python}':
            if len(command) < 2 or not Path(command[1]).is_relative_to(code):
                raise LedgerError('Python command must execute a captured project script')
        elif not request['command'][0].startswith('{tool:'):
            raise LedgerError('Command must start with {python} or a pinned {tool:name}')
    targets = [expand(token) for token in request.get('publish_json', [])]
    text_targets = [expand(token) for token in request.get('publish_text', [])]
    if any(not Path(path).is_relative_to(work / 'outputs') for path in targets + text_targets) or set(targets) & set(text_targets):
        raise LedgerError('Publication rewriting requires distinct declared output files')
    hashes = []
    for item in request.get('publish_hashes', []):
        if set(item) != {'file', 'path', 'sha256'}:
            raise LedgerError('Published hash binding needs file, path and sha256 JSON pointers')
        filename = expand(item['file'])
        if filename not in targets:
            raise LedgerError('Hash bindings must name a declared rewritten JSON output')
        hashes.append(dict(item, file=filename))
    collection = {}
    for target_token, source_token in request.get('collect', {}).items():
        target, origin = expand(target_token), expand(source_token)
        if not target_token.startswith('{output:') or not source_token.startswith(('{scratch:', '{output:')):
            raise LedgerError('Collection copies generated scratch/output files into declared outputs')
        if target == origin:
            raise LedgerError('Collection source and destination must differ')
        collection[target] = origin
    for source_token, target_token in request.get('path_aliases', {}).items():
        if not source_token.startswith('{scratch:') or not target_token.startswith('{output:'):
            raise LedgerError('Published aliases map generated scratch paths into collected output bundles')
        origin, target = expand(source_token), expand(target_token)
        if not any(dst.startswith(target + '/') and src.startswith(origin + '/') and dst[len(target):] == src[len(origin):]
                   for dst, src in collection.items()):
            raise LedgerError('Published directory alias requires matching collected files')
        published[origin] = rewrite(target, published)
    return {'run_id': intent['run_id'], 'command': command, 'python': request['command'] is not None and request['command'][0] == '{python}',
            'code': str(code), 'code_hashes': expected, 'packages': packages, 'controlled': controlled,
            'bindings': bindings, 'published_paths': published, 'publish_json': targets, 'publish_text': text_targets, 'publish_hashes': hashes,
            'environment': environment, 'config': config, 'collect': collection, 'cwd': str(work / 'scratch')}


def status(ledger, run_id):
    intent, _ = ledger._intent(run_id)
    work = ledger.path(intent['workspace'])
    return {'intent': intent, 'plan': read_json(work / 'execution-plan.json'),
            'execution': read_json(work / 'execution.json') if (work / 'execution.json').exists() else None,
            'receipt': read_json(work / 'result.json') if (work / 'result.json').exists() else None,
            'ledger_status': ledger.state()['runs'][run_id]['status']}


def verify_plan(ledger, intent, plan):
    ledger._verify_inputs(intent)
    if plan != build_plan(ledger, intent):
        raise LedgerError('Execution plan differs from the immutable operation')
    if plan['code_hashes'] != {item['path']: item['sha256'] for item in intent['producer']['code']['files']}:
        raise LedgerError('Execution code manifest differs from captured source')
    directory = Path(plan['code'])
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(plan['code_hashes']):
        raise LedgerError('Captured execution tree gained or lost files')
    for name, digest in plan['code_hashes'].items():
        if sha(resource_file(directory, name)) != digest:
            raise LedgerError('Executed code snapshot changed')
    for name, digest in plan['controlled'].items():
        if sha(Path(name)) != digest:
            raise LedgerError('Prepared execution document/layout changed')


def execute(ledger, run_id):
    """Run once. An absent result after launch is uncertainty, never a retry."""
    state = status(ledger, run_id)
    intent, plan = state['intent'], state['plan']
    if plan['command'] is None:
        raise LedgerError('This operation is a handoff; inspect allocated bindings')
    if state['ledger_status'] != 'started':
        raise LedgerError('Run is terminal or conflicted')
    verify_plan(ledger, intent, plan)
    work = ledger.path(intent['workspace'])
    with ledger.lock():
        marker = work / 'execution.json'
        if marker.exists():
            raise LedgerError('Execution already attempted; reconcile or recover without rerunning')
        atomic(marker, encoded({'run_id': run_id, 'plan_sha256': sha(work / 'execution-plan.json'), 'command': plan['command']}))
    try:
        command, payload = plan['command'], None
        if plan['python']:
            payload = json.dumps({'argv': command[1:], 'code': plan['code'], 'packages': plan['packages']})
            command = [sys.executable, '-I', '-S', '-B', '-c', CHILD]
        result = subprocess.run(command, input=payload, text=True, capture_output=True,
                                cwd=plan['cwd'], env=plan['environment'])
        atomic(work / 'stdout.txt', result.stdout.encode('utf-8'))
        atomic(work / 'stderr.txt', result.stderr.encode('utf-8'))
        verify_plan(ledger, intent, plan)
        if result.returncode:
            atomic(work / 'result.json', encoded({'run_id': run_id, 'exit_code': result.returncode}))
            raise LedgerError(f'Command failed ({result.returncode}): {result.stderr.strip()}')
        for target, origin in plan['collect'].items():
            src = ledger.path(Path(origin).relative_to(ledger.root).as_posix())
            dst = ledger.path(Path(target).relative_to(ledger.root).as_posix())
            if not src.is_file() or dst.exists():
                raise LedgerError('Collected source is missing or destination already exists')
            dst.parent.mkdir(parents=True, exist_ok=True)
            with src.open('rb') as incoming, dst.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
        atomic(work / 'result.json', encoded({'run_id': run_id, 'exit_code': 0, 'outputs': output_hashes(ledger, intent),
                                             'publication_files': {name: Path(name).read_bytes().decode('utf-8') for name in plan['publish_json'] + plan['publish_text']},
                                             'stdout_sha256': sha(work / 'stdout.txt'), 'stderr_sha256': sha(work / 'stderr.txt')}))
    except Exception as exc:
        ledger.fail(run_id, 'execution-failed', str(exc))
        raise
    return status(ledger, run_id)


def rewrite(value, replacements):
    if isinstance(value, dict):
        return {key: rewrite(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite(item, replacements) for item in value]
    if isinstance(value, str):
        for src in sorted(replacements, key=len, reverse=True):
            if value == src or value.startswith(src + '/'):
                return replacements[src] + value[len(src):]
    return value


def output_hashes(ledger, intent):
    result = {}
    for output in intent['outputs']:
        root = ledger.path(intent['workspace'] + '/' + output['output_slot'])
        for file in ledger._manifest(root, output['contract']):
            result[str(root / file['path'])] = file['sha256']
    return result


def finish(ledger, run_id):
    state = status(ledger, run_id)
    if state['ledger_status'] == 'completed':
        return ledger.recover(run_id)
    intent, plan = state['intent'], state['plan']
    if state['ledger_status'] != 'started':
        raise LedgerError('Run is terminal or conflicted')
    if state['receipt'] is None or state['receipt'].get('exit_code') != 0:
        raise LedgerError('No witnessed successful result; reconcile uncertainty without re-execution')
    verify_plan(ledger, intent, plan)
    work = ledger.path(intent['workspace'])
    transform_path = work / 'publication-transforms.json'
    saved_transforms = read_json(transform_path) if transform_path.exists() else None
    try:
        current = output_hashes(ledger, intent)
    except Exception as exc:
        ledger.fail(run_id, 'output-contract-failed', str(exc))
        raise
    expected = state['receipt']['outputs']
    transforms = {}
    originals = state['receipt']['publication_files']
    if set(originals) != set(plan['publish_json'] + plan['publish_text']):
        raise LedgerError('Publication receipt differs from the declared rewritten outputs')
    for filename in plan['publish_json'] + plan['publish_text']:
        path = Path(filename)
        original = originals[filename].encode('utf-8')
        if hashlib.sha256(original).hexdigest() != expected.get(filename):
            raise LedgerError('Publication receipt bytes differ from the successful output hash')
        if filename in plan['publish_text']:
            text = original.decode('utf-8')
            for src in sorted(plan['published_paths'], key=len, reverse=True):
                text = text.replace(src, plan['published_paths'][src])
            rewritten = text.encode('utf-8')
            if original != rewritten:
                transforms[str(path)] = {'content': text, 'sha256': hashlib.sha256(rewritten).hexdigest()}
            continue
        payload = rewrite(json.loads(original), plan['published_paths'])
        for item in plan['publish_hashes']:
            if item['file'] != filename:
                continue
            container, key = pointer(payload, item['path'])
            target = Path(container[key])
            if not target.is_relative_to(ledger.root / 'history'):
                raise LedgerError('Published hash reference must resolve to immutable history')
            if not target.is_file():
                raise LedgerError('Complete the referenced dependency before publishing its hash')
            destination, field = pointer(payload, item['sha256'])
            destination[field] = sha(target)
        rewritten = encoded(payload)
        if original != rewritten:
            transforms[str(path)] = {'content': rewritten.decode('utf-8'), 'sha256': hashlib.sha256(rewritten).hexdigest()}
    if saved_transforms is not None and saved_transforms != transforms:
        raise LedgerError('Publication transform journal differs from the witnessed outputs and immutable operation')
    if set(current) != set(expected) or any(digest not in {
            expected[name], (saved_transforms or {}).get(name, {}).get('sha256')} for name, digest in current.items()):
        raise LedgerError('Successful output bytes changed; preserve edits and reconcile before publication')
    atomic(transform_path, encoded(transforms))
    for filename, item in transforms.items():
        atomic(Path(filename), item['content'].encode('utf-8'), replace=True)
    return ledger.finalize(run_id)


def handoff(ledger, run_id, receipt=None):
    """Mark handoff before action, then attach observed outcome evidence."""
    state = status(ledger, run_id)
    if state['plan']['command'] is not None or state['ledger_status'] != 'started':
        raise LedgerError('A started manual/external operation is required')
    work = ledger.path(state['intent']['workspace'])
    verify_plan(ledger, state['intent'], state['plan'])
    with ledger.lock():
        if receipt is None:
            if (work / 'execution.json').exists():
                raise LedgerError('Handoff already started; reconcile its outcome, never repeat blindly')
            atomic(work / 'execution.json', encoded({'run_id': run_id, 'handoff': state['intent']['producer']['settings']['command_operation']['handoff']}))
        else:
            if not (work / 'execution.json').exists() or not isinstance(receipt, dict) or not receipt.get('evidence'):
                raise LedgerError('Receipt requires a started handoff and actual outcome evidence')
            atomic(work / 'result.json', encoded({'run_id': run_id, 'exit_code': 0,
                                                'outputs': output_hashes(ledger, state['intent']),
                                                'publication_files': {name: Path(name).read_bytes().decode('utf-8') for name in state['plan']['publish_json'] + state['plan']['publish_text']},
                                                'external_receipt': receipt}))
    return status(ledger, run_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-root', type=Path)
    parser.add_argument('action', choices=['prepare', 'execute', 'finish', 'status', 'handoff', 'receipt'])
    parser.add_argument('value', help='Request JSON for prepare, otherwise run ID')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv)
    ledger = Ledger(load_project(args.config_root))
    if args.action == 'prepare':
        result = prepare(ledger, read_json(args.value))
    elif args.action in {'handoff', 'receipt'}:
        result = handoff(ledger, args.value, read_json(args.receipt) if args.action == 'receipt' and args.receipt else None)
    else:
        result = {'execute': execute, 'finish': finish, 'status': status}[args.action](ledger, args.value)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
