#!/usr/bin/env bash
# Fixture: a suite that is killed by SIGKILL before it prints anything.
kill -KILL $$
