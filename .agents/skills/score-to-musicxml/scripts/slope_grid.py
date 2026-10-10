"""Slope/curvature-aware five-line staff model. Coordinates use a 1600px-wide preview.
Seeds are manually located on SOURCE images; each of five lines is fitted independently.
No note's pitch is read against a constant horizontal reference.
"""
from pathlib import Path
import argparse, hashlib, json, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, load_project
import cv2
import numpy as np

def diatonic_pitch(position, clef_bottom="E4"):
    letters="CDEFGAB"
    base=7*int(clef_bottom[1:])+letters.index(clef_bottom[0])
    octave,index=divmod(base+int(position),7)
    return letters[index]+str(octave)

def evaluate(system,x):
    t=(np.asarray(x)-system["x0"])/(system["x1"]-system["x0"])
    return np.array([np.polynomial.polynomial.polyval(t,c) for c in system["coefficients"]])

def robust_fit(t,y,spacing):
    rng=np.random.default_rng(20260911)
    best=None
    for _ in range(150):
        idx=rng.choice(len(t),4,replace=False)
        c=np.polynomial.polynomial.polyfit(t[idx],y[idx],3)
        residual=np.abs(np.polynomial.polynomial.polyval(t,c)-y)
        keep=residual<max(1.5,spacing*.16)
        score=(int(keep.sum()),-float(np.median(residual)))
        if best is None or score>best[0]:best=(score,keep)
    keep=best[1]
    for _ in range(4):
        c=np.polynomial.polynomial.polyfit(t[keep],y[keep],3)
        residual=np.abs(np.polynomial.polynomial.polyval(t,c)-y)
        keep=residual<max(1.5,spacing*.16)
    return c,keep,residual

def fit_system(gray,seed):
    anchors = seed.get("anchors") if isinstance(seed,dict) else None
    if anchors:
        x0,yl=anchors[0];x1,yr=anchors[-1];sl=sr=seed["spacing"]
    else:
        x0,x1,yl,yr,sl,sr=seed
    h,w=gray.shape
    blur=cv2.GaussianBlur(gray,(0,0),9)
    dark=np.maximum(blur.astype(float)-gray.astype(float),0)
    xs=np.arange(x0+sl,x1-sl,8.0)
    ts=(xs-x0)/(x1-x0)
    coeff=[]; checks=[]
    for k in range(5):
        if anchors:
            ac=np.polynomial.polynomial.polyfit([(x-x0)/(x1-x0) for x,y in anchors],[y for x,y in anchors],min(3,len(anchors)-1))
            pred=np.polynomial.polynomial.polyval(ts,ac)+k*(sl+(sr-sl)*ts)
        else:
            pred=yl+(yr-yl)*ts+k*(sl+(sr-sl)*ts)
        for iteration in range(3):
            ys=[]
            for x,y in zip(xs,pred):
                radius=(sl+sr)/2*(.43 if iteration==0 else .25)
                candidates=np.arange(max(2,int(y-radius)),min(h-2,int(y+radius)+1))
                offsets=np.arange(-int(sl*.9),int(sl*.9)+1)
                xx=np.clip((x+offsets).astype(int),0,w-1)
                slope=(yr-yl+k*(sr-sl))/(x1-x0)
                yy=np.clip(np.rint(candidates[:,None]+offsets[None,:]*slope).astype(int),1,h-2)
                score=dark[yy,xx[None,:]].mean(axis=1)
                peak=int(score.argmax())
                # Subpixel center of the ridge's 3 samples.
                lo=max(0,peak-1);hi=min(len(score),peak+2)
                weights=np.maximum(score[lo:hi]-score.min(),.01)
                ys.append(float(np.average(candidates[lo:hi],weights=weights)))
            c,keep,res=robust_fit(ts,np.array(ys),(sl+sr)/2)
            pred=np.polynomial.polynomial.polyval(ts,c)
        coeff.append(c.tolist())
        checks.append({"inlier_fraction":float(keep.mean()),"median_residual_px":float(np.median(res))})
    sys={"x0":x0,"x1":x1,"coefficients":coeff,"line_checks":checks}
    lines=evaluate(sys,np.linspace(x0,x1,200))
    gaps=np.diff(lines,axis=0)
    sys["min_spacing"]=float(gaps.min());sys["max_spacing"]=float(gaps.max())
    sys["accepted_geometry"]=bool(gaps.min()>min(sl,sr)*.6 and gaps.max()<max(sl,sr)*1.5 and min(c["inlier_fraction"] for c in checks)>.65)
    if not sys["accepted_geometry"]:raise ValueError("Staff fit fails quality gates: "+str(sys))
    return sys

