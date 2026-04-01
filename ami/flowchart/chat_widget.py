"""
Qt Widget-Based Chat Interface for AMI Natural Language Graph Building

This module provides a simple Qt widget for natural language graph building
that solves the fundamental problems of the QtConsole approach:

1. Direct state access - no IPC, instant graph state
2. Non-blocking - background threads for OpenCode subprocess
3. Simple - standard Qt patterns, ~250 lines
4. Works - no event loop blocking issues

Architecture:
- Qt Main Thread: UI, state access, code execution
- Background QThread: OpenCode subprocess (isolated)
- Qt Signals: Thread-safe communication (built-in)
"""

import json
import re
import traceback
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
)
from qtpy.QtCore import Qt, Signal, QThread, Slot


class ChatWorker(QThread):
    """Background thread for OpenCode subprocess calls."""

    # Signals
    response_received = Signal(str)  # Agent response (JSON string)
    error_occurred = Signal(str)  # Error message

    def __init__(self, bridge, prompt):
        """
        Initialize chat worker.

        Args:
            bridge: OpenCodeBridge instance
            prompt: Full prompt to send to agent (includes graph state)
        """
        super().__init__()
        self.bridge = bridge
        self.prompt = prompt

    def run(self):
        """Execute OpenCode subprocess call (blocking, but isolated in thread)."""
        try:
            # Call agent (blocks, but we're in background thread so UI stays responsive)
            result = self.bridge.ask(self.prompt, timeout=120, stream_progress=False)

            # Emit response to main thread
            self.response_received.emit(result)  # ask() already returns string

        except RuntimeError as e:
            error_msg = str(e)
            # If session not found, clear it and retry once
            if "Session not found" in error_msg:
                self.bridge.session_id = None
                try:
                    result = self.bridge.ask(
                        self.prompt, timeout=120, stream_progress=False
                    )
                    self.response_received.emit(result)
                    return
                except Exception as retry_error:
                    self.error_occurred.emit(f"Retry failed: {retry_error}")
                    return
            # Other runtime errors
            self.error_occurred.emit(error_msg)

        except Exception as e:
            # Emit error to main thread
            self.error_occurred.emit(str(e))


class ChatWidget(QWidget):
    """Qt widget for natural language graph building chat."""

    # Signals for thread-safe code execution
    execute_code_signal = Signal(str)  # Code to execute on main thread

    def __init__(self, ctrl, parent=None):
        """
        Initialize chat widget.

        Args:
            ctrl: Flowchart instance (provides access to graph state and execution)
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.ctrl = ctrl  # Direct reference to Flowchart
        self.bridge = None  # OpenCodeBridge (lazy init)
        self.command_history = []  # In-memory command history
        self.history_index = -1  # Current position in history
        self.current_worker = None  # Current background worker

        self._setup_ui()
        self._connect_signals()
        self._init_bridge()

    def _setup_ui(self):
        """Create UI layout."""
        # Window setup
        self.setWindowTitle("AMI Chat - Natural Language Graph Builder")
        self.resize(600, 500)

        # Main layout
        layout = QVBoxLayout()

        # Output area (conversation history)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText(
            "Chat conversation will appear here...\n\n"
            "Try: 'create a scatter plot of source_0.raw vs source_1.raw'"
        )
        layout.addWidget(self.output_text)

        # Input area
        input_layout = QHBoxLayout()

        # Input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("You: Type your message here...")
        input_layout.addWidget(self.input_field)

        # Send button
        self.send_button = QPushButton("Send")
        self.send_button.setFixedWidth(80)
        input_layout.addWidget(self.send_button)

        layout.addLayout(input_layout)

        self.setLayout(layout)

        # Initial welcome message
        self._append_output("=== AMI Natural Language Graph Builder ===")
        self._append_output("Ask me to create graphs in plain English!")
        self._append_output("Example: 'create a scatter plot of laser vs detector'")
        self._append_output("")
        self._append_output("Tip: Use up/down arrows to navigate command history")
        self._append_output("=" * 50)
        self._append_output("")

    def _connect_signals(self):
        """Connect Qt signals/slots."""
        # Input submission
        self.input_field.returnPressed.connect(self._on_submit)
        self.send_button.clicked.connect(self._on_submit)

        # Code execution signal
        self.execute_code_signal.connect(self._execute_code_slot)

    def _init_bridge(self):
        """Initialize OpenCodeBridge (lazy)."""
        try:
            from ami.flowchart.graph_builder import OpenCodeBridge

            self.bridge = OpenCodeBridge()
            self._append_output("[System] OpenCode bridge initialized")
        except Exception as e:
            self._append_output(f"[System] Warning: Could not initialize OpenCode: {e}")
            self._append_output("[System] AI features will not be available")

    def _on_submit(self):
        """Handle user input submission."""
        # Get user input
        user_input = self.input_field.text().strip()
        if not user_input:
            return

        # Clear input field
        self.input_field.clear()

        # Add to command history
        self.command_history.append(user_input)
        self.history_index = len(self.command_history)

        # Display user message
        self._append_output(f"You: {user_input}")
        self._append_output("")

        # Check if bridge is available
        if self.bridge is None:
            self._append_output("[Error] OpenCode bridge not available")
            self._append_output("")
            return

        # Get graph state (INSTANT - direct access, same process)
        try:
            from ami.flowchart.graph_builder import get_graph_state

            state = get_graph_state(self.ctrl.amicli)
        except Exception as e:
            self._append_output(f"[Error] Could not get graph state: {e}")
            self._append_output("")
            return

        # Build full prompt with context
        prompt = self._build_prompt(user_input, state)

        # Display status
        self._append_output("[System] Sending request to agent...")

        # Launch background worker (NON-BLOCKING)
        self.current_worker = ChatWorker(self.bridge, prompt)
        self.current_worker.response_received.connect(self._on_response_received)
        self.current_worker.error_occurred.connect(self._on_error_occurred)
        self.current_worker.start()

    def _build_prompt(self, user_input, state):
        """
        Build full prompt with graph state context.

        Args:
            user_input: User's message
            state: Dict with nodes, sources, connections, available_sources

        Returns:
            Full prompt string
        """
        # Format available sources
        sources_str = ", ".join(state.get("available_sources", []))

        # Format existing nodes (if any)
        nodes_str = ""
        if state.get("nodes"):
            nodes_str = "\nExisting nodes in graph:\n"
            for node in state["nodes"]:
                nodes_str += f"  - {node['name']} ({node['type']})\n"

        # Build prompt
        prompt = f"""Available data sources: {sources_str}
{nodes_str}
User request: {user_input}

