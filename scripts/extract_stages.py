"""Extract common.stages from QuickSearch locale JS."""
import json
import re
import sys

JS = r"G:/魔兽/QuickSearch_0.74c/resources/app/js/app520a4269.js"


def main() -> None:
    js = open(JS, encoding="utf-8").read()
    idx = js.find("[大天使]")
    start = js.rfind("stages:[", 0, idx)
    end = js.find("],otherType:", start)
    chunk = js[start + len("stages:") : end + 1]
    stages = json.loads(chunk)
    print(json.dumps(stages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
