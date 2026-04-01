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
from datetime import datetime
from html import escape
from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QTextBrowser,
    QLineEdit,
    QPushButton,
    QApplication,
)
from qtpy.QtCore import Qt, Signal, QThread, Slot, QTimer

# Syntax highlighting
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter


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

        # Message storage system for HTML rendering
        self._messages = []  # List of message dicts
        self._code_blocks = {}  # {block_id: code_string}
        self._code_visibility = {}  # {block_id: bool (visible?)}
        self._copy_flash_timers = {}  # {block_id: QTimer for flash effect}
        self._block_counter = 0  # Auto-incrementing ID

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
        self.output_text = QTextBrowser()
        self.output_text.setOpenLinks(False)
        self.output_text.setOpenExternalLinks(False)
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

        # Link clicks in QTextBrowser
        self.output_text.anchorClicked.connect(self._handle_link_click)

    def _handle_link_click(self, url):
        """
        Handle clicks on code block links (toggle show/hide, copy).

        Args:
            url: QUrl with fragment like "toggle:block_1" or "copy:block_1"
        """
        fragment = url.fragment()  # Get everything after #

        if not fragment or ":" not in fragment:
            return

        action, block_id = fragment.split(":", 1)

        if action == "toggle":
            # Toggle code visibility
            if block_id in self._code_visibility:
                self._code_visibility[block_id] = not self._code_visibility[block_id]
                self._render_messages()

        elif action == "copy":
            # Copy code to clipboard
            code = self._code_blocks.get(block_id, "")
            if code:
                QApplication.clipboard().setText(code)
                # Flash the copy button to show success
                self._flash_copy_button(block_id)

    def _flash_copy_button(self, block_id):
        """
        Temporarily show 'Copied!' on the copy button.

        Args:
            block_id: ID of the code block that was copied
        """
        # Cancel any existing timer for this block
        if block_id in self._copy_flash_timers:
            self._copy_flash_timers[block_id].stop()

        # Mark as copied (special state)
        self._code_blocks[f"{block_id}_copied"] = True
        self._render_messages()

        # Set timer to revert after 2 seconds
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._revert_copy_button(block_id))
        timer.start(2000)  # 2 seconds

        self._copy_flash_timers[block_id] = timer

    def _revert_copy_button(self, block_id):
        """Revert copy button back to normal state."""
        if f"{block_id}_copied" in self._code_blocks:
            del self._code_blocks[f"{block_id}_copied"]
        self._render_messages()

    def _append_message(self, msg_type, content, **kwargs):
        """
        Append a message to the chat.

        Args:
            msg_type: 'user', 'system', 'agent', 'warning', 'separator', 'code'
            content: The message content
            **kwargs: Additional properties (block_id, number, etc.)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        self._messages.append(
            {"type": msg_type, "content": content, "timestamp": timestamp, **kwargs}
        )
        self._render_messages()

    def _append_code_block(self, code, block_number):
        """
        Append a collapsible code block.

        Args:
            code: Python code string
            block_number: Code block number (1, 2, 3...)
        """
        # Generate unique ID
        self._block_counter += 1
        block_id = f"block_{self._block_counter}"

        # Store code and initial state
        self._code_blocks[block_id] = code
        self._code_visibility[block_id] = False  # Collapsed by default

        # Add to messages
        self._append_message("code", code, block_id=block_id, number=block_number)

    def _highlight_python(self, code):
        """
        Syntax highlight Python code using Pygments.

        Args:
            code: Raw Python code string

        Returns:
            HTML string with inline-styled syntax highlighting
        """
        formatter = HtmlFormatter(
            style="monokai",  # Dark theme
            noclasses=True,  # Inline styles (no external CSS)
            nowrap=True,  # Don't wrap in <div>
            linenos=False,  # We handle line numbers separately
        )
        return highlight(code, PythonLexer(), formatter)

    def _generate_line_numbers(self, code):
        """
        Generate HTML for line numbers column.

        Args:
            code: Code string

        Returns:
            HTML string with line numbers separated by <br>
        """
        line_count = len(code.splitlines())
        return "<br>".join(str(i + 1) for i in range(line_count))

    def _format_code_block(self, code, block_id, block_number):
        """
        Format a code block with all features.

        Args:
            code: Python code string
            block_id: Unique block identifier
            block_number: Display number (1, 2, 3...)

        Returns:
            HTML string for the complete code block
        """
        visible = self._code_visibility.get(block_id, False)
        copied = f"{block_id}_copied" in self._code_blocks
        line_count = len(code.splitlines())

        # Toggle state
        toggle_icon = "▼" if visible else "▶"
        toggle_text = "Hide" if visible else "Show"

        # Copy button state
        if copied:
            copy_btn_html = '<span class="copy-btn-success">[✓ Copied!]</span>'
        else:
            copy_btn_html = f'<a href="#copy:{block_id}" class="copy-btn">[📋 Copy]</a>'

        # Always render header
        html = f"""
    <div class="code-container">
        <div class="code-header">
            <span class="code-title">Generated Code {block_number}</span>
            <span class="code-info">({line_count} lines)</span>
            <span class="code-actions">
                <a href="#toggle:{block_id}" class="code-toggle">[{toggle_icon} {toggle_text}]</a>
                {copy_btn_html}
            </span>
        </div>
