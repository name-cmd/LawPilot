import os
# 【关键修改】在导入任何相关库之前，设置全局环境变量指向国内镜像站
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from huggingface_hub import snapshot_download

# 指定模型名称和目标路径
model_id = "Qwen/Qwen3-0.6B"

save_path = "./models/Qwen2.5-7B-Instruct/"

# 可选：export HF_TOKEN=hf_xxx（访问 gated 模型时需要）
my_hf_token = os.environ.get("HF_TOKEN")

# 确保目标文件夹存在
os.makedirs(save_path, exist_ok=True)

print(f"开始下载模型 {model_id} 到 {save_path} ...")

# 执行下载
# ignore_patterns 可以用来跳过不需要的文件，例如 TensorFlow 或 Safetensors 的特定版本
# 这里我们默认下载所有 PyTorch 相关文件
snapshot_download(
    repo_id=model_id,
    local_dir=save_path,
    local_dir_use_symlinks=False, # 设为 False 可直接保存文件而不是软链接，更方便后续迁移
    token=my_hf_token,
   # 精准排除其他框架的权重以及冗余的传统 PyTorch 权重
    ignore_patterns=[
        "*.msgpack", # 排除 Flax 权重
        "*.h5",      # 排除 TensorFlow 权重
        "*.ot",      # 排除 Rust 权重
        "*.bin"      # 排除传统 PyTorch 权重（保留 model.safetensors 即可）
    ]
)

print("下载完成！")