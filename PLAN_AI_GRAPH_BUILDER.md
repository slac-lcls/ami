# AI-Assisted Graph Building for AMI - Implementation Status

## Current Status: ✅ PHASES 1-3 COMPLETE, IMPROVEMENTS NEEDED

Build an AI-assisted graph building system for AMI that enables users to construct analysis graphs using natural language commands via an IPython magic command (`%build_graph`). The system includes a "View Source" feature to see Python code equivalent of graphs and export them as reusable templates.

**Implementation Date:** March 30, 2026  
**Branch:** `feature/ai-graph-builder`  
**Status:** Functional but needs improvements (agent hallucinating nodes)

**Key Design Principles:**
- Use existing Flowchart API wherever possible
- Minimal wrappers only where they genuinely simplify
- User-generated templates from real graphs
- Data-driven documentation based on actual usage

**Total Effort:** ~20 hours (completed in 1 session)

---

## Phase 1: GUI Console Enhancement

**Effort:** 2-3 hours  
**Goal:** Extend AmiCli with minimal strategic helpers

### 1.1 AmiCli Helper Methods

**File:** `ami/flowchart/Flowchart.py` (around line 1029)

Add to `AmiCli` class:

```python
class AmiCli():
    def __init__(self, ctrl, chartWidget, chart, graph, graphCommHandler):
        self.ctrl = ctrl
        self.chartWidget = chartWidget
        self.chart = chart
        self.graph = graph
        self.graphCommHandler = graphCommHandler
    
    def connect_nodes(self, src, src_term, dst, dst_term):
        """Connect two nodes by name (string-based helper)"""
        if isinstance(src, str):
            src = self.graph.nodes[src]['node']
        if isinstance(dst, str):
            dst = self.graph.nodes[dst]['node']
        src.terminals[src_term].connectTo(dst.terminals[dst_term])
    
    def disconnect_nodes(self, src, src_term, dst, dst_term):
        """Disconnect two nodes by name"""
        if isinstance(src, str):
            src = self.graph.nodes[src]['node']
        if isinstance(dst, str):
            dst = self.graph.nodes[dst]['node']
        src.terminals[src_term].disconnectFrom(dst.terminals[dst_term])
    
    def build_from_spec(self, spec):
        """
        Build multiple nodes and connections from specification.
        
        spec = {
            'nodes': [(type, name), ...],
            'connections': [(src, src_term, dst, dst_term), ...],
            'config': {node_name: {param: value}, ...}
        }
        """
        created_nodes = {}
        
        for node_type, node_name in spec.get('nodes', []):
            node = self.chart.createNode(node_type, node_name)
            created_nodes[node_name] = node
        
        for src, src_term, dst, dst_term in spec.get('connections', []):
            self.connect_nodes(src, src_term, dst, dst_term)
        
        for node_name, params in spec.get('config', {}).items():
            node = self.graph.nodes[node_name]['node']
            if hasattr(node, 'values'):
                node.values.update(params)
                if hasattr(node, 'sigStateChanged'):
                    node.sigStateChanged.emit(node)
        
        return list(created_nodes.values())
    
    def node_info(self, name):
        """Get node details including connections"""
        node = self.graph.nodes[name]['node']
        connections_in = []
        connections_out = []
        
        for term_name, term in node.terminals.items():
            for conn in term.connections():
                if term._io == 'in':
                    connections_in.append(
                        (conn.node().name(), conn.name(), term_name)
                    )
                else:
                    connections_out.append(
                        (term_name, conn.node().name(), conn.name())
                    )
        
        return {
            'type': node.__class__.__name__,
            'terminals': {name: t._io for name, t in node.terminals.items()},
            'values': getattr(node, 'values', {}),
            'connections_in': connections_in,
            'connections_out': connections_out
        }
```

### 1.2 Namespace Setup

**File:** `ami/flowchart/Flowchart.py` (around line 1053)

```python
from ami.flowchart.library.common import SourceNode

kernel.shell.push({
    'amicli': self.amicli,
    'chart': self.chart,              # Flowchart (has .source_library, .createNode())
    'graph': self.chart._graph,       # NetworkX graph
    'LIBRARY': LIBRARY,               # Node types
    'SourceNode': SourceNode,         # For source creation
    'np': np,
    'pg': pg
})
```

### 1.3 Register Magic Command

```python
from ami.flowchart.graph_builder import register_graph_builder_magic
register_graph_builder_magic(kernel.shell, self.amicli)
```

---

## Phase 2: Magic Command & Graph Builder

**Effort:** 4-6 hours (UPDATED: includes server management)  
**Goal:** Create IPython magic command with AI agent integration via dedicated OpenCode server

### 2.1 Create graph_builder.py

**File:** `ami/flowchart/graph_builder.py` (NEW)

Key components:
- `OpenCodeBridge` class - Manages long-running OpenCode server
- `register_graph_builder_magic()` - Register `%build_graph` and `%bg` commands
- `get_graph_state()` - Extract current graph state for agent context
- `invoke_agent_for_graph_building()` - Call AI agent via server with prompt
- `build_agent_prompt()` - Generate comprehensive prompt with API docs
- `extract_code_from_response()` - Parse agent response for executable code
- `get_current_graph_source()` - Get Python source for current graph (for agent)

### 2.2 OpenCode Server Management & Agent Invocation

**Architecture:** Start dedicated `opencode serve` when AMI GUI launches, communicate via `opencode run --attach` for fast requests (~200ms) with session continuity.

#### 2.2.1 OpenCodeBridge Class

**File:** `ami/flowchart/graph_builder.py`

```python
import subprocess
import json
import time
import re
import os

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
        self.server = subprocess.Popen(
            ['opencode', 'serve', '--port', '0'],  # 0 = random port
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for server URL (printed to stderr)
        self.url = self._wait_for_url()
    
    def _wait_for_url(self, timeout=10):
        """
        Extract server URL from startup output.
        OpenCode prints "Server listening on http://localhost:XXXX" to stderr.
        """
        import select
        start = time.time()
        
        while time.time() - start < timeout:
            # Non-blocking read from stderr
            if select.select([self.server.stderr], [], [], 0.1)[0]:
                line = self.server.stderr.readline()
                match = re.search(r'http://[^\s]+', line)
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
        # Check if server is still alive
        if self.server.poll() is not None:
            self.start_server()
            self.session_id = None  # Reset session
        
        cmd = [
            'opencode', 'run',
            '--attach', self.url,
            '--agent', 'ami-graph-builder',
            '--format', 'json',
            '--dir', os.getcwd(),
        ]
        
        # Continue session if we have one (enables conversation history)
        if self.session_id:
            cmd += ['--session', self.session_id]
        
        cmd.append(prompt)
        
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout
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
        for line in output.split('\n'):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if 'sessionID' in event:
                    return event['sessionID']
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
```

