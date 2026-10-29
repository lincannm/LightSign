"""在原有合成图像集上评估固定 YuNet 配置，并将结果保存到新目录。"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2
import numpy as np
from PIL import Image

from light_sign.vision import Counter, ROOT

EXPERIMENTS = ROOT / 'experiments'
MANIFEST = EXPERIMENTS / 'data/manifest.json'


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = a[2] * a[3] + b[2] * b[3] - intersection
    return intersection / union if union else 0


def summarize(rows):
    tp = sum(row['tp'] for row in rows)
    fp = sum(row['fp'] for row in rows)
    fn = sum(row['fn'] for row in rows)
    return {
        'images': len(rows), 'tp': tp, 'fp': fp, 'fn': fn,
        'precision': tp / (tp + fp) if tp + fp else 0,
        'recall': tp / (tp + fn) if tp + fn else 0,
        'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        'count_mae': float(np.mean([abs(row['pred_count'] - row['count']) for row in rows])),
        'count_exact': float(np.mean([row['pred_count'] == row['count'] for row in rows])),
        'median_ms': float(np.median([row['elapsed_ms'] for row in rows])),
        'p95_ms': float(np.percentile([row['elapsed_ms'] for row in rows], 95)),
    }


def main():
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    counter = Counter()
    rows = []
    for record in manifest:
        path = (EXPERIMENTS / record['path']).resolve()
        if not path.is_relative_to(EXPERIMENTS.resolve()):
            raise ValueError('数据清单路径超出实验目录')
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError(f'数据哈希校验失败：{path.name}')
        with Image.open(path) as image:
            prediction, _ = counter.run(image)
        pairs = sorted(
            [(iou(box, truth), pi, gi)
            for pi, box in enumerate(prediction['boxes'])
            for gi, truth in enumerate(record['boxes'])],
            reverse=True,
        )
        matched_predictions, matched_truth = set(), set()
        for overlap, pi, gi in pairs:
            if overlap >= 0.5 and pi not in matched_predictions and gi not in matched_truth:
                matched_predictions.add(pi)
                matched_truth.add(gi)
        rows.append({
            'file': path.relative_to(ROOT).as_posix(), 'sha256': record['sha256'],
            'split': record['split'], 'condition': record['condition'],
            'count': record['count'], 'prediction': prediction['boxes'],
            'pred_count': prediction['count'], 'elapsed_ms': prediction['elapsed_ms'],
            'tp': len(matched_predictions),
            'fp': prediction['count'] - len(matched_predictions),
            'fn': record['count'] - len(matched_truth),
        })
    if MANIFEST.read_bytes() != manifest_bytes:
        raise RuntimeError('评测期间数据清单发生变化')
    summaries = [
        {'split': split, **summarize([row for row in rows if row['split'] == split])}
        for split in ('development', 'test')
    ]
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
    output = EXPERIMENTS / f'yunet_synthetic_{stamp}'
    output.mkdir(exist_ok=False)
    metadata = {
        'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        'python': platform.python_version(), 'opencv': cv2.__version__,
        'model': json.loads((ROOT / 'models/yunet.provenance.json').read_text(encoding='utf-8-sig')),
        'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'protocol': '固定 YuNet 参数，development/test 分别报告；不对测试集选参。IoU≥0.5。',
        'summary': summaries, 'predictions': rows,
    }
    (output / 'results.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(), 'summary': summaries}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
