from pathlib import Path
import sys,json,io,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import Image,ImageDraw,ImageFilter
import numpy as np,cv2,qrcode
from light_sign.vision import ROOT,Counter
from light_sign import store
EXPERIMENTS=ROOT/'experiments';RESULTS=EXPERIMENTS/'results';RESULTS.mkdir(parents=True,exist_ok=True)
mode=json.loads((ROOT/'models/policy.json').read_text(encoding='utf-8'))['mode'];src=Image.open(EXPERIMENTS/'data/astronaut_source.png').crop((160,50,300,190));rng=np.random.default_rng(999);rows=[];counter=Counter();out=EXPERIMENTS/'data/stress';out.mkdir(parents=True,exist_ok=True)
for i in range(40):
 im=Image.new('RGB',(640,480),(90,90,90));patch=src.resize((140,140));angle=float(rng.choice([-35,-25,25,35]));patch=patch.rotate(angle,resample=Image.Resampling.BILINEAR,fillcolor=(90,90,90))
 if i>=20:ImageDraw.Draw(patch).rectangle((0,80,140,140),fill=(60,60,60))
 im.paste(patch,(240,150));path=out/f'{i:03d}.png';im.save(path);r,_=counter.run(im,mode);rows.append({'path':path.relative_to(EXPERIMENTS).as_posix(),'expected_count':1,'count':r['count'],'angle':angle,'occluded':i>=20,'latency_ms':r['elapsed_ms']})
summary={'protocol':'Post-selection stress probe; same public source face as development and test. No tuning after these results. Not independent identities. Count-only, no box AP.','mode':mode,'n':40,'correct_counts':sum(r['count']==1 for r in rows),'mae':float(np.mean([abs(r['count']-1)for r in rows])),'rows':rows};(RESULTS/'stress.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print({k:v for k,v in summary.items()if k!='rows'})
import tempfile
with tempfile.TemporaryDirectory()as td:
 c=store.connect(Path(td)/'db');k=b'qrcode-test-key';e=store.event(c,'二维码解码测试');token=store.issue(c,k,e,120,now=1000);im=np.array(qrcode.make(token).convert('RGB'));decoded,_,_=cv2.QRCodeDetector().detectAndDecode(im);assert decoded==token;assert store.checkin(c,k,decoded,'DEMO01',True,1001)['ok'];c.close();(RESULTS/'qr_roundtrip.json').write_text(json.dumps({'decode_equals_token':True,'verified_checkin':True,'image_shape':list(im.shape),'payload_characters':len(token)},indent=2),encoding='utf-8');print('PASS QR image decode and signed check-in')
