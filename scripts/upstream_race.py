# Independent audit harness. Requires a separate private checkout; do not redistribute unlicensed upstream.
from pathlib import Path
import sys,tempfile,threading,concurrent.futures,json
import argparse
parser=argparse.ArgumentParser(description='Optional private upstream database audit; no upstream code bundled.');parser.add_argument('--upstream-src',required=True);parser.add_argument('--output',default='audit/upstream_race_rerun.json');args=parser.parse_args()
sys.path.insert(0,str(Path(args.upstream_src).resolve()))
from database import Database
rows=[]
for trial in range(5):
 with tempfile.TemporaryDirectory()as td:
  path=str(Path(td)/'up.db');db=Database(path);uid=db.add_student('Demo Person','D001','DEMO','demo@example.invalid');barrier=threading.Barrier(8)
  def run(i):
   d=Database(path);old=d.has_marked_today
   def checked(*args,**kw):
    result=old(*args,**kw);barrier.wait();return result
   d.has_marked_today=checked
   return d.mark_attendance(uid,'2026-10-10','10:00:00')
  with concurrent.futures.ThreadPoolExecutor(max_workers=8)as ex:result=list(ex.map(run,range(8)))
  rows.append({'trial':trial,'requests':8,'accepted':sum(result),'stored_rows':len(db.get_all_attendance()),'method':'barrier after read-before-insert; intentionally aligned race, not production frequency'})
Path(args.output).write_text(json.dumps(rows,indent=2));print(rows)
