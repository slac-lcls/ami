#!/usr/bin/env python3
"""
Test OpenCodeBridge server startup
"""

import sys

sys.path.insert(0, "/sdf/home/s/seshu/dev/ami")

from ami.flowchart.graph_builder import OpenCodeBridge

print("Testing OpenCodeBridge initialization...")
print("=" * 60)

try:
    bridge = OpenCodeBridge()

    if bridge.server and bridge.url:
        print(f"✓ SUCCESS: Server started at {bridge.url}")
        print(f"✓ Server process: {bridge.server.pid}")

        # Clean up
        bridge.close()
        print("✓ Server closed cleanly")
    else:
        print("✗ FAILED: Server or URL is None")
        print(f"  server: {bridge.server}")
        print(f"  url: {bridge.url}")

except Exception as e:
    print(f"✗ FAILED: {e}")
    import traceback

    traceback.print_exc()

print("=" * 60)
