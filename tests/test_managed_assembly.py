"""Real encoded Flow assembly through ordinary and centrally managed execution."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/artifact-bookkeeping/scripts'))

from artifact_ledger import Ledger, LedgerError, reference
from ledger_execution import prepare, execute, finish, status
from ledger_tools import elf_dependencies, validate_execution
from scripts.project_runtime import load_project

SCRIPT = '.agents/skills/barnsang-video/scripts/assemble_flow.py'


def media_resource(bundle, tool):
    """Select the configured qualified tool's actual ELF dependency closure."""
    pending = ['bin/' + tool, 'lib/ld-linux-x86-64.so.2']
    files = set()
    while pending:
        name = pending.pop()
        if name in files:
            continue
        files.add(name)
        metadata = elf_dependencies(bundle / name)
        pending.extend('lib/' + library for library in metadata['needed'])
    execution = {'mode': 'dynamic-elf', 'entrypoint': 'bin/' + tool,
                 'loader': 'lib/ld-linux-x86-64.so.2', 'library_dirs': ['lib']}
    source = {'execution': execution,
              'evidence': 'Configured qualified Linux media bundle; bounded synthetic media test'}
    validate_execution(bundle, {'source': source, 'files': [{'path': name} for name in sorted(files)]})
    command = [str(bundle / execution['loader']), '--inhibit-cache', '--library-path',
               str(bundle / 'lib'), str(bundle / execution['entrypoint'])]
    return sorted(files), source, command


