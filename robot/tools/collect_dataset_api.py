#!/usr/bin/env python3
import argparse
import time
import os
import sys
import base64
import json
from pathlib import Path
from datetime import datetime
import urllib.request

API_URL_DEFAULT = "http://127.0.0.1:5000/api/camera/frame"


def fetch_frame_b64(url: str, timeout: float = 5.0) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read()
        obj = json.loads(data.decode("utf-8"))
        if not obj.get("success"):
            return None
        frame_b64 = obj.get("data", {}).get("frame")
        if not frame_b64:
            return None
        return base64.b64decode(frame_b64)
    except Exception as e:
        print(f"[ERR] fetch_frame_b64: {e}", file=sys.stderr)
        return None


def main():
    p = argparse.ArgumentParser(
        description="Collect dataset via /api/camera/frame")
    p.add_argument("--out", default="photos/dataset",
                   help="base output dir (inside project)")
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between shots")
    p.add_argument("--duration", type=float, default=300.0,
                   help="total seconds (use 0 for infinite)")
    p.add_argument("--prefix", default="dataset", help="filename prefix")
    p.add_argument("--url", default=API_URL_DEFAULT,
                   help="camera API endpoint")
    p.add_argument("--quality", type=int, default=95,
                   help="re-encode JPEG quality if needed (unused: saving raw jpeg)")
    args = p.parse_args()

    # рабочая папка с таймстампом
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] output dir: {out_dir.resolve()}")

    t0 = time.time()
    n = 0
    try:
        while True:
            if args.duration > 0 and (time.time() - t0) >= args.duration:
                break

            jpeg_bytes = fetch_frame_b64(args.url)
            if jpeg_bytes:
                fname = out_dir / f"{args.prefix}_{n:06d}.jpg"
                with open(fname, "wb") as f:
                    f.write(jpeg_bytes)
                print(f"[OK] {fname.name}")
                n += 1
            else:
                print("[WARN] empty frame", file=sys.stderr)

            time.sleep(max(args.interval, 0.05))
    except KeyboardInterrupt:
        pass

    print(f"[DONE] saved: {n} files -> {out_dir.resolve()}")


if __name__ == "__main__":
    main()
