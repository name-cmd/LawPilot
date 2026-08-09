# -*- coding: utf-8 -*-
"""下载 4 个供应商官方 logo（Qwen / DeepSeek / Kimi / GLM），存到前端 public/logos/。

用途：模型选择器在模型名前展示供应商 logo（web/frontend/src/components/chat/ModelSelector.vue）。
每个品牌有多个候选官方来源（GitHub 官方组织头像最稳定），按顺序尝试，失败自动换下一个；
全部失败时打印中文提示，可手动下载图片放到指定位置并命名为规定文件名。

用法：
    C:/Users/75806/.conda/envs/LawTrust/python.exe scripts/download_model_logos.py [--force]
"""
import argparse
import io
import sys
from pathlib import Path

import requests
from PIL import Image

# 各品牌候选来源（按优先级排序；GitHub 官方组织头像地址稳定、常年可用）
BRANDS = {
    # brand 名（也是文件名）: [(来源描述, URL), ...]
    "qwen": [
        ("Qwen 官方 GitHub 组织头像", "https://avatars.githubusercontent.com/QwenLM"),
        ("通义千问官网 favicon", "https://qianwen.aliyun.com/favicon.ico"),
    ],
    "deepseek": [
        ("DeepSeek 官方 GitHub 组织头像", "https://avatars.githubusercontent.com/deepseek-ai"),
        ("DeepSeek 官网 favicon", "https://www.deepseek.com/favicon.ico"),
    ],
    "kimi": [
        ("Kimi 官方 GitHub 组织头像", "https://avatars.githubusercontent.com/MoonshotAI"),
        ("Kimi 官网 favicon", "https://www.kimi.com/favicon.ico"),
    ],
    "glm": [
        # zai-org 是智谱（Z.ai）官方开源组织，GLM 系列模型的发布方；zhipuai 组织头像为空占位图、官网 favicon 返回 HTML，均不可用
        ("智谱 Z.ai 官方 GitHub 组织头像", "https://avatars.githubusercontent.com/zai-org"),
    ],
}

# 前端期望的存放目录（Vite publicDir，构建时原样复制进 dist）
LOGO_DIR = Path(__file__).resolve().parent.parent / "web" / "frontend" / "public" / "logos"


def is_png(data: bytes) -> bool:
    """校验文件头是否为 PNG（\\x89PNG）。"""
    return data[:4] == b"\x89PNG"


def is_ico(data: bytes) -> bool:
    """校验文件头是否为 ICO（00 00 01 00）。"""
    return data[:4] == b"\x00\x00\x01\x00"


def download_brand(brand: str, urls: list, force: bool) -> bool:
    """尝试下载某个品牌，成功返回 True。ICO 源会经 PIL 转成 PNG 再存盘（保证扩展名与内容一致）。"""
    target = LOGO_DIR / f"{brand}.png"
    if target.exists() and not force:
        print(f"  [{brand}] 已存在（跳过，--force 可强制重下）：{target}")
        return True
    for desc, url in urls:
        try:
            print(f"  [{brand}] 尝试 {desc}：{url}")
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.content
            target.parent.mkdir(parents=True, exist_ok=True)
            if is_png(data):
                target.write_bytes(data)
            elif is_ico(data):
                # 官网 favicon 多为 ICO：用 PIL 转成 PNG，浏览器 <img> 才能稳妥显示
                Image.open(io.BytesIO(data)).save(target, "PNG")
            else:
                print(f"    -> 内容不是 PNG/ICO 图片（{len(data)} 字节），换下一个来源")
                continue
            print(f"    -> 成功：{target}（{target.stat().st_size} 字节）")
            return True
        except Exception as e:
            print(f"    -> 失败：{e}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 4 个供应商官方 logo 到 web/frontend/public/logos/")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的文件")
    args = parser.parse_args()

    print(f"下载目录：{LOGO_DIR}")
    failed = []
    for brand, urls in BRANDS.items():
        if not download_brand(brand, urls, args.force):
            failed.append(brand)

    if failed:
        print("\n以下品牌下载失败，请手动下载对应官方 logo（透明背景 PNG 最佳）后放到：")
        print(f"  {LOGO_DIR}")
        for brand in failed:
            print(f"  - {brand}.png")
        print("完成后重新运行本脚本（或直接刷新页面，缺图的模型只是不显示 logo，不影响使用）。")
        return 1

    print("\n全部 logo 就绪！接下来：cd web/frontend && npm run build，然后重启后端生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
