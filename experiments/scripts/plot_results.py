from pathlib import Path
import argparse
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


parser = argparse.ArgumentParser()
parser.add_argument('--font', help='Optional path to a Chinese font you have permission to use')
parser.add_argument('--out', help='Output directory, default results/figures')
args = parser.parse_args()

root = Path(__file__).resolve().parents[1]
output = Path(args.out) if args.out else root / 'results/figures'
output.mkdir(parents=True, exist_ok=True)
if args.font:
    plt.rcParams['font.family'] = FontProperties(fname=args.font).get_name()
plt.rcParams['axes.unicode_minus'] = False

results = sorted(root.glob('yunet_synthetic_*/results.json'))
if not results:
    raise SystemExit('未找到 YuNet 合成数据评测结果，请先运行 evaluate.py')
summary = json.loads(results[-1].read_text(encoding='utf-8'))['summary']
test = next(row for row in summary if row['split'] == 'test')

fig, axes = plt.subplots(1, 2, figsize=(7, 3.4))
for axis, key, title in zip(
    axes,
    ('recall', 'count_mae'),
    ('人脸召回率', '清点人数平均绝对误差'),
):
    value = test[key] * 100 if key == 'recall' else test[key]
    axis.bar(['YuNet'], [value], color='#087CB0')
    axis.set_title(title)
    axis.bar_label(axis.containers[0], fmt='%.2f')
save = output / '01-yunet-synthetic.png'
fig.tight_layout()
fig.savefig(save, dpi=180, bbox_inches='tight')
plt.close(fig)
print(save)