#### 2.2.2 Integration with FlowchartCtrlWidget

**File:** `ami/flowchart/Flowchart.py` (around line 1053, after IPython kernel setup)

```python
# Start OpenCode graph builder server
from ami.flowchart.graph_builder import OpenCodeBridge
self.graph_builder = OpenCodeBridge()

# Register cleanup on exit
import atexit
atexit.register(self.graph_builder.close)

# Pass to magic command registration
from ami.flowchart.graph_builder import register_graph_builder_magic
register_graph_builder_magic(kernel.shell, self.amicli, self.graph_builder)
```

#### 2.2.3 Agent Invocation Function

**File:** `ami/flowchart/graph_builder.py`

```python
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
```

#### 2.2.4 Response Parsing (Structured JSON)

**File:** `ami/flowchart/graph_builder.py`

Agent is instructed (via Phase 3 SKILL.md) to return structured JSON response:

```json
{
  "explanation": "Brief description of what the code does",
  "code": "executable Python code as string (may contain \\n)",
  "warnings": ["optional list of warnings"],
  "next_steps": ["optional list of suggestions"]
}
```

**Extraction code:**

```python
def extract_code_from_response(json_output):
    """
    Parse JSON events to extract structured response.
    
    Agent returns final response as JSON code block:
    ```json
    {
      "explanation": "Creates scatter plot for X vs Y",
      "code": "scatter = chart.createNode('ScatterPlot', 'my_plot')",
      "warnings": ["Ensure sources exist"],
      "next_steps": ["Configure axis labels"]
    }
    ```
    
    Returns: Python code as string
    """
    import re
    
    # Parse events in reverse (agent's final response is at the end)
    for line in reversed(json_output.split('\n')):
        if not line.strip():
            continue
        
        try:
            event = json.loads(line)
            
            if event.get('type') == 'text':
                text = event.get('part', {}).get('text', '')
                
                # Look for JSON code block in final message
                match = re.search(r'```json\n(.*?)```', text, re.DOTALL)
                if match:
                    response = json.loads(match.group(1))
                    
                    # Print explanation to console
                    if 'explanation' in response:
                        print(f"[Graph Builder] {response['explanation']}")
                    
                    # Print warnings to console
                    if 'warnings' in response:
                        for warning in response['warnings']:
                            print(f"[Graph Builder] ⚠️  {warning}")
                    
                    # Print next steps to console
                    if 'next_steps' in response:
                        print(f"[Graph Builder] Next steps:")
                        for step in response['next_steps']:
                            print(f"  - {step}")
                    
                    return response.get('code', '')
        
        except (json.JSONDecodeError, KeyError):
            continue
    
    raise ValueError("No structured JSON response found in agent output")
```

**Benefits of structured response:**
- ✅ Robust parsing (no regex for code blocks)
- ✅ Clear separation of explanation vs code
- ✅ User feedback via warnings/next_steps
- ✅ Easy to validate and extend
- ✅ Single source of truth for code

#### 2.2.5 Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| First request | 2-3s | Server startup time |
| Subsequent requests | ~200ms | No startup overhead |
| Session continuity | ✓ | Agent remembers context |
| Auto-recovery | ✓ | Restarts on crash |
| Memory overhead | ~100MB | Running server |

### 2.3 Graph State Extraction

Uses NetworkX efficiently:
```python
def get_graph_state(amicli):
    """
    Extract current graph state for agent context.
    
    Returns dict with:
    - nodes: list of {name, type, params}
    - sources: list of source names
    - connections: list of {from, to, terminals}
    - available_sources: list of detectors/PVs
    """
    # Use chart.nodes(data='node') and graph.edges(data=True)
    # Extract: node types, source nodes, connections
    # Query: source_library.sourceList, graphCommHandler.sources
    # Query: graphCommHandler.features
```

### 2.4 Agent Prompt Structure

**Includes:**
- User request
- Current graph state (nodes, sources, connections)
- Available API (with examples)
- Source discovery methods
- Node types available
- **Required response format** (structured JSON)
- Example outputs

**Response Format Requirement:**

Agent must return structured JSON in final message:
```json
{
  "explanation": "Description of what code does",
  "code": "executable Python code",
  "warnings": ["optional warnings"],
  "next_steps": ["optional suggestions"]
}
```

**Execution:** 
1. Extract `code` from JSON response
2. Print `explanation`, `warnings`, `next_steps` to console
3. Execute code via `ipython_shell.ex(code)` with error handling

---

## Phase 2.5: View Source Feature

**Effort:** 4-6 hours  
**Goal:** GUI button to view/export Python code for current graph

### 2.5.1 Source Code Generator

**File:** `ami/flowchart/Flowchart.py` (Flowchart class)

```python
def generateSourceCode(self):
    """Generate Python code that recreates current graph"""
    # Header with timestamp
    # Import SourceNode
    # Create source nodes (with sanitized names)
    # Create processing nodes
    # Configure parameters (from node.values)
    # Connect nodes
    # Return Python code as string
```

**Key requirement:** Sanitize node/source names for valid Python variables:
```python
def sanitize_name(name):
    """Convert to valid Python variable"""
    sanitized = name.replace(':', '_').replace('.', '_').replace('-', '_')
    if sanitized[0].isdigit():
        sanitized = 'node_' + sanitized
    return sanitized
```

### 2.5.2 Add Toolbar Button

**File:** `ami/flowchart/Editor.py` (around line 250)

```python
self.actionViewSource = QtWidgets.QAction(parent)
self.actionViewSource.setIconText("View Source")
self.toolBar.addAction(self.actionViewSource)
```

**File:** `ami/flowchart/Flowchart.py` (FlowchartCtrlWidget, around line 780)

```python
self.ui.actionViewSource.triggered.connect(self.viewSourceClicked)
```

### 2.5.3 Source View Window

