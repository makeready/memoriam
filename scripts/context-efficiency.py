#!/usr/bin/env python3
"""Run the context-efficiency pipeline.

Usage:
    python3 scripts/context-efficiency.py [--analyze-only]

Respects config.json settings. Use --analyze-only to skip rule and hook generation.
"""

import sys
from pathlib import Path

# Add module to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "context-efficiency"))

from pipeline import main

if __name__ == "__main__":
    main()
