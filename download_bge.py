import os
from modelscope import snapshot_download

# 1. 定义模型 ID
model_id = "BAAI/bge-base-zh-v1.5"

# 2. 直接指定你最终想要的绝对路径（和 Qwen 结构完全一致）
target_dir = "./models1/bge-base-zh-v1.5"

print("正在下载 BGE Embedding 模型到指定目录...")

# 3. 使用 local_dir 参数强行指定目录
model_dir = snapshot_download(
    model_id=model_id, 
    local_dir=target_dir
)

print("\n下载完成！")
print(f"模型文件已直接保存至: {model_dir}")