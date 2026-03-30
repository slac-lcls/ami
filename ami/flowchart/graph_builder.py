"""
AI-Assisted Graph Building for AMI

This module provides IPython magic commands for building AMI analysis graphs
using natural language via an AI agent.
"""

import subprocess
import json
import time
import re
import os
import select


class OpenCodeBridge:
    """
    Manages long-running OpenCode server for AI-assisted graph building.

    Lifecycle:
    - Starts when AMI GUI opens
    - Maintains session across requests
    - Auto-restarts on failure
    - Cleans up on AMI exit
    """

    def __init__(self):
        self.server = None
        self.url = None
        self.session_id = None
        self.start_server()

    def start_server(self):
        """Start OpenCode server on random port"""
        try:
            self.server = subprocess.Popen(
                ["opencode", "serve", "--port", "0"],  # 0 = random port
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait for server URL (printed to stderr)
            self.url = self._wait_for_url()
            print(f"[Graph Builder] OpenCode server started at {self.url}")
        except Exception as e:
            print(f"[Graph Builder] Warning: Could not start OpenCode server: {e}")
            print(
                "[Graph Builder] Magic commands will use basic prompts without AI agent"
            )
            self.server = None
            self.url = None

    def _wait_for_url(self, timeout=10):
        """
        Extract server URL from startup output.
        OpenCode prints "Server listening on http://localhost:XXXX" to stderr.
        """
        start = time.time()

        while time.time() - start < timeout:
            # Non-blocking read from stderr
            if select.select([self.server.stderr], [], [], 0.1)[0]:
                line = self.server.stderr.readline()
                match = re.search(r"http://[^\s]+", line)
                if match:
                    return match.group(0)

        raise RuntimeError("OpenCode server failed to start within timeout")

    def ask(self, prompt, timeout=120):
        """
        Send request to agent via server.

        Maintains session continuity - agent remembers previous interactions.
        Auto-restarts server if it crashed.

        Returns: JSON output from agent (list of event objects)
        """
        # Check if server was never started
        if self.server is None:
            raise RuntimeError("OpenCode server not available")

        # Check if server is still alive
        if self.server.poll() is not None:
            self.start_server()
            self.session_id = None  # Reset session

        cmd = [
            "opencode",
            "run",
            "--attach",
            self.url,
            "--agent",
            "ami-graph-builder",
            "--format",
            "json",
            "--dir",
            os.getcwd(),
        ]

        # Continue session if we have one (enables conversation history)
        if self.session_id:
            cmd += ["--session", self.session_id]

        cmd.append(prompt)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )

            if result.returncode != 0:
                raise RuntimeError(f"Agent invocation failed: {result.stderr}")

            # Extract session ID for next request
            self.session_id = self._extract_session_id(result.stdout)

            return result.stdout

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Agent request timed out after {timeout}s")

    def _extract_session_id(self, output):
        """
        Parse session ID from JSON events.
        Format: {"type":"step_start","sessionID":"ses_xxx",...}
        """
        for line in output.split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if "sessionID" in event:
                    return event["sessionID"]
            except json.JSONDecodeError:
                pass
        return self.session_id  # Keep existing if not found

    def close(self):
        """Clean shutdown of server"""
        if self.server and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait()


def register_graph_builder_magic(ipython_shell, amicli, bridge):
    """
    Register %build_graph and %bg magic commands.

    Args:
        ipython_shell: IPython shell instance
        amicli: AmiCli instance for graph manipulation
        bridge: OpenCodeBridge instance for AI agent communication
    """

    # Store references in the magic function's closure
    _amicli = amicli
    _bridge = bridge
    _ipython_shell = ipython_shell

    def build_graph(line):
        """
        Build graph nodes using natural language.

        Usage:
            %build_graph show cspad detector
            %build_graph add ROI and sum it
            %build_graph correlate laser with detector
        """
        if not line.strip():
            print("Usage: %build_graph <description>")
            print("Example: %build_graph create a scatter plot for laser vs detector")
            return

        print(f"[Graph Builder] Processing: {line}")
        print("[Graph Builder] Invoking AI agent...")

        try:
            # Get current graph state
            graph_state = get_graph_state(_amicli)

            # Invoke agent
            code = invoke_agent_for_graph_building(line, graph_state, _amicli, _bridge)

            if code:
                print("[Graph Builder] Executing generated code...")
                # Execute the code in the IPython environment
                _ipython_shell.ex(code)
                print("[Graph Builder] Done!")
            else:
                print("[Graph Builder] No code generated.")

        except RuntimeError as e:
            if "OpenCode server not available" in str(e):
                print(f"[Graph Builder] Error: {e}")
                print(
                    "[Graph Builder] The AI agent requires OpenCode to be installed and available."
                )
                print("[Graph Builder] You can still use the basic AMI API:")
                print("  chart.createNode('NodeType', 'node_name')")
                print("  amicli.connect_nodes('src', 'Out', 'dst', 'In')")
            else:
                print(f"[Graph Builder] Error: {e}")
                import traceback

                traceback.print_exc()
        except Exception as e:
            print(f"[Graph Builder] Error: {e}")
            import traceback

            traceback.print_exc()

    # Register the magic function with IPython
    ipython_shell.register_magic_function(
        build_graph, magic_kind="line", magic_name="build_graph"
    )
    ipython_shell.register_magic_function(
        build_graph, magic_kind="line", magic_name="bg"
    )

    print("Graph builder magic commands registered: %build_graph, %bg")


