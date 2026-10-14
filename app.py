from pathlib import Path
import io,json,time,tempfile
import streamlit as st
import pandas as pd
import numpy as np
import cv2,qrcode
from PIL import Image,UnidentifiedImageError
from light_sign import store
from light_sign.vision import Counter,ROOT
st.set_page_config(page_title='轻签 LightSign',page_icon='🔷',layout='wide')
st.title('轻签 · 活动签到与匿名人数核验')
st.caption('本地原型 / 限时签名二维码 / 事务去重 / 匿名视觉计数')
st.info('用于自愿活动签到。视觉只输出匿名人脸框数量，不识别身份、不关联签到、不生成缺勤判断。演示图片和参与代号均为合成或公开样例。')
@st.cache_resource
def counter():return Counter()
c=store.connect();k=store.key();tabs=st.tabs(['活动与二维码','自愿签到','匿名计数','台账与实验'])
with tabs[0]:
 col1,col2=st.columns(2)
 with col1:
  title=st.text_input('新活动名称',value='开源技术体验活动')
  if st.button('创建活动'):store.event(c,title);st.success('已创建活动')
  events=c.execute('SELECT * FROM events ORDER BY created DESC').fetchall()
  if events:
   eid=st.selectbox('选择活动',[r['id']for r in events],format_func=lambda x:next(r['title']+(' · 开放'if r['active']else' · 已关闭')for r in events if r['id']==x))
   ttl=st.slider('二维码有效秒数',10,600,120,10)
   if st.button('生成限时二维码'):
    try:st.session_state.token=store.issue(c,k,eid,ttl);st.session_state.token_event=eid
    except ValueError as ex:st.error(str(ex))
   a,b=st.columns(2)
   if a.button('撤销该活动二维码'):store.revoke(c,eid);st.success('已撤销；原二维码将被拒绝')
   if b.button('关闭活动'):store.close(c,eid);st.success('已关闭；新签到将被拒绝')
 with col2:
  if st.session_state.get('token'):
   qr=qrcode.make(st.session_state.token).convert('RGB');st.image(qr,width=330);buf=io.BytesIO();qr.save(buf,format='PNG');st.download_button('下载二维码 PNG',buf.getvalue(),'activity_qr.png','image/png');st.code(st.session_state.token,language=None);st.caption('二维码可分享并可能被转发；签名验证完整性与期限，不证明本人在场。')
with tabs[1]:
 st.subheader('核验二维码并自愿签到')
 token=st.text_area('二维码文本',value=st.session_state.get('token',''),height=100)
 file=st.file_uploader('或上传二维码图片',type=['png','jpg','jpeg'],key='qr')
 if file:
  try:
   qr_image=np.array(Image.open(file).convert('RGB'));decoded,_,_=cv2.QRCodeDetector().detectAndDecode(qr_image)
   if decoded:token=decoded;st.success('已解码二维码')
   else:st.warning('未成功解码，请复制二维码文本')
  except (UnidentifiedImageError,ValueError,OSError):st.error('无法读取二维码图片')
 code=st.text_input('参与代号（请勿使用姓名或学号）',value='DEMO001',max_chars=24)
 consent=st.checkbox('我自愿参加，并了解本机保存活动内代号摘要及签到时间')
 if st.button('提交签到',type='primary'):
  result=store.checkin(c,k,token,code,consent);st.session_state.last_checkin=result
 if st.session_state.get('last_checkin'):
  r=st.session_state.last_checkin;(st.success if r['ok']else st.warning)(r['reason']);st.json(r)
 st.caption('代号属于自报信息，可使用多个代号；系统没有身份认证或防代签保证。不可将结果用于成绩、纪律或其他高影响决策。')
with tabs[2]:
 st.subheader('匿名视觉核验：与签到身份完全分开')
 source=st.radio('图像来源',['内置合成样例','上传图片','摄像头照片'],horizontal=True)
 im=None
 try:
  if source=='内置合成样例':
   p=st.selectbox('选择合成场景',list((ROOT/'samples').glob('*.png')),format_func=lambda p:p.stem);im=Image.open(p)
  elif source=='上传图片':
   f=st.file_uploader('上传用于匿名计数的图片',type=['png','jpg','jpeg'],key='faces')
   if f:im=Image.open(f)
  else:
   f=st.camera_input('由操作者自愿拍摄，不会保存原图')
   if f:im=Image.open(f)
  mode=json.loads((ROOT/'models/policy.json').read_text())['mode']
  if st.button('运行匿名计数',type='primary')and im is not None:
   result,safe=counter().run(im,mode);st.session_state.counter_result=result;st.session_state.counter_image=safe
  if st.session_state.get('counter_result'):
   r=st.session_state.counter_result;a,b=st.columns(2)
   with a:st.image(st.session_state.counter_image,caption='全画面马赛克输出；框为匿名检测，不表示身份或真实人数')
   with b:st.metric('检测到的人脸框数',r['count']);st.metric('本次处理耗时',f"{r['elapsed_ms']:.1f} ms");st.json(r);st.download_button('下载匿名计数 JSON',json.dumps(r,ensure_ascii=False,indent=2),'anonymous_count.json')
  st.caption('模型可能漏检、误检或重复计数。单张画面检测框数不等于独立到场人数；照片、屏幕中的人脸也可能计入。马赛克是显示处理，不构成形式化匿名保证。')
 except (UnidentifiedImageError,ValueError,OSError):st.error('图片无法读取，请更换有效文件')
with tabs[3]:
 st.subheader('活动内代号摘要台账')
 rr=store.rows(c);st.dataframe(pd.DataFrame(rr),use_container_width=True);st.download_button('导出台账 CSV',pd.DataFrame(rr).to_csv(index=False).encode('utf-8-sig'),'checkins.csv','text/csv');st.download_button('导出台账 JSON',json.dumps(rr,ensure_ascii=False,indent=2),'checkins.json')
 st.caption('时间为UTC Unix秒；不保存参与原代号、姓名、邮箱、原图或人脸模板。签到代号摘要仍属于可关联的假名数据。密钥由本机首次运行生成，请勿公开runtime。')
 st.subheader('实际实验与来源');summ=json.loads((ROOT/'results/vision_summary.json').read_text());st.dataframe(pd.DataFrame([r for r in summ if r['split']=='test'and r['condition']=='all']),use_container_width=True);st.json(json.loads((ROOT/'results/system_checks.json').read_text()))
 st.markdown('参考仓库：psesaank/FaceRecognitionAttendance。未发现许可，交付包不复制上游源文件或模型。匿名检测器使用OpenCV Haar模型，保留XML内Intel许可；数据来源NASA公开图片，经scikit-image提供。')
c.close()
