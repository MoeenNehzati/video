"""Offline FluidSynth renderer with explicit per-channel sample-library selection."""
from pathlib import Path
import ctypes as C, os, json, hashlib, struct, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from bin.read_config import ROOT
from verification import require
import numpy as np
import mido
P=C.c_void_p;I=C.c_int;F=C.c_float;D=C.c_double;S=C.c_char_p
SPECS={
 'new_fluid_settings':(P,[]),'delete_fluid_settings':(None,[P]),
 'fluid_settings_setnum':(I,[P,S,D]),'fluid_settings_setint':(I,[P,S,I]),
 'new_fluid_synth':(P,[P]),'delete_fluid_synth':(None,[P]),
 'fluid_synth_sfload':(I,[P,S,I]),'fluid_synth_program_select':(I,[P,I,I,I,I]),
 'fluid_synth_system_reset':(I,[P]),'fluid_synth_all_sounds_off':(I,[P,I]),
 'fluid_synth_noteon':(I,[P,I,I,I]),'fluid_synth_noteoff':(I,[P,I,I]),
 'fluid_synth_set_gen':(I,[P,I,I,F]),
 'fluid_synth_cc':(I,[P,I,I,I]),'fluid_synth_pitch_bend':(I,[P,I,I]),
 'fluid_synth_write_float':(I,[P,I,P,I,I,P,I,I]),
 'fluid_synth_set_reverb_group_roomsize':(I,[P,I,D]),'fluid_synth_set_reverb_group_damp':(I,[P,I,D]),
 'fluid_synth_set_reverb_group_width':(I,[P,I,D]),'fluid_synth_set_reverb_group_level':(I,[P,I,D]),
 'fluid_synth_set_reverb_on':(I,[P,I,I]),'fluid_synth_set_chorus_on':(I,[P,I,I]),
}
def load_library(path):
 # Loading native software happens only during explicit renderer construction.
 handle = os.add_dll_directory(str(path.parent)) if os.name == 'nt' else None
 try:
  lib = C.CDLL(str(path))
  for name,(result,args) in SPECS.items():
   function=getattr(lib,name);function.restype=result;function.argtypes=args
  return lib, handle
 except BaseException:
  if handle is not None:handle.close()
  raise

def sf_presets(path):
 # Traverse RIFF/LIST structure; sample data can coincidentally contain the bytes 'phdr'.
 with path.open('rb') as f:
  require(f.read(4)==b'RIFF', "FluidSynth/sample validation failed: f.read(4)==b'RIFF'");size=struct.unpack('<I',f.read(4))[0];require(f.read(4)==b'sfbk', "FluidSynth/sample validation failed: f.read(4)==b'sfbk'")
  while f.tell()<size+8:
   tag=f.read(4);length=struct.unpack('<I',f.read(4))[0];start=f.tell()
   if tag==b'LIST' and f.read(4)==b'pdta':
    while f.tell()<start+length:
     sub=f.read(4);n=struct.unpack('<I',f.read(4))[0]
     if sub==b'phdr':
      data=f.read(n);out=[]
      for i in range(0,n-38,38):
       name,program,bank,*_=struct.unpack('<20sHHHIII',data[i:i+38]);out.append({'name':name.split(b'\0')[0].decode('latin1'),'bank':bank,'program':program})
      return out
     f.seek(n+(n%2),1)
   f.seek(start+length+(length%2))
 raise ValueError('No presets '+str(path))

