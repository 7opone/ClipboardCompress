# ============================================================
# Snipaste Clipboard Optimizer - 带自动清理功能版
# ============================================================
# 📘 功能说明：
#   本脚本用于优化 Snipaste 截图复制后的剪贴板内容，
#   将原始未压缩的位图（BMP）自动压缩为 PNG，以减小体积。
#   同时自动管理生成的临时文件，避免长期运行占用磁盘空间。
#
# ⚙️ 工作模式：
#   --mode IMAGE ：将压缩后的 PNG 写回剪贴板（仅含 PNG 格式）
#                  ⚠️ 部分应用不支持 PNG 剪贴板，可能粘贴失败；
#                  优点：不生成临时文件。
#
#   --mode FILE  ：生成临时 PNG 文件并放入剪贴板（CF_HDROP）
#                  ✅ 兼容性最佳，几乎所有程序都能正常“粘贴文件”；
#                  缺点：会在临时目录生成图片，但会自动清理。
#
# 💾 临时目录与清理策略：
#   - 临时目录：%TEMP%\snipaste_png_clip
#   - 每次启动时和每次生成新文件后自动清理
#   - 默认策略：
#       ▪ 保留最近 24 小时内的文件
#       ▪ 限制目录总容量 ≤ 200 MB
#       ▪ 限制文件总数 ≤ 1000 个
#   - 可通过命令行参数修改：
#       --max-age-hours  <小时>
#       --max-total-mb   <容量MB>
#       --max-files      <数量>
#   - 手动清理一次后退出：
#       python snipaste_clipboard_optimizer_clean.py --clean-now
#
# 🧩 使用示例：
#   1️⃣ 普通启动（推荐 FILE 模式）：
#       python snipaste_clipboard_optimizer_clean.py --mode FILE
#   2️⃣ 若目标程序支持 PNG 剪贴板（如浏览器、部分 IM）：
#       python snipaste_clipboard_optimizer_clean.py --mode IMAGE
#   3️⃣ 修改清理阈值：
#       python snipaste_clipboard_optimizer_clean.py --mode FILE \
#           --max-age-hours 12 --max-total-mb 100 --max-files 300
#
# 💡 注意事项：
#   - 压缩后文件大小与 Snipaste 手动保存 PNG 相同（≈1MB）。
#   - 程序通过监听剪贴板变化自动触发，不会重复处理。
#   - 若你的程序粘贴后仍是 20MB+，说明它只读取未压缩位图，
#     属于目标程序行为，与压缩逻辑无关。
#
# 🧰 环境依赖：
#   pip install pillow pywin32
#
# 🧱 兼容性：
#   - Windows 10/11（64位）
#   - Python 3.8+
#
# 📦 版本：
#   2025.10.31  优化版（含自动清理、日志时间戳、错误处理）
#
# ============================================================

import argparse, datetime as dt, io, os, sys, struct, tempfile, time, ctypes
from ctypes import wintypes
from PIL import ImageGrab, Image
import win32clipboard as wcb, win32con
import win32gui, win32process

# ---------- Windows 内存 API ----------
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
GMEM_MOVEABLE = 0x0002
GlobalAlloc = kernel32.GlobalAlloc; GlobalAlloc.argtypes=[wintypes.UINT, ctypes.c_size_t]; GlobalAlloc.restype=wintypes.HGLOBAL
GlobalLock  = kernel32.GlobalLock;  GlobalLock.argtypes=[wintypes.HGLOBAL]; GlobalLock.restype=ctypes.c_void_p
GlobalUnlock= kernel32.GlobalUnlock;GlobalUnlock.argtypes=[wintypes.HGLOBAL];GlobalUnlock.restype=wintypes.BOOL
RtlMoveMemory = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t) (("RtlMoveMemory", ctypes.WinDLL("kernel32")))

# ---------- 进程查询 API ----------
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
OpenProcess = kernel32.OpenProcess; OpenProcess.argtypes=[wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]; OpenProcess.restype=wintypes.HANDLE
CloseHandle = kernel32.CloseHandle; CloseHandle.argtypes=[wintypes.HANDLE]; CloseHandle.restype=wintypes.BOOL

