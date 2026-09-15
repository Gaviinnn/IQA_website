import os
import numpy as np
from PIL import Image, ImageOps, ImageFilter

def process_image(input_path, max_size=512, blur_radius=2.0, noise_std=15, quality=20):
    """
    处理单张图片：
    生成两张——统一分辨率版与降质版
    """
    print(f"\n=== 处理：{input_path} ===")

    try:
        img = Image.open(input_path)
    except Exception as e:
        print(f"无法打开：{input_path} ({e})")
        return

    # 修正方向
    img = ImageOps.exif_transpose(img).convert("RGB")

    # 统一分辨率（最长边=max_size）
    w, h = img.size
    scale = max(w, h) / max_size if max(w, h) > max_size else 1
    new_size = (int(w / scale), int(h / scale))
    img_resized = img.resize(new_size, Image.Resampling.LANCZOS)

    # 输出路径
    name, ext = os.path.splitext(input_path)
    unified_path = f"{name}_unified.jpg"
    degraded_path = f"{name}_degraded.jpg"

    # 保存统一分辨率版
    img_resized.save(unified_path, "JPEG", quality=95)

    # 生成降质版（模糊 + 噪声 + 压缩）
    img_degraded = img_resized.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    arr = np.array(img_degraded).astype(np.float32)
    noise = np.random.normal(0, noise_std, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    img_degraded = Image.fromarray(arr)
    img_degraded.save(degraded_path, "JPEG", quality=quality, optimize=False)

    print(f"统一版：{unified_path} ({new_size})")
    print(f"降质版：{degraded_path} (blur={blur_radius}, noise={noise_std}, q={quality})")


def batch_process(folder_path, max_size=512, blur_radius=2.0, noise_std=15, quality=20):
    """
    批量处理文件夹中的图片
    """
    exts = (".jpg", ".jpeg", ".png", ".webp")
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(exts):
            input_path = os.path.join(folder_path, filename)
            process_image(input_path, max_size=max_size,
                          blur_radius=blur_radius, noise_std=noise_std, quality=quality)


if __name__ == "__main__":
    print("请输入图片路径（或文件夹路径）：")
    path = input(">>> ").strip().strip('"')

    m = input("统一最大边长像素（默认512）: ")
    max_size = int(m) if m else 512
    blur = float(input("模糊半径(默认2.0): ") or 2.0)
    noise = float(input("噪声强度(默认15): ") or 15)
    q = int(input("压缩质量(1-100, 默认20): ") or 20)

    if os.path.isdir(path):
        batch_process(path, max_size=max_size, blur_radius=blur, noise_std=noise, quality=q)
    elif os.path.isfile(path):
        process_image(path, max_size=max_size, blur_radius=blur, noise_std=noise, quality=q)
    else:
        print("路径无效，请输入单张图片或文件夹路径。")