Please generate Python code to fulfill this request using the AMI graph building API."""

        return prompt

    @Slot(str)
    def _on_response_received(self, response_str):
        """
        Handle agent response (runs on Qt main thread).

        Args:
            response_str: String with newline-separated JSON events from agent
        """
        self._append_output("[System] Response received, processing...")
        self._append_output("")

        # Show agent's conversational text first
        self._show_agent_text(response_str)

        # Extract code from response
        codes = self._extract_code(response_str)

        if codes:
            self._append_output(f"[System] Found {len(codes)} code block(s)")
            self._append_output("")

            # Display and execute each code block
            for i, code in enumerate(codes, 1):
                self._append_output(f"--- Generated Code {i} ---")
                self._append_output(code)
                self._append_output("--- End Code ---")
                self._append_output("")

                # Auto-execute (emit signal for thread-safe execution)
                self.execute_code_signal.emit(code)
        else:
            # No code found - agent might have just answered with text
            self._append_output("[System] No code to execute")

        self._append_output("")

    @Slot(str)
    def _on_error_occurred(self, error_msg):
        """
        Handle error from background worker.

        Args:
            error_msg: Error message string
        """
        self._append_output(f"[Error] {error_msg}")
        self._append_output("")

    def _extract_code(self, response_str):
        """
        Extract executable code from agent response.

        Matches the working extract_code_from_response() from graph_builder.py.
        Parses in reverse to get the final response from the agent.

        Args:
            response_str: String with newline-separated JSON events from agent

        Returns:
            List of code strings
        """
        codes = []

        try:
            # Parse events in reverse (agent's final response is at the end)
            for line in reversed(response_str.split("\n")):
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)

                    # Look for text events (agent's responses)
                    if event.get("type") == "text":
                        text = event.get("part", {}).get("text", "")

                        # Look for JSON code block (ami-graph-builder skill format)
                        match = re.search(r"```json\n(.*?)```", text, re.DOTALL)
                        if match:
                            try:
                                response = json.loads(match.group(1))

                                # Check if it's a question (no code to execute)
                                if response.get("type") == "question":
                                    # Display question to user
                                    self._append_output("")
                                    self._append_output("Agent has questions:")
                                    if "message" in response:
                                        self._append_output(response["message"])
                                    for q in response.get("questions", []):
                                        self._append_output(
                                            f"  Q: {q.get('question', '')}"
                                        )
                                        if "options" in q:
                                            for opt in q["options"]:
                                                self._append_output(f"     - {opt}")
                                    self._append_output("")
                                    return []  # No code to execute

                                # Extract code from response
                                if "code" in response:
                                    code = response["code"]

                                    # Show explanation if provided
                                    if "explanation" in response:
                                        self._append_output(
                                            f"Agent: {response['explanation']}"
                                        )
                                        self._append_output("")

                                    # Show warnings if provided
                                    if "warnings" in response:
                                        for warning in response["warnings"]:
                                            self._append_output(f"⚠️  {warning}")
                                        self._append_output("")

                                    codes.append(code)

                                    # Only process the first (most recent) JSON block found
                                    if codes:
                                        return codes

                            except json.JSONDecodeError:
                                # Not valid JSON, skip
                                continue

                except json.JSONDecodeError:
                    # Skip lines that aren't valid JSON events
                    continue

        except Exception as e:
            self._append_output(f"[Warning] Code extraction error: {e}")

        return codes

    def _extract_text(self, response_str):
        """
        Extract text content from agent response.

        Args:
            response_str: String with newline-separated JSON events from agent

        Returns:
            Combined text content from all events
        """
        text_parts = []

        try:
            # Parse newline-separated JSON events
            for line in response_str.split("\n"):
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)

                    if isinstance(event, dict) and "content" in event:
                        text_parts.append(event["content"])

                except json.JSONDecodeError:
                    continue

        except Exception as e:
            self._append_output(f"[Warning] Text extraction error: {e}")

        return "\n".join(text_parts)

    def _show_agent_text(self, response_str):
        """
        Show agent's conversational text (excluding code blocks).

        Args:
            response_str: String with newline-separated JSON events
        """
        agent_texts = []

        try:
            # Parse events in order (not reversed - show conversation flow)
            for line in response_str.split("\n"):
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)

                    # Look for text events
                    if event.get("type") == "text":
                        text = event.get("part", {}).get("text", "")

                        # Skip if this text contains a ```json block (that's code, shown separately)
                        if "```json" in text:
                            continue

                        # Skip empty text
                        if text.strip():
                            agent_texts.append(text)

                except json.JSONDecodeError:
                    continue

        except Exception as e:
            self._append_output(f"[Warning] Text display error: {e}")

        # Display agent text if any was found
        if agent_texts:
            self._append_output("Agent:")
            for text in agent_texts:
                self._append_output(text)
            self._append_output("")  # Blank line for separation

    @Slot(str)
    def _execute_code_slot(self, code):
        """
        Execute code on Qt main thread (slot for signal).

        Args:
            code: Python code string to execute
        """
        self._execute_code(code)

    def _execute_code(self, code):
        """
        Execute generated code on Qt main thread.

        Uses Flowchart's _execute_graph_code method which handles:
        - Namespace setup (chart, graph, amicli, helpers)
        - Error handling
        - Thread-safe execution

        Args:
            code: Python code string to execute
        """
        try:
            self._append_output("[System] Executing code...")

            # Build execution namespace
            # self.ctrl is FlowchartCtrlWidget, which has .chart (Flowchart) and .amicli
            from ami.flowchart.graph_builder import ensure_source
            import numpy as np
            import pyqtgraph as pg

            namespace = {
                "chart": self.ctrl.chart,
                "graph": self.ctrl.chart._graph,
                "amicli": self.ctrl.amicli if hasattr(self.ctrl, "amicli") else None,
                "ensure_source": lambda name: ensure_source(
                    self.ctrl.amicli if hasattr(self.ctrl, "amicli") else None, name
                ),
                "np": np,
                "pg": pg,
            }

            exec(code, namespace)

            self._append_output("[System] ✅ Execution successful!")

        except Exception as e:
            error_msg = f"[Execution Error] {e}\n{traceback.format_exc()}"
            self._append_output(error_msg)

        self._append_output("")

    def _append_output(self, text):
        """
        Append text to output area.

        Args:
            text: Text to append
        """
        self.output_text.append(text)

        # Auto-scroll to bottom
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def keyPressEvent(self, event):
        """
        Handle keyboard shortcuts.

        Args:
            event: Key event
        """
        # Command history navigation (up/down arrows)
        if event.key() == Qt.Key_Up:
            if self.history_index > 0:
                self.history_index -= 1
                self.input_field.setText(self.command_history[self.history_index])
        elif event.key() == Qt.Key_Down:
            if self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.input_field.setText(self.command_history[self.history_index])
            elif self.history_index == len(self.command_history) - 1:
                self.history_index = len(self.command_history)
                self.input_field.clear()
        else:
            # Pass other keys to parent
            super().keyPressEvent(event)
