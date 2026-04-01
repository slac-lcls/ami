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


class OpenCodeBridge:
    """
    Connects to OpenCode server for AI-assisted graph building.

    The server is started at AMI startup (see ami/client/flowchart.py).
    This class just connects to the existing server.
    """

    def __init__(self):
        self.session_id = None
        # Get server URL from environment variable
        self.url = os.environ.get("OPENCODE_SERVER_URL", None)

        if self.url:
            print(f"[Graph Builder] Using OpenCode server at {self.url}")
        else:
            print("[Graph Builder] Warning: OpenCode server not available")
            print("[Graph Builder] Set OPENCODE_SERVER_URL environment variable")

    def ask(self, prompt, timeout=120, stream_progress=True):
        """
        Send request to agent via server.

        Maintains session continuity - agent remembers previous interactions.

        Args:
            prompt: The prompt to send to the agent
            timeout: Maximum time to wait for response
            stream_progress: If True, display real-time progress indicators

        Returns: JSON output from agent (list of event objects)
        """
        # Check if server URL is available
        if self.url is None:
            raise RuntimeError("OpenCode server not available")

        cmd = [
            "opencode",
            "run",
            "--attach",
            self.url,
            # NOTE: ami-graph-builder is a skill, not an agent
            # The default agent will load the skill automatically from
            # .opencode/skills/ami-graph-builder/SKILL.md
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
            # Use Popen for streaming output
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,  # Python 3.6 compatible
            )

            output_lines = []
            start_time = time.time()

            # Stream output line by line
            if proc.stdout:
                for line in proc.stdout:
                    output_lines.append(line)

                    # Check timeout
                    if time.time() - start_time > timeout:
                        proc.kill()
                        raise RuntimeError(f"Agent request timed out after {timeout}s")

                    # Display progress if enabled
                    if stream_progress:
                        self._display_progress(line)

            # Wait for process to complete
            proc.wait()

            if proc.returncode != 0:
                stderr_output = ""
                if proc.stderr:
                    stderr_output = proc.stderr.read()
                raise RuntimeError(f"Agent invocation failed: {stderr_output}")

            # Combine all output
            full_output = "".join(output_lines)

            # Extract session ID for next request
            self.session_id = self._extract_session_id(full_output)

            return full_output

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

    def _display_progress(self, line):
        """
        Display real-time progress indicators based on JSON events.

        Shows status like:
        - ⚙️  Starting...
        - 🔧 Using tool: read
        - 💭 Thinking...
        - ✍️  Generating code...
        """
        if not line.strip():
            return

        try:
            event = json.loads(line)
            event_type = event.get("type", "")

            # Show step start
            if event_type == "step_start":
                print("⚙️  Starting...")

            # Show tool usage
            elif event_type == "tool_use":
                tool_name = event.get("part", {}).get("name", "unknown")
                # Map common tool names to user-friendly descriptions
                tool_labels = {
                    "read": "📖 Reading files",
                    "glob": "🔍 Finding files",
                    "grep": "🔎 Searching code",
                    "skill": "📚 Loading skill",
                    "bash": "⚡ Running command",
                }
                label = tool_labels.get(tool_name, f"🔧 Using tool: {tool_name}")
                print(label)

            # Show thinking/text generation (only show once per text block)
            elif event_type == "text":
                # Only show the first text event to indicate thinking started
                if not hasattr(self, "_shown_thinking"):
                    print("💭 Generating solution...")
                    self._shown_thinking = True

            # Show step complete
            elif event_type == "step_finish":
                print("✅ Ready")
                # Reset thinking flag for next request
                if hasattr(self, "_shown_thinking"):
                    delattr(self, "_shown_thinking")

        except json.JSONDecodeError:
            # Not JSON, ignore
            pass


