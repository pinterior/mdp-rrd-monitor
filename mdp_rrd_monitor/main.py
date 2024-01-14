#!/usr/bin/env python

from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timedelta
import itertools
from logging import Formatter, StreamHandler, getLogger
import logging
from pathlib import Path
import subprocess
import time
from typing import Optional

import microdotphat

logger = getLogger(__name__)


@dataclass(frozen=True)
class Target:
    symbol: str
    file: Path
    scale: float

    @staticmethod
    def of(s: str):
        a = s.split(",", 2)
        match a:
            case [y, p]:
                if len(y) != 1:
                    raise ValueError(f"length of symbol must be 1: {y}")
                return Target(y, Path(p), 1.0)
            case [y, p, f]:
                if len(y) != 1:
                    raise ValueError(f"length of symbol must be 1: {y}")
                return Target(y, Path(p), float(f))
            case _:
                raise ValueError("target must be 'symbol,rrdfile[,scale]' format")


@dataclass
class State:
    at: datetime
    value: float


def get_value(target: Target, rrdcache: Optional[Path]):
    cmdline = ["rrdtool", "lastupdate", target.file]
    if rrdcache is not None:
        cmdline += ["--daemon", f"unix:{rrdcache}"]
    r = subprocess.run(cmdline, text=True, capture_output=True)
    if r.returncode != 0:
        return None

    a = r.stdout.splitlines()[-1]
    if ":" in a:
        logger.debug(f"{a}")
        t, v = a.split(":", 1)
        if v == "U":
            return None
        return State(datetime.fromtimestamp(int(t)), float(v))
    return None


def scroll_to(s: str, row_spacing: int, scroll_wait: float):
    microdotphat.write_string(s, offset_y=microdotphat.HEIGHT + row_spacing, kerning=False)
    microdotphat.show()
    for y in range(microdotphat.HEIGHT + row_spacing):
        microdotphat.scroll_to(position_y=y)
        microdotphat.show()
        time.sleep(scroll_wait)

    microdotphat.write_string(s, kerning=False)
    microdotphat.scroll_to()
    microdotphat.show()


def format(v: float):
    r = "%5.1f" % v
    if 5 < len(r) or (r[0] != " " and r[0] != "-"):
        r = "%5d" % v
        if 5 < len(r) or (r[0] != " " and r[0] != "-"):
            r = " High" if 0 < v else " Low "
    return r


def main():
    parser = ArgumentParser()
    parser.add_argument("--update-interval", help="interval between data update (in seconds)", type=float, default=300)
    parser.add_argument("--error-threashold", help="(in seconds)", type=float, default=1800)
    parser.add_argument("--rrdcache", help="path of the socket of rrdcache daemon", type=Path)
    parser.add_argument("--brightness", help="brightness of LED", type=float, default=0.03)
    parser.add_argument("--row-spacing", help="row spacing (in pixels)", type=int, default=4)
    parser.add_argument("--scroll-wait", help="scroll wait (in seconds)", type=float, default=0.1)
    parser.add_argument("--row-wait", help="row wait (in seconds)", type=float, default=3)
    parser.add_argument("-v", "--verbose", help="set log level to DEBUG", action="store_true")
    parser.add_argument("target", help="target file", type=Target.of, nargs="+")
    args = parser.parse_args()

    root_logger = getLogger()
    if args.verbose:
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)
    handler = StreamHandler()
    handler.setFormatter(Formatter("[%(asctime)s] %(levelname)s:%(name)s:%(message)s"))
    root_logger.addHandler(handler)

    if not microdotphat.is_connected():
        logger.error("Micro dot pHAT not found.")
        exit(1)

    update_interval = timedelta(seconds=args.update_interval)
    error_threashold = timedelta(seconds=args.error_threashold)
    rrdcache: Optional[Path] = args.rrdcache

    brightness: float = args.brightness
    row_spacing: int = args.row_spacing
    scroll_wait: float = args.scroll_wait
    row_wait: float = args.row_wait

    targets = args.target
    states: list[Optional[State]] = [None for _ in targets]

    microdotphat.set_brightness(brightness)

    for i, t in itertools.cycle(enumerate(targets)):
        now = datetime.now()

        s = states[i]
        logging.debug(f"{i}: {s}")

        if s is None or update_interval < now - s.at:
            ns = get_value(t, rrdcache)
            if ns is not None:
                states[i] = s = ns

        if s is None or error_threashold < now - s.at:
            scroll_to(t.symbol + " ERR ", row_spacing, scroll_wait)

        else:
            v = s.value * t.scale
            r = format(v)
            scroll_to(t.symbol + r, row_spacing, scroll_wait)

        time.sleep(row_wait)


if __name__ == "__main__":
    main()
