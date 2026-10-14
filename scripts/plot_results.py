from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import argparse
a=argparse.ArgumentParser();a.add_argument('--font',help='Optional path to a Chinese font you have permission to use');args=a.parse_args()
R=Path(__file__).resolve().parents[1];O=R/'results/figures';O.mkdir(exist_ok=True)
if args.font:plt.rcParams['font.family']=FontProperties(fname=args.font).get_name()
plt.rcParams['axes.unicode_minus']=False
S=json.loads((R/'results/vision_summary.json').read_text());modes=['baseline','small','clahe','gamma'];labels=['上游检测参数','小尺寸窗口','小窗口及CLAHE','Gamma及CLAHE'];colors=['#A2AEBF','#729DBF','#087CB0','#53BDC4']
def save(name):plt.tight_layout();plt.savefig(O/name,dpi=180,bbox_inches='tight');plt.close()
rr=[next(r for r in S if r['split']=='test'and r['condition']=='all'and r['mode']==m)for m in modes]
fig,ax=plt.subplots(figsize=(8,3.7));b=ax.bar(labels,[r['recall']*100 for r in rr],color=colors);ax.bar_label(b,fmt='%.2f');ax.set_ylim(0,115);ax.set_ylabel('召回率 %');ax.set_title('80张合成图 / 160实例 / IoU≥0.5 / 同一源脸');save('01-recall.png')
fig,axes=plt.subplots(1,2,figsize=(8,3.4));
for ax,key,title in zip(axes,['count_mae','median_ms'],['计数平均绝对误差','单图处理延迟中位数 ms']):
 b=ax.bar(range(4),[r[key]for r in rr],color=colors);ax.bar_label(b,fmt='%.2f');ax.set_xticks(range(4),['原参数','小窗口','CLAHE','Gamma']);ax.set_title(title);ax.set_ylim(0,max(r[key]for r in rr)*1.25)
save('02-cost.png')
fig,ax=plt.subplots(figsize=(7,3.5));b=ax.bar(['合成测试80图','倾斜遮挡挑战40图'],[100*rr[2]['count_exact'],100*json.loads((R/'results/stress.json').read_text())['correct_counts']/json.loads((R/'results/stress.json').read_text())['n']],color=['#087CB0','#C96A43']);ax.bar_label(b,fmt='%.0f%%');ax.set_ylim(0,115);ax.set_ylabel('计数完全正确比例');ax.set_title('同源脸挑战揭示边界，不能代表跨人群泛化');save('03-stress.png')
fig,ax=plt.subplots(figsize=(7,3.5));b=ax.bar(['上游 8个同步请求','新版 40个并发请求'],[json.loads((R/'audit/upstream_race.json').read_text())[0]['stored_rows'],next(x for x in json.loads((R/'results/system_checks.json').read_text()) if x['case']=='concurrent_40_same_participant')['accepted']],color=['#C96A43','#087CB0']);ax.bar_label(b,fmt='%.0f');ax.set_ylabel('同一活动对象的入库行数');ax.set_ylim(0,10);ax.set_title('上游人为同步竞态复现 / 新版事务及唯一约束');save('04-race.png')
