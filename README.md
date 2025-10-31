# Snipaste Clipboard Optimizer (with Auto-Cleanup)

This utility optimizes images copied to the clipboard (especially from Snipaste) by converting uncompressed bitmaps (BMP) to PNG, significantly reducing size. It also manages temporary files to avoid disk space bloat during long-term use.

## Features
- Clipboard image compression: converts BMP to PNG automatically
- Two operation modes:
  - IMAGE: write PNG back to clipboard as PNG format (may not be supported by some apps)
  - FILE: save PNG to a temp file and place it to clipboard as a file drop (best compatibility)
- Auto-clean temporary directory:
  - Directory: %TEMP%\\snipaste_png_clip
  - Keeps files within last N hours (default: 24h)
  - Limits total size (default: 200 MB)
  - Limits file count (default: 1000)
  - Runs on start and after generating new files
- Robust clipboard monitoring: avoid duplicate processing with sequence numbers
- Detailed logging with timestamps

## Requirements
- Windows 10/11 (64-bit)
- Python 3.8+
- Python packages: `pillow`, `pywin32`

Install dependencies:

```bash
pip install pillow pywin32
```

## Usage
Run from a terminal (PowerShell/CMD):

```bash
python clipboard_compress_cli_v1.0.py --mode FILE
```

- IMAGE mode (only PNG content in clipboard):

```bash
python clipboard_compress_cli_v1.0.py --mode IMAGE
```

- Adjust cleanup thresholds:

```bash
python clipboard_compress_cli_v1.0.py --mode FILE \
  --max-age-hours 12 --max-total-mb 100 --max-files 300
```

- One-time cleanup and exit:

```bash
python clipboard_compress_cli_v1.0.py --clean-now
```

## Notes
- Resulting PNG size is similar to Snipaste manual PNG save (~1MB typical).
- If the target program still pastes a large 20MB+ bitmap, it likely reads only BMP from clipboard; this behavior is on the target program side.
- FILE mode offers near-universal compatibility across applications.

## How It Works
- Monitors clipboard sequence number changes
- Grabs image using Pillow's ImageGrab
- Compresses to PNG
- Depending on mode:
  - IMAGE: registers PNG clipboard format and sets PNG bytes
  - FILE: writes PNG to temp folder and sets CF_HDROP
- Periodically cleans temp dir based on age/size/count

## License
MIT (add your preferred license here)

## Acknowledgements
- Built for optimizing Snipaste clipboard workflow on Windows
- Uses Pillow and pywin32; low-level memory operations via WinAPI