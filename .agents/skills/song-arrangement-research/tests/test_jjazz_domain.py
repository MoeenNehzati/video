"""Ordinary JJazz CLI with synthetic tools; not live toolkit qualification."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from uuid import uuid4

import mido

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/jjazzlab_experiments'))

from verification import sha
from scripts.read_config import ROOT

ENTRY = ROOT / '.agents/skills/song-arrangement-research/scripts/jjazzlab_experiments/execute_child_plans.py'
AUDITOR = '''import mido

def read_midi(path):
    midi=mido.MidiFile(path)
    tracks=[]
    for track in midi.tracks:
        tick=0; active={}; notes=[]; meta=[]
        for msg in track:
            tick+=msg.time
            if msg.is_meta:
                if msg.type=='track_name': meta.append((tick,3,msg.name.encode().hex()))
                if msg.type=='marker': meta.append((tick,6,msg.text.encode().hex()))
                if msg.type=='set_tempo': meta.append((tick,81,msg.tempo.to_bytes(3,'big').hex()))
                if msg.type=='time_signature': meta.append((tick,88,bytes([msg.numerator,msg.denominator.bit_length()-1]).hex()))
            elif msg.type=='note_on' and msg.velocity:
                active[(msg.channel,msg.note)]=(tick,msg.velocity)
            elif msg.type in ('note_on','note_off'):
                start,velocity=active.pop((msg.channel,msg.note)); notes.append((msg.note,start,tick-start,msg.channel,velocity))
        tracks.append({'notes':notes,'meta':meta,'errors':[]})
    return {'ppq':midi.ticks_per_beat,'tracks':tracks}

def triples(track,ppq):
    return sorted((p,t/ppq,d/ppq) for p,t,d,c,v in track['notes'])
'''
JAVA = '''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[sys.argv.index('ChildExperiment')+2:]
for value in args:
    directory=Path(value); cfg=json.loads((directory/'parameters.json').read_text())
    for filename in [cfg['filename']+'.sng',cfg['filename']+'.mix','raw_import_chords.tsv','verified_chords.tsv','midi_export_adjustments.txt','generation.txt','native_reload_verified.txt','tracks.tsv']:
        (directory/filename).write_text('synthetic-native-fixture\\n')
'''


class JjazzDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='jj-'); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.data=self.root/'d'; self.data.mkdir()
        self.resources=self.root/'resources'; self.resources.mkdir()
        self.cache=tempfile.TemporaryDirectory(prefix='jc'); self.addCleanup(self.cache.cleanup)
        self.config={'paths':{'data_root':str(self.data),'resource_cache':self.cache.name},
                     'resources':{'python_packages':str(Path(mido.__file__).parent.parent),'java_tools':str(self.resources),
                                  'jjazzlab_toolkit':str(self.resources/'toolkit.jar'),'jjazzlab_rhythms':str(self.resources/'rhythms'),
                                  'midi_audit':str(self.resources/'audit.py')}}
        (self.resources/'java.py').write_text(JAVA)
        (self.resources/'javac.py').write_text("#!/usr/bin/env python3\nimport pathlib,sys\nassert pathlib.Path(sys.argv[-1]).name=='ChildExperiment.java'\n(pathlib.Path(sys.argv[sys.argv.index('-d')+1])/'ChildExperiment.class').write_bytes(b'fixture')\n")
        with zipfile.ZipFile(self.resources/'toolkit.jar', 'w') as archive:
            archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\n')
        (self.resources/'audit.py').write_text(AUDITOR)
        (self.resources/'rhythms').mkdir(); (self.resources/'rhythms/style.sty').write_bytes(b'synthetic-style')
        self.config['tools']={name:{'command':[sys.executable,str(self.resources/(name+'.py'))]} for name in ('java','javac')}
        lines=[]
        for section,values in self.config.items():
            if section == 'tools':
                for name, tool in values.items():
                    lines.extend(['[tools.'+name+']', 'command='+json.dumps(tool['command'])])
            else:
                lines.append('['+section+']'); lines.extend(key+'='+json.dumps(value) for key,value in values.items())
        (self.root/'config.toml').write_text('\n'.join(lines)+'\n')
        self.inputs={}
        self.fixture_sources={}
        source=self.data/'source.musicxml'; source.write_text('<score-partwise/>')
        self.register('source_xml',source)
        source_midi=self.data/'source.mid'
        midi=mido.MidiFile(ticks_per_beat=480); track=mido.MidiTrack(); midi.tracks.append(track)
        track.extend([mido.MetaMessage('track_name',name='Original melody'),mido.MetaMessage('set_tempo',tempo=500000),
                      mido.MetaMessage('time_signature',numerator=4,denominator=4),mido.MetaMessage('marker',text='C'),
                      mido.Message('note_on',note=60,velocity=70,channel=0),mido.Message('note_off',note=60,velocity=0,channel=0,time=480),
                      mido.MetaMessage('end_of_track',time=1440)])
        midi.save(source_midi); self.register('source_midi',source_midi)
        baseline=self.data/'baseline'; baseline.mkdir(); midi.save(baseline/'base.mid')
        base={'stem':'song','id':'00_base','filename':'base','ensemble':'duo','source_xml':str(source),'source_sha256':sha(source),
              'source_midi':str(source_midi),'source_midi_sha256':sha(source_midi),'title':'Song','style':'style','variation':'Main A-1',
              'intensity':0,'room':'studio','counter_library':'clarinet','percussion_events':[],'bars':1,'meter':'4/4','tempo':120,
              'chords':[{'bar':0,'beat':0,'name':'C'}]}
        (baseline/'parameters.json').write_text(json.dumps(base)); self.register('parameters',baseline/'parameters.json')
        for filename,value in [('input.properties','title=Song\ntempo=120\nbars=1\nvariation=Main A-1\nstyle=style\nintensity=0\nensemble=duo\nlead=0\ncounter_program=1\ncounter_volume=75\n'),('chords.tsv','0\t0\tC\n'),('melody.tsv','60\t0\t1\t70\n'),('upper.tsv',''),('tracks.tsv','baseline\n'),('native_reload_verified.txt','verified\n')]:
            (baseline/filename).write_text(value)
            self.register('baseline_'+filename,baseline/filename)
        self.register('baseline_base.mid',baseline/'base.mid')
        research=self.data/'research.json'; research.write_text(json.dumps({'song_id':'song','evidence':[{'id':'source'}]})); self.register('research',research)
        prompt=self.data/'PROMPT.md'; prompt.write_text('Reviewed prompt'); self.register('prompt',prompt)
        variant={'id':'01_drums','label':'Drums','axis':'percussion','rationale':'Participation','evidence_ids':['source'],
                 'baseline_percussion':'preserve','events':[[42,2,0.25,40]],'participation_windows':[[2,3]]}
        plan={'song_id':'song','adapter':'barnsang_percussion_v1','source_xml':str(source),'source_sha256':sha(source),
              'research_file':str(research),'research_sha256':sha(research),'baseline_folder':str(baseline),
              'baseline_midi_sha256':sha(baseline/'base.mid'),'output_root':str(self.data/'legacy'),
              'vocals':'user_supplied','audience':{'age_min':3,'age_max':8,'context':'play'},'invariants':['melody'],
              'variants':[variant]}
        self.plan=self.data/'plan.json'; self.plan.write_text(json.dumps(plan)); self.register('plan',self.plan)
    def register(self,role,path):
        self.fixture_sources[role]=path

    def run_cli(self):
        return subprocess.run([sys.executable,str(ENTRY),'--config-root',str(self.root),str(self.plan),
                               '--out','folders.json','--scratch','scratch','--output-root','legacy'],capture_output=True,text=True)

    def test_synthetic_cli_preserves_inputs_and_frozen_midi(self):
        before={p:p.read_bytes() for p in self.fixture_sources.values()}
        result=self.run_cli(); self.assertEqual(result.returncode,0,result.stderr)
        folder=Path(json.loads((self.data/'folders.json').read_text())[0])
        self.assertTrue((folder/'song__01_drums.sng').is_file())
        self.assertTrue((folder/'song__01_drums.mid').is_file())
        self.assertTrue((folder/'native_reload_verified.txt').is_file())
        self.assertTrue(all(json.loads((folder/'verification.json').read_text())['checks'].values()))
        self.assertEqual({p:p.read_bytes() for p in before},before)
        second=self.run_cli(); self.assertNotEqual(second.returncode,0)
        self.assertIn('already exists',second.stderr)
        self.assertEqual({p:p.read_bytes() for p in before},before)

    def test_stale_source_rejected_before_tools(self):
        self.fixture_sources['source_xml'].write_text('changed')
        result=self.run_cli(); self.assertNotEqual(result.returncode,0)
        self.assertIn('Source hash changed',result.stderr)
        self.assertFalse((self.data/'legacy').exists())
        self.assertFalse((self.data/'scratch').exists())

    def test_tool_failure_does_not_write_success_manifest(self):
        (self.resources/'java.py').write_text('raise RuntimeError("fixture Java failure")\n')
        result=self.run_cli(); self.assertNotEqual(result.returncode,0)
        self.assertIn('fixture Java failure',result.stderr)
        self.assertFalse((self.data/'folders.json').exists())

if __name__=='__main__': unittest.main()
