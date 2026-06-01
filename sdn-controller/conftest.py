"""Pytest configuration for the SDN controller test suite.

Ensures the ``tradenet_sdn`` package is importable regardless of where pytest is
invoked from (the directory containing this file is the package root).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
