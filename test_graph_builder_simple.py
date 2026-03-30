#!/usr/bin/env python3
"""
Simple test of OpenCodeBridge without full AMI dependencies
"""

import subprocess
import re
import time

print("Testing OpenCode server startup...")
print("=" * 60)

# Start server
print("Starting server...")
server = subprocess.Popen(
    ["opencode", "serve", "--port", "0"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    universal_newlines=True,
)

# Read stderr to get URL
print("Waiting for server URL...")
start = time.time()
url = None

while time.time() - start < 10:
    if server.poll() is not None:
        print("ERROR: Server process died!")
        break

    line = server.stderr.readline()
    if line:
        print(f"  stderr: {line.strip()}")
        match = re.search(r"http://[^\s]+", line)
        if match:
            url = match.group(0)
            print(f"\n✓ SUCCESS: Found URL: {url}")
            break

    time.sleep(0.1)

if not url:
    print("\n✗ FAILED: No URL found within timeout")
else:
    print("\n✓ Server is running")

# Clean up
print("\nCleaning up...")
server.terminate()
server.wait()
print("Done!")
print("=" * 60)
