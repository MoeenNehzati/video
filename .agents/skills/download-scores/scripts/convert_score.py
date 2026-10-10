"""Convert one explicit score; preserve container safety and MIDI trailing silence."""
from pathlib import Path
import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, fresh_output, load_project, tool_command


def preserve_midi_duration(args):
    """Preserve MusicXML's repeat-expanded silence without changing sounding events."""
    from music21 import converter
    import mido

    score = converter.parse(str(args.score), forceSource=True).expandRepeats()
    midi = mido.MidiFile(args.midi)
    if midi.type not in (0, 1) or midi.ticks_per_beat <= 0 or not score.parts:
        raise ValueError('Duration preservation requires a score and synchronous PPQ MIDI')
    ticks = Fraction(str(score.highestTime)) * midi.ticks_per_beat
    if ticks.denominator != 1:
        raise ValueError('Score duration is not exactly representable at the exported MIDI resolution')
    expected = int(ticks)
    ends = [sum(message.time for message in track) for track in midi.tracks]
    if not midi.tracks or any(not track or track[-1].type != 'end_of_track'
                             or any(message.type == 'end_of_track' for message in track[:-1])
                             for track in midi.tracks):
        raise ValueError('MIDI must have one terminal end-of-track event per track')
    if any(end > expected for end in ends):
        raise ValueError('MIDI exceeds the source duration; refusing to truncate events')
    for track, end in zip(midi.tracks, ends):
        track[-1].time += expected - end
    if any(end != expected for end in ends):
        midi.save(args.midi)
    print(json.dumps({'musicxml_duration_beats': str(score.highestTime),
                      'midi_ticks_per_beat': midi.ticks_per_beat,
                      'original_track_end_ticks': ends, 'track_end_ticks': expected,
                      'changed_events': 'end_of_track only'}))


def validate_score_container(path):
    def check_xml(blob, member='', members=()):
        text = blob.decode('utf-8-sig')
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b|<\?xml-stylesheet\b', text, re.I):
            raise ValueError('Score DTD/entities/stylesheets require a explicitly bound conversion input')
        document = ET.fromstring(text)
        fields = {'source', 'src', 'href', 'url', 'path', 'file', 'filename', 'full-path', 'stylesheet'}
        def reference(value, root_relative=False):
            if not value:
                return
            name = posixpath.normpath(posixpath.join('' if root_relative else posixpath.dirname(member), value))
            if (not members or value.startswith(('/', '\\')) or '\\' in value or ':' in value
                    or name not in members):
                raise ValueError('External score images/files need a explicitly bound conversion input')
        for element in document.iter():
            for key, value in element.attrib.items():
                key = key.rsplit('}', 1)[-1].lower()
                if key in fields:
                    reference(value, key == 'full-path')
            if element.tag.rsplit('}', 1)[-1].lower() in {'path', 'file', 'filename', 'stylesheet'}:
                reference((element.text or '').strip())
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = set(archive.namelist())
            if len(members) != len(archive.namelist()):
                raise ValueError('Duplicate paths inside score container')
            for name in members:
                parts = name.replace('\\', '/').split('/')
                if name.startswith(('/', '\\')) or '..' in parts or ':' in name:
                    raise ValueError('Unsafe path inside score container')
                if Path(name).suffix.lower() in {'.xml', '.musicxml', '.mscx', '.mss', '.svg'}:
                    check_xml(archive.read(name), name, members)
        return
    if path.suffix.lower() in {'.xml', '.musicxml'}:
        check_xml(path.read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('score', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--engine', choices=['musescore', 'audiveris'], default='musescore')
    add_config_argument(parser)
    args = parser.parse_args(argv)
    config = load_project(args.config_root)
    source = data_path(config, args.score, must_exist=True)
    output = fresh_output(data_path(config, args.out), inputs=[source])
    log_path = fresh_output(data_path(config, args.log), inputs=[source, output])
    scratch = fresh_output(data_path(config, args.scratch, directory=True), inputs=[source, output, log_path])
    if len({source, output, log_path, scratch}) != 4 or any(path.is_relative_to(scratch) for path in (source, output, log_path)):
        raise ValueError('Source, output, log and scratch must be distinct and outside scratch')
    extension = output.suffix.lower().lstrip('.')
    if extension not in {'musicxml', 'mxl', 'mid', 'pdf'}:
        raise ValueError('Unsupported score conversion format')
    if args.engine == 'audiveris' and extension != 'mxl':
        raise ValueError('Audiveris exports MXL only')
    validate_score_container(source)
    command = tool_command(config, args.engine)
    scratch.mkdir(parents=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if args.engine == 'musescore':
        command += ['-o', str(output), str(source)]
    else:
        generated = scratch / 'generated'
        generated.mkdir()
        command += ['-batch', '-export', '-output', str(generated), str(source)]
    environment = os.environ.copy()
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run(command, cwd=scratch, env=environment, capture_output=True)
    log = result.stdout + result.stderr
    for path, token in ((source, '{input:score}'), (output, '{output}'), (scratch, '{scratch}')):
        log = log.replace(str(path).encode(), token.encode())
    log_path.write_bytes(log)
    if result.returncode:
        raise ValueError(f'{args.engine} failed with exit status {result.returncode}')
    if args.engine == 'audiveris':
        if any(path.is_symlink() for path in generated.rglob('*')):
            raise ValueError('Audiveris generated a symbolic link')
        matches = list(generated.rglob('*.mxl'))
        if len(matches) != 1:
            raise ValueError('Audiveris did not produce one unambiguous MXL result')
        output.write_bytes(matches[0].read_bytes())
    if output.is_symlink() or not output.is_file() or not output.stat().st_size:
        raise ValueError('Converter returned success without a nonempty output')
    if args.engine == 'musescore' and extension == 'mid' and source.suffix.lower() in {'.xml', '.musicxml', '.mxl'}:
        from types import SimpleNamespace
        from contextlib import redirect_stdout
        with log_path.open('a', encoding='utf-8') as stream, redirect_stdout(stream):
            preserve_midi_duration(SimpleNamespace(score=source, midi=output))


if __name__ == '__main__':
    main()
