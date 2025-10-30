#!/usr/bin/env python3
"""
Lightweight launcher script that executes the package entrypoint
without importing the top-level module name (avoids name collision
when a package directory `perfbench/` exists).

Usage: keep using `./perfbench.py -init` as before.
"""
import os
import sys
import runpy

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PATH = os.path.join(HERE, 'perfbench', '__main__.py')

if not os.path.exists(MAIN_PATH):
    sys.stderr.write('perfbench package entry not found (perfbench/__main__.py)\n')
    sys.exit(1)

# run the package __main__ by path to avoid importing the top-level name
runpy.run_path(MAIN_PATH, run_name='__main__')