def banks(manifest):
 """The external manifest maps routing keys to SF2 paths and attribution."""
 result={}
 for key,value in json.loads(manifest.read_text(encoding='utf-8')).items():
  path=Path(value['path'])
  if not path.is_absolute():path=manifest.parent/path
  path=path.resolve(strict=True)
  if path.is_relative_to(ROOT):raise ValueError('soundfont_manifest libraries must be outside the repository')
  if not value.get('credits'):raise ValueError('Missing sample credits for '+key)
  result[key]={**value,'path':str(path),'presets':sf_presets(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 for key in ['generaluser','nylon','steel','bass','clarinet','drums','salamander']:
  if key not in result:raise ValueError('Missing routing library '+key)
 return result

class Renderer:
 def __init__(self,banks,library_path,rate=48000):
  self.lib,self.dll_handle=load_library(Path(library_path))
  self.banks=banks;self.rate=rate;self.settings=self.lib.new_fluid_settings()
  for name,val in [('synth.sample-rate',rate),('synth.gain',.25)]:require(self.lib.fluid_settings_setnum(self.settings,name.encode(),val)==0, 'FluidSynth/sample validation failed: self.lib.fluid_settings_setnum(self.settings,name.encode(),val)==0')
  for name,val in [('synth.polyphony',512),('synth.cpu-cores',1),('synth.threadsafe-api',0),('synth.midi-channels',32)]:require(self.lib.fluid_settings_setint(self.settings,name.encode(),val)==0, 'FluidSynth/sample validation failed: self.lib.fluid_settings_setint(self.settings,name.encode(),val)==0')
  self.synth=self.lib.new_fluid_synth(self.settings);require(self.synth, 'FluidSynth/sample validation failed: self.synth')
  self.ids={}
  for key,b in banks.items():
   print('Loading',key,flush=True);self.ids[key]=self.lib.fluid_synth_sfload(self.synth,b['path'].encode(),0);require(self.ids[key]>=0, 'FluidSynth/sample validation failed: self.ids[key]>=0')
  self.probe_cache={};self.level_cache={}
 def frames(self,n):
  data=np.zeros((n,2),np.float32)
  require(self.lib.fluid_synth_write_float(self.synth,n,data.ctypes.data,0,2,data.ctypes.data,1,2)==0, 'FluidSynth/sample validation failed: self.lib.fluid_synth_write_float(self.synth,n,data.ctypes.data,0,2,data.ctypes.data,1,2)==0')
  return data
 def select(self,ch,key,bank,program):
  require(self.lib.fluid_synth_program_select(self.synth,ch,self.ids[key],bank,program)==0, (ch,key,bank,program))
 def sounding(self,key,bank,program,pitch):
  k=(key,bank,program,pitch)
  if k not in self.probe_cache:
   self.lib.fluid_synth_all_sounds_off(self.synth,31);self.select(31,key,bank,program)
   self.lib.fluid_synth_cc(self.synth,31,7,100);self.lib.fluid_synth_noteon(self.synth,31,pitch,80)
   data=self.frames(self.rate//4);self.probe_cache[k]=float(np.max(np.abs(data)))>1e-6
   self.lib.fluid_synth_all_sounds_off(self.synth,31)
  return self.probe_cache[k]
 def route(self,channel,program):
  if channel==9:key='drums'
  elif program in (0,1):key='salamander'
  elif program==24:key='nylon'
  elif program==25:key='steel'
  elif program in (32,33,34,35):key='bass'
  elif program==71:key='clarinet'
  else:return 'generaluser',0,program
  preset=self.banks[key]['presets'][0];return key,preset['bank'],preset['program']
 def test_level(self,key,bank,program,pitches):
  signature=(key,bank,program,tuple(pitches))
  if signature not in self.level_cache:
   self.lib.fluid_synth_system_reset(self.synth)
   self.lib.fluid_synth_set_reverb_on(self.synth,-1,0);self.lib.fluid_synth_set_chorus_on(self.synth,-1,0)
   self.select(30,key,bank,program);self.lib.fluid_synth_set_gen(self.synth,30,48,0.)
   self.lib.fluid_synth_cc(self.synth,30,7,100);self.lib.fluid_synth_cc(self.synth,30,11,127)
   data=[]
   for pitch in pitches:
    self.lib.fluid_synth_all_sounds_off(self.synth,30);self.lib.fluid_synth_noteon(self.synth,30,pitch,72)
    data.append(self.frames(int(self.rate*.6)));self.lib.fluid_synth_noteoff(self.synth,30,pitch)
    data.append(self.frames(int(self.rate*.25)))
   signal=np.concatenate(data).astype(np.float64);self.level_cache[signature]=float(np.sqrt(np.mean(signal*signal)))
   self.lib.fluid_synth_all_sounds_off(self.synth,30)
  return self.level_cache[signature]
 def render(self,path,room):
  midi=mido.MidiFile(path)
  self.lib.fluid_synth_system_reset(self.synth)
  self.lib.fluid_synth_set_reverb_on(self.synth,-1,0);self.lib.fluid_synth_set_chorus_on(self.synth,-1,0)
  programs={};used={};lead_channel=None
  for track in midi.tracks:
   is_lead=any(m.type=='track_name' and 'Original melody' in m.name for m in track)
   if is_lead:lead_channel=next(m.channel for m in track if m.type=='note_on' and m.velocity>0)
   for msg in track:
    if msg.type=='program_change':programs[msg.channel]=msg.program
    if msg.type=='note_on' and msg.velocity>0:used.setdefault(msg.channel,set()).add(msg.note)
  routes={};fallbacks={}
  for ch,pitches in used.items():
   program=programs.get(ch,0);key,bank,preset=self.route(ch,program)
   missing=[pitch for pitch in sorted(pitches) if not self.sounding(key,bank,preset,pitch)]
   if missing:
    # Dedicated drum kit covers its own kit pieces; GM percussion provides e.g. shakers/congas.
    if ch!=9:raise RuntimeError(('Missing pitched samples',ch,key,missing))
    fallbacks[ch]=set(missing)
   routes[ch]={'library':key,'bank':bank,'preset':preset,'gm_program':program,'required_pitches':sorted(pitches),'fallback_percussion_pitches':missing}
  for ch,r in routes.items():
   available=[n for n in r['required_pitches'] if n not in r['fallback_percussion_pitches']]
   picks=sorted(set(available[round(i*(len(available)-1)/3)] for i in range(4))) if available else [36,38,42]
   reference_program=0 if ch==lead_channel else r['gm_program']
   reference_bank=128 if ch==9 else 0
   if ch==9:reference_program=0
   a=self.test_level(r['library'],r['bank'],r['preset'],picks)
   b=self.test_level('generaluser',reference_bank,reference_program,picks)
   require(a>1e-8 and b>1e-8, (ch,r['library'],a,b))
   gain_db=float(np.clip(20*np.log10(b/a),-18,18))
   r['sample_level_calibration_db']=round(gain_db,4)
   r['calibration_reference']='GeneralUser GS program '+str(reference_program)+' (lead instruments matched to piano)'
   r['calibration_pitches']=picks
  self.lib.fluid_synth_system_reset(self.synth)
  self.lib.fluid_synth_set_reverb_on(self.synth,-1,1)
  self.frames(self.rate*10) # Clear prior song/probe release and reverb buffers.
  for ch,r in routes.items():
   self.select(ch,r['library'],r['bank'],r['preset'])
   require(self.lib.fluid_synth_set_gen(self.synth,ch,48,-10*r['sample_level_calibration_db'])==0, "FluidSynth/sample validation failed: self.lib.fluid_synth_set_gen(self.synth,ch,48,-10*r['sample_level_calibration_db'])==0")
  if fallbacks:self.select(25,'generaluser',128,0)
  rooms={'studio':(.25,.55,35,.13),'hall':(.86,.32,85,.36),'chamber':(.5,.5,60,.22)}
  settings=rooms[room]
  for suffix,value in zip(['roomsize','damp','width','level'],settings):getattr(self.lib,'fluid_synth_set_reverb_group_'+suffix)(self.synth,-1,value)
  self.lib.fluid_synth_set_reverb_on(self.synth,-1,1)
  events=[];seconds=0.
  for msg in midi:seconds+=msg.time;events.append((round(seconds*self.rate),msg))
  length=round((seconds+5)*self.rate);output=np.zeros((length,2),np.float32);cursor=0
  for at,msg in events:
   if at>cursor:output[cursor:at]=self.frames(at-cursor);cursor=at
   if msg.is_meta:continue
   ch=getattr(msg,'channel',None)
   if ch is None:continue # Deliberately retain explicit sample selections instead of GM reset sysex.
   targets=[ch]
   if msg.type in ('note_on','note_off') and ch in fallbacks and msg.note in fallbacks[ch]:targets=[25]
   elif msg.type=='control_change' and ch in fallbacks:targets=[ch,25]
   for dest in targets:
    if msg.type=='note_on':self.lib.fluid_synth_noteon(self.synth,dest,msg.note,msg.velocity)
    elif msg.type=='note_off':self.lib.fluid_synth_noteoff(self.synth,dest,msg.note)
    elif msg.type=='control_change' and msg.control not in (0,32,91,93,121):self.lib.fluid_synth_cc(self.synth,dest,msg.control,msg.value)
    elif msg.type=='pitchwheel':self.lib.fluid_synth_pitch_bend(self.synth,dest,msg.pitch+8192)
  output[cursor:]=self.frames(length-cursor)
  # A short fade only in the far reverb tail, after every written note has ended.
  fade=min(self.rate,len(output));output[-fade:]*=np.linspace(1,0,fade,dtype=np.float32)[:,None]
  require(np.isfinite(output).all() and np.max(abs(output))>1e-5, 'FluidSynth/sample validation failed: np.isfinite(output).all() and np.max(abs(output))>1e-5')
  return output,{'routes':routes,'reverb':dict(zip(['roomsize','damping','width','level'],settings)),'sample_rate':self.rate,'release_tail_seconds':5}
 def close(self):
  self.lib.delete_fluid_synth(self.synth);self.lib.delete_fluid_settings(self.settings)
  if self.dll_handle is not None:self.dll_handle.close()


class CounterRenderer(Renderer):
 """Preserve the selected supporting instrument independently of GM program."""
 def route(self,channel,program):
  if channel==self.counter_channel:
   key=self.counter_library;preset=self.banks[key]['presets'][0]
   return key,preset['bank'],preset['program']
  return super().route(channel,program)
