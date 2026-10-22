from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import argparse
a=argparse.ArgumentParser();a.add_argument('--font',help='Optional path to a Chinese font you have permission to use');a.add_argument('--out',help='Output directory, default results/figures');args=a.parse_args()
R=Path(__file__).resolve().parents[1];O=Path(args.out)if args.out else R/'results/figures';O.mkdir(parents=True,exist_ok=True)
if args.font:plt.rcParams['font.family']=FontProperties(fname=args.font).get_name()
plt.rcParams['axes.unicode_minus']=False
S=json.loads((R/'results/vision_summary.json').read_text(encoding='utf-8'));modes=['baseline','small','clahe','gamma'];labels=['参考仓库参数','小尺寸窗口','小窗口及CLAHE','Gamma及CLAHE'];colors=['#A2AEBF','#729DBF','#087CB0','#53BDC4']
def save(name):plt.tight_layout();plt.savefig(O/name,dpi=180,bbox_inches='tight');plt.close()
rr=[next(r for r in S if r['split']=='test'and r['condition']=='all'and r['mode']==m)for m in modes]
fig,ax=plt.subplots(figsize=(8,3.7));b=ax.bar(labels,[r['recall']*100 for r in rr],color=colors);ax.bar_label(b,fmt='%.2f');ax.set_ylim(0,115);ax.set_ylabel('召回率 %');ax.set_title('80张合成图 / 160实例 / IoU≥0.5 / 同一源脸');save('01-recall.png')
fig,axes=plt.subplots(1,2,figsize=(8,3.4));
for ax,key,title in zip(axes,['count_mae','median_ms'],['清点人数平均绝对误差','单图处理延迟中位数 ms']):
 b=ax.bar(range(4),[r[key]for r in rr],color=colors);ax.bar_label(b,fmt='%.2f');ax.set_xticks(range(4),[l.replace('及','\n及')for l in labels],fontsize=8);ax.set_title(title);ax.set_ylim(0,max(r[key]for r in rr)*1.25)
save('02-cost.png')
fig,ax=plt.subplots(figsize=(7,3.5));b=ax.bar(['参考仓库：8个刻意对齐的请求','新版：40个同代号请求'],[json.loads((R/'audit/upstream_race.json').read_text(encoding='utf-8'))[0]['stored_rows'],next(x for x in json.loads((R/'results/system_checks.json').read_text(encoding='utf-8')) if x['case']=='concurrent_40_same_participant')['accepted']],color=['#C96A43','#087CB0']);ax.bar_label(b,fmt='%.0f');ax.set_ylabel('最后留下的签到记录数');ax.set_ylim(0,10);ax.set_title('同一代号重复提交后留下的记录（请求量不同，不代表实际故障率）');save('03-race.png')
