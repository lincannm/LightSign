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

    # 构建命令
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_file),
        "--server.port", "8503",
        "--server.address", "127.0.0.1"
    ]

    print("正在启动 LightSign 轻签系统...")
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
