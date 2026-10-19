# 开源及第三方资源使用清单

核查日期2026-10-10。本表区分参考仓库与合法再分发资源；未公开上传，实际团队审核仍待完成。完整环境版本见audit/environment.txt。

|资源/类型|版本与来源|许可|使用、义务与自主边界|状态及开放方式|
|---|---|---|---|---|
|FaceRecognitionAttendance 参考仓库|psesaank，commit980986f55e69bc5c6125ae81abf190af6755656a；https://github.com/psesaank/FaceRecognitionAttendance|未发现LICENSE或明确授权|仅本地审查和运行数据库对照；不复制或再分发源代码、图片、数据库或模型；非授权fork|成果仅保留链接、提交号、哈希与审计结果；如后续复制需先获权利人授权|
|OpenCV运行库|4.10.0实测，https://opencv.org/|Apache-2.0及依赖条款|匿名Haar检测、CLAHE、二维码解码；算法未主张发明；官方依赖安装时遵守NOTICE与第三方条款|提供pyproject.toml与uv.lock，不打包整个环境；团队需复核发布版本|
|Haar正面人脸模型XML|随OpenCV4.10.0，models中原文件及哈希|XML内Intel开源计算机视觉许可，Copyright2000 Intel|保留完整版权、条件与免责；不得用Intel名义背书；原模型不修改，新增预处理和评估独立实现|随源码分发XML；不声称新模型训练成果|
|NASA源照片|scikit-image.data.astronaut，https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut|官方说明public domain/no known copyright restrictions|注明NASA/scikit-image；裁剪合成标注修改；不暗示人物/NASA背书|分发原图和变体，仅工程验证，不作身份识别库|
|Streamlit|原实验1.65.0；当前依赖锁定1.66.0，https://streamlit.io/|Apache-2.0|本地Web与表单，未修改库；新增页面独立实现|依赖安装，保留适用条款|
|qrcode|8.2，https://pypi.org/project/qrcode/|BSD-3-Clause|将签名文本编码成二维码，不发明编码算法；未修改库|依赖安装，需保留版权及免责|
|NumPy与pandas|1.26.4、3.0.6实测，见环境快照|BSD-3-Clause|数组计算、结果表格与导出；未修改库|依赖安装，遵守版权与免责声明|
|Pillow|12.3.0实测，https://pillow.readthedocs.io/|HPND及其第三方条款|读取与缩放图像；未修改库|依赖安装，完整依赖许可另行适用|
|cryptography|当前解析版本见uv.lock，https://cryptography.io/|Apache-2.0或BSD-3-Clause双许可证；二进制组件另适用其条款|本机生成和检查HTTPS自签名证书；不安装根证书或修改设备信任；未修改库|依赖安装，Windows预编译包自带所需组件，无需安装OpenSSL命令；保留适用许可|
|Python与SQLite|Python3.12；SQLite版本见setup.json|Python PSF；SQLite public domain|HMAC-SHA256、secrets、base64、sqlite3；不发明密码算法或数据库|使用系统/官方解释器，依赖版本记录|
|scikit-image|仅数据生成，版本见setup.json|BSD-3-Clause；数据许可独立|读取NASA图；不是模型训练依赖|不打包库；数据说明引用独立素材许可|
|AIC赛事模板|用户2026作品方案模板及附件1/2|用户提供赛事用途材料|保留格式及赛事页眉；不主张赛事标识或模板权利|仅本次参赛文档使用，不作项目商标|
|Codex与系统合成语音|本次代码、实验、文本、图表、排版；macOS Tingting配音|平台与系统适用条款|AI辅助完整披露，真实团队须理解、修改、复验及核查权利；无人工已审核结论|本地材料，团队确认再提交/开放；未生成虚假团队贡献|

新增代码拟MIT开放，只有有权再分发的模型与素材随包保留；根LICENSE不覆盖第三方。署名不是未许可代码的再分发授权。不开放runtime密钥、签到记录或参与者信息。本任务未向上游发Issue/PR，未报名、上传或正式提交。