class ManagedAssemblyTests(unittest.TestCase):
    def test_real_media_matches_standalone_and_keeps_exact_edges_and_usable_paths(self):
        configured = load_project().get('resources', {}).get('native_tools')
        if not configured or not (Path(configured) / 'bin/ffmpeg').is_file():
            self.skipTest('BLOCKED: configured qualified native FFmpeg bundle unavailable')
        bundle = Path(configured)
        if not (bundle / 'lib/ld-linux-x86-64.so.2').is_file():
            self.skipTest('BLOCKED: this bounded real-media test requires the qualified Linux ELF bundle')
        with tempfile.TemporaryDirectory(prefix='managed assembly ') as temporary:
            root = Path(temporary)
            data = root / 'data'
            data.mkdir()
            config = {'paths': {'data_root': str(data), 'resource_cache': str(root / 'cache')},
                      'bookkeeping': {'actor_id': 'assembly-test', 'host_id': str(uuid4())},
                      'resources': {'native_tools': str(bundle)}}
            ledger = Ledger(config)
            resources, commands = {}, {}
            for tool in ('ffmpeg', 'ffprobe'):
                files, source, command = media_resource(bundle, tool)
                version = subprocess.run([*command, '-version'], check=True, capture_output=True,
                                         text=True).stdout.splitlines()[0]
                event = ledger.register_resource('resources.native_tools', files, label=tool,
                                                 version=version, source=source)
                resources[tool] = reference(event['data']['updates'][0])
                commands[tool] = command
            ffmpeg = commands['ffmpeg']
            subprocess.run([*ffmpeg, '-n', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000:duration=2', '-c:a', 'pcm_s16le',
                            str(data / 'source.wav')], check=True, capture_output=True)
            for name, color, duration in [('a', 'red', .6), ('b', 'green', .8), ('c', 'blue', 1.0)]:
                subprocess.run([*ffmpeg, '-n', '-v', 'error', '-f', 'lavfi', '-i',
                                f'color=c={color}:s=160x120:r=12:d={duration}',
                                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(data / f'{name}.mp4')],
                               check=True, capture_output=True)
            settings = {'source_bpm': 120, 'target_bpm': 100, 'beats_per_bar': 4,
                        'verse_bars': 1, 'interlude_bars': 0, 'verse_groups': [['a', 'b'], ['c']],
                        'width': 160, 'height': 120, 'fps': 12, 'preset': 'ultrafast'}
            (data / 'settings.json').write_text(json.dumps(settings))
            (data / 'nested').mkdir()
            clip_map = data / 'nested/clips.json'
            clip_map.write_text(json.dumps([{'id': name, 'file': f'{name}.mp4'} for name in 'abc']))
            original_map = clip_map.read_bytes()
            sources = {'song_config': 'settings.json', 'clips': 'nested/clips.json',
                       'audio': 'source.wav', **{f'clip_{name}': f'{name}.mp4' for name in 'abc'}}
            inputs = {}
            for name, filename in sources.items():
                event = ledger.import_files({Path(filename).name: data / filename}, kind='source', label=name)
                inputs[name] = {**reference(event['data']['updates'][0]),
                                'files': [Path(filename).name], 'purpose': name}
            local = root / 'standalone'
            local.mkdir()
            (local / 'config.toml').write_text('[paths]\ndata_root=' + json.dumps(str(data)) + '\n' +
                ''.join(f'[tools.{tool}]\ncommand=' + json.dumps(command) + '\n'
                        for tool, command in commands.items()))
            args = ['--song-config', 'settings.json', '--clips', 'nested/clips.json', '--audio', 'source.wav',
                    '--output', 'standalone/film.mp4', '--output-audio', 'standalone/audio.wav',
                    '--timeline', 'standalone/timeline.json']
            result = subprocess.run([sys.executable, str(ROOT / SCRIPT), '--config-root', str(local), *args],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            baseline = json.loads((data / 'standalone/timeline.json').read_text())
            audio_edge = {'output': 'audio', 'files': ['audio.wav'], 'purpose': 'prepared soundtrack'}
            film_edge = {'output': 'film', 'files': ['film.mp4'], 'purpose': 'assembled film'}
            request = {'operation': 'assemble-flow', 'skill': 'barnsang-video',
                'declaration': '.agents/skills/barnsang-video/SKILL.md', 'code': [SCRIPT],
                'inputs': inputs, 'resources': resources,
                'outputs': {name: {'kind': name, 'label': name,
                    'contract': {'files': [{'path': filename, 'role': name}]}, 'dependencies': dependencies}
                    for name, filename, dependencies in [
                        ('audio', 'audio.wav', ['song_config', 'audio']),
                        ('film', 'film.mp4', [*inputs, audio_edge]),
                        ('timeline', 'timeline.json', [*inputs, audio_edge, film_edge])]},
                'documents': {'clips': {'input': 'clips', 'bindings': {
                    f'/{index}/file': '{input:clip_' + name + '}' for index, name in enumerate('abc')}}},
                'config': {'tools': {tool: {'command': '{tool:' + tool + '}'} for tool in commands}},
                'command': ['{python}', '{code:' + SCRIPT + '}',
                    '--song-config', '{input:song_config}', '--clips', '{document:clips}',
                    '--audio', '{input:audio}', '--output', '{output:film/film.mp4}',
                    '--output-audio', '{output:audio/audio.wav}', '--timeline', '{output:timeline/timeline.json}'],
                'publish_json': ['{output:timeline/timeline.json}']}
            bad = copy.deepcopy(request)
            bad['documents']['clips']['bindings']['/0/file'] = '{input:clip_b}'
            with self.assertRaisesRegex(LedgerError, 'Indirect input differs'):
                prepare(ledger, bad)
            intent = prepare(ledger, request)
            run_id = intent['run_id']
            self.assertEqual(clip_map.read_bytes(), original_map)
            execute(ledger, run_id)
            with self.assertRaisesRegex(LedgerError, 'already attempted'):
                execute(ledger, run_id)
            finish(ledger, run_id)
            outputs = {name: ledger.resolve(spec['artifact_id'], spec['revision_id'])
                       for name, spec in zip(request['outputs'], intent['outputs'])}
            self.assertEqual({dep['revision_id'] for dep in outputs['audio']['dependencies']},
                             {inputs[name]['revision_id'] for name in ('song_config', 'audio')})
            expected_film = {dep['revision_id'] for dep in inputs.values()} | {outputs['audio']['revision_id']}
            self.assertEqual({dep['revision_id'] for dep in outputs['film']['dependencies']}, expected_film)
            self.assertEqual({dep['revision_id'] for dep in outputs['timeline']['dependencies']},
                             expected_film | {outputs['film']['revision_id']})
            timeline_path = ledger.path(outputs['timeline']['history_path'] + '/timeline.json')
            managed = json.loads(timeline_path.read_text())
            for key in ('tempo', 'duration_s', 'verse_starts_s', 'settings'):
                self.assertEqual(managed[key], baseline[key])
            for actual, expected in zip(managed['clips'], baseline['clips']):
                self.assertEqual({k: v for k, v in actual.items() if k != 'path'},
                                 {k: v for k, v in expected.items() if k != 'path'})
            self.assertEqual(Path(managed['prepared_audio']).read_bytes(),
                             Path(baseline['prepared_audio']).read_bytes())
            film = Path(managed['film'])
            probe = subprocess.run([*commands['ffprobe'], '-v', 'error', '-show_streams', '-of', 'json', str(film)],
                                   check=True, capture_output=True, text=True)
            streams = json.loads(probe.stdout)['streams']
            self.assertEqual({stream['codec_type'] for stream in streams}, {'audio', 'video'})
            video = next(stream for stream in streams if stream['codec_type'] == 'video')
            self.assertEqual((video['codec_name'], video['width'], video['height']), ('h264', 160, 120))
            self.assertAlmostEqual(float(video['duration']), managed['duration_s'], delta=1 / settings['fps'])
            decode = subprocess.run([*commands['ffmpeg'], '-v', 'error', '-i', str(film), '-f', 'null', '-'],
                                    capture_output=True, text=True)
            self.assertEqual(decode.returncode, 0, decode.stderr)
            before = set((data / 'ledger').iterdir())
            finish(ledger, run_id)
            self.assertEqual(set((data / 'ledger').iterdir()), before)
            self.assertEqual(status(ledger, run_id)['ledger_status'], 'completed')
            for folder in ('inputs', 'outputs', 'scratch'):
                shutil.rmtree(ledger.path(intent['workspace']) / folder)
            self.assertNotIn('/work/', timeline_path.read_text())
            for path in [managed['audio'], managed['film'], managed['prepared_audio'],
                         *[clip['path'] for clip in managed['clips']]]:
                self.assertTrue(Path(path).is_file(), path)
                self.assertTrue(Path(path).is_relative_to(data / 'history'), path)
            fresh = prepare(ledger, request)
            self.assertNotEqual(fresh['run_id'], run_id)
            self.assertTrue({spec['artifact_id'] for spec in fresh['outputs']}.isdisjoint(
                           {spec['artifact_id'] for spec in intent['outputs']}))