**File:** `ami/flowchart/Flowchart.py` (FlowchartCtrlWidget class)

Create `viewSourceClicked()` method that:
- Generates source code via `chart.generateSourceCode()`
- Opens Qt window with read-only text display
- Provides buttons:
  - **Copy to Clipboard** - Copy code to clipboard
  - **Export as Script...** - Save as .py file
  - **Export as Template...** - Save as parameterized template
  - **Close**

### 2.5.4 Template Export (Option A)

**Implementation:** `generateTemplate()` method

Wraps source code in function with:
- Template name (from user input dialog)
- Description (from user input dialog)
- TODO comments for parameterization
- Timestamp and metadata
- Function wrapper with indented source code
- Example usage comment

Generated format:
```python
# AMI Graph Template: template_name
"""
User description here

Auto-generated template from AMI graph
Created: 2026-03-30 HH:MM:SS
"""

def template_name_template():
    """
    User description
    
    TODO: Add parameters for customization:
    - Source names
    - Node names  
    - ROI dimensions
    - etc.
    """
    
    # [Indented source code from generateSourceCode()]

# Example usage:
# template_name_template()
```

**Future Enhancement (Option B):** Interactive dialog to define parameters before export

---

## Phase 3: AI Agent Skill

**Effort:** 9-13 hours (REDUCED from 20-25 hours)  
**Goal:** Create ami-graph-builder skill with data-driven documentation

### 3.1 Directory Structure

```
/sdf/group/lcls/ds/dm/apps/dev/opencode/skills/ami-graph-builder/
├── SKILL.md                      # Main agent instructions (~300 lines)
├── references/
│   ├── nodes_display.md          # Top 7 display nodes
│   ├── nodes_processing.md       # Top 5 processing nodes (Sum, Projection, Binning, Average, Calculator)
│   ├── nodes_roi.md              # ROI nodes
│   ├── nodes_statistics.md       # MeanVsScan, StatsVsScan
│   ├── nodes_control.md          # Filter, PythonEditor (with usage guidance)
│   └── graph_patterns.md         # 5 core patterns
├── templates/
│   ├── simple_correlation.py     # From simple_correlation_2.fc
│   ├── pump_probe.py             # From complex_example.fc
│   ├── roi_analysis.py           # Manual
│   ├── waveform_analysis.py      # From run22.fc
│   └── scan_analysis.py          # From LODCM_rocking_curve.fc
└── user_templates/               # User contributions via Export
    └── README.md                 # How to contribute templates
```

### 3.2 Critical Nodes to Document (16 nodes, data-driven)

**Based on actual .fc file usage:**

**Display (7):**
1. ScatterPlot ⭐⭐⭐⭐⭐ (5 occurrences)
2. ScalarPlot ⭐⭐⭐⭐ (4 occurrences)
3. LinePlot ⭐⭐⭐⭐ (4 occurrences)
4. WaveformViewer ⭐⭐ (2 occurrences)
5. ImageViewer ⭐
6. ScalarViewer ⭐
7. Histogram ⭐

**Processing (5):**
8. Sum ⭐⭐⭐ (3 occurrences)
9. Projection ⭐
10. Binning ⭐
11. Average (commonly used)
12. Calculator (for simple math expressions)

**ROI (1):**
13. Roi2D ⭐

**Statistics (2):**
14. MeanVsScan ⭐⭐⭐⭐ (4 occurrences)
15. StatsVsScan (document with MeanVsScan)

**Control/Custom (2):**
16. Filter ⭐⭐ (2 occurrences)
17. **PythonEditor ⭐⭐** (2 occurrences) - For custom Python processing

### 3.3 Node Documentation Format (Hybrid)

```markdown
## NodeName - Brief Description

**Purpose:** What it does

**Terminals:** Input → Output (with types)

**Key Parameters:** List main configurable parameters

**Common Use Cases:**
- Use case 1
- Use case 2

**Example:**
```python
node = chart.createNode('NodeName', 'my_node')
# Configure...
# Connect...
```

**See also:** Related templates
```

### 3.4 Core Graph Patterns (5 patterns from real .fc files)

1. **Simple Correlation** - Source → Source → ScatterPlot (X vs Y)
2. **Pump-Probe Analysis** - Detector → ROI → Sum → Filter → MeanVsScan
3. **ROI Analysis** - Detector → Roi2D → Sum → Viewer
4. **Waveform Analysis** - Source → PeakFinder → Projection → Plot
5. **Scan Analysis** - Sources → MeanVsScan → LinePlot

### 3.5 SKILL.md Structure

- Role and purpose
- Graph building workflow (structured narrative + examples)
- API quick reference
- Links to node categories
- Pattern guide (links to templates)
- Code generation guidelines
- **Handling custom processing requests** (Calculator vs PythonEditor)
- **Response format requirements** (structured JSON - see 3.5.1)
- Handling ambiguity
- Concrete examples

#### 3.5.1 Response Format Requirements (CRITICAL)

**Must include in SKILL.md:**

```markdown
## Response Format

CRITICAL: You MUST return your final response as a JSON object in a code block.

### Required Format

```json
{
  "explanation": "Brief description of what the code does",
  "code": "executable Python code as a string (use \\n for newlines)",
  "warnings": ["Optional: list of warnings about assumptions made"],
  "next_steps": ["Optional: list of suggestions for the user"]
}
```

### Field Descriptions

**Required fields:**
- `explanation` (string): 1-2 sentence description of what the code accomplishes
- `code` (string): Executable Python code using the AMI flowchart API
  - Use `chart.createNode(type, name)` to create nodes
  - Use `amicli.connect_nodes(src, src_term, dst, dst_term)` to connect
  - Include print statements for user feedback
  - May contain `\n` for multi-line code

**Optional fields:**
- `warnings` (list of strings): Assumptions or preconditions (e.g., "Assumes source 'laser' exists")
- `next_steps` (list of strings): Suggestions for what to do next (e.g., "Configure axis labels in GUI")

### Examples

**Example 1: Simple scatter plot**
```json
{
  "explanation": "Creates a scatter plot to correlate laser intensity with detector signal",
  "code": "print('Creating scatter plot...')\nscatter = chart.createNode('ScatterPlot', 'laser_vs_detector')\namicli.connect_nodes('laser_source', 'Out', 'scatter', 'In')\namicli.connect_nodes('detector_source', 'Out', 'scatter', 'In.1')\nprint('Scatter plot created! Configure axis labels in the GUI.')",
  "warnings": ["Assumes 'laser_source' and 'detector_source' nodes exist in the graph"],
  "next_steps": ["Set X and Y axis labels in the plot widget", "Adjust plot colors and markers"]
}
```

**Example 2: ROI analysis**
```json
{
  "explanation": "Creates ROI on detector image and computes sum within region",
  "code": "print('Creating ROI and sum nodes...')\nroi = chart.createNode('Roi2D', 'detector_roi')\nsum_node = chart.createNode('Sum', 'roi_sum')\namicli.connect_nodes('detector_source', 'Out', 'roi', 'In')\namicli.connect_nodes('roi', 'Out', 'sum_node', 'In')\nprint('ROI created! Draw the region in the detector viewer.')",
  "warnings": ["User must manually draw ROI rectangle in the detector image viewer"],
  "next_steps": ["Open detector viewer and draw ROI", "Connect roi_sum to a plot to visualize"]
}
```

### Validation

Before returning your response:
1. ✅ Check JSON is valid (no syntax errors)
2. ✅ `explanation` field is present and concise
3. ✅ `code` field contains executable Python
4. ✅ Code uses correct API: `chart.createNode()`, `amicli.connect_nodes()`
5. ✅ Code includes print statements for user feedback
6. ✅ If assumptions made, include in `warnings`
```

