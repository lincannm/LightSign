from pathlib import Path
import sys,json,tempfile,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np,cv2,qrcode
from light_sign import store
parser=argparse.ArgumentParser(description='Signed token QR image round trip.');parser.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'results/qr_roundtrip.json'));args=parser.parse_args();OUT=Path(args.output);OUT.parent.mkdir(parents=True,exist_ok=True)
# Encode a signed token as a QR image, decode it back with OpenCV, then complete one check-in with the decoded text.
with tempfile.TemporaryDirectory()as td:
 c=store.connect(Path(td)/'db');k=b'qrcode-test-key';e=store.event(c,'二维码解码测试');token=store.issue(c,k,e,120,now=1000);im=np.array(qrcode.make(token).convert('RGB'));decoded,_,_=cv2.QRCodeDetector().detectAndDecode(im);assert decoded==token;assert store.checkin(c,k,decoded,'DEMO01',True,1001)['ok'];c.close();OUT.write_text(json.dumps({'decode_equals_token':True,'verified_checkin':True,'image_shape':list(im.shape),'payload_characters':len(token)},indent=2),encoding='utf-8');print('PASS QR image decode and signed check-in')
