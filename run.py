#!/usr/bin/env python3
"""同时启动组织者与参与者入口，退出时回收两个服务进程。"""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

from light_sign import store
from light_sign.network import participant_base_url

ROOT = Path(__file__).resolve().parent


def port_number(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须在 1 到 65535 之间")
    return port


def certificate_files(http=False, hosts=()):
    if http:
        return None
    from light_sign.certificates import certificate_paths, ensure_certificate
    cert, key = certificate_paths(ROOT)
    if ensure_certificate(cert, key, hosts):
        print("已生成或更新本机 HTTPS 自签名证书。", flush=True)
    return cert, key


def server_command(app, host, port, certificates):
    return [
        sys.executable, "-m", "streamlit", "run", str(ROOT / app),
        "--server.address", host, "--server.port", str(port),
        "--server.headless", "true",
        # --http 显式覆盖配置中的证书路径。
        "--server.sslCertFile", str(certificates[0]) if certificates else "",
        "--server.sslKeyFile", str(certificates[1]) if certificates else "",
    ]


def stop_servers(processes):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organizer-port", type=port_number, default=8503)
    parser.add_argument("--participant-port", type=port_number, default=8504)
    parser.add_argument("--organizer-host", default="127.0.0.1", help="组织者默认仅本机可访问")
    parser.add_argument("--participant-host", default="0.0.0.0", help="参与者默认允许局域网访问")
    parser.add_argument("--participant-url", help="二维码中的参与者入口，例如 https://192.168.1.10:8504/")
    parser.add_argument("--http", action="store_true", help="使用 HTTP，局域网手机摄像头需要 HTTPS")
    args = parser.parse_args(argv)
    if args.organizer_port == args.participant_port:
        parser.error("组织者和参与者必须使用不同端口")

    scheme = "http" if args.http else "https"
    env = os.environ.copy()
    env["LIGHTSIGN_PARTICIPANT_PORT"] = str(args.participant_port)
    env["LIGHTSIGN_PARTICIPANT_HOST"] = args.participant_host
    env["LIGHTSIGN_PARTICIPANT_SCHEME"] = scheme
    if args.participant_url:
        from light_sign.links import participant_link
        try:
            participant_link(args.participant_url, "validate-address")
        except ValueError as error:
            parser.error(str(error))
        env["LIGHTSIGN_PARTICIPANT_URL"] = args.participant_url

    try:
        participant_url = participant_base_url(
            scheme, args.participant_port, args.participant_host,
            override=env.get("LIGHTSIGN_PARTICIPANT_URL"),
        )
    except ValueError as error:
        participant_url = None
        print(str(error), file=sys.stderr)
    if participant_url:
        # 本次运行固定分享地址，使二维码与启动时生成的证书地址一致。
        env["LIGHTSIGN_PARTICIPANT_URL"] = participant_url

    processes = []
    try:
        # 启动前检查两个端口，避免只启动一半，也不影响其他已有服务。
        for host, port in [(args.organizer_host, args.organizer_port),
                           (args.participant_host, args.participant_port)]:
            with socket.socket() as probe:
                probe.bind((host, port))
        hosts = [args.organizer_host, args.participant_host]
        if participant_url:
            hosts.append(urlsplit(participant_url).hostname)
        certificates = certificate_files(args.http, hosts)
        connection = store.connect()
        connection.close()
        store.key()
        print("正在启动 LightSign 轻签系统…", flush=True)
        print(f"组织者入口：{scheme}://localhost:{args.organizer_port}/（默认仅本机）", flush=True)
        if participant_url:
            print(f"参与者入口：{participant_url}", flush=True)
        print("手机连接同一 Wi-Fi 后，扫描组织者页面的活动二维码签到。按 Ctrl+C 同时停止两个服务。", flush=True)
        if certificates:
            print("已启用 HTTPS；浏览器会按默认规则显示自签名证书警告，系统不会安装信任或绕过检查。", flush=True)
        else:
            print("使用 HTTP；局域网手机可使用活动链接或上传二维码图片签到。", flush=True)
        for app, host, port in [("app.py", args.organizer_host, args.organizer_port),
                                ("participant.py", args.participant_host, args.participant_port)]:
            processes.append(subprocess.Popen(server_command(app, host, port, certificates), cwd=ROOT, env=env))
        while True:
            for process in processes:
                if process.poll() is not None:
                    print("一个入口服务已退出，正在停止另一个入口。", file=sys.stderr)
                    return process.returncode or 1
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n正在停止两个入口…")
        return 0
    except (OSError, ValueError, ImportError) as error:
        print(f"启动失败：{error}", file=sys.stderr)
        return 1
    finally:
        stop_servers(processes)


if __name__ == "__main__":
    sys.exit(main())