"""

        # Only render code-body if visible
        if visible:
            line_numbers_html = self._generate_line_numbers(code)
            highlighted_code = self._highlight_python(code)

            html += f"""
        <div class="code-body">
            <table class="code-table">
                <tr>
                    <td class="line-numbers">{line_numbers_html}</td>
                    <td class="code-content">
                        <pre>{highlighted_code}</pre>
                    </td>
                </tr>
            </table>
        </div>
"""

        html += "    </div>\n    "
        return html

    def _render_messages(self):
        """
        Render all messages as HTML with Material Design styling.

        Regenerates entire output from message storage.
        Preserves scroll position intelligently.
        """
        # Build HTML with embedded CSS
        html_parts = [
            """
    <html>
    <head>
    <style>
        /* Base styles */
        body {
            font-family: 'Segoe UI', 'Roboto', Arial, sans-serif;
            font-size: 13px;
            line-height: 1.6;
            color: #212121;
            margin: 10px;
            background-color: #FAFAFA;
        }
        
        /* Message styles */
        p {
            margin: 6px 0;
            padding: 4px 0;
        }
        
        .timestamp {
            color: #9E9E9E;
            font-size: 11px;
            font-family: 'Consolas', monospace;
            margin-right: 8px;
        }
        
        .user {
            color: #1976D2;
            font-weight: 600;
        }
        
        .system {
            color: #757575;
            font-style: italic;
        }
        
        .agent {
            color: #388E3C;
            font-weight: 600;
        }
        
        .warning {
            color: #F57C00;
            padding-left: 20px;
        }
        
        /* Separator */
        .separator {
            text-align: center;
            color: #757575;
            font-weight: 600;
            margin: 20px 0 15px 0;
            padding: 12px 0;
            background: linear-gradient(to right, #E8F5E9, #C8E6C9, #E8F5E9);
            border-radius: 4px;
        }
        
        /* Code container */
        .code-container {
            margin: 15px 0;
            background-color: #FFFFFF;
            border-left: 4px solid #4CAF50;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .code-header {
            background: linear-gradient(to bottom, #E8F5E9, #C8E6C9);
            padding: 10px 15px;
            border-bottom: 1px solid #A5D6A7;
            display: flex;
            align-items: center;
        }
        
        .code-title {
            font-weight: 600;
            color: #2E7D32;
        }
        
        .code-info {
            color: #66BB6A;
            margin-left: 8px;
            font-size: 12px;
        }
        
        .code-actions {
            margin-left: auto;
        }
        
        .code-toggle {
            color: #2196F3;
            text-decoration: none;
            margin-left: 10px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .code-toggle:hover {
            text-decoration: underline;
            color: #1976D2;
        }
        
        .copy-btn {
            color: #2196F3;
            text-decoration: none;
            margin-left: 10px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .copy-btn:hover {
            text-decoration: underline;
            color: #1976D2;
        }
        
        .copy-btn-success {
            color: #4CAF50;
            font-weight: 600;
            margin-left: 10px;
            font-size: 12px;
        }
        
        .code-body {
            background-color: #2b2b2b;
        }
        
        /* Code table */
        .code-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
        }
        
        .line-numbers {
            color: #75715e;
            text-align: right;
            padding: 12px 8px 12px 12px;
            border-right: 1px solid #444;
            vertical-align: top;
            user-select: none;
            background-color: #1e1e1e;
            width: 40px;
        }
        
        .code-content {
            padding: 0;
            vertical-align: top;
            width: 100%;
        }
        
        .code-content pre {
            margin: 0;
            padding: 12px;
            background-color: #2b2b2b;
            overflow-x: auto;
            line-height: 1.5;
        }
    </style>
    </head>
    <body>
    """
        ]

        # Render each message
        for msg in self._messages:
            msg_type = msg["type"]
            content = msg["content"]
            timestamp = msg.get("timestamp", "")

            if msg_type == "user":
                html_parts.append(
                    f'<p><span class="timestamp">[{timestamp}]</span>'
                    f'<span class="user">You: {escape(content)}</span></p>'
                )

            elif msg_type == "system":
                html_parts.append(
                    f'<p><span class="timestamp">[{timestamp}]</span>'
                    f'<span class="system">{escape(content)}</span></p>'
                )

            elif msg_type == "agent":
                html_parts.append(
                    f'<p><span class="timestamp">[{timestamp}]</span>'
                    f'<span class="agent">Agent: {escape(content)}</span></p>'
                )

            elif msg_type == "warning":
                html_parts.append(
                    f'<p><span class="timestamp">[{timestamp}]</span>'
                    f'<span class="warning">⚠️  {escape(content)}</span></p>'
                )

            elif msg_type == "separator":
                html_parts.append(
                    f'<div class="separator">━━━ {escape(content)} ━━━</div>'
                )

            elif msg_type == "code":
                block_id = msg["block_id"]
                block_number = msg.get("number", "")
                code_html = self._format_code_block(content, block_id, block_number)
                html_parts.append(code_html)

            elif msg_type == "text":
                # Plain text fallback
                html_parts.append(f"<p>{escape(content)}</p>")

        html_parts.append("</body></html>")

        # Save scroll position
        scrollbar = self.output_text.verticalScrollBar()
        old_scroll = scrollbar.value()
        was_at_bottom = old_scroll >= scrollbar.maximum() - 10

        # Update HTML
        self.output_text.setHtml("".join(html_parts))

        # Restore scroll position intelligently
        if was_at_bottom:
            # Stay at bottom for new messages
            scrollbar.setValue(scrollbar.maximum())
        else:
            # Maintain scroll position when toggling
            scrollbar.setValue(old_scroll)

    def _init_bridge(self):
        """Initialize OpenCodeBridge (lazy)."""
        try:
            from ami.flowchart.graph_builder import OpenCodeBridge

            self.bridge = OpenCodeBridge()
            self._append_message("system", "[System] OpenCode bridge initialized")
        except Exception as e:
            self._append_message(
                "system", f"[System] Warning: Could not initialize OpenCode: {e}"
            )
            self._append_message("system", "[System] AI features will not be available")

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
        self._append_message("user", user_input)

        # Check if bridge is available
        if self.bridge is None:
            self._append_message("system", "[Error] OpenCode bridge not available")
            return

        # Get graph state (INSTANT - direct access, same process)
        try:
            from ami.flowchart.graph_builder import get_graph_state

            state = get_graph_state(self.ctrl.amicli)
        except Exception as e:
            self._append_message("system", f"[Error] Could not get graph state: {e}")
            return

        # Build full prompt with context
        prompt = self._build_prompt(user_input, state)

        # Display status
        self._append_message("system", "[System] Sending request to agent...")

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
        self._append_message("system", "[System] Response received, processing...")

        # Show agent's conversational text first
        self._show_agent_text(response_str)

        # Extract code from response
        codes = self._extract_code(response_str)

        if codes:
            self._append_message("system", f"[System] Found {len(codes)} code block(s)")

            # Display and execute each code block
            for i, code in enumerate(codes, 1):
                self._append_code_block(code, i)

                # Auto-execute (emit signal for thread-safe execution)
                self.execute_code_signal.emit(code)
        else:
            # No code found - agent might have just answered with text
            self._append_message("system", "[System] No code to execute")

    @Slot(str)
    def _on_error_occurred(self, error_msg):
        """
        Handle error from background worker.

        Args:
            error_msg: Error message string
        """
        self._append_message("system", f"[Error] {error_msg}")

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

                                    # Show separator only if there's content
                                    if (
                                        "explanation" in response
                                        or "warnings" in response
                                    ):
                                        self._append_message(
                                            "separator", "Agent's Response"
                                        )

                                    # Show explanation if provided
                                    if "explanation" in response:
                                        self._append_message(
                                            "agent", response["explanation"]
                                        )

                                    # Show warnings if provided
                                    if "warnings" in response:
                                        for warning in response["warnings"]:
                                            self._append_message("warning", warning)

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

                        # Skip if this text contains any code block (shown separately via collapsible blocks)
                        if "```" in text:
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
            self._append_message("system", "[System] Executing code...")

            # Build execution namespace
            # self.ctrl is FlowchartCtrlWidget, which has .chart (Flowchart) and .amicli
            import numpy as np
            import pyqtgraph as pg

            namespace = {
                "chart": self.ctrl.chart,
                "graph": self.ctrl.chart._graph,
                "amicli": self.ctrl.amicli if hasattr(self.ctrl, "amicli") else None,
                "np": np,
                "pg": pg,
            }

            exec(code, namespace)

            self._append_message("system", "[System] ✅ Execution successful!")

        except Exception as e:
            error_msg = f"[Execution Error] {e}\n{traceback.format_exc()}"
            self._append_message("system", error_msg)

    def _append_output(self, text):
        """
        Append plain text output (backward compatibility wrapper).

        Args:
            text: Text to append
        """
        self._append_message("text", text)

        # Auto-scroll is now handled by _render_messages()
        # Keeping this method for backward compatibility with any remaining calls

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
