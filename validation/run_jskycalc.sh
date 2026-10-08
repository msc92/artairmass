#!/usr/bin/env bash
# Regenerate JSkyCalc reference values (needs Java 8 `jjs` and the original jar).
set -euo pipefail
cd "$(dirname "$0")/.."
JJS="${JJS:-$(command -v jjs || echo "/Library/Internet Plug-Ins/JavaAppletPlugin.plugin/Contents/Home/bin/jjs")}"
JAR="${JSKYCALC_JAR:-JSkyCalc-master/JSkyCalc.jar}"
.venv/bin/python validation/make_cases.py
"$JJS" -cp "$JAR" validation/harness/jskycalc_oracle.js -- \
    validation/fixtures/cases.json validation/fixtures/jskycalc_reference.json
