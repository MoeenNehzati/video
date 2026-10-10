"""Resource-backed execution for reviewed tools and explicit native loader closures."""
from pathlib import Path
import os
import re
import struct
import sys

from artifact_ledger import LedgerError, resource_file


def resource_argument(directory, value, manifest):
    """Expand only an explicitly declared private resource file or directory."""
    if value == '{resource}':
        return str(directory)
    prefix, marker, name = value.partition('{resource}/')
    if not marker or '{' in name or '}' in name or (prefix and not prefix.endswith('=')):
        raise LedgerError('Invalid resource-relative tool argument')
    path = resource_file(directory, name)
    if name not in manifest and not any(file.startswith(name.rstrip('/') + '/') for file in manifest):
        raise LedgerError('Tool argument is outside the resource manifest')
    return prefix + str(path)


def elf_dependencies(path):
    """Read loader and DT_NEEDED without executing an untrusted binary."""
    blob = path.read_bytes()
    if blob[:4] != b'\x7fELF' or len(blob) < 64 or blob[4] not in (1, 2) or blob[5] not in (1, 2):
        raise LedgerError('Unsupported or malformed ELF resource')
    endian = '<' if blob[5] == 1 else '>'
    wide = blob[4] == 2
    def unpack(fmt, offset):
        try:
            return struct.unpack_from(endian + fmt, blob, offset)
        except struct.error as exc:
            raise LedgerError('Truncated ELF resource') from exc
    offset = unpack('Q' if wide else 'I', 32 if wide else 28)[0]
    width, count = unpack('HH', 54 if wide else 42)
    if width < (56 if wide else 32) or offset + width * count > len(blob):
        raise LedgerError('Invalid ELF program headers')
    loads, dynamic, interpreter = [], None, None
    for index in range(count):
        values = unpack('IIQQQQQQ' if wide else 'IIIIIIII', offset + index * width)
        kind = values[0]
        start, address, size = (values[2], values[3], values[5]) if wide else (values[1], values[2], values[4])
        if start + size > len(blob):
            raise LedgerError('Truncated ELF segment')
        if kind == 1:
            loads.append((address, start, size))
        elif kind == 2:
            dynamic = (start, size)
        elif kind == 3:
            interpreter = blob[start:start + size].rstrip(b'\0').decode('utf-8')
    if dynamic is None:
        return {'loader': interpreter, 'needed': [], 'search_paths': [], 'dynamic': False}
    tags = {}
    step = 16 if wide else 8
    for position in range(dynamic[0], sum(dynamic), step):
        tag, value = unpack('qQ' if wide else 'iI', position)
        if tag == 0:
            break
        tags.setdefault(tag, []).append(value)
    address = tags.get(5, [None])[0]
    tables = [(start + address - base, size - (address - base)) for base, start, size in loads
              if address is not None and base <= address < base + size]
    if any(tags.get(tag) for tag in (1, 15, 29)) and len(tables) != 1:
        raise LedgerError('ELF dynamic string table is missing or ambiguous')
    def string(item):
        start, size = tables[0]
        end = blob.find(b'\0', start + item, start + size) if item < size else -1
        if end < 0:
            raise LedgerError('Invalid ELF dependency string')
        return blob[start + item:end].decode('utf-8')
    needed = []
    for item in tags.get(1, []):
        name = string(item)
        if not name or '/' in name or '\\' in name:
            raise LedgerError('ELF dependencies must use portable library basenames')
        needed.append(name)
    search = [folder for tag in (15, 29) for item in tags.get(tag, []) for folder in string(item).split(':')]
    return {'loader': interpreter, 'needed': needed, 'search_paths': search, 'dynamic': True}


