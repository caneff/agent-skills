#!/usr/bin/env bash
# Defect class 1 in the flesh: a suite that finds a real problem, says so, and
# exits 0 anyway. Before #954 the gate read the zero and printed PASS.
echo "FAIL: config/app.yaml declares a port the service never binds"
exit 0