def register_graph_builder_magic(
    ipython_shell, amicli, bridge, ipython_widget=None, code_executor=None
):
    """
    Register %build_graph and %bg magic commands.

    Args:
        ipython_shell: IPython shell instance
        amicli: AmiCli instance for graph manipulation
        bridge: OpenCodeBridge instance for AI agent communication
        ipython_widget: Optional RichJupyterWidget for banner display
        code_executor: Optional CodeExecutor for thread-safe execution
    """

    # Store references in the magic function's closure
    _amicli = amicli
    _bridge = bridge
    _ipython_shell = ipython_shell
    _ipython_widget = ipython_widget
    _code_executor = code_executor

    def build_graph(line):
        """
        Build graph nodes using natural language.

        Usage:
            %build_graph show cspad detector
            %build_graph add ROI and sum it
            %build_graph correlate laser with detector

        Note: Avoid ending with '?' as IPython treats it as help operator.
              Use: %bg correlate laser and delta_t
              Not: %bg correlate laser and delta_t?
        """
        if not line.strip():
            print("Usage: %build_graph <description>")
            print("Example: %build_graph create a scatter plot for laser vs detector")
            print("")
            print("Note: IPython treats '?' as help operator. To use questions:")
            print("  Option 1 (recommended): Don't use '?' at end")
            print("    %bg correlate laser and delta_t")
            print("  Option 2: Not needed - agent understands without '?'")
            print("    %bg can we correlate laser and delta_t")
            print("")
            return

        print(f"[Graph Builder] Processing: {line}")
        print("")

        try:
            # Get current graph state
            graph_state = get_graph_state(_amicli)

            # Invoke agent (with streaming progress)
            code = invoke_agent_for_graph_building(line, graph_state, _amicli, _bridge)

            if code:
                # Display code preview
                print("")
                print("─" * 60)
                print("Generated code:")
                print("─" * 60)
                for line in code.split("\n"):
                    print(line)
                print("─" * 60)
                print("")
                print("[Graph Builder] Executing...")

                # Execute via signal (thread-safe)
                if _code_executor:
                    _code_executor.execute_code.emit(code)
                    # Note: "Done!" message prints from GUI thread slot
                else:
                    # Fallback if no executor (shouldn't happen)
                    print("[Graph Builder] Warning: No code executor available")
                    try:
                        _ipython_shell.ex(code)
                        print("[Graph Builder] ✅ Done!")
                    except Exception as e:
                        print(f"[Graph Builder] Execution error: {e}")
                        import traceback

                        traceback.print_exc()
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

    # Create help function to show features
    def graph_help():
        """Show AMI Graph Builder features and usage."""
        print("")
        print("=" * 60)
        print("AMI Graph Builder")
        print("=" * 60)
        print("")
        print("Build graphs conversationally using natural language:")
        print("")
        print("  %build_graph <request>  or  %bg <request>")
        print("")
        print("  Examples:")
        print("    %bg correlate laser and delta_t")
        print("    %bg now add a filter where laser > 5")
        print("    %bg show me what this does")
        print("")
        print("The agent remembers your conversation, so you can")
        print("refer back to previous requests naturally.")
        print("")
        print("Helper functions:")
        print("  • graph_help()           - Show this help")
        print("  • amicli.connect_nodes() - Connect nodes manually")
        print("  • ensure_source()        - Create source nodes")
        print("  • chart.createNode()     - Create any node type")
        print("")
        print("Tip: Don't end commands with '?' (IPython help conflict)")
        print("=" * 60)
        print("")

    # Register helper function in namespace
    _ipython_shell.push({"graph_help": graph_help})

    # Note: Banner is displayed via RichJupyterWidget.banner property in Flowchart.py


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


