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
import logging
import re
import traceback
from datetime import datetime
from html import escape

# Setup logger for chat widget
logger = logging.getLogger(__name__)

# Try to import markdown library
try:
    import markdown

    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False
    logger.warning("markdown library not available - agent text will be plain")
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

        # Retry loop state
        self._retry_iteration = 0  # Current retry iteration
        self._max_retries = 3  # Maximum retry attempts
        self._original_user_input = None  # Original user request
        self._current_response_data = None  # Parsed response data for retry

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

    def _markdown_to_html(self, text):
        """
        Convert markdown text to HTML.

        Supports:
        - **bold**, *italic*
        - `inline code`
        - Lists (bullet and numbered)
        - ## Headings
        - Links [text](url)
        - Tables

        Args:
            text: Markdown-formatted text

        Returns:
            HTML string
        """
        if not HAS_MARKDOWN:
            # Fallback: escape HTML and preserve line breaks
            html = escape(text)
            html = html.replace("\n", "<br>")
            return html

        # Convert markdown to HTML
        html = markdown.markdown(
            text,
            extensions=[
                "fenced_code",  # Support ```code blocks```
                "nl2br",  # Convert \n to <br>
                "tables",  # Support | tables |
                "sane_lists",  # Better list handling
            ],
        )

        return html

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
        
        /* Agent formatted text (markdown rendered) */
        .agent_formatted {
            color: #2E7D32;
            margin: 8px 0;
            line-height: 1.7;
        }
        
        .agent_formatted strong {
            color: #1B5E20;
            font-weight: 700;
        }
        
        .agent_formatted em {
            font-style: italic;
        }
        
        .agent_formatted code {
            background-color: #E8F5E9;
            padding: 2px 5px;
            border-radius: 3px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            color: #1B5E20;
            border: 1px solid #C8E6C9;
        }
        
        .agent_formatted ul, .agent_formatted ol {
            margin: 6px 0;
            padding-left: 24px;
        }
        
        .agent_formatted li {
            margin: 3px 0;
        }
        
        .agent_formatted h1, .agent_formatted h2, .agent_formatted h3 {
            color: #1B5E20;
            font-weight: 600;
            margin: 10px 0 6px 0;
        }
        
        .agent_formatted h1 { font-size: 16px; }
        .agent_formatted h2 { font-size: 15px; }
        .agent_formatted h3 { font-size: 14px; }
        
        .agent_formatted p {
            margin: 6px 0;
        }
        
        .agent_formatted a {
            color: #1976D2;
            text-decoration: underline;
        }
        
        .agent_formatted a:hover {
            color: #1565C0;
        }
        
        .agent_formatted table {
            border-collapse: collapse;
            margin: 8px 0;
            font-size: 12px;
        }
        
        .agent_formatted th {
            background-color: #E8F5E9;
            padding: 6px 10px;
            border: 1px solid #C8E6C9;
            font-weight: 600;
        }
        
        .agent_formatted td {
            padding: 6px 10px;
            border: 1px solid #E0E0E0;
        }
        
        .agent_formatted_label {
            color: #388E3C;
            font-weight: 600;
            margin-right: 6px;
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

            elif msg_type == "agent_formatted":
                # Render markdown-formatted agent text
                label = msg.get(
                    "label", ""
                )  # Optional "Agent:" label for first segment

                if label:
                    html_parts.append(
                        f'<p><span class="timestamp">[{timestamp}]</span>'
                        f'<span class="agent_formatted_label">{escape(label)}</span>'
                        f'<span class="agent_formatted">{content}</span></p>'
                    )
                else:
                    html_parts.append(
                        f'<p><span class="agent_formatted">{content}</span></p>'
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

        # Reset retry state for new user request
        self._retry_iteration = 0
        self._original_user_input = user_input

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
        # Format available sources with types
        sources = state.get("available_sources", [])
        source_library = (
            self.ctrl.chart.source_library
            if hasattr(self.ctrl.chart, "source_library")
            else None
        )

        if source_library and sources:
            # Get types for each source and format with abbreviated unions
            sources_with_types = []
            for source_name in sources:
                try:
                    source_type = source_library.getSourceType(source_name)
                    # Format type: Union[A, B] → A|B
                    type_str = (
                        str(source_type.__name__)
                        if hasattr(source_type, "__name__")
                        else str(source_type)
                    )
                    # Abbreviate Union syntax for readability
                    if type_str.startswith("Union["):
                        type_str = type_str[6:-1].replace(
                            ", ", "|"
                        )  # Union[A, B] → A|B
                    sources_with_types.append(f"{source_name} ({type_str})")
                except (KeyError, AttributeError):
                    # Type not available - use Any to indicate accepts anything
                    sources_with_types.append(f"{source_name} (Any)")

            sources_str = ", ".join(sources_with_types)
        else:
            # Fallback if no source library available
            sources_str = ", ".join(sources)

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
        Handle agent response with automatic retry on errors (runs on Qt main thread).

        Args:
            response_str: String with newline-separated JSON events from agent
        """
        self._append_message("system", "[System] Response received, processing...")

        # Show agent's conversational text first
        logger.debug(f"Response received: {len(response_str)} characters")
        logger.debug(f"Response preview: {response_str[:500]}")
        self._show_agent_text(response_str)

        # Extract code and response data from response
        codes, response_data = self._extract_code_with_data(response_str)

        if codes:
            self._append_message("system", f"[System] Found {len(codes)} code block(s)")

            # Display and execute each code block with retry logic
            for i, code in enumerate(codes, 1):
                self._append_code_block(code, i)

                # Execute code and get result
                exec_result = self._execute_code(code)

                # Handle execution result
                if exec_result["status"] == "success":
                    # Success - show next_steps if provided
                    self._handle_success(response_data, exec_result)
                    # Reset retry counter
                    self._retry_iteration = 0
                else:
                    # Error - check if we should retry
                    self._handle_error_with_retry(exec_result, response_data)
        else:
            # No code found - log diagnostics and inform user
            self._handle_no_code_response(response_str)
            # Reset retry counter
            self._retry_iteration = 0

    def _handle_no_code_response(self, response_str):
        """
        Handle responses without executable code.
        Logs diagnostics to terminal without cluttering UI.

        Args:
            response_str: Raw response string from agent
        """
        # Count events and analyze response content
        event_count = 0
        text_event_count = 0
        text_with_code_blocks = 0
        text_without_code = 0

        for line in response_str.split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                event_count += 1

                if event.get("type") == "text":
                    text_event_count += 1
                    text = event.get("part", {}).get("text", "")

                    if "```" in text:
                        text_with_code_blocks += 1
                    elif text.strip():
                        text_without_code += 1

            except json.JSONDecodeError:
                continue

        # Log analysis to terminal
        logger.debug(f"No code to execute - Response analysis:")
        logger.debug(f"  Total events: {event_count}")
        logger.debug(f"  Text events: {text_event_count}")
        logger.debug(f"  Text with code blocks: {text_with_code_blocks}")
        logger.debug(f"  Text without code: {text_without_code}")

        # Warn if truly empty (unusual case)
        if event_count == 0:
            logger.warning("Agent returned completely empty response (0 events)")
            self._append_message("warning", "⚠️  Agent returned empty response")
        elif text_event_count == 0:
            logger.warning(
                f"Agent response had {event_count} events but no text content"
            )
            self._append_message("warning", "⚠️  Agent response contained no text")
        else:
            # Normal case - agent answered with text only
            logger.info(f"Agent responded with text explanation (no executable code)")
            self._append_message(
                "system",
                "[System] Agent responded with explanation (no code generated)",
            )

    @Slot(str)
    def _on_error_occurred(self, error_msg):
        """
        Handle error from background worker.

        Args:
            error_msg: Error message string
        """
        self._append_message("system", f"[Error] {error_msg}")

    def _handle_success(self, response_data, exec_result):
        """
        Handle successful code execution.

        Args:
            response_data: Parsed agent response dict
            exec_result: Execution result dict
        """
        # Show captured output if any
        if exec_result.get("output"):
            output = exec_result["output"].strip()
            if output:
                self._append_message("output", output)

        # Show next_steps if provided
        next_steps = response_data.get("next_steps", [])
        if next_steps:
            steps_text = "**Next steps:**\n" + "\n".join(
                f"- {step}" for step in next_steps
            )
            self._append_message("agent", steps_text)

    def _handle_error_with_retry(self, exec_result, response_data):
        """
        Handle execution error and potentially retry.

        Args:
            exec_result: Execution result dict with error info
            response_data: Parsed agent response dict
        """
        # Increment retry counter
        self._retry_iteration += 1

        # Check if we should retry
        if self._retry_iteration < self._max_retries:
            # Build retry prompt
            retry_prompt = self._build_retry_prompt(exec_result, response_data)

            # Send retry request to agent
            self._append_message(
                "system",
                f"[System] Retry attempt {self._retry_iteration + 1}/{self._max_retries}...",
            )

            # Get graph state for retry
            try:
                from ami.flowchart.graph_builder import get_graph_state

                state = get_graph_state(self.ctrl.amicli)
            except Exception as e:
                self._append_message(
                    "system", f"[Error] Could not get graph state: {e}"
                )
                self._retry_iteration = 0
                return

            # Build full prompt with context
            full_prompt = self._build_prompt(retry_prompt, state)

            # Launch background worker for retry (NON-BLOCKING)
            self.current_worker = ChatWorker(self.bridge, full_prompt)
            self.current_worker.response_received.connect(self._on_response_received)
            self.current_worker.error_occurred.connect(self._on_error_occurred)
            self.current_worker.start()
        else:
            # Max retries reached
            self._append_message(
                "system",
                f"⚠️ Maximum retry attempts ({self._max_retries}) reached. "
                f"Unable to resolve the error automatically.",
            )
            self._retry_iteration = 0

    def _build_retry_prompt(self, exec_result, response_data):
        """
        Build retry prompt for agent with error details.

        Args:
            exec_result: Execution result dict with error info
            response_data: Original agent response dict

        Returns:
            str: Retry prompt
        """
        prompt = (
            f"Your code failed with the following error:\n\n"
            f"**Error Type:** {exec_result['error_type']}\n"
            f"**Error Message:** {exec_result['error']}\n\n"
            f"**Traceback:**\n```\n{exec_result['traceback']}\n```\n\n"
            f"Please analyze the error and generate corrected code. "
            f"Common issues:\n"
            f"- Wrong terminal names (ScatterPlot uses 'X'/'Y', not 'In'/'In.1')\n"
            f"- Binning uses 'Bins' output, not 'XBins' (only Binning2D has XBins/YBins)\n"
            f"- Source node doesn't exist (check available sources)\n"
            f"- Missing .name() method when connecting nodes\n\n"
            f"This is attempt {self._retry_iteration + 2} of {self._max_retries}. "
            f"Generate corrected code in the same JSON format."
        )

        return prompt

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

    def _extract_code_with_data(self, response_str):
        """
        Extract executable code AND response data from agent response.

        Args:
            response_str: String with newline-separated JSON events from agent

        Returns:
            tuple: (codes_list, response_data_dict)
                codes_list: List of code strings
                response_data_dict: Parsed response with explanation, warnings, next_steps
        """
        codes = []
        response_data = {}

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
                                    # Return empty - no code to execute
                                    return ([], response)

                                # Extract code and metadata
                                if "code" in response:
                                    codes.append(response["code"])
                                    response_data = response

                                    # Only process the first (most recent) JSON block found
                                    if codes:
                                        return (codes, response_data)

                            except json.JSONDecodeError:
                                # Not valid JSON, skip
                                continue

                except json.JSONDecodeError:
                    # Skip lines that aren't valid JSON events
                    continue

        except Exception as e:
            self._append_output(f"[Warning] Code extraction error: {e}")

        return (codes, response_data)

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

                        # If text contains code blocks, extract text before/after them
                        if "```" in text:
                            # Split by triple backticks
                            parts = text.split("```")

                            # Parts at even indices (0, 2, 4...) are OUTSIDE code blocks
                            # Parts at odd indices (1, 3, 5...) are INSIDE code blocks
                            for i, part in enumerate(parts):
                                if (
                                    i % 2 == 0
                                ):  # Outside code block - this is explanatory text
                                    cleaned = part.strip()
                                    if cleaned:
                                        agent_texts.append(cleaned)
                                        logger.debug(
                                            f"Extracted text segment (before/after code): {len(cleaned)} chars"
                                        )
                            continue  # Already processed this event

                        # No code blocks - add text directly
                        if text.strip():
                            agent_texts.append(text)

                except json.JSONDecodeError:
                    continue

        except Exception as e:
            self._append_output(f"[Warning] Text display error: {e}")

        # Log how many text segments were extracted
        logger.debug(f"Extracted {len(agent_texts)} text segments from agent response")

        # If no text was extracted, log why
        if not agent_texts:
            # Count how many text events were skipped
            skipped_with_code = 0
            for line in response_str.split("\n"):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "text":
                        text = event.get("part", {}).get("text", "")
                        if "```" in text:
                            skipped_with_code += 1
                except json.JSONDecodeError:
                    continue

            if skipped_with_code > 0:
                logger.debug(
                    f"Skipped {skipped_with_code} text events containing code blocks"
                )

        # Display agent text if any was found
        if agent_texts:
            # First text segment gets "Agent:" prefix
            for i, text in enumerate(agent_texts):
                # Convert markdown to HTML
                formatted_html = self._markdown_to_html(text)

                # First segment includes "Agent:" label
                if i == 0:
                    self._append_message(
                        "agent_formatted", formatted_html, label="Agent:"
                    )
                else:
                    self._append_message("agent_formatted", formatted_html)

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

        Returns:
            dict: Execution result with keys:
                - status: 'success' or 'error'
                - output: captured stdout (on success)
                - error: error message (on error)
                - error_type: exception class name (on error)
                - traceback: full traceback string (on error)
        """
        import sys
        import io

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()

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

            # Success - get captured output
            output = captured_output.getvalue()

            self._append_message("system", "[System] ✅ Execution successful!")

            return {"status": "success", "output": output}

        except Exception as e:
            error_msg = f"[Execution Error] {e}\n{traceback.format_exc()}"
            self._append_message("system", error_msg)

            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }

        finally:
            # Restore stdout
            sys.stdout = old_stdout

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
