# 数据来源和协议

唯一源图：scikit-image.data.astronaut，NASA照片。官方说明：https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut ，注明public domain/no known copyright restrictions。数据源身份信息仅用于资源署名；系统不识别该人物，不建立任何身份样本库，不暗示NASA或照片人物支持本项目。

处理：手工固定裁剪(160,50,300,190)，手工近似人脸框(17,16,96,96)相对裁剪；非专家逐图标注。缩放60至144像素、在640×480纯色场景粘贴0至4张裁剪、亮度变化和模糊。GT由合成位置及手工参考框计算，不由待测检测器输出生成。每组80图，四条件各20图，每条件0/1/2/3/4人脸各4图。源照片为同一人物，多个框是重复图像实例，不是独立真实人。

development种子1010，test种子20261010，源脸共享；所有变换和SHA256记录于manifest。YuNet 参数固定后，development 和 test 分别评估，不在 test 上调参。无训练数据或新模型训练。

图片本身来自公有领域素材；本项目生成代码MIT。保留NASA及scikit-image来源和修改说明。未使用原仓库人脸、学生信息或真实参与者图片。没有新增真人标注成果。最重要的局限是单源脸，不能用高分承诺真实活动计数效果。
