"""匿名清点的 CPU 兼容路径及按钮交互回归检查。"""

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from light_sign import store, vision

ROOT = Path(__file__).resolve().parents[2]


class CounterTests(unittest.TestCase):
    def test_yunet_counts_current_samples_and_preserves_metadata(self):
        counter = vision.Counter()
        with Image.open(ROOT / 'samples' / '多人合成样例.png') as image:
            result, safe = counter.run(image)
        self.assertEqual(result['count'], 4)
        self.assertEqual(result['mode'], 'yunet')
        self.assertEqual(result['backend'], 'opencv_cpu')
        self.assertEqual(result['model'], 'face_detection_yunet_2023mar.onnx')
        self.assertEqual(len(result['scores']), 4)
        self.assertEqual(safe.size, (640, 480))

    def test_yunet_test_set_is_readable_without_using_predictions_as_labels(self):
        annotations = json.loads((ROOT / 'samples_yunet' / 'annotations.json').read_text(encoding='utf-8'))
        self.assertEqual(set(annotations['images']), {'1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg'})
        self.assertTrue(all(isinstance(item['count'], int) for item in annotations['images'].values()))
        counter = vision.Counter()
        for path in sorted((ROOT / 'samples_yunet').glob('*.jpg')):
            with self.subTest(path=path.name):
                with Image.open(path) as image:
                    result, safe = counter.run(image)
            self.assertGreaterEqual(result['count'], 0)
            self.assertEqual(safe.size, image.size)

    def test_samples_finish_in_fresh_process_without_opencl_configuration(self):
        # 子进程设定超时，让驱动卡死回归能够明确失败，而非挂住整个测试。
        script = """
import json
from PIL import Image
from light_sign.vision import Counter, ROOT
counter = Counter()
results = {}
for path in sorted((ROOT / 'samples').glob('*.png')):
    with Image.open(path) as image:
        result, safe = counter.run(image)
    results[path.name] = {'count': result['count'], 'size': safe.size}
print(json.dumps(results))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", timeout=30, check=True,
        )
        results = json.loads(completed.stdout)
        self.assertEqual({name: item["count"] for name, item in results.items()}, {
            "合成弱光样例.png": 4,
            "多人合成样例.png": 4,
            "无人场景.png": 0,
        })
        self.assertTrue(all(item["size"] == [640, 480] for item in results.values()))

    def test_every_run_disables_opencl_before_image_processing(self):
        counter = vision.Counter()
        convert = vision.cv2.cvtColor

        with patch.object(vision.cv2.ocl, "setUseOpenCL", wraps=vision.cv2.ocl.setUseOpenCL) as disable:
            def cpu_convert(*args, **kwargs):
                disable.assert_called_with(False)
                return convert(*args, **kwargs)

            with patch.object(vision.cv2, "cvtColor", side_effect=cpu_convert):
                for _ in range(2):
                    result, safe = counter.run(Image.new("RGB", (96, 96)))
                    self.assertEqual(result["count"], 0)
                    self.assertEqual(safe.size, (96, 96))
            self.assertEqual(disable.call_count, 2)


class CountingPageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / "test.db"
        connect = store.connect
        self.connect_patch = patch.object(store, "connect", side_effect=lambda: connect(database))
        self.key_patch = patch.object(store, "key", return_value=b"counting-test-key")
        self.connect_patch.start()
        self.addCleanup(self.connect_patch.stop)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.session_state["organizer_authenticated"] = True
        app.run()
        self.assertEqual(len(app.exception), 0)
        return app

    def start_button(self, app):
        return next(button for button in app.button if button.label == "开始清点")

    def test_counting_button_shows_real_result_and_anonymized_image(self):
        app = self.app()
        self.assertFalse(self.start_button(app).disabled)
        self.start_button(app).click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["counter_result"]["count"], 4)
        self.assertEqual(app.session_state["counter_image"].size, (640, 480))
        self.assertTrue(any(metric.label == "检测到的人脸框数" and metric.value == "4"
                            for metric in app.metric))
        self.assertTrue(any(button.label == "下载结果 JSON" for button in app.get("download_button")))

    def test_empty_scene_shows_zero_instead_of_hiding_result(self):
        app = self.app()
        scene = next(select for select in app.selectbox if select.label == "选择场景")
        scene.set_value(ROOT / "samples" / "无人场景.png").run()
        self.start_button(app).click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["counter_result"]["count"], 0)
        self.assertTrue(any(metric.label == "检测到的人脸框数" and metric.value == "0"
                            for metric in app.metric))

    def test_sources_without_image_disable_start_and_show_guidance(self):
        for source in ("上传图片", "摄像头拍摄"):
            with self.subTest(source=source):
                app = self.app()
                app.radio[0].set_value(source).run()
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(self.start_button(app).disabled)
                self.assertTrue(any("请先上传图片或拍摄照片" in item.value for item in app.info))

    def test_uploaded_image_can_be_counted(self):
        app = self.app()
        with (ROOT / "samples" / "多人合成样例.png").open("rb") as handle:
            image = io.BytesIO(handle.read())
        with patch("streamlit.file_uploader", return_value=image):
            app.radio[0].set_value("上传图片").run()
            self.assertFalse(self.start_button(app).disabled)
            self.start_button(app).click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["counter_result"]["count"], 4)

    def test_camera_photo_can_be_counted(self):
        app = self.app()
        with (ROOT / "samples" / "多人合成样例.png").open("rb") as handle:
            image = io.BytesIO(handle.read())
        with patch("streamlit.camera_input", return_value=image):
            app.radio[0].set_value("摄像头拍摄").run()
            self.assertFalse(self.start_button(app).disabled)
            self.start_button(app).click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["counter_result"]["count"], 4)


if __name__ == "__main__":
    unittest.main()
