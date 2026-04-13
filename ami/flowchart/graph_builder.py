"""
AI-Assisted Graph Building for AMI

Backend utilities for the chat widget interface that enables building AMI
analysis graphs using natural language via an AI agent.

Uses the official OpenCode Python SDK for type-safe, reliable communication
with the OpenCode server. The SDK handles session management, message sending,
and response parsing with built-in Pydantic validation.
"""

import json
import os

import opencode_ai
from opencode_ai import Opencode


class OpenCodeBridge:
    """
    Connects to OpenCode server for AI-assisted graph building via REST API.

    The server is started at AMI startup (see ami/client/flowchart.py).
    This class uses the REST API with explicit skill parameter for reliable
    skill loading.
    """

    def __init__(self):
        self.session_id = None
        self.url = os.environ.get("OPENCODE_SERVER_URL", None)

        if self.url:
            print(f"[Graph Builder] Using OpenCode server at {self.url}")
            try:
                # Create SDK client
                self.client = Opencode(base_url=self.url)
                # Quick connection test
                _ = self.client.session.list()
                print("[Graph Builder] ✅ Connected to OpenCode server")
            except Exception as e:
                print(f"[Graph Builder] ⚠️  Connection failed: {e}")
                self.client = None
        else:
            print("[Graph Builder] Warning: OpenCode server not available")
            print("[Graph Builder] Set OPENCODE_SERVER_URL environment variable")
            self.client = None

    def ask(self, prompt, timeout=120, stream_progress=True):
        """
        Send request to agent via OpenCode SDK.

        Maintains session continuity - agent remembers previous interactions.

        Args:
            prompt: The prompt to send to the agent
            timeout: Maximum time to wait for response
            stream_progress: If True, display real-time progress indicators

        Returns: JSON output from agent (list of event objects formatted as JSON strings)
        """
        if self.client is None:
            raise RuntimeError("OpenCode server not available")

        # Create session on first request
        if self.session_id is None:
            # Note: extra_body={} required to send empty JSON body to server
            session = self.client.session.create(extra_body={})
            self.session_id = session.id
            print(f"[Graph Builder] Created session: {self.session_id}")

        try:
            # Send message using SDK
            # Use default model and explicitly enable ami-graph-builder skill
            response = self.client.with_options(timeout=timeout).session.chat(
                self.session_id,
                model_id="claude-4-5-sonnet",  # Default model
                provider_id="anthropic",  # Default provider
                parts=[{"type": "text", "text": prompt}],
                tools={"ami-graph-builder": True},  # Explicitly enable skill
            )

            # Display progress if enabled
            if stream_progress:
                for part in response.parts:
                    self._display_progress_from_part(part)

            # Convert SDK response to JSON string format for compatibility
            # with existing chat_widget.py parsing code
            return self._format_response_as_json(response)

        except opencode_ai.APIConnectionError as e:
            raise RuntimeError(f"Cannot connect to OpenCode server: {e}")
        except opencode_ai.APITimeoutError:
            raise RuntimeError(f"Request timed out after {timeout}s")
        except opencode_ai.APIStatusError as e:
            raise RuntimeError(f"API error {e.status_code}: {e.response}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error: {e}")

    def _format_response_as_json(self, response):
        """
        Convert SDK AssistantMessage to JSON string format.

        The chat widget expects JSON strings (one event per line), but the SDK
        returns an AssistantMessage with parts as dicts. This method bridges the gap.

        Args:
            response: AssistantMessage object from SDK with .parts as list of dicts

        Returns: JSON string (one event per line) compatible with chat_widget parsing
        """
        events = []

        # Add each part as an event
        for part_dict in response.parts:
            # Parts are already dicts from the SDK
            part_type = part_dict.get("type", "unknown")

            # Map SDK part types to event types expected by chat widget
            # SDK uses "step-start", we expect "step_start", etc.
            event_type_map = {
                "step-start": "step_start",
                "step-finish": "done",
                "text": "text",
                "tool": "tool_use",
            }

            event_type = event_type_map.get(part_type, part_type)
            # chat_widget.py expects "part" field, not "data"
            events.append({"type": event_type, "part": part_dict})

        # Convert to JSON string format (one event per line)
        return "\n".join(json.dumps(event) for event in events)

    def _display_progress_from_part(self, part):
        """
        Display real-time progress indicators from SDK part dicts.

        Shows status like:
        - 🔧 Using tool: read
        - 💭 Thinking...
        - ✅ Ready

        Args:
            part: Part dict from SDK response
        """
        # Parts from SDK are already dicts
        part_type = part.get("type", "")

        # Show tool usage
        if part_type == "tool":
            tool_name = part.get("name", "unknown")
            tool_labels = {
                "read": "📖 Reading files",
                "glob": "🔍 Finding files",
                "grep": "🔎 Searching code",
                "skill": "📚 Loading skill",
                "bash": "⚡ Running command",
            }
            label = tool_labels.get(tool_name, f"🔧 Using tool: {tool_name}")
            print(label)

        # Show thinking/text generation
        elif part_type == "text":
            if not hasattr(self, "_shown_thinking"):
                print("💭 Generating solution...")
                self._shown_thinking = True

        # Show step complete
        elif part_type == "step-finish":
            print("✅ Ready")
            if hasattr(self, "_shown_thinking"):
                delattr(self, "_shown_thinking")

    def close_session(self):
        """
        Clean up session resources.

        Deletes the session on the server to prevent orphaned sessions.
        Called when chat widget is closed.
        """
        if self.client and self.session_id:
            try:
                self.client.session.delete(self.session_id)
                print(f"[Graph Builder] Deleted session: {self.session_id}")
                self.session_id = None
            except Exception as e:
                print(f"[Graph Builder] Failed to delete session: {e}")


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
            error_msg += "\n\nDid you mean one of these?\n  - " + "\n  - ".join(
                suggestions[:5]
            )
        else:
            error_msg += "\n\nAvailable sources include:\n  - " + "\n  - ".join(
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
