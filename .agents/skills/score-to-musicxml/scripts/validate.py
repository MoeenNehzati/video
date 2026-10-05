"""Validate exported MusicXML; structural validity is NOT source fidelity."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter,defaultdict
import xml.etree.ElementTree as ET
from lxml import etree
DUR={"whole":F(4),"half":F(2),"quarter":F(1),"eighth":F(1,2),"16th":F(1,4),"32nd":F(1,8),"64th":F(1,16)}
def text(n,path,default=None):return n.findtext(path,default)
def canonical(path):
    root=ET.parse(path).getroot();items=[];div=F(1);meter=None
    for part in root.findall("part"):
        div=F(1);meter=None
        for m in part.findall("measure"):
            cursor=F(0);last=F(0);mn=m.get("number")
            for e in m:
                if e.tag=="attributes":
                    if text(e,"divisions") is not None:div=F(text(e,"divisions"))
                    if e.find("time") is not None:meter=tuple((c.tag,c.text) for c in e.find("time"))
                    items.append(["attributes",part.get("id"),mn,sorted((c.tag,ET.tostring(c,encoding="unicode").strip()) for c in e if c.tag!="divisions")])
                elif e.tag=="backup":cursor-=F(text(e,"duration"))/div
                elif e.tag=="forward":cursor+=F(text(e,"duration"))/div
                elif e.tag=="note":
                    onset=last if e.find("chord") is not None else cursor
                    dur=F(text(e,"duration","0"))/div
                    pitch=tuple(text(e,"pitch/"+k) for k in ["step","alter","octave"]) if e.find("pitch") is not None else None
                    if pitch:pitch=(pitch[0],pitch[1] or "0",pitch[2])
                    lyrics=tuple((l.get("number","1"),text(l,"syllabic","single"),text(l,"text",""),tuple(x.get("type","") for x in l.findall("extend"))) for l in e.findall("lyric"))
                    notation=tuple(sorted((x.tag,tuple(sorted(x.attrib.items()))) for n in e.findall("notations") for x in n))
                    items.append(["note",part.get("id"),mn,str(onset),str(dur),pitch,e.find("rest") is not None,text(e,"type"),len(e.findall("dot")),lyrics,notation,tuple((b.get("number"),b.text) for b in e.findall("beam"))])
                    if e.find("notehead") is not None:
                        nh=e.find("notehead");items.append(["notehead",part.get("id"),mn,str(onset),pitch,nh.text,tuple(sorted(nh.attrib.items()))])
                    for container in e.findall("notations/*"):
                        if len(container):items.append(["notation_detail",part.get("id"),mn,str(onset),container.tag,tuple((child.tag,child.text,tuple(sorted(child.attrib.items()))) for child in container)])
                    if e.find("chord") is None:last=cursor;cursor+=dur
                elif e.tag=="harmony":
                    onset=cursor+F(text(e,"offset","0"))/div
                    items.append(["harmony",part.get("id"),mn,str(onset),tuple(text(e,k,"") for k in ["root/root-step","root/root-alter","kind","bass/bass-step","bass/bass-alter"]),tuple(ET.tostring(d,encoding="unicode") for d in e.findall("degree"))])
                    display=[]
                    for child_path,keys in [("kind",("text","use-symbols","stack-degrees","parentheses-degrees","bracket-degrees")),("root/root-step",("text",)),("bass/bass-step",("text",)),("function",("text",))]:
                        child=e.find(child_path)
                        if child is not None:
                            attrs=tuple((key,child.get(key)) for key in keys if child.get(key) is not None)
                            if attrs:display.append((child_path,attrs))
                    if display:items.append(["harmony_display",part.get("id"),mn,str(onset),tuple(display)])
                elif e.tag=="print" and e.get("new-system")=="yes":items.append(["system",part.get("id"),mn])
                elif e.tag=="direction":
                    for w in e.findall("direction-type/words"):items.append(["words",part.get("id"),mn,w.text])
                elif e.tag=="barline":
                    items.append(["barline",part.get("id"),mn,text(e,"bar-style"),tuple(tuple(sorted(x.attrib.items())) for x in e.findall("repeat")),tuple(tuple(sorted(x.attrib.items())) for x in e.findall("ending"))])
    return items

def audit(path,schema_path=None,expected=None):
    path=Path(path);issues=[];root=ET.parse(path).getroot()
    if schema_path:
        schema=etree.XMLSchema(etree.parse(str(schema_path)))
        if not schema.validate(etree.parse(str(path))):issues.extend("schema: "+str(x) for x in schema.error_log)
    counts=Counter();measure_lengths=[]
    if not root.findall("part"):issues.append("no parts")
    for part in root.findall("part"):
        divisions=F(1);capacity=None;lyric_states={};open_slurs={}
        for m in part.findall("measure"):
            counts["measures"]+=1;cursor=F(0);end=F(0);previous=F(0);occupancy=defaultdict(list)
            mn=m.get("number")
            for e in m:
                if e.tag=="attributes":
                    if text(e,"divisions"):divisions=F(text(e,"divisions"))
                    if divisions<=0:issues.append(f"m{mn}: nonpositive divisions")
                    time=e.find("time")
                    if time is not None and time.find("senza-misura") is None:
                        bs=time.findall("beats");bt=time.findall("beat-type")
                        capacity=sum(sum(F(v) for v in b.text.split("+"))*4/F(t.text) for b,t in zip(bs,bt))
                elif e.tag in ["backup","forward"]:
                    d=F(text(e,"duration"))/divisions
                    cursor+=d if e.tag=="forward" else -d
                    if cursor<0:issues.append(f"m{mn}: timeline before measure start")
                    end=max(end,cursor)
                elif e.tag=="print":
                    if e.get("new-system")=="yes":counts["system_breaks"]+=1
                    if e.get("new-page")=="yes":counts["page_breaks"]+=1
                elif e.tag=="harmony":
                    counts["harmonies"]+=1
                    onset=cursor+F(text(e,"offset","0"))/divisions
                    if onset<0 or capacity is not None and onset>=capacity:issues.append(f"m{mn}: chord onset outside measure")
                elif e.tag=="note":
                    isrest=e.find("rest") is not None;counts["rests" if isrest else "notes"]+=1
                    grace=e.find("grace") is not None
                    duration=F(text(e,"duration","0"))/divisions
                    if not grace and duration<=0:issues.append(f"m{mn}: nonpositive note duration")
                    typ=text(e,"type");dots=len(e.findall("dot"))
                    if typ in DUR and not grace:
                        written=DUR[typ]*sum(F(1,2**i) for i in range(dots+1))
                        tm=e.find("time-modification")
                        if tm is not None:written*=F(text(tm,"normal-notes"))/F(text(tm,"actual-notes"))
                        if duration!=written:issues.append(f"m{mn}: written duration disagrees with playback duration")
                    start=previous if e.find("chord") is not None else cursor
                    voice=text(e,"voice","1")
                    if e.find("chord") is None:
                        if duration:
                            for a,b in occupancy[voice]:
                                if start<b and start+duration>a:issues.append(f"m{mn}: overlapping non-chord events in voice {voice}")
                            occupancy[voice].append((start,start+duration))
                        previous=cursor;cursor+=duration
                    end=max(end,start+duration)
                    for ly in e.findall("lyric"):
                        counts["lyrics"]+=bool(text(ly,"text"))
                        if not text(ly,"text"):continue
                        verse=ly.get("number","1");state=lyric_states.get(verse,False);sy=text(ly,"syllabic","single")
                        if state and sy not in ["middle","end"]:issues.append(f"m{mn}: verse {verse} broken syllable continuation")
                        if not state and sy in ["middle","end"]:issues.append(f"m{mn}: verse {verse} orphan syllable ending")
                        lyric_states[verse]=sy in ["begin","middle"]
                    for slur in e.findall("notations/slur"):
                        key=slur.get("number","1")
                        if slur.get("type")=="start":
                            if key in open_slurs:issues.append(f"m{mn}: duplicate slur start")
                            open_slurs[key]=mn
                        elif slur.get("type")=="stop":
                            if key not in open_slurs:issues.append(f"m{mn}: orphan slur stop")
                            open_slurs.pop(key,None)
            measure_lengths.append({"part":part.get("id"),"measure":mn,"duration":str(end),"capacity":str(capacity),"implicit":m.get("implicit")=="yes"})
            if capacity is not None and end!=capacity:
                allowed=(expected or {}).get("partial_measures",{}).get(mn)
                if allowed is None or end!=F(allowed):issues.append(f"m{mn}: duration {end} differs from meter {capacity}; no verified partial-measure exception")
        if any(lyric_states.values()):issues.append("unfinished lyric word")
        if open_slurs:issues.append("unclosed slur")
    if expected:
        for key,value in expected.get("counts",{}).items():
            if counts[key]!=value:issues.append(f"completeness {key}: {counts[key]} != source {value}")
    return {"file":str(path),"issues":issues,"counts":dict(counts),"measure_lengths":measure_lengths,"structural_pass":not issues,"source_fidelity_certified":False}