def get_graph_state(amicli):
    """
    Extract current graph state for agent context.

    Returns dict with:
    - nodes: list of {name, type, params}
    - sources: list of source names
    - connections: list of {from, to, terminals}
    - available_sources: list of detectors/PVs
    """
    state = {"nodes": [], "sources": [], "connections": [], "available_sources": []}

    # Extract nodes from graph
    for name, gnode in amicli.graph.nodes(data="node"):
        if gnode is None:
            continue

        node_info = {
            "name": name,
            "type": gnode.__class__.__name__,
            "params": getattr(gnode, "values", {}),
        }

        state["nodes"].append(node_info)

        # Track source nodes separately
        if node_info["type"] == "SourceNode":
            state["sources"].append(name)

    # Extract connections from graph
    for src_name, dst_name, edge_data in amicli.graph.edges(data=True):
        state["connections"].append(
            {"from": src_name, "to": dst_name, "data": edge_data}
        )

    # Get available sources from source library
    if hasattr(amicli.chart, "source_library"):
        source_list = amicli.chart.source_library.sourceList
        if source_list:
            state["available_sources"] = list(source_list.keys())

    return state


def invoke_agent_for_graph_building(user_prompt, graph_state, amicli, bridge):
    """
    Invoke OpenCode agent via dedicated server.

    Fast (~200ms) after initial startup because server is already running.
    Maintains conversation context via session continuity.
    """
    full_prompt = build_agent_prompt(user_prompt, graph_state, amicli)

    # Send to agent via server (fast - no startup overhead)
    json_output = bridge.ask(full_prompt)

    # Extract executable Python code from JSON events
    code = extract_code_from_response(json_output)

    return code


def build_agent_prompt(user_request, graph_state, amicli):
    """
    Generate comprehensive prompt for AI agent.

    Includes:
    - User request
    - Current graph state
    - Available API
    - Source discovery methods
    - Node types available
    - Required response format
    """

    prompt = f"""You are helping build an AMI analysis graph using Python.

USER REQUEST: {user_request}

CURRENT GRAPH STATE:
- Nodes: {len(graph_state["nodes"])} nodes
- Sources: {", ".join(graph_state["sources"]) if graph_state["sources"] else "None"}
- Available sources: {", ".join(graph_state["available_sources"][:10]) if graph_state["available_sources"] else "None"}

AVAILABLE API:
1. Create nodes: chart.createNode(type, name)
2. Connect nodes: amicli.connect_nodes(src, src_term, dst, dst_term)
3. Disconnect nodes: amicli.disconnect_nodes(src, src_term, dst, dst_term)

IMPORTANT: You MUST return a JSON object with this exact format:
{{
  "explanation": "Brief description of what the code does",
  "code": "executable Python code",
  "warnings": ["optional warnings"],
  "next_steps": ["optional suggestions"]
}}

The code field should contain executable Python that builds the requested graph structure.
Use print statements to provide user feedback.

Example response:
{{
  "explanation": "Creates a scatter plot to correlate laser and detector signals",
  "code": "print('Creating scatter plot...')\\nscatter = chart.createNode('ScatterPlot', 'laser_vs_detector')\\nprint('Done!')",
  "warnings": ["Assumes laser and detector sources exist"],
  "next_steps": ["Configure axis labels in GUI"]
}}
"""

    return prompt


def extract_code_from_response(json_output):
    """
    Parse JSON events to extract structured response.

    Agent returns final response as JSON code block:
    ```json
    {{
      "explanation": "Creates scatter plot for X vs Y",
      "code": "scatter = chart.createNode('ScatterPlot', 'my_plot')",
      "warnings": ["Ensure sources exist"],
      "next_steps": ["Configure axis labels"]
    }}
    ```

    Returns: Python code as string
    """

    # Parse events in reverse (agent's final response is at the end)
    for line in reversed(json_output.split("\n")):
        if not line.strip():
            continue

        try:
            event = json.loads(line)

            if event.get("type") == "text":
                text = event.get("part", {}).get("text", "")

                # Look for JSON code block in final message
                match = re.search(r"```json\n(.*?)```", text, re.DOTALL)
                if match:
                    response = json.loads(match.group(1))

                    # Print explanation to console
                    if "explanation" in response:
                        print(f"[Graph Builder] {response['explanation']}")

                    # Print warnings to console
                    if "warnings" in response:
                        for warning in response["warnings"]:
                            print(f"[Graph Builder] ⚠️  {warning}")

                    # Print next steps to console
                    if "next_steps" in response:
                        print("[Graph Builder] Next steps:")
                        for step in response["next_steps"]:
                            print(f"  - {step}")

                    return response.get("code", "")

        except (json.JSONDecodeError, KeyError):
            continue

    raise ValueError("No structured JSON response found in agent output")
