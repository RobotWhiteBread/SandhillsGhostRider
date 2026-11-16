import json, numpy as np, tifffile
from PIL import Image
from scipy import ndimage as ndi
D="/mnt/user-data/uploads/SANDHILLS/data/"; G="/home/claude/sandhills/geo/"
g=json.load(open(G+"geo.json")); W,E,N,S,X0,X1,Z0,Z1,NX,NY,MX,MZ=[g[k] for k in "W E N S X0 X1 Z0 Z1 NX NY MX MZ".split()]
LON0,LAT0=-99.30228,42.01215
dw=tifffile.imread(D+"dem_5m_w.tif"); de=tifffile.imread(D+"dem_5m_e.tif")
F=np.concatenate([dw,de],axis=1).astype(np.float32); print(F.shape, np.isnan(F).sum(), F.min(), F.max())
np.save("dem5.npy",F)
FW,FN,P=-99.4,42.075,5e-5
FX0=(FW-LON0)*MX; FX1=FX0+F.shape[1]*P*MX; FZ0=(LAT0-FN)*MZ; FZ1=FZ0+F.shape[0]*P*MZ
print("fine rect",FX0,FX1,FZ0,FZ1,"cell",P*MX,P*MZ)
json.dump(dict(FX0=FX0,FX1=FX1,FZ0=FZ0,FZ1=FZ1,FNX=F.shape[1],FNY=F.shape[0],FW=FW,FN=FN,P=P),open("fine.json","w"))
dem=np.load(G+"dem20.npy")
# sample coarse dem at fine pixel centers (subsample every 8th)
jj,ii=np.mgrid[0:F.shape[0]:8,0:F.shape[1]:8]
x=FX0+(ii+.5)*P*MX; z=FZ0+(jj+.5)*P*MZ
fx=(x-X0)/(X1-X0)*NX-.5; fz=(z-Z0)/(Z1-Z0)*NY-.5
c=ndi.map_coordinates(dem,[fz,fx],order=1)
f=F[::8,::8]; d=f-c; print("fine-coarse mean",d.mean(),"std",d.std(),"p5 p95",np.percentile(d,[5,95]))
# smoothed comparison to check shift
fs=ndi.uniform_filter(F,size=(4,5))[::8,::8]; print("smoothed diff std",(fs-c).std())
nw=Image.open(D+"naip_5m_w.jpg").convert("RGB"); ne=Image.open(D+"naip_5m_e.jpg").convert("RGB")
NA=Image.new("RGB",(3700,2000)); NA.paste(nw,(0,0)); NA.paste(ne,(1850,0)); NA.save("naip5_full.png")
# previews: home (x=0,z=0)
def crop(x,z,r,name):
    i=int((x-FX0)/(P*MX)); j=int((z-FZ0)/(P*MZ)); NA.crop((i-r,j-r,i+r,j+r)).resize((600,600)).save(name)
crop(0,0,150,"pv_home.png"); crop(-2922,-5188,150,"pv_cem.png")
