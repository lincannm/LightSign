from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from PIL import Image,ImageFilter
ROOT=Path(__file__).resolve().parents[1]
def main():
 from skimage import data
 (ROOT/'data').mkdir(parents=True,exist_ok=True)
 source=Image.fromarray(data.astronaut());source.save(ROOT/'data/astronaut_source.png');crop=source.crop((160,50,300,190));manifest=[]
 for split,seed in [('development',1010),('test',20261010)]:
  rng=np.random.default_rng(seed);out=ROOT/'data'/split;out.mkdir(exist_ok=True)
  for i in range(80):
   n=i%5;im=Image.new('RGB',(640,480),tuple(int(x)for x in rng.integers(50,200,3)));boxes=[]
   for k in range(n):
    side=int(rng.integers(60,145));x=int(rng.integers(10,160-side if side<145 else 16))+(k%2)*320;y=int(rng.integers(10,80))+(k//2)*240
    patch=crop.resize((side,side),Image.Resampling.BILINEAR);im.paste(patch,(x,y));s=side/140;boxes.append([x+17*s,y+16*s,96*s,96*s])
   condition=['clean','dark','blur','dark_blur'][i//20];factor=float(rng.uniform(.12,.35))if'dark'in condition else 1.;im=Image.fromarray(np.uint8(np.array(im)*factor))
   if'blur'in condition:im=im.filter(ImageFilter.GaussianBlur(1.2))
   f=out/f'{i:03d}.png';im.save(f);manifest.append({'path':f.relative_to(ROOT).as_posix(),'split':split,'condition':condition,'count':n,'boxes':boxes,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'brightness_factor':factor})
 (ROOT/'data/manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');(ROOT.parent/'samples').mkdir(exist_ok=True)
 for name,i in [('多人合成样例',4),('合成弱光样例',24),('无人场景',0)]:
  import shutil
  shutil.copy2(ROOT/'data/test'/f'{i:03d}.png',ROOT.parent/'samples'/f'{name}.png')
 print('160 synthetic compositions; source shared across development/test; NOT independent people')
if __name__=='__main__':main()