def validate_execution(directory, descriptor):
    source = descriptor.get('source')
    execution = source.get('execution') if isinstance(source, dict) else None
    if not isinstance(execution, dict):
        raise LedgerError('Tool descriptor source.execution is required')
    mode = execution.get('mode')
    native = mode in {'dynamic-elf', 'dynamic-library'}
    fields = {'entrypoint', 'mode'} | ({'library_dirs'} if native else set()) | ({'loader'} if mode == 'dynamic-elf' else set())
    if 'arguments' in execution:
        fields.add('arguments')
    if set(execution) != fields:
        raise LedgerError('Tool execution descriptor has missing or unknown fields')
    arguments = execution.get('arguments', [])
    manifest = {file['path'] for file in descriptor['files']}
    if (not isinstance(arguments, list) or any(not isinstance(arg, str) or not arg
            or not re.fullmatch(r'[A-Za-z0-9_.=+/{}/-]+', arg) or arg.startswith('/')
            or '..' in arg.split('=', 1)[-1].split('/') or '=/' in arg for arg in arguments)
            or (mode == 'dynamic-library' and arguments)):
        raise LedgerError('Tool prefix arguments must be portable flags/module names, not external paths')
    for arg in arguments:
        if '{' in arg or '}' in arg:
            resource_argument(directory, arg, manifest)
    if execution['entrypoint'] not in manifest:
        raise LedgerError('Tool entrypoint is absent from its resource manifest')
    entrypoint = resource_file(directory, execution['entrypoint'])
    if not native:
        if executable_mode(entrypoint) != mode:
            raise LedgerError('Resource execution mode differs from executable format')
        return
    if mode == 'dynamic-elf' and execution['loader'] not in manifest:
        raise LedgerError('Native loader is absent from resource manifest')
    directories = execution['library_dirs']
    if not isinstance(directories, list) or not directories or any(not isinstance(value, str) for value in directories) or len(set(directories)) != len(directories):
        raise LedgerError('Native tool needs explicit unique library directories')
    for folder in directories:
        if folder != '.':
            resource_file(directory, folder)
    pending, visited = [execution['entrypoint']], set()
    if mode == 'dynamic-elf':
        pending.append(execution['loader'])
    # Runtime-loaded libraries need the same closure checks as direct dependencies.
    for name in manifest:
        with resource_file(directory, name).open('rb') as stream:
            if stream.read(4) == b'\x7fELF':
                pending.append(name)
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        metadata = elf_dependencies(resource_file(directory, name))
        for folder in metadata['search_paths']:
            folder = folder.replace('${ORIGIN}', '$ORIGIN')
            if not (folder == '$ORIGIN' or folder.startswith('$ORIGIN/')) or '$' in folder[7:]:
                raise LedgerError('Native RPATH/RUNPATH must remain relative to its snapshot origin')
            target = (resource_file(directory, name).parent / folder[7:].lstrip('/')).resolve()
            if not target.is_relative_to(Path(directory).resolve()):
                raise LedgerError('Native RPATH/RUNPATH escapes the private resource snapshot')
        for needed in metadata['needed']:
            matches = [needed if folder == '.' else folder + '/' + needed for folder in directories]
            matches = [value for value in matches if value in manifest]
            if len(matches) != 1:
                raise LedgerError(f'Native resource dependency missing or ambiguous: {needed}')
            pending.append(matches[0])
    if not elf_dependencies(entrypoint)['dynamic']:
        raise LedgerError('Declared dynamic tool has no dynamic loader metadata')


def executable_mode(path):
    """Recognize static ELF or a reviewed stdlib Python tool, never guess its loader."""
    blob = path.read_bytes()
    if blob.startswith(b'#!') and b'python' in blob.splitlines()[0]:
        return 'python-stdlib'
    if blob[:4] != b'\x7fELF' or len(blob) < 64 or blob[4] not in (1, 2) or blob[5] not in (1, 2):
        raise LedgerError('Tool snapshot adapter supports static ELF or declared stdlib Python only')
    endian = '<' if blob[5] == 1 else '>'
    if blob[4] == 2:
        offset = struct.unpack_from(endian + 'Q', blob, 32)[0]
        width, count = struct.unpack_from(endian + 'HH', blob, 54)
    else:
        offset = struct.unpack_from(endian + 'I', blob, 28)[0]
        width, count = struct.unpack_from(endian + 'HH', blob, 42)
    if width < 4 or offset + width * count > len(blob):
        raise LedgerError('Invalid executable program headers')
    for index in range(count):
        kind = struct.unpack_from(endian + 'I', blob, offset + index * width)[0]
        if kind in (2, 3):
            raise LedgerError('Dynamic executable requires a closed library/loader snapshot adapter; no production started')
    return 'static-elf'


