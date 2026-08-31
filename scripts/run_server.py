#!/usr/bin/env python3
"""Start LawPilot web server."""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn

if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = 6006

    # 获取本机局域网 IP，方便测试人员在同一 WiFi 下直连
    lan_ip = "无法获取"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("114.114.114.114", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print("=" * 56)
    print("  律策智枢 LawPilot — 服务启动")
    print("=" * 56)
    print(f"  本机访问：  http://localhost:{PORT}")
    print(f"            http://127.0.0.1:{PORT}")
    if lan_ip != "无法获取":
        print(f"  局域网访问：http://{lan_ip}:{PORT}")
    print(f"  API 文档：  http://localhost:{PORT}/docs")
    print("=" * 56)
    print()

    # 启动前预检端口占用：重复启动是常见操作失误（uvicorn 报 [Errno 10048]），
    # 这里先探测一次，给出通俗提示而不是让初学者看裸报错
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((HOST, PORT))
        except OSError:
            print("=" * 56)
            print("  ❌ 启动失败：端口 6006 已被占用")
            print("     说明：之前启动的服务仍在运行，无需重复启动。")
            print("     如需重启：先关闭旧进程（任务管理器里结束 python 进程），再运行本脚本。")
            print("=" * 56)
            sys.exit(1)

    uvicorn.run(
        "web.backend.main:app",
        host=HOST,
        port=PORT,
        reload=False,
    )