def ensure_source(amicli, source_name):
    """
    Ensure a source node exists in the graph for the given experiment source.

    This function provides smart source creation with validation:
    - Checks if source already exists in graph (returns immediately if yes)
    - Creates SourceNode if source exists in source_library but not in graph
    - Raises helpful error if source doesn't exist in experiment data

    Args:
        amicli: AmiCli instance with chart and graph access
        source_name (str): Name of the source from the experiment

    Returns:
        str: The source node name (for use in connect_nodes)

    Raises:
        ValueError: If source_name is not available in the experiment data,
                   with suggestions for similar source names

    Example:
        >>> ensure_source(amicli, 'laser_power')  # Creates if needed
        'laser_power'
        >>> ensure_source(amicli, 'laser_power')  # No-op if exists
        'laser_power'
        >>> ensure_source(amicli, 'invalid')      # Raises error with suggestions
        ValueError: Source 'invalid' not available...
    """
    from ami.flowchart.library.common import SourceNode

    # Check if source already exists in graph
    if source_name in amicli.chart._graph:
        # Source already in graph, nothing to do
        return source_name

    # Try to get the source type from the experiment data
    try:
        node_type = amicli.chart.source_library.getSourceType(source_name)
    except KeyError:
        # Source doesn't exist in experiment data
        # Provide helpful error with suggestions
        available = list(amicli.chart.source_library.sourceList.keys())

        # Try fuzzy matching for suggestions
        suggestions = []
        source_lower = source_name.lower()
        for avail in available:
            # Simple fuzzy matching: contains substring or similar
            if source_lower in avail.lower() or avail.lower() in source_lower:
                suggestions.append(avail)

        # Build error message
        error_msg = f"Source '{source_name}' not available in experiment data."

        if suggestions:
            error_msg += f"\n\nDid you mean one of these?\n  - " + "\n  - ".join(
                suggestions[:5]
            )
        else:
            error_msg += f"\n\nAvailable sources include:\n  - " + "\n  - ".join(
                available[:10]
            )
            if len(available) > 10:
                error_msg += f"\n  ... and {len(available) - 10} more"

        raise ValueError(error_msg)

    # Source exists in data but not in graph - create it
    source_node = SourceNode(
        name=source_name, terminals={"Out": {"io": "out", "ttype": node_type}}
    )

    # Add to graph at a default position
    # Position doesn't matter much since user can rearrange in GUI
    amicli.chart.addNode(node=source_node, pos=[100, 100])

    return source_name


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
    Generate comprehensive prompt for AI agent with rich context.

    Includes:
    - User request
    - Current graph state (nodes, connections, sources)
    - Available sources categorized by type
    - Available API
    - Guidance on when to ask questions vs generate code
    - Required response formats (question or code)
    """

    # Categorize available sources for better context
    sources_by_type = _categorize_sources(graph_state.get("available_sources", []))

    # Format existing nodes for context
    existing_nodes_summary = _format_existing_nodes(graph_state.get("nodes", []))

    prompt = f"""IMPORTANT: Load the ami-graph-builder skill using the skill tool and follow its instructions exactly.

The skill contains complete instructions on:
- How to generate Python code for AMI graph building
- The correct JSON response format (question or code response)
- All available node types and when to use them
- When to ask clarifying questions vs generate code
- How SourceNodes work (built-in viewers, no need for display nodes)

USER REQUEST: {user_request}

CURRENT GRAPH STATE:
- Total nodes: {len(graph_state["nodes"])}
- Existing source nodes: {", ".join(graph_state["sources"]) if graph_state["sources"] else "None"}
{existing_nodes_summary}

AVAILABLE SOURCES (from experiment):
{_format_sources_by_type(sources_by_type)}

