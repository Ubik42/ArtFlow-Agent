from __future__ import annotations

from pathlib import Path

import bpy
import numpy as np

repo_root = Path(__file__).resolve().parents[2]
root = repo_root / "artifacts/goal/m24-s1-scene-conditioning"
source = root / "depth.exr"
target = root / "depth-normalized.png"
beauty_path = root / "beauty.png"
conditioning_path = root / "scene-conditioning.png"

image = bpy.data.images.load(str(source), check_existing=False)
width, height = image.size
pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
depth = pixels[:, :, 0]
valid = depth[np.isfinite(depth) & (depth > 0) & (depth < 1.0e9)]
if valid.size == 0:
    raise RuntimeError("Unreal depth pass has no finite positive pixels")
near, far = np.percentile(valid, [2.0, 98.0])
if far <= near:
    raise RuntimeError("Unreal depth pass has no usable range")
normalized = 1.0 - np.clip((depth - near) / (far - near), 0.0, 1.0)
normalized[~np.isfinite(depth)] = 0.0
rgba = np.empty((height, width, 4), dtype=np.float32)
rgba[:, :, :3] = normalized[:, :, None]
rgba[:, :, 3] = 1.0
output = bpy.data.images.new("ArtFlow_NormalizedDepth", width=width, height=height, alpha=True)
output.pixels = rgba.reshape(-1)
output.filepath_raw = str(target)
output.file_format = "PNG"
output.save()
beauty_image = bpy.data.images.load(str(beauty_path), check_existing=False)
beauty = np.asarray(beauty_image.pixels[:], dtype=np.float32).reshape(height, width, 4)
conditioning = beauty.copy()
conditioning[:, :, :3] = np.clip(
    beauty[:, :, :3] * (0.78 + 0.22 * normalized[:, :, None]), 0.0, 1.0
)
conditioning_image = bpy.data.images.new(
    "ArtFlow_SceneConditioning", width=width, height=height, alpha=True
)
conditioning_image.pixels = conditioning.reshape(-1)
conditioning_image.filepath_raw = str(conditioning_path)
conditioning_image.file_format = "PNG"
conditioning_image.save()
print(f"ARTFLOW_DEPTH_NORMALIZED near={near:.6f} far={far:.6f} size={width}x{height}")
