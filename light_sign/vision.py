from pathlib import Path
import time
import cv2
import numpy as np
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1]
class Counter:
 def __init__(self):
  self.model=cv2.CascadeClassifier(str(ROOT/'models/haarcascade_frontalface_default.xml'))
  if self.model.empty():raise RuntimeError('匿名检测模型缺失')
 def run(self,image,mode='clahe'):
  start=time.perf_counter();im=ImageOps.exif_transpose(image).convert('RGB');im.thumbnail((960,720));rgb=np.array(im);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
  if mode=='clahe':gray=cv2.createCLAHE(clipLimit=2,tileGridSize=(8,8)).apply(gray)
  elif mode=='gamma':
   if float(gray.mean())<90:gray=np.uint8(255*np.sqrt(gray.astype(float)/255))
   gray=cv2.createCLAHE(clipLimit=2,tileGridSize=(8,8)).apply(gray)
  elif mode not in ['baseline','small']:raise ValueError('unknown mode')
  boxes=self.model.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=5,minSize=(80,80)if mode=='baseline'else(24,24))
  boxes=[[int(x),int(y),int(w),int(h)]for x,y,w,h in boxes];safe=cv2.resize(cv2.resize(rgb,(max(1,rgb.shape[1]//24),max(1,rgb.shape[0]//24))),rgb.shape[1::-1],interpolation=cv2.INTER_NEAREST)
  for x,y,w,h in boxes:cv2.rectangle(safe,(x,y),(x+w,y+h),(20,180,190),2)
  result={'count':len(boxes),'boxes':boxes,'elapsed_ms':1000*(time.perf_counter()-start),'mode':mode,'width':rgb.shape[1],'height':rgb.shape[0],'scope':'anonymous detections only; no identity, no attendance association'}
  return result,Image.fromarray(safe)