### 3.6 PythonEditor Node Documentation

**Purpose:** Enable custom Python processing when standard nodes don't fit

**In `references/nodes_control.md`:**

```markdown
## PythonEditor - Custom Python Processing

**Purpose:** Write custom Python code to process events when standard nodes don't provide needed functionality

**Terminals:** Dynamic (user adds inputs/outputs via GUI)

**Key Features:**
- Write Python class with event processing methods
- Define inputs and outputs dynamically
- Access to full Python and NumPy
- Good for simple Map-style operations

**When to Use:**
- Custom mathematical operations not available in Calculator
- Conditional logic beyond what Filter provides
- Combining multiple operations in custom way
- Prototyping before creating a proper custom node

**Agent Creation Pattern:**
```python
print("Creating PythonEditor for custom processing...")
editor = chart.createNode('PythonEditor', 'custom_processor')
print("")
print("⚠️  User must configure the Python code in GUI:")
print("   1. Right-click node → 'Add Input' to define inputs")
print("   2. Right-click node → 'Add Output' to define outputs")
print("   3. Double-click node to open code editor")
print("   4. Implement the event() method")
print("")
print("Template structure:")
print("  class EventProcessor():")
print("      def event(self, input1, input2):")
print("          # Your processing code here")
print("          return output")
```

**Example Use Cases:**
- Apply custom calibration: `output = input * cal_factor + offset`
- Conditional processing: `if x > threshold: return process(x) else: return 0`
- Combine operations: `return np.sqrt(x**2 + y**2)`
- Load external data files for lookup tables

**Decision Tree for Custom Processing:**

1. **Simple math expression?** → Use **Calculator** node
2. **Basic filtering/conditions?** → Use **Filter** node  
3. **Custom Python logic needed?** → Use **PythonEditor** node

**Agent should prefer Calculator when possible, use PythonEditor only when necessary.**
```

### 3.7 Handling Custom Processing Requests (in SKILL.md)

**Add section to agent instructions:**

```markdown
## Handling Requests for Custom Processing

When user requests custom logic not available in standard nodes:

**Decision Tree:**

1. **Can Calculator do it?** (simple math expressions like `x * 2 + 5`)
   - YES → Create Calculator node, explain expression syntax
   - NO → Continue to step 2

2. **Can existing nodes be combined?** (e.g., Sum + Average)
   - YES → Build pipeline with existing nodes
   - NO → Continue to step 3

3. **Requires custom Python code?**
   - Create PythonEditor node
   - Explain that user must write the code in GUI
   - Provide template structure

**Example Scenarios:**

**Scenario 1:** "multiply ROI sum by 2.5 and add 10"
```python
# Use Calculator - simple expression
print("Creating Calculator node for: (roi_sum * 2.5) + 10")
calc = chart.createNode('Calculator', 'scaled_sum')
print("In Calculator GUI, enter expression: (In * 2.5) + 10")
amicli.connect_nodes('roi_sum', 'Out', 'scaled_sum', 'In')
```

**Scenario 2:** "apply custom calibration from a file"
```python
# Requires PythonEditor - external data
print("This requires loading external calibration data.")
print("Creating PythonEditor node...")
editor = chart.createNode('PythonEditor', 'calibration')
print("")
print("⚠️  Please configure in GUI:")
print("  1. Add input for raw values")
print("  2. Add output for calibrated values")
print("  3. Double-click to edit code")
print("  4. In __init__: load calibration file")
print("  5. In event(): apply calibration")
```

**Scenario 3:** "filter events where laser > 100 and detector < 50"
```python
# Use Filter - boolean conditions
print("Creating Filter node for: (laser > 100) AND (detector < 50)")
filter_node = chart.createNode('Filter', 'event_filter')
print("In Filter GUI, enter expression:")
print("  (laser > 100) & (detector < 50)")
amicli.connect_nodes('laser', 'Out', 'event_filter', 'In')
amicli.connect_nodes('detector', 'Out', 'event_filter', 'In.1')
```
```

### 3.8 Template Generation Workflow

**For initial 5 templates:**
1. Implement View Source feature
2. Load each reference .fc file in AMI GUI
3. Click "View Source"
4. Click "Export as Template"
5. Manually enhance with better parameter TODOs
6. Add to templates/ directory

**For user contributions:**
- Users create graphs in GUI
- Export as template
- Place in user_templates/ directory
- Agent can reference all templates

---

## Data-Driven Design Insights

### Analysis of Existing .fc Files

**Files analyzed:**
- `examples/complex_example.fc` - Pump-probe with 14 nodes
- `simple_correlation_2.fc` - Simple scatter with 3 nodes
- `tests/graphs/run22.fc` - Waveform analysis with 19 nodes
- `tests/graphs/LODCM_rocking_curve.fc` - Scan analysis with 15 nodes