Load the ami-graph-builder skill now and use it to generate the appropriate response for this request.
"""

    return prompt


def _categorize_sources(available_sources):
    """Categorize sources by type for better prompt context."""
    categories = {"detectors": [], "motors": [], "lasers": [], "pvs": [], "other": []}

    for src in available_sources:
        src_lower = src.lower()
        if any(
            keyword in src_lower
            for keyword in ["det", "cam", "cspad", "epix", "jungfrau"]
        ):
            categories["detectors"].append(src)
        elif any(keyword in src_lower for keyword in ["motor", "pos", "stage"]):
            categories["motors"].append(src)
        elif "laser" in src_lower:
            categories["lasers"].append(src)
        elif ":" in src:  # Likely a PV name
            categories["pvs"].append(src)
        else:
            categories["other"].append(src)

    return categories


def _format_sources_by_type(sources_by_type):
    """Format categorized sources for prompt."""
    lines = []

    if sources_by_type["detectors"]:
        lines.append(f"  Detectors: {', '.join(sources_by_type['detectors'][:5])}")
        if len(sources_by_type["detectors"]) > 5:
            lines.append(
                f"             ... and {len(sources_by_type['detectors']) - 5} more"
            )

    if sources_by_type["lasers"]:
        lines.append(f"  Lasers: {', '.join(sources_by_type['lasers'])}")

    if sources_by_type["motors"]:
        lines.append(f"  Motors: {', '.join(sources_by_type['motors'][:5])}")
        if len(sources_by_type["motors"]) > 5:
            lines.append(f"          ... and {len(sources_by_type['motors']) - 5} more")

    if sources_by_type["pvs"]:
        lines.append(f"  PVs: {len(sources_by_type['pvs'])} available")

    if sources_by_type["other"]:
        lines.append(f"  Other: {', '.join(sources_by_type['other'][:3])}")
        if len(sources_by_type["other"]) > 3:
            lines.append(f"         ... and {len(sources_by_type['other']) - 3} more")

    return "\n".join(lines) if lines else "  No sources available"


def _format_existing_nodes(nodes):
    """Format existing nodes for prompt context."""
    if not nodes:
        return ""

    node_types = {}
    for node in nodes:
        node_type = node.get("type", "Unknown")
        node_types[node_type] = node_types.get(node_type, 0) + 1

    summary = "- Node types in graph: " + ", ".join(
        [f"{count}x {ntype}" for ntype, count in node_types.items()]
    )
    return summary


def extract_code_from_response(json_output):
    """
    Parse JSON events to extract structured response.

    Agent can return two types of responses:

    1. Question Response (needs clarification):
    ```json
    {{
      "type": "question",
      "message": "What's unclear",
      "questions": [{{"question": "...", "options": [...], "context": "..."}}],
      "assumptions_if_skipped": "What I'll assume"
    }}
    ```

    2. Code Response (ready to execute):
    ```json
    {{
      "explanation": "Creates scatter plot for X vs Y",
      "code": "scatter = chart.createNode('ScatterPlot', 'my_plot')",
      "warnings": ["Ensure sources exist"],
      "next_steps": ["Configure axis labels"]
    }}
    ```

    Returns: Python code as string, or None if questions were asked
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

                    # Handle Question Response
                    if response.get("type") == "question":
                        print("")
                        print("=" * 60)
                        print("[Graph Builder] I need more information")
                        print("=" * 60)
                        print("")

                        if "message" in response:
                            print(f"{response['message']}")
                            print("")

                        # Print each question
                        for i, q in enumerate(response.get("questions", []), 1):
                            print(f"Question {i}: {q['question']}")

                            if "options" in q:
                                for j, opt in enumerate(q["options"], 1):
                                    print(f"  {j}. {opt}")

                            if "context" in q:
                                print(f"  ℹ️  {q['context']}")

                            print("")

                        if "assumptions_if_skipped" in response:
                            print(
                                f"💡 If you just want me to proceed: {response['assumptions_if_skipped']}"
                            )
                            print("")

                        print(
                            "Please provide more details and run %build_graph again with:"
                        )
                        print("  - More specific request")
                        print("  - Or respond 'proceed' to use assumptions")
                        print("")
                        print("=" * 60)

                        return None  # No code to execute

                    # Handle Code Response (existing logic)
                    if "explanation" in response:
                        print(f"[Graph Builder] {response['explanation']}")

                    if "warnings" in response:
                        for warning in response["warnings"]:
                            print(f"[Graph Builder] ⚠️  {warning}")

                    if "next_steps" in response:
                        print("[Graph Builder] Next steps:")
                        for step in response["next_steps"]:
                            print(f"  - {step}")

                    # Get code and decode escaped newlines from JSON representation
                    code = response.get("code", "")
                    if not code:
                        return ""

                    # Decode \n from JSON string to actual newlines
                    code = code.replace("\\n", "\n")

                    # Validate syntax before returning
                    try:
                        import ast

                        ast.parse(code)
                    except SyntaxError as e:
                        print("")
                        print("[Graph Builder] ⚠️  Generated code has syntax error:")
                        print(f"[Graph Builder]    {e}")
                        if e.lineno:
                            print(f"[Graph Builder]    Error on line {e.lineno}")
                            print("[Graph Builder] Generated code:")
                            for i, line in enumerate(code.split("\n"), 1):
                                marker = ">>>" if i == e.lineno else "   "
                                print(f"  {marker} {i}: {line}")
                        else:
                            print("[Graph Builder] Generated code:")
                            for i, line in enumerate(code.split("\n"), 1):
                                print(f"      {i}: {line}")
                        print("")
                        print(
                            "[Graph Builder] Not executing - this is likely an agent bug"
                        )
                        print("[Graph Builder] Please report this issue")
                        return None

                    return code

        except (json.JSONDecodeError, KeyError):
            continue

    raise ValueError("No structured JSON response found in agent output")
