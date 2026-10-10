"""Capture Python distribution resources and execute one isolated managed stage."""
from __future__ import annotations

import csv
import importlib.metadata
import json
import io
import os
import re
from pathlib import Path
import sys
import sysconfig

from artifact_ledger import Ledger, LedgerError, atomic, encoded, reference, resource_file, sha
from scripts.read_config import ROOT


PYTHON_RESOURCE_KEY = 'resources.python_packages'


def distribution_manifest(packages, package_root):
    """Resolve installed dependency metadata and retain every runtime RECORD file."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    package_root = Path(package_root).resolve(strict=True)
    queued = [Requirement(name) for name in packages]
    if not queued:
        raise LedgerError('Specify the Python distributions consumed by this stage')
    collected, processed, versions, exclusions = set(), {}, {}, []
    while queued:
        requirement = queued.pop()
        name = canonicalize_name(requirement.name)
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise LedgerError(f'Python runtime unavailable: install declared distribution {name}') from exc
        if requirement.specifier and not requirement.specifier.contains(distribution.version, prereleases=True):
            raise LedgerError(f'Installed {name} {distribution.version} does not satisfy {requirement}')
        extras = set(requirement.extras)
        if name in processed and extras <= processed[name]:
            continue
        extras.update(processed.get(name, set()))
        processed[name] = extras
        versions[name] = distribution.version
        root = Path(distribution.locate_file('')).resolve()
        if root != package_root:
            raise LedgerError(f'{name} is outside configured {PYTHON_RESOURCE_KEY}: {root}')
        record = distribution.read_text('RECORD')
        if not record:
            raise LedgerError(f'{name} has no complete installed RECORD manifest')
        rows = list(csv.reader(io.StringIO(record)))
        if not rows or any(len(row) != 3 or not row[0] for row in rows):
            raise LedgerError(f'{name} has an invalid installed RECORD manifest')
        files = [row[0] for row in rows]
        wrappers = {entry.name for entry in distribution.entry_points if entry.group == 'console_scripts'}
        scripts = Path(sysconfig.get_path('scripts')).resolve()
        for relative in files:
            path = Path(distribution.locate_file(relative))
            resolved = path.resolve()
            if not resolved.is_relative_to(package_root):
                wrapper_names = wrappers | ({name + suffix for name in wrappers for suffix in ('.exe', '-script.py')} if os.name == 'nt' else set())
                wrapper = resolved.parent == scripts and resolved.name in wrapper_names
                man_root = Path(sysconfig.get_path('data')).resolve() / 'share/man'
                section = re.fullmatch(r'man([1-9])', resolved.parent.name)
                manual = (section is not None and resolved.parent.parent == man_root
                          and resolved.name in {entry + '.' + section[1] + suffix for entry in wrappers for suffix in ('', '.gz')})
                if (wrapper or manual) and not path.is_symlink():
                    kind = 'console-script wrapper' if wrapper else 'console-script manual'
                    item = {'distribution': name, 'path': relative, 'reason': f'Declared {kind}; import-only stage never consumes it'}
                    if item not in exclusions:
                        exclusions.append(item)
                    continue
                raise LedgerError(f'Unsafe external Python distribution record: {name}: {relative}')
            # Lexical traversal is rejected even if resolution happens to return inside the root.
            if any(part in ('', '.', '..') for part in relative.split('/')):
                raise LedgerError(f'Unsafe Python distribution record: {name}: {relative}')
            source = resource_file(package_root, relative)
            if not source.is_file():
                raise LedgerError(f'Python distribution file is missing: {name}: {relative}')
            collected.add(relative)
        for value in distribution.requires or []:
            dependency = Requirement(value)
            if dependency.marker is None or any(dependency.marker.evaluate({'extra': extra}) for extra in ('', *sorted(extras))):
                queued.append(dependency)
    return {'files': sorted(collected), 'versions': dict(sorted(versions.items())),
            'exclusions': sorted(exclusions, key=lambda item: (item['distribution'], item['path']))}


def capture_python_runtime(ledger, packages):
    """Register exact package files; prepare subsequently snapshots those bytes."""
    configured = ledger.config.get('resources', {}).get('python_packages')
    if not configured:
        raise LedgerError(f'Configure {PYTHON_RESOURCE_KEY} to the observed Python site-packages directory')
    manifest = distribution_manifest(packages, configured)
    event = ledger.register_resource(PYTHON_RESOURCE_KEY, manifest['files'], label='Python runtime packages',
                                     version=json.dumps(manifest['versions'], sort_keys=True),
                                     source={'adapter': 'isolated-python-import', 'requested': sorted(packages),
                                             'distributions': manifest['versions'], 'exclusions': manifest['exclusions'],
                                             'platform_boundary': 'Python interpreter, standard library and operating system are observed, not copied'})
    return reference(event['data']['updates'][0])


def _captured_code(ledger, intent, directory):
    code = intent['producer']['code']
    snapshot = code['snapshot']
    if snapshot is None:
        raise LedgerError('Isolated production requires a captured code snapshot')
    record = ledger.resolve(**snapshot)
    if not record['available']:
        raise LedgerError('Captured project code is unavailable')
    by_hash = {}
    for file in record['files']:
        by_hash.setdefault(file['sha256'], file)
    expected = {}
    for file in code['files']:
        name = file['path']
        if name.startswith('/') or '\\' in name or ':' in name or any(part in ('', '.', '..') for part in name.split('/')):
            raise LedgerError('Unsafe captured source path')
        captured = by_hash.get(file['sha256'])
        if captured is None:
            raise LedgerError(f'Code snapshot does not preserve executed source: {name}')
        source = ledger.path(record['history_path'] + '/' + captured['path'])
        if sha(source) != file['sha256']:
            raise LedgerError('Captured source integrity failure')
        destination = resource_file(directory, name)
        atomic(destination, source.read_bytes())
        expected[name] = file['sha256']
    actual = set()
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise LedgerError('Unexpected symlink in captured code execution tree')
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(expected):
        raise LedgerError('Unexpected file in captured code execution tree')
    return expected
