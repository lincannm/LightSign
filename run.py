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

import click

from light_sign import store
from light_sign.network import participant_base_url

ROOT = Path(__file__).resolve().parent


def log(message="", color=None, bold=False, err=False):
    """终端支持时启用颜色，重定向或设置 NO_COLOR 时保留纯文本。"""
    click.echo(click.style(message, fg=color, bold=bold), err=err,
               color=False if "NO_COLOR" in os.environ else None)


def print_startup(args, scheme, participant_url, certificates):
    log()
    log("  LightSign · 轻签系统", "cyan", bold=True)
    log("  正在启动组织者与参与者服务…", "bright_black")
    log("  " + "─" * 60, "bright_black")
    log()
    log("  组织者入口  ·  活动管理 / 二维码 / 人数清点", "cyan", bold=True)
    organizer_host = "localhost" if args.organizer_host in ("127.0.0.1", "0.0.0.0") else args.organizer_host
    if ":" in organizer_host:
        organizer_host = f"[{organizer_host}]"
    log(f"  {scheme}://{organizer_host}:{args.organizer_port}/", "cyan", bold=True)
    log("  访问范围：本机" if args.organizer_host in ("127.0.0.1", "localhost", "::1") else "  访问范围：由 --organizer-host 指定的监听地址决定", "bright_black")
    log()
    log("  参与者入口  ·  手机扫码签到", "green", bold=True)
    if participant_url:
        log(f"  {participant_url}", "green", bold=True)
        log("  手机与电脑连接同一 Wi-Fi 后，扫描活动二维码签到。", "bright_black")
    else:
        log("  暂无可分享地址，请检查局域网或设置 --participant-url。", "yellow")
    log()
    if certificates:
        log("  HTTPS 提示：使用本机自签名证书，首次访问会有浏览器安全提示。", "yellow")
        log("  系统不会自动安装证书信任或绕过浏览器检查。", "bright_black")
    else:
        log("  HTTP 模式：手机可通过活动链接或上传二维码图片签到。", "yellow")
    log("  按 Ctrl+C 同时停止两个服务。", bold=True)
    log()
    log("  " + "─" * 60, "bright_black")
    log()


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
        log("[证书] 已生成或更新本机 HTTPS 自签名证书。", "green")
    return cert, key


def server_command(app, host, port, certificates):
    return [
        sys.executable, "-m", "streamlit", "run", str(ROOT / app),
        "--server.address", host, "--server.port", str(port),
        "--server.headless", "true",
        # 保留警告和错误，省略与统一启动面板重复的底层启动日志。
        "--logger.level", "warning",
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
    env["STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE"] = "true"
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
        log(f"[网络] {error}", "yellow", err=True)
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
        print_startup(args, scheme, participant_url, certificates)
        for app, host, port in [("app.py", args.organizer_host, args.organizer_port),
                                ("participant.py", args.participant_host, args.participant_port)]:
            processes.append(subprocess.Popen(server_command(app, host, port, certificates), cwd=ROOT, env=env))
        while True:
            for process in processes:
                if process.poll() is not None:
                    log("[停止] 一个入口服务已退出，正在停止另一个入口。", "red", err=True)
                    return process.returncode or 1
            time.sleep(0.3)
    except KeyboardInterrupt:
        log("\n[停止] 正在停止两个入口…", "yellow")
        return 0
    except (OSError, ValueError, ImportError) as error:
        log(f"[错误] 启动失败：{error}", "red", bold=True, err=True)
        return 1
    finally:
        stop_servers(processes)


if __name__ == "__main__":
    sys.exit(main())
