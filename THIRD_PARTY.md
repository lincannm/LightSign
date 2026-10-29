# 开源及第三方资源使用清单

核查日期 2026-10-29。本表区分参考仓库与可合法再分发的资源；根目录 LICENSE（MIT）只覆盖项目自主编写的代码，不覆盖下列第三方资源。完整环境版本见 experiments/audit/environment.txt，数据来源与使用边界见 experiments/data/README.md。

|资源/类型|版本与来源|许可|使用、义务与自主边界|状态及开放方式|
|---|---|---|---|---|
|FaceRecognitionAttendance 参考仓库|psesaank，commit980986f55e69bc5c6125ae81abf190af6755656a；https://github.com/psesaank/FaceRecognitionAttendance|未发现LICENSE或明确授权|仅本地审查和运行数据库对照；不复制或再分发源代码、图片、数据库或模型；非授权fork|已核验（不分发，仅保留链接、提交号、哈希与审计结论）|
|OpenCV运行库|4.10.0实测，https://opencv.org/|Apache-2.0及依赖条款|YuNet人脸检测、二维码解码；未修改库；官方依赖安装时遵守NOTICE与第三方条款|已核验（提供pyproject.toml与uv.lock，不打包整个环境）|

|YuNet人脸检测模型|OpenCV Zoo `face_detection_yunet_2023mar.onnx`，固定 revision 48b10fa505aeb51fbd127fc60a5c660040e823b7；模型SHA-256见 `models/yunet.provenance.json`|MIT，完整文本见 `models/LICENSE.yunet`|仅用于人脸框检测，不使用SFace或任何身份特征；保留模型版权、许可和来源元数据|已核验（模型随项目仓库分发；不自动联网下载）|
|NASA源照片|scikit-image.data.astronaut，https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut|官方说明public domain/no known copyright restrictions|注明NASA/scikit-image；裁剪、合成、标注属于修改；不暗示人物/NASA背书|已核验（分发原图和变体，仅工程验证，不作身份识别库）|
|Streamlit与click|Streamlit 原实验1.65.0、当前锁定1.66.0；click 8.5.0，https://streamlit.io/|Apache-2.0 / BSD-3-Clause|本地Web界面、表单与启动终端输出，未修改库；新增页面独立实现|已核验（依赖安装，保留适用条款）|
|qrcode|8.2，https://pypi.org/project/qrcode/|BSD-3-Clause|将签名文本编码成二维码；未修改库|已核验（依赖安装，保留版权及免责）|
|NumPy与pandas|1.26.4、3.0.6实测，见环境快照|BSD-3-Clause|数组计算、结果表格与导出；未修改库|已核验（依赖安装，保留版权与免责声明）|
|Pillow|12.3.0实测，https://pillow.readthedocs.io/|HPND及其第三方条款|读取、方向校正与缩放图像；未修改库|已核验（依赖安装，完整依赖许可另行适用）|
|cryptography|46.0.7，见uv.lock，https://cryptography.io/|Apache-2.0或BSD-3-Clause双许可证；二进制组件另适用其条款|本机生成和检查HTTPS自签名证书；不安装根证书或修改设备信任；未修改库|已核验（依赖安装，本机私钥不随成果分发）|
|Python与SQLite|Python3.12；SQLite版本见experiments/results/setup.json|Python PSF；SQLite public domain|HMAC-SHA256、secrets、base64、sqlite3；使用标准库实现，未自行实现密码算法|已核验（使用官方解释器，依赖版本有记录）|
|scikit-image与matplotlib|0.24.0、3.11.2，仅实验数据生成与绘图，见experiments/audit/environment.txt|BSD-3-Clause / PSF风格许可；数据许可独立|读取NASA源图与绘制统计图表；不是模型训练或日常运行依赖|已核验（可选依赖，不打包库；数据说明引用独立素材许可）|
|AIC赛事模板|2026作品方案模板及附件1/2|赛事方提供的参赛用材料|保留格式及赛事页眉；不主张赛事标识或模板权利|不适用（仅本次参赛文档使用）|
|AI辅助工具|Codex、Claude Code|平台适用条款|辅助代码、实验脚本、文本、图表与排版；团队成员负责理解、修改、复跑与来源核查|已核验（使用范围在技术报告中披露）|

参赛阶段以网盘链接受限提交源码、模型、实验数据与结果，晋级后按技术报告中的开放计划公开。只有可再分发的模型与素材随包保留。不公开 local_data/ 中的签名密钥、签到记录，也不分发 certs/ 中的本机私钥。
