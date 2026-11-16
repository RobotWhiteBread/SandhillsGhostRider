import json, numpy as np, pickle, zlib, base64, math
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
import shapely
from shapely.geometry import shape, box, Polygon, MultiPolygon
from shapely.ops import transform
G="/home/claude/sandhills/geo/"
g=json.load(open(G+"geo.json")); W,E,N,S,X0,X1,Z0,Z1,NX,NY,MX,MZ=[g[k] for k in "W E N S X0 X1 Z0 Z1 NX NY MX MZ".split()]
LON0,LAT0=-99.30228,42.01215
fj=json.load(open("fine.json")); FX0,FX1,FZ0,FZ1,FNX,FNY,FW,FN,P=[fj[k] for k in "FX0 FX1 FZ0 FZ1 FNX FNY FW FN P".split()]
DXF,DZF=P*MX,P*MZ; DXC,DZC=(X1-X0)/NX,(Z1-Z0)/NY
ss=lambda a,b,x: (lambda t:t*t*(3-2*t))(np.clip((x-a)/(b-a),0,1))
F=np.load("dem5.npy"); Y5=F-700.0
dem=np.load(G+"dem20.npy")
A=np.asarray(Image.open("naip5_full.png")).astype(np.float32); V=A.mean(2); exg=A[...,1]-(A[...,0]+A[...,2])/2
L=pickle.load(open("wet.pkl","rb"))
def toloc(geom): return transform(lambda x,y,z=None:((x-LON0)*MX,(LAT0-y)*MZ),geom)
def cls(a):
    if a[:1]=='L' or a[:3] in ('PUB','PAB') or a[:4] in ('R2UB','R3UB'): return 'water'
    if a[:5] in ('PEM1F','PEM1G'): return 'marsh'
    if a[:5]=='PEM1C': return 'wetC'
    if a[:3]=='PEM': return 'wetA'
    if a[:3]=='PFO': return 'forest'
    if a[:3]=='PSS': return 'shrub'
    if 'US' in a[:5] or a[:4]=='R4SB': return 'shore'
    return 'other'
polys=[]
for a,ac,gj in L:
    try: gg=toloc(shape(gj))
    except Exception: continue
    if not gg.is_valid: gg=gg.buffer(0)
    polys.append((cls(a),a,gg))
import collections; print(collections.Counter(c for c,_,_ in polys))
# ---------- rasterize classes on a grid (supersampled) ----------
def rast(gx0,gz0,dx,dz,nx,ny,ssn,order,vals):
    im=Image.new("L",(nx*ssn,ny*ssn),0); dr=ImageDraw.Draw(im)
    def pts(ring): return [((x-gx0)/dx*ssn,(z-gz0)/dz*ssn) for x,z in ring.coords]
    for c in order:
        v=vals[c]
        for cc,a,gg in polys:
            if cc!=c: continue
            for p in (gg.geoms if hasattr(gg,'geoms') else [gg]):
                if p.geom_type!='Polygon' or p.is_empty: continue
                dr.polygon(pts(p.exterior),fill=v)
                for h in p.interiors: dr.polygon(pts(h),fill=0)
    return np.asarray(im.resize((nx,ny),Image.BOX)).astype(np.float32)/255
WV={'wetA':153,'wetC':199,'marsh':255}
nwi_f=rast(FX0,FZ0,DXF,DZF,FNX,FNY,2,['wetA','wetC','marsh'],WV)
water_f=rast(FX0,FZ0,DXF,DZF,FNX,FNY,2,['water','marsh'],{'water':255,'marsh':0})
shore_f=rast(FX0,FZ0,DXF,DZF,FNX,FNY,2,['shore'],{'shore':255})
forest_f=rast(FX0,FZ0,DXF,DZF,FNX,FNY,1,['forest'],{'forest':255})
shrub_f=rast(FX0,FZ0,DXF,DZF,FNX,FNY,1,['shrub'],{'shrub':255})
print("fine fractions wet",(nwi_f>.3).mean(),"water",(water_f>.5).mean(),"shore",(shore_f>.5).mean(),"forest",(forest_f>.5).mean(),"shrub",(shrub_f>.5).mean())
# ---------- fine channels ----------
tpi=Y5-ndi.uniform_filter(Y5,size=(55,73))
ridge=ss(0.5,6.5,tpi)
na=Image.open("naip5_full.png"); 
print("V pct fine",np.percentile(V,[50,90,98]),"exg",np.percentile(exg,[10,50,90]))
nc=np.asarray(Image.open(G+"naip_crop.jpg").convert("RGB")).astype(np.float32); Vc=nc.mean(2); exgc=nc[...,1]-(nc[...,0]+nc[...,2])/2
print("V pct coarse",np.percentile(Vc,[50,90,98]),"exg",np.percentile(exgc,[10,50,90]))
# map fine stats onto coarse thresholds by percentile matching
def pm(x,ref,src):
    qs=np.linspace(0,100,201); return np.interp(x,np.percentile(src,qs),np.percentile(ref,qs))
