import json
import streamlit as st
import pandas as pd
from PIL import Image,UnidentifiedImageError
from light_sign import store
from light_sign.organizer_qr import clear_qr,issue_qr,show_qr
from light_sign.vision import Counter,ROOT

st.set_page_config(page_title='轻签 · 组织者管理',page_icon='🔷',layout='wide')
st.title('轻签 · 组织者管理')
st.caption('活动与二维码 / 人数清点 / 签到记录导出')
st.info('用于自愿活动签到。视觉清点只输出匿名人脸框数量，不识别身份、不关联签到记录。演示图片和参与代号均为合成样例。')
@st.cache_resource
def counter():return Counter()
c=store.connect();k=store.key();tabs=st.tabs(['活动与二维码','人数清点','记录与数据'])
with tabs[0]:
 col1,col2=st.columns(2)
 with col1:
  title=st.text_input('新活动名称',value='开源技术体验活动')
  if st.button('创建活动'):
   try:store.event(c,title);st.success('已创建活动')
   except ValueError as ex:st.error(str(ex))
  events=c.execute('SELECT * FROM events ORDER BY created DESC').fetchall()
  if events:
   eid=st.selectbox('选择活动',[r['id']for r in events],format_func=lambda x:next(r['title']+(' · 开放'if r['active']else' · 已关闭')for r in events if r['id']==x))
   ttl=st.slider('二维码有效秒数',10,600,120,10)
   auto_refresh=st.checkbox('二维码自动刷新',value=True,key='qr_auto_refresh',help='开启后，到期自动生成新的二维码；关闭后，到期显示黑色过期提示。')
   if st.button('生成限时二维码',type='primary'):
    clear_qr()
    try:
     issue_qr(c,k,eid,ttl)
    except ValueError as ex:st.error(str(ex))
   a,b=st.columns(2)
   if a.button('撤销该活动二维码'):
    store.revoke(c,eid);clear_qr();st.success('已撤销,原二维码将失效')
   if b.button('关闭活动'):
    store.close(c,eid);clear_qr();c.close();st.rerun()
 with col2:
  if events:show_qr(eid,ttl,auto_refresh)
with tabs[1]:
 st.subheader('匿名人数清点')
 source=st.radio('图像来源',['内置样例','上传图片','摄像头拍摄'],horizontal=True)
 im=None
 try:
  if source=='内置样例':
   p=st.selectbox('选择场景',list((ROOT/'samples').glob('*.png')),format_func=lambda p:p.stem);im=Image.open(p)
  elif source=='上传图片':
   f=st.file_uploader('上传图片用于人数清点',type=['png','jpg','jpeg'],key='faces')
   if f:im=Image.open(f)
  else:
   f=st.camera_input('拍摄照片,不会保存原图')
   if f:im=Image.open(f)
  mode=json.loads((ROOT/'models/policy.json').read_text())['mode']
  if st.button('开始清点',type='primary')and im is not None:
   result,safe=counter().run(im,mode);st.session_state.counter_result=result;st.session_state.counter_image=safe
  if st.session_state.get('counter_result'):
   r=st.session_state.counter_result;a,b=st.columns(2)
   with a:st.image(st.session_state.counter_image,caption='匿名检测结果,框为自动识别,不代表真实人数')
   with b:st.metric('检测到的人脸框数',r['count']);st.metric('处理耗时',f"{r['elapsed_ms']:.1f} ms");st.json(r);st.download_button('下载结果 JSON',json.dumps(r,ensure_ascii=False,indent=2),'anonymous_count.json')
  st.caption('模型可能漏检、误检或重复清点。检测框数不等于实际人数;照片或屏幕中的人脸也可能被计入。')
 except (UnidentifiedImageError,ValueError,OSError):st.error('图片无法读取,请换个文件试试')
with tabs[2]:
 st.subheader('签到记录')
 rr=store.rows(c);st.dataframe(pd.DataFrame(rr),width='stretch');st.download_button('导出 CSV',pd.DataFrame(rr).to_csv(index=False).encode('utf-8-sig'),'checkins.csv','text/csv');st.download_button('导出 JSON',json.dumps(rr,ensure_ascii=False,indent=2),'checkins.json')
 st.caption('时间为UTC时间戳(秒);系统不保存真实姓名、学号、邮箱或人脸数据。代号经过加密处理,但仍可能被关联。请妥善保管runtime目录。')
 with st.expander('测试数据与技术说明'):
  st.subheader('模型测试结果');summ=json.loads((ROOT/'results/vision_summary.json').read_text());st.dataframe(pd.DataFrame([r for r in summ if r['split']=='test'and r['condition']=='all']),width='stretch');st.json(json.loads((ROOT/'results/system_checks.json').read_text()))
  st.markdown('**技术参考**:本项目参考 psesaank/FaceRecognitionAttendance 仓库设计思路。匿名检测使用 OpenCV Haar Cascade 模型(保留 Intel 原始许可);演示图片来自 NASA 公开数据集,由 scikit-image 提供。')
c.close()
