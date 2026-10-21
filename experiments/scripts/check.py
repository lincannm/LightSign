from pathlib import Path
import sys,tempfile,json,time,threading,concurrent.futures
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from light_sign import store
ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'results';RESULTS.mkdir(parents=True,exist_ok=True)
checks=[]
with tempfile.TemporaryDirectory()as td:
 path=Path(td)/'db';c=store.connect(path);k=b'controlled-test-key-32bytes-long!!';e=store.event(c,'合成活动');token=store.issue(c,k,e,120,now=1000)
 for name,t,code,consent,now,want in [('valid',token,'DEMO1',True,1001,True),('duplicate',token,'DEMO1',True,1002,False),('no_consent',token,'DEMO2',False,1003,False),('tampered',token[:-1]+('0'if token[-1]!='0'else'1'),'DEMO2',True,1004,False),('expired',token,'DEMO2',True,1120,False),('invalid_code',token,'中文姓名',True,1005,False)]:
  r=store.checkin(c,k,t,code,consent,now);assert r['ok']==want,(name,r);checks.append({'case':name,'passed':True,'result':r['reason']})
 token2=store.issue(c,k,e,120,now=1000);store.revoke(c,e);r=store.checkin(c,k,token2,'DEMO3',True,1001);assert not r['ok'];checks.append({'case':'revoked','passed':True,'result':r['reason']})
 token3=store.issue(c,k,e,120,now=1000);store.close(c,e);r=store.checkin(c,k,token3,'DEMO3',True,1001);assert not r['ok'];checks.append({'case':'closed','passed':True,'result':r['reason']})
 e2=store.event(c,'并发合成活动');token=store.issue(c,k,e2,120,now=1000)
 def worker(i):
  local=store.connect(path);start=time.perf_counter();r=store.checkin(local,k,token,'SAME01',True,1001);local.close();return {'accepted':r['ok'],'ms':1000*(time.perf_counter()-start)}
 with concurrent.futures.ThreadPoolExecutor(max_workers=8)as ex:rr=list(ex.map(worker,range(40)))
 assert sum(r['accepted']for r in rr)==1;checks.append({'case':'concurrent_40_same_participant','passed':True,'accepted':sum(r['accepted']for r in rr),'requests':40,'latencies_ms':[r['ms']for r in rr]})
 assert c.execute('SELECT count(*) FROM checkins WHERE event=?',(e2,)).fetchone()[0]==1
 # Database stores no code, image, email, template or face identifier.
 schema=' '.join(r[0]for r in c.execute("SELECT sql FROM sqlite_master WHERE type='table'"));assert all(s not in schema for s in ['embedding','face_image','email','student_name']);checks.append({'case':'minimal_schema','passed':True})
 c.close()
(RESULTS/'system_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS',len(checks),'checks')