Vm=pm(V,Vc,V); exgm=pm(exg,exgc,exg)
sand=np.maximum(ss(156,188,Vm)*ss(17,10,exgm), shore_f*.65)
spec_wet=ss(15,24,exgm)*(0.45+0.55*ss(2.5,-2.5,tpi))
wet=np.maximum(spec_wet*.8, nwi_f)
print("sand frac",(sand>.5).mean(),"wet frac",(wet>.5).mean(),"marsh",(wet>.9).mean(),"ridge",(ridge>.5).mean())
# alpha: ridge*.8, open water -> 1
alpha=np.where(water_f>.5,1.0,ridge*.8)
# ---------- trees from the aerial ----------
med=ndi.zoom(ndi.median_filter(V[::2,::2],size=15),2,order=1)[:FNY,:FNX]
tree=(V<82)&(V<med-30)&(A[...,2]<A[...,1]+4)&(water_f<.3)
lab,n=ndi.label(tree); objs=ndi.find_objects(lab)
rng=np.random.default_rng(7); trees=[]
forest_d=ndi.binary_dilation(forest_f>.3,iterations=3); shrub_d=ndi.binary_dilation(shrub_f>.3,iterations=2); wet_d=ndi.binary_dilation(wet>.45,iterations=3)
for k,sl in enumerate(objs):
    if sl is None: continue
    m=lab[sl]==k+1; jj,ii=np.nonzero(m); jj=jj+sl[0].start; ii=ii+sl[1].start; s=len(jj)
    fr=forest_d[jj,ii].mean(); sh=shrub_d[jj,ii].mean(); wt=wet_d[jj,ii].mean()
    h=max(sl[0].stop-sl[0].start,sl[1].stop-sl[1].start); thin=s/(h*h)
    if sh>.5: typ=2; per=1
    elif fr>.5 or (wt>.5 and s>=3 and thin>.25): typ=1; per=5
    else: typ=0; per=1
    cnt=max(1,int(round(s/per))); idx=rng.choice(s,size=min(cnt,s),replace=False)
    for q in idx:
        x=FX0+(ii[q]+rng.random())*DXF; z=FZ0+(jj[q]+rng.random())*DZF
        sc=(.75+.5*rng.random()) if typ!=1 else min(1.5,.75+.12*math.sqrt(s/cnt)+.3*rng.random())
        trees.append([round(x,1),round(z,1),typ,round(sc,2)])
print("trees",len(trees),collections.Counter(t[2] for t in trees))
# ---------- 10 m height grid (mesh) ----------
H10=Y5.reshape(FNY//2,2,FNX//2,2).mean(axis=(1,3))
# ---------- water polygons with levels ----------
crect=box(X0+40,Z0+40,X1-40,Z1-40)
def level(p,q):
    minx,minz,maxx,maxz=p.bounds
    if minx>FX0 and maxx<FX1 and minz>FZ0 and maxz<FZ1:
        i0,i1=int((minx-FX0)/DXF),int((maxx-FX0)/DXF)+1; j0,j1=int((minz-FZ0)/DZF),int((maxz-FZ0)/DZF)+1
        sub=Y5[j0:j1,i0:i1]; gx,gz=FX0+(np.arange(i0,i1)+.5)*DXF,FZ0+(np.arange(j0,j1)+.5)*DZF
    else:
        i0,i1=max(0,int((minx-X0)/DXC)),min(NX,int((maxx-X0)/DXC)+1); j0,j1=max(0,int((minz-Z0)/DZC)),min(NY,int((maxz-Z0)/DZC)+1)
        sub=dem[j0:j1,i0:i1]-700.0; gx,gz=X0+(np.arange(i0,i1)+.5)*DXC,Z0+(np.arange(j0,j1)+.5)*DZC
    if sub.size==0: return None
    XX,ZZ=np.meshgrid(gx,gz); inside=shapely.contains_xy(p,XX,ZZ)
    vals=sub[inside] if inside.sum()>=3 else sub.ravel()
    return float(np.percentile(vals,q))
waters=[]; nv=0
for c,a,gg in polys:
    if c not in ('water','marsh'): continue
    gg=gg.intersection(crect)
    for p in (gg.geoms if hasattr(gg,'geoms') else [gg]):
        if p.geom_type!='Polygon' or p.area<40: continue
        p=p.simplify(1.2,preserve_topology=True)
        if p.is_empty or p.geom_type!='Polygon': continue
        lv=level(p,30 if c=='water' else 18)
        if lv is None: continue
        lv+= .1 if c=='water' else .04
        rings=[[round(v,1) for xy in list(p.exterior.coords)[:-1] for v in xy]]+[[round(v,1) for xy in list(h.coords)[:-1] for v in xy] for h in p.interiors if Polygon(h).area>20]
        nv+=sum(len(r) for r in rings)//2
        waters.append([round(lv,2),1 if c=='marsh' else 0]+[rings])
print("water polys",len(waters),"verts",nv)
# ---------- coarse wet channel refresh ----------
nwi_c=rast(X0,Z0,DXC,DZC,NX,NY,2,['wetA','wetC','marsh'],WV)
np.save("nwi_c.npy",nwi_c)
# ---------- pack fine ----------
hq=np.clip(np.round((F-683.0)*200.0),0,65535).astype(np.int64)
d=hq.copy(); d[:,1:]=hq[:,1:]-hq[:,:-1]; d[1:,0]=hq[1:,0]-hq[:-1,0]
# second-order: predict from row above too
d2=d.copy(); d2[1:,1:]=d[1:,1:]-d[:-1,1:]
q8=lambda a:np.round(np.clip(a,0,1)*255).astype(np.uint8).tobytes()
raw=(d2&0xFFFF).astype('<u2').tobytes()+q8(sand)+q8(wet)+q8(alpha)
z=zlib.compress(raw,9); print("fine raw",len(raw),"z",len(z))
open("fine.bin","wb").write(z)
meta=dict(FX0=FX0,FX1=FX1,FZ0=FZ0,FZ1=FZ1,FNX=FNX,FNY=FNY,HQ=200.0,H0=683.0,trees=trees,waters=waters)
json.dump(meta,open("fine_meta.json","w"),separators=(',',':'))
na.save("naip5.jpg",quality=84)
import os; print({f:os.path.getsize(f) for f in ["fine.bin","fine_meta.json","naip5.jpg"]})
