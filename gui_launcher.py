"""VectorZip desktop GUI entry point."""
import os
import sys

# Allow running from the repo root without an install
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import main

if __name__ == "__main__":
    main()
