"""Synthetic rendering parity; no real instrument or native synth qualification."""
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/jjazzlab_experiments'))
from verification import sha
from render_child_versions import render
import sample_renderer

AUDITOR = '''import mido
import math
def read_midi(path):
    midi = mido.MidiFile(path)
    tracks = []
    for track in midi.tracks:
        tick, active, notes, meta = 0, {}, [], []
        for msg in track:
            tick += msg.time
            if msg.type == 'note_on' and msg.velocity:
                active[(msg.channel,msg.note)] = (tick,msg.velocity)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and not msg.velocity):
                start, velocity = active.pop((msg.channel,msg.note))
                notes.append((msg.note,start,tick-start,msg.channel,velocity))
            elif msg.type == 'track_name': meta.append((tick,3,msg.name.encode().hex()))
            elif msg.type == 'marker': meta.append((tick,6,msg.text.encode().hex()))
            elif msg.type == 'set_tempo': meta.append((tick,81,msg.tempo.to_bytes(3,'big').hex()))
            elif msg.type == 'time_signature': meta.append((tick,88,bytes([msg.numerator,int(math.log2(msg.denominator))]).hex()))
        tracks.append({'notes':notes,'meta':meta,'errors':[]})
    return {'ppq':midi.ticks_per_beat,'tracks':tracks}
def triples(track,ppq):
    return sorted((p,t/ppq,d/ppq) for p,t,d,ch,v in track['notes'])
'''


def midi_bytes(backing=False):
    import mido
    midi = mido.MidiFile(ticks_per_beat=480)
    lead = mido.MidiTrack()
    lead.extend([mido.MetaMessage('track_name', name='Original melody'), mido.MetaMessage('time_signature', numerator=4, denominator=4),
                 mido.MetaMessage('set_tempo', tempo=600000), mido.MetaMessage('marker', text='C')])
    if not backing:
        lead.extend([mido.Message('note_on', channel=0, note=60, velocity=80), mido.Message('note_off', channel=0, note=60, time=480)])
    background = mido.MidiTrack([mido.MetaMessage('track_name', name='Background line'),
                                mido.Message('program_change', channel=1, program=71),
                                mido.Message('note_on', channel=1, note=48, velocity=60),
                                mido.Message('note_off', channel=1, note=48, time=480)])
    midi.tracks.extend([lead, background])
    stream = io.BytesIO(); midi.save(file=stream)
    return stream.getvalue()


def sf2_bytes():
    records = b''.join(struct.pack('<20sHHHIII', name, 0, 0, 0, 0, 0, 0) for name in (b'Fixture', b'EOP'))
    body = b'pdta' + b'phdr' + struct.pack('<I', len(records)) + records
    riff = b'sfbk' + b'LIST' + struct.pack('<I', len(body)) + body
    return b'RIFF' + struct.pack('<I', len(riff)) + riff


class RenderDomainTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='render ö space ');self.addCleanup(temporary.cleanup)
        self.work=Path(temporary.name); self.data=self.work/'data';self.data.mkdir()
        self.resources=self.work/'resources';self.resources.mkdir()
        source_dir=self.data/'source';source_dir.mkdir()
        for name, content in {'source.musicxml':b'<score/>','source.mid':midi_bytes(),'baseline.mid':midi_bytes(),'child-plan.json':b'{}'}.items():
            (source_dir/name).write_bytes(content)
        cfg = {'filename': 'arrangement-a', 'baseline_filename': 'baseline', 'stem': 'song', 'id': 'variant-a',
               'title': 'Synthetic fixture', 'source_xml': str(source_dir / 'source.musicxml'),
               'source_midi': str(source_dir / 'source.mid'), 'source_sha256': sha(source_dir / 'source.musicxml'),
               'source_midi_sha256': sha(source_dir / 'source.mid'), 'baseline_folder': str(source_dir),
               'baseline_midi_sha256': sha(source_dir / 'baseline.mid'), 'child_plan': str(source_dir / 'child-plan.json'),
               'child_plan_sha256': sha(source_dir / 'child-plan.json'), 'tempo': 100, 'meter': '4/4',
               'chords': [{'bar': 0, 'beat': 0, 'name': 'C'}], 'variant_operations': {'baseline_percussion': 'preserve', 'events': []},
               'counter_library': 'generaluser', 'room': 'studio'}
        native = {'parameters.json': json.dumps(cfg).encode(), 'tracks.tsv': b'voice\tchannel\nOriginal melody\t0\nBackground line\t1\n',
                  'native_reload_verified.txt': b'Synthetic test evidence only'}

        self.folder=self.data/'arrangement';self.folder.mkdir()
        native.update({'arrangement-a.mid':midi_bytes(),'arrangement-a_backing.mid':midi_bytes(backing=True)})
        for name,content in native.items(): (self.folder/name).write_bytes(content)
        (self.resources/'audit.py').write_text(AUDITOR)
        (self.resources/'fixture.sf2').write_bytes(sf2_bytes())
        keys=['generaluser','nylon','steel','bass','clarinet','drums','salamander']
        (self.resources/'fonts.json').write_text(json.dumps({key:{'path':'fixture.sf2','credits':'Synthetic fixture only'} for key in keys}))
        (self.resources/'CREDITS.md').write_text('Synthetic fixture only')
        (self.resources/'library').write_bytes(b'Synthetic native library placeholder')
        (self.resources/'encoder.py').write_text('from pathlib import Path\nimport sys\nPath(sys.argv[-1]).write_bytes(b"synthetic encoded MP3")\n')
        self.config={'paths':{'data_root':str(self.data)},'resources':{
            'midi_audit':str(self.resources/'audit.py'),'fluidsynth_library':str(self.resources/'library'),
            'soundfont_manifest':str(self.resources/'fonts.json'),'soundfont_credits':str(self.resources/'CREDITS.md')},
            'tools':{'ffmpeg':{'command':[sys.executable,str(self.resources/'encoder.py')]}}}

    def test_synthetic_render_preserves_alignment_loudness_and_no_clobber(self):
        class SyntheticRenderer:
            def __init__(self, fonts, library): pass
            def render(self,path,room):
                amplitude=.06 if '_backing' in path.name else .1
                wave=amplitude*np.sin(2*np.pi*440*np.arange(96000)/48000)
                return np.column_stack((wave,wave)),{'routes':{'1':{'library':'generaluser'}},'fixture_synthesis':True}
            def close(self): pass
        out=self.data/'reports';audio=self.data/'audio'
        with patch.object(sample_renderer,'CounterRenderer',SyntheticRenderer):
            render([self.folder],out,self.config,audio_out=audio)
        result=json.loads((out/'verification.json').read_text())[0]
        self.assertTrue(result['fixture_synthesis'])
        self.assertEqual(result['human_listening_review'],'pending')
        self.assertTrue(result['verification']['backing_audio_frame_aligned'])
        self.assertLess(abs(result['final_lufs']+18.3),.05)
        directory=Path(result['folder'])
        full=sf.info(directory/'arrangement-a.wav');backing=sf.info(directory/'arrangement-a_backing.wav')
        self.assertEqual((full.frames,full.channels,full.samplerate,full.subtype),(backing.frames,2,48000,'PCM_24'))
        before={p:p.read_bytes() for p in directory.iterdir()}
        with self.assertRaisesRegex(ValueError,'must be empty'):
            render([self.folder],out,self.config,audio_out=audio)
        self.assertEqual({p:p.read_bytes() for p in before},before)

    def test_existing_audio_refused_before_synth_loading(self):
        target=self.data/'audio/song/variant-a';target.mkdir(parents=True)
        (target/'keep').write_text('original')
        with patch.object(sample_renderer,'CounterRenderer',side_effect=AssertionError('native load')):
            with self.assertRaisesRegex(ValueError,'destination already exists'):
                render([self.folder],self.data/'reports',self.config,audio_out=self.data/'audio')
        self.assertEqual((target/'keep').read_text(),'original')
        self.assertFalse((self.data/'reports').exists())