def process(source,seeds,out):
    out=Path(out)
    original=cv2.imread(str(source))
    if original is None: raise ValueError("Source is not a readable image")
    if not isinstance(seeds,list) or not seeds: raise ValueError("Provide at least one staff seed")
    out.mkdir(parents=True,exist_ok=True)
    scale=1600/original.shape[1]
    im=cv2.resize(original,(1600,round(original.shape[0]*scale)))
    gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    systems=[]
    for i,seed in enumerate(seeds):
        s=fit_system(gray,seed);s["system"]=i+1
        systems.append(s)
        x=np.arange(round(s["x0"]),round(s["x1"])+1)
        curves=evaluate(s,x)
        overlay=im.copy()
        # Five staff lines in red. Intervening spaces and ledger guides in cyan.
        for k in range(-4,15):
            if k<=0:y=curves[4]-k/2*(curves[4]-curves[3])
            elif k>=8:y=curves[0]-(k-8)/2*(curves[1]-curves[0])
            else:
                ix=4-k//2
                y=curves[ix] if k%2==0 else (curves[ix]+curves[ix-1])/2
            pts=np.column_stack([x,np.rint(y)]).astype(np.int32)
            color=(40,40,235) if k in [0,2,4,6,8] else (220,160,20)
            if k in [0,2,4,6,8]:cv2.polylines(overlay,[pts],False,color,1,cv2.LINE_AA)
            else:
                for j in range(0,len(pts),12):cv2.polylines(overlay,[pts[j:j+5]],False,color,1,cv2.LINE_AA)
            cv2.putText(overlay,diatonic_pitch(k),(max(0,int(x[0])-42),int(y[0])+4),cv2.FONT_HERSHEY_SIMPLEX,.35,color,1,cv2.LINE_AA)
        top=max(0,int(curves.min()-90));bottom=min(im.shape[0],int(curves.max()+95))
        cv2.imwrite(str(out/f"system_{i+1}_grid.png"),overlay[top:bottom])
        cv2.imwrite(str(out/f"system_{i+1}_source.png"),im[top:bottom])
        s["crop_y"]=[top,bottom]
        # Flatten by interpolation through each individually fitted staff line.
        # Uniform output spacing; x is unchanged. Save map definition, not a lossy replacement source.
        target_spacing=float(np.median(np.diff(curves,axis=0)))
        target_lines=np.arange(5)*target_spacing+85
        out_h=int(target_lines[-1]+100)
        xx,yy=np.meshgrid(np.arange(im.shape[1]),np.arange(out_h))
        all_lines=evaluate(s,np.clip(np.arange(im.shape[1]),s["x0"],s["x1"]))
        map_y=np.empty_like(yy,dtype=np.float32)
        for col in range(im.shape[1]):
            map_y[:,col]=np.interp(np.arange(out_h),target_lines,all_lines[:,col])
            upper=np.arange(out_h)<target_lines[0]; lower=np.arange(out_h)>target_lines[-1]
            map_y[upper,col]=all_lines[0,col]+(np.arange(out_h)[upper]-target_lines[0])*(all_lines[1,col]-all_lines[0,col])/target_spacing
            map_y[lower,col]=all_lines[-1,col]+(np.arange(out_h)[lower]-target_lines[-1])*(all_lines[-1,col]-all_lines[-2,col])/target_spacing
        flat=cv2.remap(im,xx.astype(np.float32),map_y,cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))
        cv2.imwrite(str(out/f"system_{i+1}_dewarped.png"),flat)
    result={"source":str(source),"source_sha256":hashlib.sha256(Path(source).read_bytes()).hexdigest(),"source_dimensions":[original.shape[1],original.shape[0]],"preview_width":1600,"source_to_preview_scale":scale,"seed_units":"1600px-wide source preview","seeds":seeds,"systems":systems}
    (out/"geometry.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    add_config_argument(p)
    p.add_argument("source");p.add_argument("seeds");p.add_argument("output")
    a=p.parse_args(argv)
    config=load_project(a.config_root)
    source=data_path(config,a.source,must_exist=True)
    seeds=data_path(config,a.seeds,must_exist=True)
    output=data_path(config,a.output,directory=True)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Geometry output directory must be new or empty")
    r=process(source,json.loads(seeds.read_text(encoding="utf-8-sig")),output)
    print(json.dumps([{"system":s["system"],"checks":s["line_checks"]} for s in r["systems"]]))

if __name__=="__main__":
    main()
