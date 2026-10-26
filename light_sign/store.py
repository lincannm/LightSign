import sqlite3,time,secrets,hmac,hashlib,json,base64,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def connect(path=None):
 p=Path(path)if path else ROOT/'local_data/activity.sqlite3';p.parent.mkdir(exist_ok=True,parents=True);c=sqlite3.connect(p,timeout=20);c.row_factory=sqlite3.Row;c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA foreign_keys=ON');c.executescript('''CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,title TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS challenges(nonce TEXT PRIMARY KEY,event TEXT NOT NULL REFERENCES events(id),expires INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS checkins(event TEXT NOT NULL REFERENCES events(id),pseudonym TEXT NOT NULL,created INTEGER NOT NULL,UNIQUE(event,pseudonym));CREATE TABLE IF NOT EXISTS audit(kind TEXT NOT NULL,event TEXT,created INTEGER NOT NULL);''');return c
def key(path=None):
 p=Path(path)if path else ROOT/'local_data/signing.key';p.parent.mkdir(exist_ok=True,parents=True)
 try:
  with p.open('xb')as f:f.write(secrets.token_bytes(32))
  p.chmod(0o600)
 except FileExistsError:pass
 return p.read_bytes()
def event(c,title):
 title=title.strip()
 if not 1<=len(title)<=60:raise ValueError('活动名称须为1至60字符')
 eid=secrets.token_hex(6);c.execute('INSERT INTO events VALUES(?,?,1,?)',(eid,title,int(time.time())));c.commit();return eid
def issue(c,k,eid,ttl=120,now=None):
 now=int(time.time())if now is None else int(now)
 if not 10<=ttl<=600:raise ValueError('有效期应为10至600秒')
 if not c.execute('SELECT 1 FROM events WHERE id=? AND active=1',(eid,)).fetchone():raise ValueError('活动未开放')
 nonce=secrets.token_hex(8);p=json.dumps({'v':1,'e':eid,'n':nonce,'x':now+ttl},separators=(',',':')).encode();b=base64.urlsafe_b64encode(p).decode().rstrip('=');sig=hmac.new(k,b.encode(),hashlib.sha256).hexdigest();c.execute('INSERT INTO challenges VALUES(?,?,?)',(nonce,eid,now+ttl));c.commit();return b+'.'+sig
def verify(c,k,token,now=None):
 now=int(time.time())if now is None else int(now)
 try:
  if len(token)>800:return None,'无效二维码'
  b,sig=token.strip().split('.')
  if not hmac.compare_digest(sig,hmac.new(k,b.encode(),hashlib.sha256).hexdigest()):return None,'签名不匹配'
  p=json.loads(base64.urlsafe_b64decode(b+'='*((-len(b))%4)))
  if p.get('v')!=1 or type(p.get('x'))is not int:return None,'格式错误'
  if now>=p['x']:return None,'二维码已过期'
  r=c.execute('SELECT ch.expires,e.active FROM challenges ch JOIN events e ON e.id=ch.event WHERE ch.nonce=? AND ch.event=?',(p['n'],p['e'])).fetchone()
  if not r or r['expires']!=p['x']:return None,'二维码已撤销或不存在'
  if not r['active']:return None,'活动已关闭'
  return p,None
 except (ValueError,KeyError,TypeError,UnicodeError):return None,'格式错误'
SCAN_FILL_SECONDS = 300


def prepare_checkin(c, k, token, now=None):
 """在二维码有效时签发填写凭证，仅供当前参与者会话保存。"""
 now = int(time.time()) if now is None else int(now)
 _, error = verify(c, k, token, now)
 if error:
  return None, error
 payload = {'qr': hashlib.sha256(token.encode()).hexdigest(), 'at': now,
            'until': now + SCAN_FILL_SECONDS}
 body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
 signature = hmac.new(k, ('scan:' + body).encode(), hashlib.sha256).hexdigest()
 return body + '.' + signature, None


def verify_scan(c, k, token, scan_ticket, now=None):
 """填写期限独立于二维码期限，但撤销和关闭活动仍立即生效。"""
 now = int(time.time()) if now is None else int(now)
 try:
  if len(scan_ticket) > 512:
   return None, '无效扫码凭证，请重新扫描二维码'
  body, signature = scan_ticket.split('.')
  expected = hmac.new(k, ('scan:' + body).encode(), hashlib.sha256).hexdigest()
  if not hmac.compare_digest(signature, expected):
   return None, '无效扫码凭证，请重新扫描二维码'
  payload = json.loads(base64.urlsafe_b64decode(body + '=' * ((-len(body)) % 4)))
  if (type(payload['at']) is not int or type(payload['until']) is not int
      or payload['until'] - payload['at'] != SCAN_FILL_SECONDS
      or payload['at'] > now
      or payload['qr'] != hashlib.sha256(token.encode()).hexdigest()):
   return None, '无效扫码凭证，请重新扫描二维码'
  if now >= payload['until']:
   return None, '填写时间已结束，请重新扫描二维码'
  # 签名证明扫码时二维码有效；数据库查询仍使用当前的撤销与活动状态。
  return verify(c, k, token, now=payload['at'])
 except (ValueError, KeyError, TypeError, UnicodeError):
  return None, '无效扫码凭证，请重新扫描二维码'


def checkin(c,k,token,code,consent,now=None,*,scan_ticket=None):
 if not consent:return {'ok':False,'reason':'请先确认自愿参加'}
 code=code.strip().upper()
 if not re.fullmatch(r'[A-Z0-9_-]{3,24}',code):return {'ok':False,'reason':'代号须为3至24位字母数字、横线或下划线'}
 # Transaction serializes validation with close/revoke and uniqueness insertion.
 c.execute('BEGIN IMMEDIATE')
 try:
  # Read the clock after the write lock so a request queued past expiry is rejected.
  now=int(time.time())if now is None else int(now)
  p,error=verify_scan(c,k,token,scan_ticket,now)if scan_ticket is not None else verify(c,k,token,now)
  if error:c.rollback();return {'ok':False,'reason':error}
  pseudo=hmac.new(k,('participant:'+p['e']+':'+code).encode(),hashlib.sha256).hexdigest()
  cur=c.execute('INSERT OR IGNORE INTO checkins VALUES(?,?,?)',(p['e'],pseudo,now));ok=cur.rowcount==1
  c.execute('INSERT INTO audit VALUES(?,?,?)',('accepted'if ok else'duplicate',p['e'],now));c.commit();return {'ok':ok,'reason':'签到成功'if ok else'本活动已签到','event':p['e'],'pseudonym':pseudo[:12]}
 except Exception:c.rollback();raise
def close(c,eid):c.execute('UPDATE events SET active=0 WHERE id=?',(eid,));c.commit()
def revoke(c,eid):c.execute('DELETE FROM challenges WHERE event=?',(eid,));c.commit()
def rows(c):return [dict(r)for r in c.execute('SELECT e.title,c.event,substr(c.pseudonym,1,12)AS participant,c.created FROM checkins c JOIN events e ON e.id=c.event ORDER BY c.created DESC')]
