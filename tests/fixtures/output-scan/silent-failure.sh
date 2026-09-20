#!/usr/bin/env bash
# Defect class 1 in the flesh: a suite that finds a real problem, says so, and
# exits 0 anyway. Witnesses the `FAIL` third of the signature set.
echo "FAIL: config/app.yaml declares a port the service never binds"
exit 0
