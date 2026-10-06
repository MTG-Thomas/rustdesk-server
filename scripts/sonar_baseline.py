#!/usr/bin/env python3
"""One-time indexing of the original source; never treat backlog as a clean gate."""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = "MTG-Thomas_rustdesk-server"


def request(endpoint, **params):
    url = "https://sonarcloud.io/api/" + endpoint + "?" + urllib.parse.urlencode(params)
    auth = base64.b64encode((os.environ["SONAR_TOKEN"] + ":").encode()).decode()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Basic " + auth}), timeout=30) as response:
        return json.load(response)


def main():
    if sys.argv[1] == "inspect":
        analyses = request("project_analyses/search", project=PROJECT, branch="master", ps=1)["analyses"]
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write("needed=" + str(not analyses).lower() + "\n")
    elif sys.argv[1] == "wait":
        receipt = dict(line.split("=", 1) for line in Path(sys.argv[2]).read_text().splitlines() if "=" in line)
        if receipt["projectKey"] != PROJECT:
            raise SystemExit("Baseline receipt belongs to another project")
        for _ in range(60):
            task = request("ce/task", id=receipt["ceTaskId"])["task"]
            if task["componentKey"] != PROJECT:
                raise SystemExit("Baseline compute task belongs to another project")
            if task["status"] == "SUCCESS":
                print("Original master baseline completed:", task["analysisId"])
                return
            if task["status"] not in ("PENDING", "IN_PROGRESS"):
                raise SystemExit("Baseline compute task failed: " + task["status"])
            time.sleep(5)
        raise SystemExit("Baseline compute task remains pending")
    else:
        raise SystemExit("Expected inspect or wait")


if __name__ == "__main__":
    main()
