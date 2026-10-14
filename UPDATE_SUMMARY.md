# 更新总结 - 2026年10月14日

## 已完成的改进

### 1. 添加摄像头扫码功能 ✓

**问题**: 签到界面只能手动输入或上传图片,手机用户无法直接扫码

**解决方案**: 
- 新增三种二维码输入方式供用户选择
- 添加 `st.camera_input()` 支持实时摄像头扫描
- 使用 OpenCV 的 `QRCodeDetector` 解码二维码

**修改文件**:
- [app.py:37-56](app.py:37-56) - 重构签到输入逻辑

### 2. 优化术语 - "台账"改为"记录" ✓

**问题**: "台账"是会计术语,对普通用户较为生僻

**解决方案**: 全局替换为更通俗的"记录"

**修改位置**:
- [app.py](app.py) - 3处
- [README.md](README.md) - 2处  
- [THIRD_PARTY.md](THIRD_PARTY.md) - 1处

### 3. 启用 HTTPS 支持 ✓

**问题**: 现代浏览器要求 HTTPS 才能访问摄像头,HTTP 环境无法使用扫码功能

**解决方案**:
- 生成自签名 SSL 证书 (RSA 4096位, 有效期365天)
- 配置 Streamlit HTTPS 服务 (端口8503)
- 启动脚本自动检测证书并显示访问信息
- 支持 localhost 和局域网访问

**新增文件**:
- `.streamlit/config.toml` - Streamlit HTTPS 配置
- `certs/openssl.cnf` - OpenSSL 证书配置
- `certs/cert.pem` - SSL 证书 (已生成,未提交)
- `certs/key.pem` - 私钥 (已生成,未提交)
- `generate_cert.py` - 证书生成脚本
- `HTTPS_SETUP.md` - 详细配置文档
- `QUICKSTART.md` - 快速启动指南
- `HTTPS_TEST_CHECKLIST.md` - 功能测试清单

**修改文件**:
- `run.py` - 添加证书检测和 IP 地址显示
- `README.md` - 添加 HTTPS 使用说明
- `.gitignore` - 排除证书和私钥文件

## Git 提交记录

```
e927091 docs(https): 添加快速启动指南和测试清单
2b00892 feat(https): 添加 HTTPS 支持以启用手机端摄像头扫码
1be0f2e feat(签到): 添加摄像头扫码功能并优化术语
```

## 如何使用

### 电脑访问

```bash
python run.py
```

访问 https://localhost:8503 并接受证书警告。

### 手机扫码

1. 启动应用,查看显示的局域网 IP 地址
2. 手机连接同一 WiFi
3. 访问 `https://<IP地址>:8503`
4. 接受证书警告
5. 进入"自愿签到"标签
6. 选择"摄像头扫码"
7. 允许摄像头权限
8. 对准二维码扫描

## 技术要点

### 为什么需要 HTTPS?

现代浏览器的安全策略:
- HTTP 环境下禁止访问摄像头/麦克风等敏感权限
- 只有 HTTPS 或 localhost 可以使用媒体设备
- 这是 W3C 标准,所有主流浏览器都遵守

### 自签名证书是否安全?

对于本地开发和内网使用,自签名证书是完全安全的:
- 数据仍然加密传输
- 浏览器警告只是因为证书未经权威机构认证
- 不适合公网部署 (公网应使用 Let's Encrypt 等免费证书)

### 证书配置

- **加密算法**: RSA 4096位
- **有效期**: 365天
- **支持域名**: localhost, 127.0.0.1
- **支持IP**: 127.0.0.1, 0.0.0.0 (通配所有网卡)

## 故障排查

### 手机无法访问

1. 确认手机和电脑在同一 WiFi
2. 检查电脑防火墙 (允许 8503 端口)
3. 临时关闭防火墙测试

### 摄像头无法打开

1. 确认使用 HTTPS (地址栏有锁图标)
2. 检查浏览器权限设置
3. 尝试刷新页面

### 证书过期

```bash
python generate_cert.py
```

## 下一步计划

- [ ] 添加二维码批量生成功能
- [ ] 支持导出签到数据为 Excel
- [ ] 添加签到统计图表
- [ ] 优化移动端界面布局

## 相关文档

- [HTTPS_SETUP.md](HTTPS_SETUP.md) - HTTPS 详细配置说明
- [QUICKSTART.md](QUICKSTART.md) - 快速启动指南  
- [HTTPS_TEST_CHECKLIST.md](HTTPS_TEST_CHECKLIST.md) - 功能测试清单
- [README.md](README.md) - 项目主文档

---

**更新日期**: 2026年10月14日  
**Git 分支**: main  
**Python 版本**: 3.14  
**Streamlit 版本**: 1.41.1
