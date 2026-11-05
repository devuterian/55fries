#!/usr/bin/env python3
"""오늘 수집 결과가 직전 수집보다 확 줄었으면 실패로 끝내서 배포를 막고 워크플로를 빨갛게 만든다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTS_DIR = ROOT / "data" / "imports"
# 최근 한 달 하루 변동폭은 3% 안쪽이었다.
MAX_DROP_RATIO = 0.20


def counts(path: Path) -> dict[str, int]:
    listings = json.loads(path.read_text())["listings"]
    return {
        "매물": len(listings),
        "판매중": sum(1 for item in listings if item["state"] == "active"),
        "판매완료": sum(1 for item in listings if item["state"] == "sold"),
        "모델": len({item["model"] for item in listings}),
    }


def check(imports_dir: Path = IMPORTS_DIR, max_drop: float = MAX_DROP_RATIO) -> list[str]:
    files = sorted(imports_dir.glob("auto-*.json"))
    if len(files) < 2:
        return []
    today, before = counts(files[-1]), counts(files[-2])
    problems = []
    for key, old in before.items():
        new = today[key]
        if old and new < old * (1 - max_drop):
            problems.append(f"{key} {old}건에서 {new}건으로 {round((1 - new / old) * 100)}% 줄었습니다")
    print(f"수집 점검: {files[-1].name} {today} / 직전 {files[-2].name} {before}")
    return problems


def main() -> None:
    problems = check()
    if problems:
        print("수집 결과가 비정상입니다. 배포하지 않습니다:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
