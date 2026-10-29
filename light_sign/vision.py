"""本地匿名人脸检测：YuNet。"""

import hashlib
import json
import math
from pathlib import Path
import threading
import time

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
YUNET_MODEL = ROOT / 'models/face_detection_yunet_2023mar.onnx'
YUNET_POLICY = ROOT / 'models/yunet_policy.json'
class Counter:
    def __init__(self):
        # Streamlit cache_resource 跨会话共享；DNN 输入尺寸和推理不得交叉修改。
        self._lock = threading.RLock()
        self._yunet = None
        self.policy = json.loads(YUNET_POLICY.read_text(encoding='utf-8-sig'))
        p = self.policy
        for name in ('score_threshold', 'nms_threshold'):
            value = p[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
                raise ValueError(f'YuNet 配置无效：{name}')
        for name in ('max_long_edge', 'top_k'):
            if type(p[name]) is not int or p[name] <= 0:
                raise ValueError(f'YuNet 配置无效：{name}')

    def _load_yunet(self):
        if self._yunet is not None:
            return self._yunet
        if not YUNET_MODEL.is_file():
            raise RuntimeError('YuNet 模型缺失，请恢复仓库中的模型文件；不会自动联网下载或切换算法。')
        metadata = json.loads((ROOT / 'models/yunet.provenance.json').read_text(encoding='utf-8-sig'))
        if hashlib.sha256(YUNET_MODEL.read_bytes()).hexdigest() != metadata['sha256']:
            raise RuntimeError('YuNet 模型校验失败，请恢复仓库中的原始模型文件。')
        p = self.policy
        self._yunet = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL), '', (320, 320), p['score_threshold'],
            p['nms_threshold'], p['top_k'],
            cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU,
        )
        return self._yunet

    def _infer_yunet(self, bgr):
        height, width = bgr.shape[:2]
        # 对很小的图片及非整倍数尺寸只做右下补边，不拉伸或放大图像。
        padded_width = max(32, math.ceil(width / 32) * 32)
        padded_height = max(32, math.ceil(height / 32) * 32)
        padded = cv2.copyMakeBorder(
            bgr, 0, padded_height - height, 0, padded_width - width,
            cv2.BORDER_CONSTANT, value=(0, 0, 0),
        )
        detector = self._load_yunet()
        detector.setInputSize((padded_width, padded_height))
        _, faces = detector.detect(padded)
        candidates = []
        if faces is not None:
            for face in faces:
                x, y, w, h = map(float, face[:4])
                score = float(face[-1])
                if not all(math.isfinite(v) for v in (x, y, w, h, score)) or w <= 0 or h <= 0:
                    continue
                # 补边区域的框不计入；先保留浮点坐标，最后统一去重与裁边。
                if 0 <= x + w / 2 < width and 0 <= y + h / 2 < height:
                    candidates.append(([x, y, w, h], score))
        return candidates

    def _detect_yunet(self, rgb):
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        height, width = bgr.shape[:2]
        candidates = self._infer_yunet(bgr)
        if not candidates:
            return [], []
        boxes, scores = zip(*candidates)
        indices = cv2.dnn.NMSBoxes(
            list(boxes), list(scores), self.policy['score_threshold'], self.policy['nms_threshold'],
        )
        detections = []
        for index in np.asarray(indices).reshape(-1):
            x, y, w, h = boxes[int(index)]
            x1, y1 = max(0, math.floor(x)), max(0, math.floor(y))
            x2, y2 = min(width, math.ceil(x + w)), min(height, math.ceil(y + h))
            if x2 > x1 and y2 > y1:
                detections.append(([x1, y1, x2 - x1, y2 - y1], float(scores[int(index)])))
        detections.sort(key=lambda item: (item[0][1], item[0][0]))
        return [b for b, _ in detections], [s for _, s in detections]

    def run(self, image):
        # OpenCL 设置具有线程关联性；每次进入推理路径都显式关闭。
        cv2.ocl.setUseOpenCL(False)
        with self._lock:
            start = time.perf_counter()
            im = ImageOps.exif_transpose(image).convert('RGB')
            original_width, original_height = im.size
            edge = self.policy['max_long_edge']
            im.thumbnail((edge, edge))
            rgb = np.array(im)
            try:
                boxes, scores = self._detect_yunet(rgb)
            except cv2.error as exc:
                raise RuntimeError('人脸检测失败，请检查本地模型和 OpenCV 环境。') from exc
            height, width = rgb.shape[:2]
            # 输出只含全画面粗马赛克；不输出原图、人脸裁剪或关键点。
            mosaic_size = (max(1, min(32, width // 24)), max(1, min(24, height // 24)))
            safe = cv2.resize(cv2.resize(rgb, mosaic_size), (width, height), interpolation=cv2.INTER_NEAREST)
            for x, y, w, h in boxes:
                cv2.rectangle(safe, (x, y), (x + w, y + h), (20, 180, 190), 2)
            result = {
                'count': len(boxes), 'boxes': boxes,
                'elapsed_ms': 1000 * (time.perf_counter() - start), 'mode': 'yunet',
                'width': width, 'height': height,
                'original_width': original_width, 'original_height': original_height,
                'coordinate_space': 'processed_image', 'backend': 'opencv_cpu',
                'scope': 'anonymous detections only; no identity, no attendance association',
            }
            result.update(scores=scores, model=YUNET_MODEL.name, policy=dict(self.policy))
            return result, Image.fromarray(safe)