**Most common node types (excluding SourceNode):**
1. ScatterPlot (5) - X vs Y correlation plots
2. ScalarPlot (4) - Time series plotting
3. MeanVsScan (4) - Binned statistics vs scan variable
4. LinePlot (4) - Line/profile plots
5. Sum (3) - Summation operations
6. Filter (2) - Conditional filtering
7. WaveformViewer (2) - 1D waveform display
8. PythonEditor (2) - Custom Python code nodes

**Common patterns identified:**
1. Simple correlation: 2 sources → ScatterPlot
2. Pump-probe: Detector → ROI → Sum → Filter → MeanVsScan + Laser → Filter → MeanVsScan
3. Waveform processing: Source → PeakFinder → Projection → Binning → Plot
4. Scan analysis: Multiple sources → PythonEditor → MeanVsScan → Plot

---

## Testing Strategy

### Phase 1 Tests
- [ ] Create node via `chart.createNode()`
- [ ] Connect via `amicli.connect_nodes()`
- [ ] Disconnect via `amicli.disconnect_nodes()`
- [ ] Build from spec with multiple nodes
- [ ] Query node info
- [ ] Verify namespace objects available

### Phase 2 Tests
- [ ] `%build_graph show cspad detector`
- [ ] `%build_graph add ROI and sum it`
- [ ] `%build_graph correlate laser with detector`
- [ ] Ambiguous request (should ask questions)
- [ ] Error handling (invalid node type)
- [ ] Agent can view source of built graph

### Phase 2.5 Tests
- [ ] View Source button shows code
- [ ] Copy to clipboard works
- [ ] Export as script saves .py file
- [ ] Export as template creates function wrapper
- [ ] Source code has valid Python syntax
- [ ] Source names sanitized correctly
- [ ] Can load .fc file and view source
- [ ] Re-execute generated code recreates graph

### Phase 3 Tests
- [ ] Agent references node documentation
- [ ] Agent uses template patterns
- [ ] Agent handles various requests correctly
- [ ] User-contributed templates work
- [ ] Documentation is accurate

---

## Success Criteria

- [ ] Users can build graphs with `%build_graph <description>`
- [ ] Agent correctly interprets 80%+ of common requests
- [ ] View Source shows valid, executable Python code
- [ ] Exported templates are reusable
- [ ] Documentation covers 15 most-used nodes
- [ ] 5 core patterns documented with templates
- [ ] System works without AI agent (graceful fallback)
- [ ] Graph modifications preserve state correctly

---

## Future Enhancements (Not in Initial Scope)

### 1. Phase 4: "Why Can't I See Data?" Diagnostics (deferred)

**Goal:** Help users diagnose why their plots/viewers show no data

**Status:** Deferred to post-launch (implement after Phases 1-3 based on user feedback)

**Estimated Effort:** 8-12 hours

**Magic Command:** `%why_no_data <node_name>` or `%wnd <node_name>`

**Requirements:**
- Graph must be actively running (requires live data)
- Uses `graphCommHandler.fetch()` for current feature values
- Uses info socket for event counts and rates
- Parses filter expressions using Python's `ast` module for boolean logic

**Diagnostic Capabilities (by priority tier):**

**Tier 1 - Must Have (Core Diagnostics):**
1. **Filter blocking all data**
   - Check if filter pass rate is 0%
   - Compare filter conditions with actual data ranges
   - Suggest adjusted filter thresholds

2. **Plot range mismatches**
   - Compare data value range vs plot axis range
   - Detect when data exists but falls outside visible plot area
   - Suggest enabling auto-scaling or adjusting axis ranges

3. **Mutually exclusive filters (cross-heartbeat correlation)**
   - Parse filter expressions in parallel branches
   - Detect conditions like `(laser > 100)` AND `(laser < 50)` on different paths
   - Identify when filters are mutually exclusive within single events
   - Suggest PickN/RollingBuffer nodes for latching across heartbeats

4. **ROI out of bounds**
   - Compare ROI coordinates vs detector image size
   - Detect when ROI rectangle is outside valid detector area
   - Suggest redrawing ROI within bounds

**Tier 2 - Should Have (High Value):**
5. **Slow/frozen graph performance**
   - Query Prometheus metrics for per-node processing time
   - Identify bottleneck nodes with low throughput
   - Check event rate at each node via info socket
   - Suggest adding filters or reducing data volume

6. **Missing expected sources**
   - List available sources from info socket (`topic == 'sources'`)
   - Fuzzy match user's source name against available sources
   - Suggest "Did you mean 'cspad_detector' instead of 'cspd_detector'?"

7. **Scan analysis issues**
   - Check if scan variable is actually changing
   - Show scan progress (collected N/M points)
   - Verify MeanVsScan/StatsVsScan nodes are receiving scan updates
   - Detect if waiting for more scan points

**Tier 3 - Nice to Have (Lower Priority):**
8. **Memory/performance warnings**
   - Query Prometheus metrics for memory usage
   - Warn if RollingBuffer consuming excessive memory
   - Detect large 2D arrays being passed unnecessarily
   - Suggest data reduction strategies (filters, ROIs, projections)

9. **Export issues**
   - Check if PvExport/ZMQ/UDPMcast nodes properly configured
   - Verify EPICS PV names are valid
   - Test export connectivity

10. **Intermittent data**
    - Monitor filter pass rate stability over time
    - Detect flaky sources dropping events
    - Identify timing issues with cross-heartbeat operations

**Implementation Approach:**

```python
def diagnose_no_data(node_name, amicli, bridge):
    """
    Diagnose why node shows no data.
    
    Steps:
    1. Trace graph backward from target node to sources
    2. Query live data at each node using graphCommHandler.fetch()
    3. Check event counts from info socket
    4. Run tier-based diagnostic checks
    5. Return structured diagnosis with suggestions
    """
    # Build prompt for agent with:
    # - Graph structure trace
    # - Live data from fetch()
    # - Event rate info
    # - Node configurations
    
    # Agent returns JSON diagnosis
    diagnosis = bridge.ask(prompt)
    
    # If auto-fix code provided, ask user confirmation
    if diagnosis.get('code'):
        if confirm("Apply suggested fix? [y/n]: "):
            exec(diagnosis['code'])
```

**Agent Response Format:**

