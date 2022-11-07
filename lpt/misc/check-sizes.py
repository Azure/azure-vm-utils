#!/usr/bin/env python3

import json
import pathlib
import sys

assert len(sys.argv) > 1, "specify input file"
input=pathlib.Path(sys.argv[1])
assert input.exists(), "specified file does not exist"

data = input.read_bytes()
print(data[0:32])
events = json.loads(data)

stats={}
for event in events:
    label = event["label"]
    if label not in stats:
        stats[label] = {}

    bin = stats[label]
    if "ttyS" in event.get("unit", ""):
        continue

    bin["count"] = bin.get("count", 0) + 1
    bin["size"] = bin.get("size", 0) + len(str(event))

for k, v in sorted(stats.items(), key=lambda x: x[1]["size"]):
    print("label=", k)
    print("  count=", v["count"])
    print("  size=", v["size"] * 1.0 / 1024, "KB")




