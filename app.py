import json
import streamlit as st
import pandas as pd
from PIL import Image,UnidentifiedImageError
from light_sign import store
from light_sign.organizer_qr import clear_qr,issue_qr,show_qr
from light_sign import auth
from light_sign.vision import Counter,ROOT

st.set_page_config(page_title='轻签 · 组织者管理',page_icon='🔷',layout='wide')
auth.require_login()
st.title('轻签 · 组织者管理')
st.caption('活动与二维码 / 人数清点 / 签到记录导出')
st.info('用于自愿活动签到。视觉清点只输出匿名人脸框数量，不识别身份、不关联签到记录。演示图片和参与代号均为合成样例。')
@st.cache_resource
def counter():return Counter()
c=store.connect();k=store.key();tabs=st.tabs(['活动与二维码','人数清点','记录与数据'])
with tabs[0]:
 col1,col2=st.columns(2)
 with col1:
  st.subheader('当前活动')
  events=c.execute('SELECT * FROM events ORDER BY created DESC').fetchall()
  activity_selector=st.container()
  with st.expander('新建活动',expanded=not events):
   st.caption('为另一场活动创建独立的签到入口和记录。')
   with st.form('create_event',border=False):
    title=st.text_input('新活动名称',placeholder='例如：开源技术体验活动')
    create=st.form_submit_button('创建活动',type='secondary'if events else'primary')
   if create:
    try:
     st.session_state.selected_event=store.event(c,title)
     clear_qr()
     events=c.execute('SELECT * FROM events ORDER BY created DESC').fetchall()
     st.success('已创建活动，并切换为当前活动')
    except ValueError as ex:st.error(str(ex))
  with activity_selector:
   if events:
    eid=st.selectbox('选择活动',[r['id']for r in events],key='selected_event',format_func=lambda x:next(r['title']+(' · 开放'if r['active']else' · 已关闭')for r in events if r['id']==x))
   else:st.info('暂无活动，请在下方创建第一个活动。')
  if events:
   st.divider()
   st.subheader('二维码设置')
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
  st.subheader('签到二维码')
  if events:
   show_qr(eid,ttl,auto_refresh)
   if st.session_state.get('token_event')!=eid:st.info('设置有效期后，点击“生成限时二维码”展示签到入口。')
  else:st.info('创建活动后，可在此生成签到二维码。')
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
  if im is None:st.info('请先上传图片或拍摄照片，再开始清点。')
  if st.button('开始清点',type='primary',disabled=im is None):
   with st.spinner('正在匿名清点，请稍候……'):
    result,safe=counter().run(im);st.session_state.counter_result=result;st.session_state.counter_image=safe
  if st.session_state.get('counter_result'):
   r=st.session_state.counter_result;a,b=st.columns(2)
   with a:st.image(st.session_state.counter_image,caption='匿名检测结果,框为自动识别')
   with b:st.metric('检测到的人脸框数',r['count']);st.metric('处理耗时',f"{r['elapsed_ms']:.1f} ms");st.json(r);st.download_button('下载结果 JSON',json.dumps(r,ensure_ascii=False,indent=2),'anonymous_count.json')
 except RuntimeError as exc:st.error(str(exc))
 except (UnidentifiedImageError,ValueError,OSError):st.error('图片或检测配置无法读取，请检查文件后重试。')
with tabs[2]:
 st.subheader('签到记录')
 rr=store.rows(c)
 records=pd.DataFrame(rr,columns=['title','event','participant','created'])
 display_records=records.copy()
 display_records['created']=pd.to_datetime(display_records['created'],unit='s',utc=True).dt.tz_convert('Asia/Shanghai').dt.strftime('%Y-%m-%d %H:%M:%S')
 display_records=display_records.rename(columns={'title':'活动名称','event':'活动编号','participant':'参与者匿名编号','created':'签到时间（北京时间）'})
 st.dataframe(display_records,width='stretch',hide_index=True)
 st.download_button('导出 CSV',records.to_csv(index=False).encode('utf-8-sig'),'checkins.csv','text/csv')
 st.download_button('导出 JSON',json.dumps(rr,ensure_ascii=False,indent=2),'checkins.json')
 st.caption('表格时间按北京时间显示；系统不保存真实姓名、学号、邮箱或人脸数据。请妥善保管 local_data（本地数据）目录。')
 with st.expander('测试数据与技术说明'):
  st.subheader('合成数据测试结果')
  try:
   results=ROOT/'experiments';current=sorted(results.glob('yunet_synthetic_*/results.json'))[-1];report=json.loads(current.read_text(encoding='utf-8'));checks=json.loads((results/'results/system_checks.json').read_text(encoding='utf-8'))
  except (OSError,UnicodeError,json.JSONDecodeError):st.info('当前未附带可读取的实验记录，请参阅技术报告或 experiments/README.md。')
  else:
   st.dataframe(pd.DataFrame(report['summary']),width='stretch');st.json(checks)
  st.markdown('**技术参考**:本项目参考 psesaank/FaceRecognitionAttendance 仓库设计思路。匿名检测使用 YuNet（保留 MIT 许可）；内置演示图片来自 NASA 公开数据集，由 scikit-image 提供。')
c.close()