```json
{
  "explanation": "Your scatter plot is empty because...",
  "diagnosis": {
    "target_node": "my_scatter_plot",
    "issue_type": "filter_blocking_all",
    "issue_node": "laser_filter",
    "data_path": ["laser_source", "laser_filter", "my_scatter_plot"],
    "details": "Filter condition 'laser > 1000' blocks all events. Laser values range from 0-150.",
    "live_data": {
      "laser_source.Out": {"current": 127.3, "events": 1000},
      "laser_filter.Out": {"current": null, "events": 0}
    }
  },
  "suggestions": [
    "Change filter condition to 'laser > 100'",
    "Check if laser units are correct (mJ vs J?)",
    "Temporarily disable filter to verify data flow"
  ],
  "code": "# Optional: Python code to fix issue (requires user approval)"
}
```

**Open Questions for Phase 4:**
- What Prometheus metrics are accessible from Python?
- What scan state information is available?
- Can we programmatically adjust plot axis ranges?
- Should diagnostics run continuously in background or on-demand only?

**Note:** Phase 4 diagnostic capabilities will be refined based on:
- User feedback from initial Phases 1-3 deployment
- Common support questions and pain points
- Available runtime introspection capabilities
- Prometheus metrics schema and accessibility

### 2. Phase 5: Graph Optimization Suggestions (deferred)

**Goal:** Suggest performance and structural improvements to existing graphs

**Status:** Deferred pending user demand and Phase 4 completion

**Estimated Effort:** 6-8 hours

**Magic Command:** `%optimize_graph` or `%og`

**Optimization Types:**
- **Performance:** Reorder operations (e.g., filter before expensive processing)
- **Simplification:** Combine redundant nodes, suggest more efficient node types
- **Best practices:** Use appropriate nodes for common patterns
- **Resource usage:** Reduce memory consumption, improve throughput

**Example Agent Response:**
```json
{
  "explanation": "Found 2 optimization opportunities",
  "optimizations": [
    {
      "priority": "high",
      "type": "reorder",
      "current_path": "detector → ROI → Filter → Sum",
      "suggested_path": "detector → Filter → ROI → Sum",
      "reason": "Filtering before ROI reduces data processed",
      "estimated_speedup": "2-3x for filtered events"
    }
  ],
  "code": "# Code to apply optimizations (requires user approval)"
}
```

### 3. Template Parameterization (Option B)
- Interactive dialog for parameter definition
- Auto-detect common parameters (source names, ROI sizes, etc.)
- User confirmation of detected parameters
- Generate proper function arguments instead of TODOs

### 4. Advanced View Source Features
- Live update as graph changes
- Editable code with re-execution
- Side-by-side graph and code view
- Syntax highlighting
- Diff view for changes

### 5. Extended Documentation
- Auto-generate docs from all 70+ nodes
- User-contributed pattern library
- Video tutorials and examples
- Interactive examples in documentation

### 6. Phase 6: Custom Node Generation (deferred)

**Goal:** Enable agent to generate custom node classes (not just PythonEditor scripts)

**Scope:**
- Agent generates Python file with custom node class
- Dynamic import and registration using existing LibraryEditor infrastructure
- Full uiTemplate support for GUI parameters
- Map and StatefulTransformation patterns
- Validation and testing of generated nodes

**What's involved:**
- Document graph node types (Map, StatefulTransformation, etc.)
- Document uiTemplate syntax comprehensively
- Provide templates for common patterns
- Agent generates `.py` file with node class
- Automatic import and registration via `LIBRARY.addNodeType()`

**Example capability:**
```
User: "create a reusable node that scales input by a configurable factor"

Agent:
1. Generates custom node class in Python file
2. Includes uiTemplate for scale_factor parameter
3. Implements to_operation() with Map
4. Loads and registers node
5. Node appears in library under "Custom" category
6. User can now use it like any built-in node
```

**Difference from PythonEditor:**
- **PythonEditor:** One-off custom processing, code in GUI
- **Custom Node:** Reusable node type, appears in library, professional integration

**Requirements:**
- `references/graph_node_types.md` - Map, StatefulTransformation, GlobalTransformation
- `references/uitemplates.md` - Comprehensive uiTemplate syntax
- `references/custom_nodes.md` - How to structure custom node classes
- `templates/custom_node_map.py` - Template for simple Map nodes
- `templates/custom_node_stateful.py` - Template for reduction nodes

**Estimated Effort:** 8-12 hours

**When to implement:** Based on user demand for creating reusable nodes vs one-off PythonEditor scripts

**Note:** Current implementation provides PythonEditor for simple custom processing. Phase 6 would enable creating proper reusable node types that integrate fully with AMI's library system.

---

## Implementation Order

**Week 1:**
1. **Day 1:** Phase 1 (2-3 hours) + Phase 2 start
2. **Day 2:** Phase 2 complete (3-4 hours total)
3. **Day 3:** Phase 2.5 complete (4-6 hours)

**Week 2:**
4. **Day 4-5:** Phase 3 - Generate templates from .fc files
5. **Day 5-6:** Phase 3 - Document 16 key nodes (including PythonEditor)
6. **Day 6-7:** Phase 3 - Write SKILL.md with custom processing guidance
7. **Day 7:** Testing and refinement

---

## Open Questions / Decisions Needed

1. **Icon for View Source button** - Which icon to use? (text editor icon?)
2. **Keyboard shortcut** - Should View Source have a hotkey? (Ctrl+Shift+V?)
3. **Phase 4 priority** - Implement adaptive mode or defer indefinitely?
4. **Template storage location** - Where should user_templates/ live? In ami repo or separate?
5. **Agent error recovery** - How should agent handle graph building failures?
6. **Source sanitization** - Edge cases for special characters in names?

---

## Architecture Decisions

### Why Minimal Wrappers?
- **Principle:** Use existing Flowchart API wherever possible
- **Only wrap when:** It genuinely simplifies common operations
- **Benefits:** Less code to maintain, users learn real API, more flexible

### Why View Source Instead of .fc Converter?
- **Single tool:** One feature does both (view + export)
- **Immediate feedback:** See code as you build in GUI
- **Learning tool:** Users understand Python API
- **No duplication:** Don't need separate converter script

### Why User-Generated Templates?
- **Real patterns:** Based on actual usage, not hypothetical
- **Community-driven:** Users share what works
- **Less upfront work:** Don't need to create all templates manually
- **Always current:** Reflects actual practices

### Why Data-Driven Node Documentation?
- **Focus effort:** Document what's actually used
- **Expand later:** Add more nodes based on demand
- **Practical:** Based on real .fc file analysis
- **Efficient:** 15 nodes vs 70+ nodes initially

