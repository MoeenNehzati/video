"""Ordinary arrangement scripts through generic orchestration, using synthetic data."""
import importlib.util
import json
from pathlib import Path
import sys
import sysconfig
import tempfile
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'.agents/skills/song-arrangement-research'
CENTRAL=ROOT/'.agents/skills/artifact-bookkeeping/scripts'
sys.path.insert(0,str(CENTRAL))
from artifact_ledger import Ledger, reference, sha
from ledger_execution import prepare, execute, finish, status, rewrite


def fixture(name):
    path=SKILL/'tests'/('test_'+name+'.py')
    spec=importlib.util.spec_from_file_location('arrangement_managed_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class ManagedArrangementTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='managed arrangement å ');self.addCleanup(temporary.cleanup)
        self.work=Path(temporary.name);self.data=self.work/'data';self.data.mkdir()
        cache=tempfile.TemporaryDirectory(prefix='ac');self.addCleanup(cache.cleanup)
        self.config={'paths':{'data_root':str(self.data),'resource_cache':cache.name},
                     'resources':{'python_packages':sysconfig.get_path('purelib')},
                     'bookkeeping':{'actor_id':'test','host_id':str(uuid4())}}
        self.ledger=Ledger(self.config)

    def imported(self,files):
        event=self.ledger.import_files(files,kind='source',label='Synthetic arrangement inputs')
        ref=reference(event['data']['updates'][0])
        return {**ref,'files':list(files),'purpose':'Explicit synthetic input'}

    def request(self,entry,inputs,outputs,arguments,packages=()):
        paths=[SKILL/'scripts/compile_brief.py',*sorted((SKILL/'scripts/jjazzlab_experiments').glob('*')),
               ROOT/'scripts/project_runtime.py',ROOT/'scripts/read_config.py',ROOT/'scripts/__init__.py']
        return {'operation':'arrangement-domain-parity','skill':'song-arrangement-research',
                'declaration':str((SKILL/'SKILL.md').relative_to(ROOT)),
                'code':[str(path.relative_to(ROOT)) for path in paths if path.is_file()],
                'inputs':inputs,'outputs':outputs,'packages':list(packages),
                'command':['{python}','{code:.agents/skills/song-arrangement-research/scripts/'+entry+'}',*arguments]}

    def output(self,files,dependencies,kind='arrangement'):
        return {'kind':kind,'label':'Synthetic '+kind,'dependencies':dependencies,
                'contract':{'files':[{'path':name,'role':kind} for name in files]}}

    def run_request(self,request):
        intent=prepare(self.ledger,request);execute(self.ledger,intent['run_id']);event=finish(self.ledger,intent['run_id'])
        records=[self.ledger.resolve(**reference(update)) for update in event['data']['updates']]
        return intent,records

    def test_compile_parity_indirect_inputs_and_durable_manifest(self):
        source,midi,parameters,research,brief=fixture('imported_skills').ImportedBriefTests().make_inputs(self.data)
        compiler_path=SKILL/'scripts/compile_brief.py'
        spec=importlib.util.spec_from_file_location('standalone_compile',compiler_path)
        compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
        direct=self.data/'standalone';compiler.compile_brief(brief,research,direct,self.config)
        inputs={name:self.imported({path.name:path}) for name,path in [('brief',brief),('research',research),('source',source)]}
        inputs['baseline']=self.imported({'parameters.json':parameters,'baseline.mid':midi})
        request=self.request('compile_brief.py',inputs,
            {'compiled':self.output(['execution_plan.json','PROMPT.md'],list(inputs))},
            ['{document:brief}','{input:research}','--out','{output:compiled}'])
        request['layouts']={'baseline':{'parameters.json':'{input:baseline/parameters.json}','baseline.mid':'{input:baseline/baseline.mid}'}}
        request['documents']={'brief':{'input':'brief','bindings':{'/source_xml':'{input:source}','/baseline_folder':'{layout:baseline}'}}}
        request['publish_json']=['{output:compiled/execution_plan.json}']
        intent,records=self.run_request(request)
        out=self.ledger.path(records[0]['history_path'])
        result=json.loads((out/'execution_plan.json').read_text());expected=json.loads((direct/'execution_plan.json').read_text())
        self.assertEqual(result['variants'],expected['variants']);self.assertEqual(result['song_length_beats'],expected['song_length_beats'])
        self.assertEqual(result['source_sha256'],sha(Path(result['source_xml'])))
        self.assertEqual(result['research_sha256'],sha(Path(result['research_file'])))
        self.assertEqual(result['baseline_midi_sha256'],sha(Path(result['baseline_folder'])/'baseline.mid'))
        self.assertNotIn('/work/',json.dumps(result))
        self.assertNotIn('/work/',(out/'PROMPT.md').read_text())
        self.assertEqual((out/'PROMPT.md').read_bytes(),(direct/'PROMPT.md').read_bytes())
        self.assertEqual({d['revision_id'] for d in records[0]['dependencies']},{d['revision_id'] for d in inputs.values()})
        finish(self.ledger,intent['run_id'])
        with self.assertRaisesRegex(ValueError,'terminal|attempted'):
            execute(self.ledger,intent['run_id'])

    def test_compile_rejects_indirect_substitution_before_execution(self):
        source,midi,parameters,research,brief=fixture('imported_skills').ImportedBriefTests().make_inputs(self.data)
        inputs={name:self.imported({path.name:path}) for name,path in [('brief',brief),('research',research),('source',source)]}
        request=self.request('compile_brief.py',inputs,{'compiled':self.output(['execution_plan.json','PROMPT.md'],list(inputs))},
                             ['{document:brief}','{input:research}','--out','{output:compiled}'])
        request['documents']={'brief':{'input':'brief','bindings':{'/source_xml':'{input:source}'}}}
        source.write_text('substituted')
        before=set(self.ledger.state()['runs'])
        with self.assertRaisesRegex(ValueError,'Indirect input differs'):
            prepare(self.ledger,request)
        self.assertEqual(set(self.ledger.state()['runs']),before)

    def test_managed_delivery_matches_standalone_portable_bundle(self):
        delivery=fixture('delivery_domain').DeliveryDomainTests();delivery.setUp();self.addCleanup(delivery.doCleanups)
        inputs={'report':self.imported({'report.json':delivery.report_path})}
        layouts={}
        for name,folder in [('audio',delivery.audio_path),('arrangement',delivery.data/'arrangement')]:
            inputs[name]=self.imported({path.name:path for path in folder.iterdir()})
            layouts[name]={filename:'{input:'+name+'/'+filename+'}' for filename in inputs[name]['files']}
        # Original report paths are in this fixture's own data root; they remain exact inputs.
        # Copy the fixture under the test ledger's root so central preflight verifies containment.
        import shutil
        for name,original in [('audio',delivery.audio_path),('arrangement',delivery.data/'arrangement')]:
            folder=self.data/name;shutil.copytree(original,folder)
        row=json.loads(delivery.report_path.read_text());row[0]['folder']=str(self.data/'audio');row[0]['arrangement_folder']=str(self.data/'arrangement')
        report=self.data/'report.json';report.write_text(json.dumps(row,sort_keys=True));inputs['report']=self.imported({'report.json':report})
        from publish_experiments import publish
        direct=self.data/'direct';publish([report],direct,self.config)
        files=[path.relative_to(direct).as_posix() for path in direct.rglob('*') if path.is_file()]
        request=self.request('jjazzlab_experiments/publish_experiments.py',inputs,
                             {'delivery':self.output(files,list(inputs),'delivery')},
                             ['{document:report}','--out-dir','{output:delivery}'],['soundfile'])
        request['layouts']=layouts
        request['documents']={'report':{'input':'report','bindings':{'/0/folder':'{layout:audio}','/0/arrangement_folder':'{layout:arrangement}'}}}
        _,records=self.run_request(request);out=self.ledger.path(records[0]['history_path'])
        self.assertEqual({name:(direct/name).read_bytes() for name in files},{name:(out/name).read_bytes() for name in files})
        page={key:records[0][key] for key in ('artifact_id','revision_id')}
        page.update(files=files,purpose='Complete synthetic listening delivery')
        browser_inputs={**inputs,'page':page}
        check=self.request('jjazzlab_experiments/check_delivery.py',browser_inputs,
                           {'check':self.output(['browser.json'],list(browser_inputs),'browser-review')},[],['soundfile'])
        check['code'].append('tests/arrangement_browser_fixture.py')
        check['command']=['{python}','{code:tests/arrangement_browser_fixture.py}','{document:report}',
                          '--page-dir','{input:page}','--out','{output:check/browser.json}','--scratch','{scratch:browser}']
        check['layouts']=layouts;check['documents']=request['documents']
        browser=self.work/'browser-fixture';browser.mkdir();(browser/'browser.py').write_text('#!/usr/bin/env python3\nraise RuntimeError("Do not launch fixture")\n')
        self.config['resources']['browser_fixture']=str(browser)
        event=self.ledger.register_resource('resources.browser_fixture',['browser.py'],label='browser orchestration fixture',version='synthetic',
                     source={'execution':{'mode':'python-stdlib','entrypoint':'browser.py'}})
        check['resources']={'browser':reference(event['data']['updates'][0])}
        check['config']={'tools':{'browser':{'command':'{tool:browser}'}}}
        intent,reviews=self.run_request(check)
        result=json.loads((self.ledger.path(reviews[0]['history_path'])/'browser.json').read_text())
        self.assertEqual(result['files_verified'],['song-a'])
        self.assertTrue(result['fixture_browser'])
        self.assertEqual(status(self.ledger,intent['run_id'])['receipt']['exit_code'],0)

    def test_managed_native_fixture_matches_standalone_and_keeps_plan_hash(self):
        import shutil
        native=fixture('jjazz_domain').JjazzDomainTests();native.setUp();self.addCleanup(native.doCleanups)
        shutil.copytree(native.data,self.data,dirs_exist_ok=True)
        for path in self.data.rglob('*.json'):
            path.write_text(path.read_text().replace(str(native.data),str(self.data)))
        runtime_config={**native.config,'paths':{'data_root':str(self.data)}}
        from execute_child_plans import execute as domain_execute
        import os
        domain_execute([self.data/'plan.json'],self.data/'direct-folders.json',runtime_config,
                       runtime={'java':native.config['tools']['java']['command'],'javac':native.config['tools']['javac']['command'],
                                'build':self.data/'direct-scratch','environment':dict(os.environ)},output_root=self.data/'direct')
        baseline=self.data/'baseline'
        baseline_dep=self.imported({p.name:p for p in baseline.iterdir()})
        inputs={name:self.imported({path.name:path}) for name,path in [('source',self.data/'source.musicxml'),
                 ('melody',self.data/'source.mid'),('research',self.data/'research.json')]}
        plan_bundle=self.imported({'execution_plan.json':self.data/'plan.json','PROMPT.md':self.data/'PROMPT.md'})
        inputs['plan']={**plan_bundle,'files':['execution_plan.json']}
        inputs['prompt']={**plan_bundle,'files':['PROMPT.md']}
        inputs['parameters']={**baseline_dep,'files':['parameters.json']}
        inputs['baseline']={**baseline_dep,'files':[f for f in baseline_dep['files'] if f!='parameters.json']}
        names=[path.relative_to(self.data/'direct').as_posix() for path in (self.data/'direct').rglob('*') if path.is_file()]
        prefix='song/01_drums/'
        midi=[name[len(prefix):] for name in names if name.endswith('.mid')]
        native_files=[name[len(prefix):] for name in names if not name.endswith('.mid') and not name.endswith('/verification.json')]
        verification=['verification.json']
        previous=[];outputs={}
        for role,group in [('native',native_files),('midi',midi),('verification',verification)]:
            outputs[role]=self.output(group,list(inputs)+list(previous),role)
            previous.append({'output':role,'files':group,'purpose':'Native generation then MIDI freeze then verification'})
        outputs['bundle']=self.output(names,list(previous),'arrangement')
        outputs['manifest']=self.output(['folders.json'],list(previous)+[
            {'output':'bundle','files':names,'purpose':'Complete published variant folders'}],'manifest')
        request=self.request('jjazzlab_experiments/execute_child_plans.py',inputs,outputs,
            ['{layout:compiled/execution_plan.json}','--out','{output:manifest/folders.json}',
             '--output-root','{scratch:variants}','--scratch','{scratch:native}'],['mido'])
        request['collect']={}
        for role,group in [('native',native_files),('midi',midi),('verification',verification)]:
            request['collect'].update({'{output:'+role+'/'+name+'}':'{scratch:variants/'+prefix+name+'}' for name in group})
        request['collect'].update({'{output:bundle/'+name+'}':'{scratch:variants/'+name+'}' for name in names})
        request['path_aliases']={'{scratch:variants}':'{output:bundle}'}
        request['layouts']={'baseline':{filename:'{input:baseline/'+filename+'}' for filename in inputs['baseline']['files']},
                            'compiled':{'execution_plan.json':'{document:plan}','PROMPT.md':'{input:prompt}'}}
        request['layouts']['baseline']['parameters.json']='{document:parameters}'
        request['documents']={
            'parameters':{'input':'parameters','bindings':{'/source_xml':'{input:source}','/source_midi':'{input:melody}'}},
            'plan':{'input':'plan','bindings':{'/source_xml':'{input:source}','/research_file':'{input:research}','/baseline_folder':'{layout:baseline}'}}}
        request['resources']={}
        for name,filename in [('java','java.py'),('javac','javac.py'),('toolkit','toolkit.jar'),('auditor','audit.py')]:
            self.config['resources'][name]=str(native.resources)
            source={'qualification':'Synthetic fixture only'}
            if name in ('java','javac'):source['execution']={'mode':'python-stdlib','entrypoint':filename}
            event=self.ledger.register_resource('resources.'+name,[filename],label=name,version='synthetic',source=source)
            request['resources'][name]=reference(event['data']['updates'][0])
        self.config['resources']['rhythms']=str(native.resources/'rhythms')
        event=self.ledger.register_resource('resources.rhythms',['style.sty'],label='rhythms',version='synthetic',source={'qualification':'Synthetic only'})
        request['resources']['rhythms']=reference(event['data']['updates'][0])
        request['config']={'tools':{name:{'command':'{tool:'+name+'}'} for name in ('java','javac')},
                           'resources':{'jjazzlab_toolkit':'{resource:toolkit/toolkit.jar}','jjazzlab_rhythms':'{resource:rhythms}',
                                        'midi_audit':'{resource:auditor/audit.py}'}}
        parameters='song/01_drums/parameters.json'
        parameter_tokens=['{output:native/parameters.json}','{output:bundle/'+parameters+'}']
        request['publish_json']=parameter_tokens+['{output:manifest/folders.json}']
        request['publish_text']=['{output:native/input.properties}','{output:bundle/song/01_drums/input.properties}']
        request['publish_hashes']=[{'file':token,'path':'/child_plan','sha256':'/child_plan_sha256'} for token in parameter_tokens]
        _,records=self.run_request(request)
        native_record,midi_record,verification_record,bundle_record,manifest_record=records
        variants=self.ledger.path(bundle_record['history_path']);manifest=self.ledger.path(manifest_record['history_path'])
        result=json.loads((variants/parameters).read_text())
        self.assertEqual(result['child_plan_sha256'],sha(Path(result['child_plan'])))
        self.assertTrue(Path(result['baseline_folder']).is_dir())
        self.assertNotIn('/work/',json.dumps(result))
        properties=(variants/'song/01_drums/input.properties').read_text()
        self.assertNotIn('/work/',properties)
        xml=next(line.split('=',1)[1] for line in properties.splitlines() if line.startswith('xml='))
        self.assertTrue(Path(xml).is_file())
        self.assertIn('/history/',xml)
        self.assertIn(native_record['revision_id'],{dep['revision_id'] for dep in midi_record['dependencies']})
        self.assertIn(midi_record['revision_id'],{dep['revision_id'] for dep in verification_record['dependencies']})
        self.assertEqual({dep['revision_id'] for dep in bundle_record['dependencies']},
                         {native_record['revision_id'],midi_record['revision_id'],verification_record['revision_id']})
        folders=json.loads((manifest/'folders.json').read_text())
        self.assertEqual(folders,[str(variants/'song/01_drums')])
        for suffix in ('.mid','_backing.mid'):
            name='song/01_drums/song__01_drums'+suffix
            self.assertEqual((variants/name).read_bytes(),(self.data/'direct'/name).read_bytes())

    def test_managed_synthetic_render_separates_audio_report_and_persistent_paths(self):
        import shutil
        domain=fixture('render_domain').RenderDomainTests();domain.setUp();self.addCleanup(domain.doCleanups)
        shutil.copytree(domain.data,self.data,dirs_exist_ok=True)
        for path in self.data.rglob('*.json'):
            path.write_text(json.dumps(rewrite(json.loads(path.read_text()),{str(domain.data):str(self.data)})))
        arrangement=self.data/'arrangement';parameters=arrangement/'parameters.json';source=self.data/'source'
        inputs={name:self.imported({path.name:path}) for name,path in [('source',source/'source.musicxml'),
                 ('melody',source/'source.mid'),('baseline',source/'baseline.mid'),('plan',source/'child-plan.json')]}
        dep=self.imported({p.name:p for p in arrangement.iterdir()})
        inputs['parameters']={**dep,'files':['parameters.json']}
        inputs['arrangement']={**dep,'files':[name for name in dep['files'] if name!='parameters.json']}
        listing=self.data/'folders.json';listing.write_text(json.dumps([str(arrangement)]));inputs['listing']=self.imported({'folders.json':listing})
        audio=['song/variant-a/'+name for name in ('arrangement-a.wav','arrangement-a.mp3','arrangement-a_backing.wav','arrangement-a_backing.mp3','CREDITS.md')]
        reports=['verification.json','song/variant-a/render_log.json']
        outputs={'audio':self.output(audio,list(inputs),'render'),
                 'report':self.output(reports,list(inputs)+[{'output':'audio','files':audio,'purpose':'Verified rendered audio'}],'verification')}
        request=self.request('jjazzlab_experiments/render_child_versions.py',inputs,outputs,[],['numpy','soundfile','pyloudnorm','scipy','mido'])
        request['code'].append('tests/arrangement_render_fixture.py')
        request['command']=['{python}','{code:tests/arrangement_render_fixture.py}','{document:listing}',
                            '--out-dir','{output:report}','--audio-dir','{output:audio}']
        request['layouts']={'arrangement':{name:'{input:arrangement/'+name+'}' for name in inputs['arrangement']['files']},
                            'baseline':{'baseline.mid':'{input:baseline}'}}
        request['layouts']['arrangement']['parameters.json']='{document:parameters}'
        request['documents']={'parameters':{'input':'parameters','bindings':{'/source_xml':'{input:source}','/source_midi':'{input:melody}',
                 '/baseline_folder':'{layout:baseline}','/child_plan':'{input:plan}'}},
                 'listing':{'input':'listing','bindings':{'/0':'{layout:arrangement}'}}}
        self.config['resources']['render_fixture']=str(domain.resources)
        # The native backend is replaced by a test instrument; domain checks still execute.
        request['resources']={}
        encoder=domain.resources/'encoder.py';encoder.write_text('#!/usr/bin/env python3\n'+encoder.read_text())
        encoded_tool=self.ledger.register_resource('resources.render_fixture',['encoder.py'],label='synthetic encoder',version='fixture',
                         source={'execution':{'mode':'python-stdlib','entrypoint':'encoder.py'}})
        request['resources']['encoder']=reference(encoded_tool['data']['updates'][0])
        # Register after adding the executable declaration's required shebang.
        resources=self.ledger.register_resource('resources.render_fixture',[p.name for p in domain.resources.iterdir()],label='synthetic render resources',version='fixture',source={'qualification':'Synthetic only'})
        request['resources']['render']=reference(resources['data']['updates'][0])
        request['config']={'tools':{'ffmpeg':{'command':'{tool:encoder}'}},'resources':{
            'midi_audit':'{resource:render/audit.py}','fluidsynth_library':'{resource:render/library}',
            'soundfont_manifest':'{resource:render/fonts.json}','soundfont_credits':'{resource:render/CREDITS.md}'}}
        request['publish_json']=['{output:report/'+name+'}' for name in reports]
        _,records=self.run_request(request)
        audio_path=self.ledger.path(records[0]['history_path']);report_path=self.ledger.path(records[1]['history_path'])
        row=json.loads((report_path/'verification.json').read_text())[0]
        self.assertEqual(row['folder'],str(audio_path/'song/variant-a'))
        self.assertTrue(Path(row['arrangement_folder']).is_dir())
        self.assertNotIn('/work/',json.dumps(row))
        self.assertTrue(row['fixture_synthesis']);self.assertEqual(row['human_listening_review'],'pending')
        self.assertLess(abs(row['final_lufs']+18.3),.05)
        self.assertIn(records[0]['revision_id'],{dep['revision_id'] for dep in records[1]['dependencies']})