def validate_tools(ledger, resources, names):
    if set(resources) != set(names):
        raise LedgerError('Request must pin an exact resource descriptor for each tool')
    for name in names:
        descriptor = ledger._descriptor(resources[name])
        installation = ledger._resource_installation(descriptor['config_key'])
        validate_execution(installation, descriptor)


def resource_directory(ledger, run_id, ref):
    intent, _ = ledger._intent(run_id)
    slots = [slot for slot in intent['resource_slots'] if slot['revision_id'] == ref['revision_id']]
    if len(slots) != 1:
        raise LedgerError('Tool resource slot is missing or ambiguous')
    return ledger.resource_paths(run_id)[slots[0]['slot']]


def native_library_paths(ledger, run_id, ref):
    descriptor = ledger._descriptor(ref)
    directory = resource_directory(ledger, run_id, ref)
    validate_execution(directory, descriptor)
    execution = descriptor['source']['execution']
    if execution['mode'] != 'dynamic-library':
        raise LedgerError('Expected a reviewed dynamic-library descriptor')
    return [str(directory if folder == '.' else directory / folder) for folder in execution['library_dirs']]


def tool_argv(ledger, run_id, ref):
    descriptor = ledger._descriptor(ref)
    directory = resource_directory(ledger, run_id, ref)
    execution = descriptor['source']['execution']
    entrypoint = resource_file(directory, execution['entrypoint'])
    validate_execution(directory, descriptor)
    manifest = {file['path'] for file in descriptor['files']}
    arguments = [resource_argument(directory, arg, manifest) if '{' in arg else arg
                 for arg in execution.get('arguments', [])]
    if execution['mode'] == 'dynamic-library':
        raise LedgerError('Shared library cannot be invoked as an executable tool')
    if execution['mode'] == 'dynamic-elf':
        folders = [str(directory if folder == '.' else directory / folder) for folder in execution['library_dirs']]
        return [str(resource_file(directory, execution['loader'])), '--inhibit-cache',
                '--library-path', os.pathsep.join(folders), str(entrypoint), *arguments]
    mode = executable_mode(entrypoint)
    if mode != execution['mode']:
        raise LedgerError('Tool snapshot executable mode changed')
    if mode == 'python-stdlib':
        return [sys.executable, '-I', '-S', str(entrypoint), *arguments]
    return [str(entrypoint), *arguments]


def tool_environment(scratch):
    """Keep tool preferences and temporary writes within the prepared run."""
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('LD_', 'DYLD_')) and key not in {
                       'PYTHONPATH', 'PYTHONHOME', 'GLIBC_TUNABLES', 'JAVA_TOOL_OPTIONS',
                       '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'NODE_OPTIONS', 'NODE_PATH'}}
    environment.update({key: str(scratch) for key in ('HOME', 'USERPROFILE', 'APPDATA',
                        'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_RUNTIME_DIR',
                        'TMPDIR', 'TEMP', 'TMP')})
    environment.pop('FFREPORT', None)
    return environment


def conversion_environment(directory, descriptor):
    profile = descriptor['source'].get('conversion')
    if profile is None and descriptor['source']['execution']['mode'] == 'python-stdlib':
        return {}
    if (not isinstance(profile, dict) or set(profile) != {'closure_review', 'environment'}
            or not isinstance(profile['closure_review'], str) or not profile['closure_review'].strip()
            or not isinstance(profile['environment'], dict)
            or any(not isinstance(name, str) for name in profile['environment'].values())
            or set(profile['environment']) - {'FONTCONFIG_FILE', 'FONTCONFIG_PATH', 'FONTCONFIG_SYSROOT', 'QT_PLUGIN_PATH',
                                            'QT_QPA_PLATFORM_PLUGIN_PATH', 'XDG_DATA_DIRS'}):
        raise LedgerError('Native converter requires reviewed font/plugin/data closure and resource-relative environment')
    manifest = {file['path'] for file in descriptor['files']}
    return {key: resource_argument(directory, '{resource}' if name == '.' else '{resource}/' + name, manifest)
            for key, name in profile['environment'].items()}
