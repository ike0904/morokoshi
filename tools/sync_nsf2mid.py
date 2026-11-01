"""
nsf2mid の変換モジュールを morokoshi/src/nsf2mid_core/ へコピーする同期スクリプト。

nsf2mid を改修したら、これを実行して morokoshi に反映する:
    python tools/sync_nsf2mid.py [nsf2mid のフォルダ]   (既定: ../nsf2mid)

- nsf2mid_core/ 内のファイルは直接編集しないこと（同期で上書きされる）。必要な改修は nsf2mid 本体に入れる
- GUI（nsf2mid_gui.py）と簡易再生（player.py）はコピーしない
- 取り込んだ nsf2mid のバージョンとコミットを nsf2mid_core/SOURCE.txt に記録する
"""
import glob
import os
import re
import shutil
import subprocess
import sys

EXCLUDE = {"nsf2mid_gui.py", "player.py"}

here = os.path.dirname(os.path.abspath(__file__))
src_root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "nsf2mid"))
src_dir = os.path.join(src_root, "src")
dst_dir = os.path.join(here, "..", "src", "nsf2mid_core")
if not os.path.isfile(os.path.join(src_dir, "nsf2mid.py")):
    sys.exit(f"nsf2mid not found: {src_dir}")

os.makedirs(dst_dir, exist_ok=True)
for old in glob.glob(os.path.join(dst_dir, "*.py")):
    os.remove(old)
files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(src_dir, "*.py"))
               if os.path.basename(p) not in EXCLUDE)
for f in files:
    shutil.copy2(os.path.join(src_dir, f), os.path.join(dst_dir, f))

with open(os.path.join(src_dir, "nsf2mid.py"), encoding="utf-8") as fp:
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', fp.read())
version = m.group(1) if m else "?"
try:
    commit = subprocess.run(["git", "-C", src_root, "log", "-1", "--format=%h %ad %s", "--date=short"],
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", src_root, "status", "--porcelain", "src"],
                           capture_output=True, text=True).stdout.strip()
except (OSError, subprocess.CalledProcessError):
    commit, dirty = "unknown", ""
with open(os.path.join(dst_dir, "SOURCE.txt"), "w", encoding="utf-8") as fp:
    fp.write("Copied from nsf2mid by tools/sync_nsf2mid.py. Do not edit these files here.\n")
    fp.write(f"version: {version}\ncommit:  {commit}{' (+ uncommitted changes)' if dirty else ''}\n")
    fp.write("files:   " + ", ".join(files) + "\n")
print(f"nsf2mid {version} -> {os.path.abspath(dst_dir)}")
print(f"  commit: {commit}{' (+ uncommitted changes)' if dirty else ''}")
print(f"  {len(files)} files: {', '.join(files)}")