---

## Key Design Decisions

### Custom Processing Strategy

**Decision:** Include PythonEditor, defer custom node generation to Phase 6

**Rationale:**
- PythonEditor is straightforward for simple custom Map operations
- Already appeared in real .fc files (2 occurrences)
- Users can write custom Python logic in GUI
- Simpler than teaching agent to generate entire node classes
- Custom node generation is powerful but complex - better as future enhancement

**What users get now:**
- Calculator node for simple expressions
- Filter node for boolean conditions
- PythonEditor for custom Python logic
- Agent helps create and connect these nodes

**What's deferred to Phase 6:**
- Agent-generated custom node classes
- Full uiTemplate generation
- Dynamic node registration
- Reusable custom nodes in library

**Benefits:**
- Keeps Phase 3 scope manageable (9-13 hours vs 17-25 hours)
- Users still have powerful customization via PythonEditor
- Can add Phase 6 later based on demand
- Focus initial implementation on composition over creation

---

---

## IMPLEMENTATION STATUS (Updated March 30, 2026)

### ✅ Completed (Phases 1-3)

**Phase 1: GUI Console Enhancement** ✅ DONE
- ✅ AmiCli helper methods (connect_nodes, disconnect_nodes, build_from_spec, node_info)
- ✅ Updated IPython namespace (chart, graph, LIBRARY, SourceNode, np, pg)
- ✅ Added graph attribute to AmiCli

**Phase 2: Magic Command & Graph Builder** ✅ DONE
- ✅ Created ami/flowchart/graph_builder.py
- ✅ OpenCodeBridge class (simplified to connect to server)
- ✅ Graph state extraction (get_graph_state)
- ✅ Agent invocation with JSON parsing
- ✅ Registered %build_graph and %bg magic commands
- ✅ OpenCode server starts at AMI launch (like dmypy)
- ✅ Server URL stored in OPENCODE_SERVER_URL environment variable

**Phase 2.5: View Source Feature** ✅ DONE
- ✅ generateSourceCode() method in Flowchart class
- ✅ "View Source" toolbar button
- ✅ Source viewer dialog with Copy/Export/Template options
- ✅ Name sanitization for valid Python variables

**Phase 3: AI Agent Skill** ✅ DONE
- ✅ Created skills/ami-graph-builder/ directory structure
- ✅ SKILL.md - Main agent instructions (~520 lines)
- ✅ Node documentation (6 reference files covering 16 nodes)
- ✅ Graph patterns documentation (5 common patterns)
- ✅ User templates directory structure

**Git Commits:** 6 commits on branch `feature/ai-graph-builder`
- ae673bf - Phases 1, 2, 2.5 implementation
- d2c1e73 - Phase 3 skill documentation
- a22c6f0 - Fix magic function registration
- e1e1af1 - Python 3.6 compatibility
- f3aa774 - Simplify server startup
- 8856d3c - Start server at AMI startup (final)

---

## ⚠️ CURRENT ISSUES & NEEDED IMPROVEMENTS

### Issue 1: Agent Hallucinating Non-Existent Nodes 🔥 HIGH PRIORITY

**Problem:** Agent invents node type names that don't exist in AMI

**Root Cause:**
- Only 16 of 97+ nodes documented
- No exhaustive list of valid node types
- No explicit constraint to only use documented nodes
- Agent guesses similar-sounding names

**Impact:** Generated code fails with "unknown node type" errors

**Solution Plan:** See Phase 3.5 below

---

## Phase 3.5: Fix Node Hallucination (NEW - CRITICAL)

**Effort:** 2-4 hours  
**Priority:** 🔥 HIGH - Fix before production use  
**Status:** ❌ NOT STARTED

### 3.5.1 Create Complete Node Type Reference

**File:** `skills/ami-graph-builder/references/all_node_types.md` (NEW)

Generate exhaustive list of all 97 valid node types:

```markdown
# Complete List of Valid AMI Node Types

**CRITICAL:** Only use node types from this list. Never invent node names.

## All Available Nodes (Alphabetical)

**Display Nodes:**
- Histogram - Distribution plot
- Histogram2D - 2D histogram
- ImageViewer - 2D image display
- LinePlot - 1D line plot
- MultiWaveformViewer - Multiple waveforms
- ObjectViewer - Generic object viewer
- ScalarPlot - Scalar vs time
- ScalarViewer - Single value display
- ScatterPlot - X vs Y correlation
- TimePlot - Time series plot
- WaveformViewer - 1D waveform display

**Processing Nodes:**
- Average, Average0D, Average1D, Average2D - Averaging operations
- Binning, Binning2D - Azimuthal/radial binning
- Calculator - Mathematical expressions
- Combinations - Combine inputs
- Constant - Constant value
- ExponentialMovingAverage1D, ExponentialMovingAverage2D - EMA
- Filter - Boolean event filtering
- GaussianFilter1D - Gaussian smoothing
- Identity - Pass-through
- Polynomial - Polynomial operations
- Projection - Dimensionality reduction
- Rotate - Rotate arrays
- Stack1d, Stack2d - Stack arrays
- Sum - Array summation
- Take - Extract elements

**ROI Nodes:**
- Roi0D, Roi1D, Roi2D - Region of interest extraction
- ScatterRoi - ROI on scatter plot

**Statistics Nodes:**
- HistMeanRMS - Histogram with stats
- Linregress0D, Linregress1D - Linear regression
- MeanVsScan - Mean vs scan variable
- MeanWaveformVsScan - Waveform mean vs scan
- RMS - Root mean square
- StatsVsScan - Full statistics vs scan
- TimeMeanRMS0D, TimeMeanRMS1D, TimeMeanRMS2D - Time-averaged stats

**Accumulator Nodes:**
- Accumulator - Accumulate over events
- Pick1 - Pick single event
- PickN - Pick N events
- RollingBuffer - Rolling event buffer
- SumN - Sum N events

**Analysis Nodes:**
- BlobFinder1D, BlobFinder2D - Find blobs
- CFD - Constant fraction discriminator
- CurveFit - Curve fitting
- EdgeFinder - Find edges
- Geometry - Geometric operations
- HitFinder - Hit detection
- Mask, Mask3dFrom2d - Masking operations
- PeakFinder1D, PeakFinderV4R3, PeakFit - Peak finding
- ThresholdingHitFinder - Threshold-based hit finding

**FFT Nodes:**
- FFT, FFT2 - Forward FFT
- IFFT, IFFT2 - Inverse FFT
- RFFT, RFFT2 - Real FFT
- IRFFT, IRFFT2 - Inverse real FFT

**Export Nodes:**
- ExportToWorker - Export to worker process
- PvExport - EPICS PV export
- ZMQ - ZMQ publisher
- UDPMcast - UDP multicast

**Special Nodes:**
- ArrayThreshold - Threshold arrays
- LoadReference1D - Load reference data
- Monitor - Monitoring node
- PythonEditor - Custom Python code
- Split - Split data streams

(Total: 97 node types)
```

