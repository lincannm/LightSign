#!/usr/bin/env python3
"""LightSign 项目启动脚本

可以通过以下方式运行：
- uv run run.py
- python run.py
"""
import sys
import subprocess
from pathlib import Path


def main():
    """启动 Streamlit 应用"""
    # 确保在项目根目录
    project_root = Path(__file__).parent

    # Streamlit 运行参数
    app_file = project_root / "app.py"

    if not app_file.exists():
        print(f"错误: 找不到应用文件 {app_file}", file=sys.stderr)
        sys.exit(1)

    # 检查证书文件
    cert_file = project_root / "certs" / "cert.pem"
    key_file = project_root / "certs" / "key.pem"

    # 构建命令 - Streamlit 会自动读取 .streamlit/config.toml
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_file)
    ]

    print("正在启动 LightSign 轻签系统...")
    if cert_file.exists() and key_file.exists():
        print("✓ 已启用 HTTPS 支持")
        print("  访问地址: https://localhost:8503")
        print("  局域网访问: https://<本机IP>:8503")
        print()
        print("注意: 首次访问需要在浏览器中接受自签名证书")
        print("  - Chrome/Edge: 点击「高级」→「继续访问」")
        print("  - Firefox: 点击「高级」→「接受风险并继续」")
        print("  - Safari: 点击「显示详细信息」→「访问此网站」")
    else:
        print("⚠ 未找到 SSL 证书,使用 HTTP 模式")
        print("  访问地址: http://localhost:8503")
    print()

    try:
        # 启动 Streamlit
        subprocess.run(cmd, cwd=project_root)
    except KeyboardInterrupt:
        print("\n应用已停止")
    except Exception as e:
        print(f"启动失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
