#!/usr/bin/env python3
"""
Try the model without a Raspberry Pi.

    python tools/webcam_test.py                  # laptop webcam
    python tools/webcam_test.py --source testData  # the bundled sample images
    python tools/webcam_test.py --source clip.mp4 --conf 0.5

Press q to quit the preview window.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                       # noqa: E402
from ultralytics import YOLO        # noqa: E402


def main():
    cfg = config.load_config()

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="0",
                        help="0 for the webcam, or a path to an image/folder/video")
    parser.add_argument("--model", default=cfg["model"]["path"])
    parser.add_argument("--conf", type=float, default=cfg["model"]["confidence"])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--save", action="store_true",
                        help="write annotated results to runs/ instead of only showing them")
    args = parser.parse_args()

    model_path = config.resolve_path(args.model)
    if not model_path.exists():
        raise SystemExit(f"Model not found: {model_path}")

    source = int(args.source) if args.source.isdigit() else str(config.resolve_path(args.source))
    device = config.device_for(cfg["model"]["device"])
    print(f"Model:  {model_path}\nSource: {source}\nDevice: {device}")

    model = YOLO(str(model_path))
    model.predict(
        source=source,
        show=True,
        save=args.save,
        conf=args.conf,
        imgsz=args.imgsz,
        device=device,
    )


if __name__ == "__main__":
    main()