### 3.5.2 Update SKILL.md - Add Critical Constraints

**File:** `skills/ami-graph-builder/SKILL.md`

Add at top (after "Your Role"):

```markdown
## ⚠️ CRITICAL CONSTRAINT: Valid Node Types Only

**YOU MUST ONLY USE NODE TYPES FROM THE OFFICIAL LIST.**

See `references/all_node_types.md` for the complete list of all 97 valid AMI node types.

**RULES:**
1. ✅ ONLY use node types from the official list
2. ❌ NEVER invent or guess node type names
3. ❌ NEVER use similar-sounding names (e.g., "DetectorViewer" doesn't exist, use "ImageViewer")
4. ❌ NEVER assume a node exists based on its function

**IF** the user requests functionality and no matching node exists:
1. Say so explicitly in your response
2. Suggest the closest available alternative
3. Explain how to achieve the goal with existing nodes or PythonEditor

**Common Mistakes to Avoid:**
- ❌ `DetectorViewer` → Use `ImageViewer`
- ❌ `PlotScalar` → Use `ScalarPlot`  
- ❌ `ROI` → Use `Roi1D` or `Roi2D`
- ❌ `Mean` → Use `Average` or `MeanVsScan`
- ❌ `Threshold` → Use `Filter` with expression
- ❌ `Correlate` → Use `ScatterPlot`
```

### 3.5.3 Enhance build_agent_prompt()

**File:** `ami/flowchart/graph_builder.py` (line ~242)

Update prompt to include common nodes:

```python
def build_agent_prompt(user_request, graph_state, amicli):
    """Generate comprehensive prompt for AI agent."""
    
    prompt = f"""You are helping build an AMI analysis graph using Python.

USER REQUEST: {user_request}

CURRENT GRAPH STATE:
- Nodes: {len(graph_state["nodes"])} nodes
- Sources: {", ".join(graph_state["sources"]) if graph_state["sources"] else "None"}
- Available sources: {", ".join(graph_state["available_sources"][:10]) if graph_state["available_sources"] else "None"}

AVAILABLE API:
1. Create nodes: chart.createNode(type, name)
2. Connect nodes: amicli.connect_nodes(src, src_term, dst, dst_term)

⚠️ CRITICAL: ONLY use these valid node types (most common):

Display: ImageViewer, WaveformViewer, ScatterPlot, ScalarPlot, LinePlot, 
         ScalarViewer, Histogram, Histogram2D, TimePlot

Processing: Sum, Average, Projection, Binning, Calculator, Filter, 
            GaussianFilter1D, Polynomial, Rotate

ROI: Roi0D, Roi1D, Roi2D, ScatterRoi

Statistics: MeanVsScan, StatsVsScan, HistMeanRMS, Linregress0D, Linregress1D

Accumulators: Pick1, PickN, RollingBuffer, SumN

Analysis: PeakFinder1D, BlobFinder1D, BlobFinder2D, HitFinder

Export: PvExport, ZMQ, UDPMcast

Special: PythonEditor (for custom code), Monitor

NEVER invent node names. If unsure, use PythonEditor or ask for clarification.

REQUIRED RESPONSE FORMAT (JSON):
{{
  "explanation": "Brief description",
  "code": "executable Python code",
  "warnings": ["optional warnings"],
  "next_steps": ["optional suggestions"]
}}
"""
    return prompt
```

### 3.5.4 Add Validation (Optional)

**File:** `ami/flowchart/graph_builder.py`

Add validation function:

```python
def validate_node_types(code):
    """Warn if code uses potentially invalid node types"""
    import re
    
    # Extract all createNode calls
    node_types = re.findall(r"createNode\(['\"](\w+)['\"]", code)
    
    # Common valid types (subset for quick check)
    known_types = {
        'ScatterPlot', 'ScalarPlot', 'LinePlot', 'ImageViewer', 'WaveformViewer',
        'Sum', 'Average', 'Projection', 'Binning', 'Calculator', 'Filter',
        'Roi1D', 'Roi2D', 'MeanVsScan', 'StatsVsScan', 'PythonEditor',
        'Histogram', 'Pick1', 'PickN', 'RollingBuffer', 'PvExport'
    }
    
    unknown = [nt for nt in node_types if nt not in known_types]
    
    if unknown:
        print(f"⚠️  Warning: Unknown node types detected: {', '.join(unknown)}")
        print(f"⚠️  Code may fail if these aren't valid AMI nodes")
```

---

## Phase 4: Diagnostics (Deferred)

**Status:** ❌ DEFERRED - Not implemented  
**Reason:** Focus on core functionality first

See original plan above for "Why Can't I See Data?" diagnostics feature.

---

## Phase 5: Graph Optimization (Deferred)

**Status:** ❌ DEFERRED - Not implemented

---

## Phase 6: Custom Node Generation (Deferred)

**Status:** ❌ DEFERRED - Not implemented

---

## Document Version History

**Version 3.0** - March 30, 2026 (Updated)
- Phases 1-3 marked as complete
- Added implementation status section
- Added Phase 3.5 for fixing node hallucination issue
- Updated with actual git commits and branch info
- Changed from planning document to status/tracking document

**Version 2.3** - March 30, 2026 (Original)
- Initial comprehensive planning document

---

## Immediate Next Steps

1. ✅ ~~Implement Phases 1-3~~ (COMPLETE)
2. 🔥 **Implement Phase 3.5** - Fix node hallucination (HIGH PRIORITY)
3. 📊 User testing and feedback collection
4. 🔧 Iterate based on real usage patterns
5. 📚 Expand documentation for more nodes as needed
6. 🚀 Merge to main branch when stable
