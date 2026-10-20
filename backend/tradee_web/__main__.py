"""python -m backend.tradee_web [--config PATH] [--port 8787]."""

import argparse
import os
import uvicorn
from .config import load_settings
from .app import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if args.config:
        os.environ["TRADEE_WEB_CONFIG"] = os.path.abspath(args.config)
    uvicorn.run(
        create_app(load_settings(args.config)), host="127.0.0.1", port=args.port
    )


if __name__ == "__main__":
    main()
