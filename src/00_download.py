"""00_download.py — fetch the source workbook.

Never commit the raw data. Commit the downloader.
"""
from pathlib import Path
import sys, urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "raw" / "online_retail_II.xlsx"
# Canonical source. If this 403s from your network, download it by hand from
# https://archive.ics.uci.edu/dataset/502/online+retail+ii and unzip into
# data/raw/. The file is ~45.9 MB.
URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
EXPECTED_BYTES = 45_869_583


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"  already present: {DEST.relative_to(ROOT)} "
              f"({DEST.stat().st_size/1e6:.1f} MB)")
        return 0
    print(f"  downloading {URL}")
    try:
        zip_path = DEST.with_suffix(".zip")
        urllib.request.urlretrieve(URL, zip_path)
        import zipfile
        with zipfile.ZipFile(zip_path) as z:
            name = [n for n in z.namelist() if n.endswith(".xlsx")][0]
            DEST.write_bytes(z.read(name))
        zip_path.unlink()
    except Exception as exc:
        print(f"  FAILED: {exc}\n"
              f"  Download manually from "
              f"https://archive.ics.uci.edu/dataset/502/online+retail+ii\n"
              f"  and place online_retail_II.xlsx in data/raw/", file=sys.stderr)
        return 1
    print(f"  saved {DEST.relative_to(ROOT)} ({DEST.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
