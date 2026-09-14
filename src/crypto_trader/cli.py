import argparse
import json

from .trader import CryptoTrader


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--symbol", default="BTCUSDT")
    s.add_argument("--interval", default="1h")
    a = sub.add_parser("analyze")
    a.add_argument("--symbol", default="BTCUSDT")
    args = p.parse_args()
    t = CryptoTrader(args.symbol)
    if args.cmd == "snapshot":
        print(json.dumps(t.snapshot(args.interval), indent=2, default=str))
    else:
        print(json.dumps(t.analyze(), indent=2, default=str))


if __name__ == "__main__":
    main()
