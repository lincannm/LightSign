# 浏览器证书错误处理指南

## 常见错误

### `NET::ERR_CERT_AUTHORITY_INVALID`

这是**正常现象**,不是真正的错误!

#### 原因
- 证书是自签名的,未经权威 CA 机构认证
- 浏览器无法验证证书的颁发者
- 但数据传输仍然是加密的,完全安全

#### 解决方法(各浏览器)

### Chrome / Edge

1. 看到警告页面「您的连接不是私密连接」或「此网站不安全」
2. 点击「高级」(Advanced)
3. 点击「继续前往 localhost (不安全)」(Proceed to localhost (unsafe))
4. 页面正常加载

**快捷方式**: 在错误页面直接输入 `thisisunsafe` (不会显示输入内容,直接敲键盘即可)

### Firefox

1. 看到「警告:潜在的安全风险」
2. 点击「高级...」(Advanced...)
3. 点击「接受风险并继续」(Accept the Risk and Continue)
4. 页面正常加载

### Safari (macOS)

1. 看到「此连接不是私密连接」
2. 点击「显示详细信息」(Show Details)
3. 点击「访问此网站」(Visit this Website)
4. 在弹出框中再次点击「访问」(Visit)
5. 可能需要输入 macOS 密码确认

### 手机浏览器

#### Chrome / Edge (Android)
1. 看到「您的连接不是私密连接」
2. 点击「高级」
3. 点击「继续访问 <IP地址> (不安全)」

#### Safari (iOS)
1. 看到「此连接不是私密连接」
2. 点击「显示详细信息」
3. 点击「访问此网站」
4. 在弹出框再次确认「访问」

#### 微信内置浏览器
- 微信浏览器对自签名证书支持较差
- 建议复制链接到 Chrome/Safari 打开
- 或使用「在浏览器中打开」功能

## 其他可能的错误

### `NET::ERR_CERT_COMMON_NAME_INVALID`

**原因**: 访问地址与证书不匹配

**解决**: 
- 使用 `https://localhost:8503` 或 `https://127.0.0.1:8503`
- 或使用启动时显示的局域网 IP

### `NET::ERR_CONNECTION_REFUSED`

**原因**: 应用未启动或端口被占用

**解决**:
```bash
# 确认应用正在运行
python run.py

# 检查端口是否被占用
netstat -ano | findstr :8503
```

### `NET::ERR_SSL_PROTOCOL_ERROR`

**原因**: SSL 配置错误或证书损坏

**解决**:
```bash
# 重新生成证书
python generate_cert.py

# 重启应用
python run.py
```

## 为什么不直接信任证书?

### 方法1: 浏览器每次手动接受(推荐)
- 最简单,无需额外配置
- 每次访问时点击「继续」即可

### 方法2: 将证书添加到系统信任库(可选)

⚠️ **警告**: 仅在完全理解风险的情况下操作

#### Windows
1. 双击 `certs/cert.pem`
2. 点击「安装证书」
3. 选择「当前用户」或「本地计算机」
4. 选择「将所有的证书放入下列存储」
5. 浏览 → 选择「受信任的根证书颁发机构」
6. 完成安装

#### macOS
1. 双击 `certs/cert.pem` 
2. 添加到「钥匙串」
3. 找到证书,双击打开
4. 展开「信任」,选择「始终信任」

#### Linux
```bash
sudo cp certs/cert.pem /usr/local/share/ca-certificates/lightsign.crt
sudo update-ca-certificates
```

### 方法3: 使用真实证书(生产环境)

如需公网访问,使用免费 SSL 证书:

1. **Let's Encrypt** - 最流行的免费证书
   ```bash
   certbot certonly --standalone -d yourdomain.com
   ```

2. **ZeroSSL** - Let's Encrypt 替代方案

3. **Cloudflare** - 提供免费 SSL 代理

然后更新 `.streamlit/config.toml`:
```toml
[server]
sslCertFile = "/path/to/fullchain.pem"
sslKeyFile = "/path/to/privkey.pem"
```

## 安全说明

### 自签名证书的限制

✅ **适用场景**:
- 本地开发和测试
- 内网/局域网使用
- 个人或小团队使用

❌ **不适用场景**:
- 公网生产环境
- 需要多人信任的场景
- 处理敏感数据的商业应用

### 数据是否安全?

虽然浏览器显示警告,但:
- ✅ 数据传输仍然加密 (TLS 1.2+)
- ✅ 可以防止中间人窃听
- ⚠️ 无法验证服务器身份
- ⚠️ 浏览器不会阻止恶意证书

**结论**: 在可信的本地/内网环境中使用是安全的。

## 常见问题

### Q: 为什么不生成没有警告的证书?

A: 要消除警告,证书必须由浏览器信任的 CA 签发。自签名证书无法做到这一点。

### Q: 每次访问都要接受证书吗?

A: 
- 电脑浏览器通常会记住选择,只需接受一次
- 手机浏览器可能每次都要确认
- 将证书添加到系统信任库可以永久解决

### Q: 可以用 HTTP 吗?

A: 可以(删除 `.streamlit/config.toml`),但摄像头功能无法使用。

### Q: 有没有其他方案?

A: 
1. 使用 ngrok/frp 等内网穿透(自动提供 HTTPS)
2. 部署到支持 HTTPS 的云平台
3. 使用 mkcert 工具生成本地信任的证书

## 总结

**`NET::ERR_CERT_AUTHORITY_INVALID` 是正常的,点击「继续」即可使用!**

这个警告只是说"我不认识签发证书的人",不代表"连接不安全"。

---

遇到问题? 查看 [HTTPS_SETUP.md](HTTPS_SETUP.md) 或提交 Issue
