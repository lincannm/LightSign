from pathlib import Path
import io,json,time,tempfile
import streamlit as st
import pandas as pd
import numpy as np
import cv2,qrcode
from PIL import Image,UnidentifiedImageError
from light_sign import store
from light_sign.vision import Counter,ROOT

# 检测是否为移动设备
def is_mobile():
    try:
        user_agent = st.context.headers.get("User-Agent", "").lower()
        return any(x in user_agent for x in ["mobile", "android", "iphone", "ipad", "ipod"])
    except:
        return False

st.set_page_config(page_title='轻签 LightSign',page_icon='🔷',layout='wide')
st.title('轻签 · 活动签到与匿名人数核验')
st.caption('本地原型 / 限时签名二维码 / 事务去重 / 匿名视觉计数')
st.info('用于自愿活动签到。视觉计数只输出匿名人脸框数量，不识别身份、不关联签到记录。演示图片和参与代号均为合成样例。')
@st.cache_resource
def counter():return Counter()
c=store.connect();k=store.key();tabs=st.tabs(['活动与二维码','自愿签到','匿名计数','记录与数据'])
with tabs[0]:
 col1,col2=st.columns(2)
 with col1:
  title=st.text_input('新活动名称',value='开源技术体验活动')
  if st.button('创建活动'):store.event(c,title);st.success('已创建活动')
  events=c.execute('SELECT * FROM events ORDER BY created DESC').fetchall()
  if events:
   eid=st.selectbox('选择活动',[r['id']for r in events],format_func=lambda x:next(r['title']+(' · 开放'if r['active']else' · 已关闭')for r in events if r['id']==x))
   ttl=st.slider('二维码有效秒数',10,600,120,10)
   if st.button('生成限时二维码',type='primary'):
    try:st.session_state.token=store.issue(c,k,eid,ttl);st.session_state.token_event=eid
    except ValueError as ex:st.error(str(ex))
   a,b=st.columns(2)
   if a.button('撤销该活动二维码'):store.revoke(c,eid);st.success('已撤销,原二维码将失效')
   if b.button('关闭活动'):store.close(c,eid);st.success('已关闭,不再接受新签到')
 with col2:
  if st.session_state.get('token'):
   qr=qrcode.make(st.session_state.token).convert('RGB');st.image(qr,width=330);buf=io.BytesIO();qr.save(buf,format='PNG');st.download_button('下载二维码 PNG',buf.getvalue(),'activity_qr.png','image/png');st.code(st.session_state.token,language=None);st.caption('二维码可分享,签名确保完整性与有效期,但不能证明持有者在场。')
with tabs[1]:
 st.subheader('扫码签到')
 # 根据设备类型选择默认输入方式
 mobile = is_mobile()
 default_index = 2 if mobile else 0  # 移动设备默认摄像头扫码,其他设备默认手动输入
 input_method=st.radio('二维码输入方式',['手动输入文本','上传图片','摄像头扫码'],index=default_index,horizontal=True)
 token=''
 if input_method=='手动输入文本':
  token=st.text_area('二维码文本',value=st.session_state.get('token',''),height=100)
 elif input_method=='上传图片':
  file=st.file_uploader('上传二维码图片',type=['png','jpg','jpeg'],key='qr_upload')
  if file:
   try:
    qr_image=np.array(Image.open(file).convert('RGB'));decoded,_,_=cv2.QRCodeDetector().detectAndDecode(qr_image)
    if decoded:token=decoded;st.success('扫码成功');st.code(token,language=None)
    else:st.warning('未能识别二维码,请换个角度或方式试试')
   except (UnidentifiedImageError,ValueError,OSError):st.error('无法读取图片')
 else:
  camera_file=st.camera_input('使用摄像头扫描二维码')
  if camera_file:
   try:
    qr_image=np.array(Image.open(camera_file).convert('RGB'));decoded,_,_=cv2.QRCodeDetector().detectAndDecode(qr_image)
    if decoded:token=decoded;st.success('扫码成功');st.code(token,language=None)
    else:st.warning('未能识别二维码,请重新拍摄或换个方式')
   except (UnidentifiedImageError,ValueError,OSError):st.error('无法读取图片')
 code=st.text_input('参与代号(请勿使用姓名或学号)',value='DEMO001',max_chars=24)
 consent=st.checkbox('我自愿参加活动')
 if st.button('提交签到',type='primary'):
  result=store.checkin(c,k,token,code,consent);st.session_state.last_checkin=result
 if st.session_state.get('last_checkin'):
  r=st.session_state.last_checkin;(st.success if r['ok']else st.warning)(r['reason']);st.json(r)
 st.caption('代号为自报信息,可使用多个代号;系统无身份认证,无法防止代签。不可用于成绩评定或纪律处分等重要场合。')
with tabs[2]:
 st.subheader('匿名人数计数')
 source=st.radio('图像来源',['内置样例','上传图片','摄像头拍摄'],horizontal=True)
 im=None
 try:
  if source=='内置样例':
   p=st.selectbox('选择场景',list((ROOT/'samples').glob('*.png')),format_func=lambda p:p.stem);im=Image.open(p)
  elif source=='上传图片':
   f=st.file_uploader('上传图片用于人数统计',type=['png','jpg','jpeg'],key='faces')
   if f:im=Image.open(f)
  else:
   f=st.camera_input('拍摄照片,不会保存原图')
   if f:im=Image.open(f)
  mode=json.loads((ROOT/'models/policy.json').read_text())['mode']
  if st.button('开始计数',type='primary')and im is not None:
   result,safe=counter().run(im,mode);st.session_state.counter_result=result;st.session_state.counter_image=safe
  if st.session_state.get('counter_result'):
   r=st.session_state.counter_result;a,b=st.columns(2)
   with a:st.image(st.session_state.counter_image,caption='匿名检测结果,框为自动识别,不代表真实人数')
   with b:st.metric('检测到的人脸框数',r['count']);st.metric('处理耗时',f"{r['elapsed_ms']:.1f} ms");st.json(r);st.download_button('下载结果 JSON',json.dumps(r,ensure_ascii=False,indent=2),'anonymous_count.json')
  st.caption('模型可能漏检、误检或重复计数。检测框数不等于实际人数;照片或屏幕中的人脸也可能被计入。')
 except (UnidentifiedImageError,ValueError,OSError):st.error('图片无法读取,请换个文件试试')
with tabs[3]:
 st.subheader('签到记录')
 rr=store.rows(c);st.dataframe(pd.DataFrame(rr),width='stretch');st.download_button('导出 CSV',pd.DataFrame(rr).to_csv(index=False).encode('utf-8-sig'),'checkins.csv','text/csv');st.download_button('导出 JSON',json.dumps(rr,ensure_ascii=False,indent=2),'checkins.json')
 st.caption('时间为UTC时间戳(秒);系统不保存真实姓名、学号、邮箱或人脸数据。代号经过加密处理,但仍可能被关联。请妥善保管runtime目录。')
 with st.expander('测试数据与技术说明'):
  st.subheader('模型测试结果');summ=json.loads((ROOT/'results/vision_summary.json').read_text());st.dataframe(pd.DataFrame([r for r in summ if r['split']=='test'and r['condition']=='all']),width='stretch');st.json(json.loads((ROOT/'results/system_checks.json').read_text()))
  st.markdown('**技术参考**:本项目参考 psesaank/FaceRecognitionAttendance 仓库设计思路。匿名检测使用 OpenCV Haar Cascade 模型(保留 Intel 原始许可);演示图片来自 NASA 公开数据集,由 scikit-image 提供。')
c.close()
