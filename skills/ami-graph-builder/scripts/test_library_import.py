#!/usr/bin/env python3
"""
Test script to verify LIBRARY can be imported and contains nodes.
"""

import sys
from pathlib import Path

# Add AMI to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

print("Attempting to import LIBRARY...")
from ami.flowchart.library import LIBRARY

print(f"\nLIBRARY type: {type(LIBRARY)}")
print(f"LIBRARY has {len(LIBRARY)} nodes")

if len(LIBRARY) > 0:
    print("\nFirst 10 nodes:")
    for i, (node_name, node_class) in enumerate(list(LIBRARY.items())[:10]):
        print(f"  {i + 1}. {node_name}: {node_class}")
    print("\n✓ LIBRARY import successful!")
else:
    print("\n✗ LIBRARY is empty!")
    print("\nDebugging info:")
    print(f"LIBRARY.__dict__: {LIBRARY.__dict__}")