# ---------- 默认配置 ----------
POLL_INTERVAL = 0.4
RETRY_OPEN_CLIPBOARD = 6
RETRY_INTERVAL = 0.08
TEMP_DIR = os.path.join(tempfile.gettempdir(), "snipaste_png_clip")

# 清理阈值（可命令行覆盖）
DEFAULT_MAX_AGE_HOURS  = 24
DEFAULT_MAX_TOTAL_MB   = 200
DEFAULT_MAX_FILE_COUNT = 1000

def now(): return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
def log(msg): print(f"[{now()}] {msg}", flush=True)

def open_clipboard_with_retry():
    for _ in range(RETRY_OPEN_CLIPBOARD):
        try: wcb.OpenClipboard(); return True
        except Exception: time.sleep(RETRY_INTERVAL)
    return False

def close_clipboard_safely():
    try: wcb.CloseClipboard()
    except Exception: pass

def get_clipboard_seq():
    try: return wcb.GetClipboardSequenceNumber()
    except Exception: return int(time.time() * 1000)

def get_png_format_id():
    try: return wcb.RegisterClipboardFormat("PNG")
    except Exception: return None

# ---- 兼容检测：前台进程是否为表格类应用、剪贴板是否含文本/HTML/RTF ----
def get_foreground_process_name():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd: return ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        hproc = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not hproc: return ""
        try:
            path = win32process.GetModuleFileNameEx(hproc, 0)
            return os.path.basename(path).lower()
        except Exception:
            return ""
        finally:
            try: CloseHandle(hproc)
            except Exception: pass
    except Exception:
        return ""

def is_spreadsheet_foreground():
    name = get_foreground_process_name()
    return name in ("excel.exe", "et.exe", "wpp.exe", "VISIO.EXE", "POWERPNT.EXE", "TencentDocs.exe", "draw.io.exe")

def clipboard_has_textual_data():
    if not open_clipboard_with_retry(): return False
    try:
        fmt = 0
        html_id = wcb.RegisterClipboardFormat("HTML Format")
        rtf_id  = wcb.RegisterClipboardFormat("Rich Text Format")
        csv_id  = wcb.RegisterClipboardFormat("CSV")
        while True:
            fmt = wcb.EnumClipboardFormats(fmt)
            if fmt == 0: break
            if fmt in (win32con.CF_TEXT, win32con.CF_OEMTEXT, win32con.CF_UNICODETEXT) or fmt in (html_id, rtf_id, csv_id):
                return True
        return False
    finally:
        close_clipboard_safely()

def grab_image_from_clipboard():
    try:
        data = ImageGrab.grabclipboard()
        if isinstance(data, Image.Image): return data, "image"
        elif isinstance(data, list) and data:
            try: return Image.open(data[0]), "files"
            except Exception: return None, "files"
        else: return None, "none"
    except Exception:
        return None, "none"

def set_clipboard_png_only(img: Image.Image):
    png_id = get_png_format_id()
    if png_id is None: raise RuntimeError("无法注册 PNG 剪贴板格式")
    out = io.BytesIO(); img.save(out, "PNG"); data = out.getvalue(); out.close()
    if not open_clipboard_with_retry(): raise RuntimeError("打开剪贴板失败（PNG 模式）")
    try: wcb.EmptyClipboard(); wcb.SetClipboardData(png_id, data)
    finally: close_clipboard_safely()

def ensure_temp_dir():
    os.makedirs(TEMP_DIR, exist_ok=True); return TEMP_DIR

def save_temp_png(img: Image.Image) -> str:
    ensure_temp_dir()
    path = os.path.join(TEMP_DIR, f"snip_{int(time.time()*1000)}.png")
    img.save(path, "PNG", optimize=True)
    return path

# ---- CF_HDROP 构造 ----
def build_dropfiles_bytes(paths):
    if not isinstance(paths, (list, tuple)): paths = [paths]
    file_bytes = ("\0".join(paths) + "\0\0").encode("utf-16le")
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # pFiles=20, pt=(0,0), fNC=0, fWide=1
    return header + file_bytes

