from pathlib import Path
import sys,json,io,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFilter
import numpy as np,cv2,qrcode
from light_sign.vision import ROOT,Counter
from light_sign import store
mode=json.loads((ROOT/'models/policy.json').read_text())['mode'];src=Image.open(ROOT/'data/astronaut_source.png').crop((160,50,300,190));rng=np.random.default_rng(999);rows=[];counter=Counter();out=ROOT/'data/stress';out.mkdir(exist_ok=True)
for i in range(40):
 im=Image.new('RGB',(640,480),(90,90,90));patch=src.resize((140,140));angle=float(rng.choice([-35,-25,25,35]));patch=patch.rotate(angle,resample=Image.Resampling.BILINEAR,fillcolor=(90,90,90))
 if i>=20:ImageDraw.Draw(patch).rectangle((0,80,140,140),fill=(60,60,60))
 im.paste(patch,(240,150));path=out/f'{i:03d}.png';im.save(path);r,_=counter.run(im,mode);rows.append({'path':str(path.relative_to(ROOT)),'expected_count':1,'count':r['count'],'angle':angle,'occluded':i>=20,'latency_ms':r['elapsed_ms']})
summary={'protocol':'Post-selection stress probe; same public source face as development and test. No tuning after these results. Not independent identities. Count-only, no box AP.','mode':mode,'n':40,'correct_counts':sum(r['count']==1 for r in rows),'mae':float(np.mean([abs(r['count']-1)for r in rows])),'rows':rows};(ROOT/'results/stress.json').write_text(json.dumps(summary,indent=2));print({k:v for k,v in summary.items()if k!='rows'})
import tempfile
with tempfile.TemporaryDirectory()as td:
 c=store.connect(Path(td)/'db');k=b'qrcode-test-key';e=store.event(c,'二维码解码测试');token=store.issue(c,k,e,120,now=1000);im=np.array(qrcode.make(token).convert('RGB'));decoded,_,_=cv2.QRCodeDetector().detectAndDecode(im);assert decoded==token;assert store.checkin(c,k,decoded,'DEMO01',True,1001)['ok'];c.close();(ROOT/'results/qr_roundtrip.json').write_text(json.dumps({'decode_equals_token':True,'verified_checkin':True,'image_shape':list(im.shape),'payload_characters':len(token)},indent=2));print('PASS QR image decode and signed check-in')
