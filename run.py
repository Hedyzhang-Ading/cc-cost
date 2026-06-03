#!/usr/bin/env python3
"""Entry point for zero-install usage.

    python3 run              # today
    python3 run projects     # all projects
    python3 run daily -d 7   # daily trend
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cc_cost.main import main

main()
