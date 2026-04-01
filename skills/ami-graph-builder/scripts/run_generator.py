#!/usr/bin/env python3
"""
Wrapper script to run the node documentation generator with ami.__init__.py patched.
"""

import sys
from pathlib import Path

# Add AMI to path
ami_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ami_root))

# Patch ami.__init__.py before it's imported
import ami

# Mock the p4p_get_version to return a dummy value
ami.p4p_get_version = lambda: "0.0.0"
ami.p4pConfig.Version = "0.0.0"
ami.p4pConfig.SupportsTimestamps = False

# Now import and run the real generator
from generate_node_docs import main

if __name__ == "__main__":
    main()