def set_clipboard_file_drop(paths):
    data = build_dropfiles_bytes(paths); size = len(data)
    hglobal = GlobalAlloc(GMEM_MOVEABLE, size)
    if not hglobal: raise RuntimeError("GlobalAlloc 失败")
    ptr = GlobalLock(hglobal)
    if not ptr: raise RuntimeError("GlobalLock 失败")
    try:
        src = (ctypes.c_char * size).from_buffer_copy(data)
        RtlMoveMemory(ptr, ctypes.addressof(src), size)
    finally:
        GlobalUnlock(hglobal)
    if not open_clipboard_with_retry(): raise RuntimeError("打开剪贴板失败（FILE 模式）")
    try:
        wcb.EmptyClipboard()
        wcb.SetClipboardData(win32con.CF_HDROP, hglobal)  # 所有权交给系统
    finally:
        close_clipboard_safely()

# ---- 清理策略 ----
def cleanup_temp_dir(max_age_hours:int, max_total_mb:int, max_files:int):
    ensure_temp_dir()
    entries = []
    total_bytes = 0
    now_ts = time.time()
    for name in os.listdir(TEMP_DIR):
        path = os.path.join(TEMP_DIR, name)
        if not os.path.isfile(path): continue
        try:
            st = os.stat(path)
            age_hours = (now_ts - st.st_mtime) / 3600.0
            if age_hours > max_age_hours:
                try: os.remove(path)
                except Exception: pass
                continue
            entries.append((st.st_mtime, st.st_size, path))
            total_bytes += st.st_size
        except Exception:
            continue

    entries.sort(key=lambda x: x[0])
    while len(entries) > max_files:
        _, sz, p = entries.pop(0)
        try: os.remove(p); total_bytes -= sz
        except Exception: pass
    max_bytes = max_total_mb * 1024 * 1024
    while total_bytes > max_bytes and entries:
        _, sz, p = entries.pop(0)
        try: os.remove(p); total_bytes -= sz
        except Exception: pass

# ---- 主逻辑 ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["IMAGE","FILE"], default="FILE",
        help="IMAGE: 剪贴板仅放 PNG；FILE: 放临时 PNG 文件（推荐）")
    ap.add_argument("--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS,
        help=f"临时文件最大保留时长（小时），默认 {DEFAULT_MAX_AGE_HOURS}")
    ap.add_argument("--max-total-mb", type=int, default=DEFAULT_MAX_TOTAL_MB,
        help=f"临时目录最大总容量（MB），默认 {DEFAULT_MAX_TOTAL_MB}")
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILE_COUNT,
        help=f"临时文件最大数量，默认 {DEFAULT_MAX_FILE_COUNT}")
    ap.add_argument("--clean-now", action="store_true", help="仅执行一次清理后退出")
    args = ap.parse_args()

    log(f"启动：模式={args.mode}，目录={TEMP_DIR}，保留≤{args.max_age_hours}h，总≤{args.max_total_mb}MB，文件≤{args.max_files}")
    cleanup_temp_dir(args.max_age_hours, args.max_total_mb, args.max_files)
    if args.clean_now:
        log("已按配置完成一次清理，退出。"); return

    last_seq = get_clipboard_seq(); ignore_until = 0.0

    while True:
        time.sleep(POLL_INTERVAL)
        seq = get_clipboard_seq()
        if seq == last_seq: continue
        last_seq = seq
        if time.time() < ignore_until: continue

        # 若前台是 Excel/WPS 或剪贴板包含文本/HTML/RTF/CSV，跳过处理，避免影响表格复制粘贴
        if is_spreadsheet_foreground() or clipboard_has_textual_data():
            log("⏭️ 检测到表格应用或文本性数据，跳过本次处理")
            ignore_until = time.time() + 0.3
            continue

        img, source = grab_image_from_clipboard()
        if not img: continue

        try:
            if args.mode == "IMAGE":
                set_clipboard_png_only(img)
                log("✅ 已压缩为 PNG 并写回剪贴板（仅 PNG 格式）")
            else:
                path = save_temp_png(img)
                set_clipboard_file_drop([path])
                log(f"✅ 已压缩为 PNG 并作为文件放入剪贴板：{path}")
                cleanup_temp_dir(args.max_age_hours, args.max_total_mb, args.max_files)

            ignore_until = time.time() + 0.6
        except Exception as e:
            log(f"❌ 处理失败：{e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已退出"); sys.exit(0)

