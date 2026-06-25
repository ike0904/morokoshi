"""
Zophar's Domain - Nintendo SNES (SPC) 全ファイル一括ダウンロード
実行方法: python download_spc.py
必要: pip install requests beautifulsoup4
"""

import os
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import unquote

BASE_URL  = "https://www.zophar.net"
LIST_URL  = "https://www.zophar.net/music/nintendo-snes-spc"
SAVE_DIR  = Path("spc_downloads")
DELAY     = 1.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.zophar.net/",
}

def get_game_slugs():
    slugs = []
    for page in range(1, 10):
        url = f"{LIST_URL}?page={page}"
        print(f"一覧取得中: {url}")
        r = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='/music/nintendo-snes-spc/']"):
            href = a["href"]
            if href.count("/") == 3 and "?page=" not in href:
                slug = href.split("/")[-1]
                if slug and slug not in slugs:
                    slugs.append(slug)
        time.sleep(DELAY)
    return slugs

def get_emu_download_url(slug):
    url = f"{BASE_URL}/music/nintendo-snes-spc/{slug}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # URLエンコード済み(%28EMU%29)と未エンコード両方に対応
        decoded = unquote(href)
        if "(EMU)" in decoded and decoded.endswith(".zip"):
            return href  # 元のURLをそのまま返す
    return None

def download_file(url, save_path):
    r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
    if r.status_code != 200:
        print(f"  HTTPエラー: {r.status_code}")
        return False
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return True

def main():
    SAVE_DIR.mkdir(exist_ok=True)
    log_path    = SAVE_DIR / "download_log.txt"
    failed_path = SAVE_DIR / "failed.txt"

    done = set()
    if log_path.exists():
        done = set(log_path.read_text(encoding="utf-8").splitlines())

    print("=== ゲーム一覧を取得中 ===")
    slugs = get_game_slugs()
    print(f"合計 {len(slugs)} タイトル")

    failed = []
    for i, slug in enumerate(slugs, 1):
        if slug in done:
            print(f"[{i}/{len(slugs)}] スキップ（取得済み）: {slug}")
            continue

        print(f"[{i}/{len(slugs)}] 処理中: {slug}")

        try:
            time.sleep(DELAY)
            emu_url = get_emu_download_url(slug)
        except Exception as e:
            print(f"  ページ取得失敗: {e}")
            failed.append(slug)
            continue

        if not emu_url:
            print(f"  EMUファイルが見つかりません")
            failed.append(slug)
            continue

        filename  = unquote(emu_url.split("/")[-1])
        save_path = SAVE_DIR / filename

        if save_path.exists():
            print(f"  既存ファイルあり: {filename}")
        else:
            print(f"  DL: {filename}")
            try:
                time.sleep(DELAY)
                if not download_file(emu_url, save_path):
                    failed.append(slug)
                    continue
            except Exception as e:
                print(f"  エラー: {e}")
                failed.append(slug)
                continue

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(slug + "\n")

    if failed:
        with open(failed_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failed))
        print(f"\n失敗: {len(failed)}件 → {failed_path}")
    else:
        print("\n全て完了！")

    print(f"保存先: {SAVE_DIR.resolve()}")

if __name__ == "__main__":
    main()
