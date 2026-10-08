# Validation against JSkyCalc

`harness/probe.js` drives JSkyCalc's own classes headless via Java 8's built-in Nashorn
engine (`jjs`), using reflection because the classes are package-private:

    "/Library/Internet Plug-Ins/JavaAppletPlugin.plugin/Contents/Home/bin/jjs" \
        -cp JSkyCalc-master/JSkyCalc.jar validation/harness/probe.js

Stage 1 extends this into a fixture generator; results are documented in VALIDATION.md.
