# Snipaste 复制剪贴板优化器（含自动清理）

该工具用于优化从 Snipaste 或其他应用复制到剪贴板的图片：将原始未压缩位图（BMP）自动压缩为 PNG，以显著降低体积。同时自动管理临时文件，避免长期运行占用磁盘空间。

## 功能特性
- 剪贴板图片自动压缩：BMP 自动转为 PNG
- 两种工作模式：
  - IMAGE：将 PNG 直接写回剪贴板为 PNG 格式（部分应用不支持）
  - FILE：保存 PNG 到临时目录并以“文件”形式放入剪贴板（兼容性最佳）
- 临时目录自动清理：
  - 目录：%TEMP%\\snipaste_png_clip
  - 保留最近 N 小时的文件（默认 24h）
  - 限制目录总容量（默认 200 MB）
  - 限制文件总数（默认 1000）
  - 在启动时及每次生成新文件后自动清理
- 可靠的剪贴板监听，避免重复处理
- 带时间戳的详细日志输出

## 环境依赖
- Windows 10/11（64 位）
- Python 3.8+
- 依赖包：`pillow`、`pywin32`

安装依赖：

```bash
pip install pillow pywin32
```

## 使用方法
在 PowerShell 或 CMD 中运行：

```bash
python clipboard_compress_cli_v1.0.py --mode FILE
```

- IMAGE 模式（剪贴板仅包含 PNG 内容）：

```bash
python clipboard_compress_cli_v1.0.py --mode IMAGE
```

- 调整清理阈值：

```bash
python clipboard_compress_cli_v1.0.py --mode FILE \
  --max-age-hours 12 --max-total-mb 100 --max-files 300
```

- 只执行一次清理后退出：

```bash
python clipboard_compress_cli_v1.0.py --clean-now
```

## 注意事项
- 压缩后 PNG 的大小与 Snipaste 手动保存 PNG 类似（通常约 1MB）。
- 若目标程序粘贴后仍显示 20MB+ 的位图，说明它只读取 BMP（未压缩位图），这是目标程序的行为，与本工具压缩逻辑无关。
- FILE 模式在各类应用中具有更好的通用兼容性。

## 工作原理
- 监听剪贴板序列号变化以触发处理
- 使用 Pillow 的 ImageGrab 读取剪贴板图片
- 压缩为 PNG
- 根据模式：
  - IMAGE：注册 PNG 剪贴板格式并写入 PNG 字节
  - FILE：写入 PNG 到临时目录并设置 CF_HDROP 使剪贴板包含文件
- 按年龄、总容量、文件数量对临时目录进行周期性清理

## 许可证
MIT（可根据你的需要更改）

## 致谢
- 为提升 Windows 环境下 Snipaste 的剪贴板工作流而构建
- 使用 Pillow 与 pywin32，并通过 WinAPI 进行低级内存操作