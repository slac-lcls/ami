#!/usr/bin/env python3
"""
Simple test script to verify magic command registration works.
"""

from IPython.terminal.embed import InteractiveShellEmbed

# Create an IPython shell
ipython = InteractiveShellEmbed()


# Create a mock amicli and bridge
class MockAmiCli:
    def __init__(self):
        self.chart = None
        self.graph = None


class MockBridge:
    def ask(self, prompt, timeout=120):
        raise RuntimeError("OpenCode server not available")


# Try to register the magic function
try:
    from ami.flowchart.graph_builder import register_graph_builder_magic

    amicli = MockAmiCli()
    bridge = MockBridge()

    register_graph_builder_magic(ipython, amicli, bridge)

    print("\n" + "=" * 60)
    print("SUCCESS: Magic commands registered!")
    print("=" * 60)
    print("\nTry these commands:")
    print("  %build_graph test")
    print("  %bg test")
    print("  %lsmagic  # to see all registered magics")
    print("\nType 'exit' to quit\n")

    ipython()

except Exception as e:
    print(f"\nERROR: Failed to register magic commands: {e}")
    import traceback

    traceback.print_exc()
