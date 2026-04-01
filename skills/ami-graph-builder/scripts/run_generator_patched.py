#!/usr/bin/env python3
"""
Wrapper script to run the node documentation generator with imports patched.
"""

import sys
from pathlib import Path

# Add AMI to path FIRST
ami_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ami_root))


# Monkey-patch importlib_metadata before ami is imported
class MockMetadata:
    class PackageNotFoundError(Exception):
        pass

    @staticmethod
    def version(package_name):
        return "0.0.0"


sys.modules["importlib_metadata"] = MockMetadata

# Also mock importlib.metadata as an attribute of importlib
import importlib

importlib.metadata = MockMetadata

# Now we can safely import from ami
from generate_node_docs import main

if __name__ == "__main__":
    main()
