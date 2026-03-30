# AMI Control/Custom Processing Nodes Reference

Control nodes manage data flow and enable custom processing logic.

## Filter - Conditional Event Filtering ⭐⭐

**Purpose:** Pass through events only when a boolean condition is met. Essential for pump-probe and conditional analysis.

**Terminals:**
- Input: `In`, `In.1`, `In.2`, etc. (values to test)
- Output: `Out` (passthrough when condition is True)

**Key Parameters:**
- `expression`: Boolean expression using input names

**Expression Syntax:**
- Inputs referenced as: `In`, `In_1`, `In_2`, etc.
- Comparison: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Logic: `&` (AND), `|` (OR), `~` (NOT)
- Examples:
  - `In > 100` - Pass events where In exceeds 100
  - `(In > 50) & (In < 150)` - Range filter
  - `(In_1 > 10) | (In_2 < 5)` - Multiple conditions

**Common Use Cases:**
- Pump-probe (laser on/off filtering)
- Event selection based on thresholds
- Data quality filtering
- Beam condition requirements
- Multi-condition event selection

**Example - Simple threshold:**
```python
# Filter events where laser intensity > 100
filter_node = chart.createNode('Filter', 'laser_on')
amicli.connect_nodes('laser_source', 'Out', 'laser_on', 'In')
print('Filter created. Set expression in GUI: In > 100')

# Process only laser-on events
amicli.connect_nodes('laser_on', 'Out', 'detector_roi', 'In')
```

**Example - Pump-probe:**
```python
# Filter for pump events (laser on)
filter_pump = chart.createNode('Filter', 'pump_filter')
amicli.connect_nodes('laser_status', 'Out', 'pump_filter', 'In')
print('Pump filter created. Set expression in GUI: In == 1')

# Process pump events
roi_pump = chart.createNode('Roi2D', 'pump_roi')
amicli.connect_nodes('detector_source', 'Out', 'pump_roi', 'In')
amicli.connect_nodes('pump_filter', 'Out', 'pump_roi', 'In.1')  # Gate signal

sum_pump = chart.createNode('Sum', 'pump_sum')
amicli.connect_nodes('pump_roi', 'Out', 'pump_sum', 'In')
```

**Example - Range filter:**
```python
# Filter events with detector value between 50 and 150
filter_range = chart.createNode('Filter', 'quality_filter')
amicli.connect_nodes('detector_source', 'Out', 'quality_filter', 'In')
print('Filter created. Set expression in GUI: (In > 50) & (In < 150)')
```

**Example - Multiple conditions:**
```python
# Filter events where laser > 100 AND detector < 1000
filter_multi = chart.createNode('Filter', 'event_select')
amicli.connect_nodes('laser_source', 'Out', 'event_select', 'In')
amicli.connect_nodes('detector_source', 'Out', 'event_select', 'In.1')
print('Filter created. Set expression in GUI: (In > 100) & (In_1 < 1000)')
```

**Important Notes:**
- Filters **drop events** when condition is False
- Downstream nodes only see filtered events
- Use `&` and `|` for logic (not `and`/`or`)
- Parentheses control precedence: `(In > 50) & (In < 150)`
- Can create separate branches for pump/probe, on/off, etc.

**See also:** Templates - pump_probe.py

---

## PythonEditor - Custom Python Processing ⭐⭐

**Purpose:** Write custom Python code to process events when standard nodes don't provide needed functionality.

**Terminals:**
- Dynamic: User adds inputs/outputs via GUI

**Key Features:**
- Write Python class with event processing methods
- Define inputs and outputs dynamically
- Access to full Python and NumPy
- Good for simple Map-style operations
- Prototyping before creating proper custom nodes

**When to Use:**
- Custom mathematical operations not available in Calculator
- Conditional logic beyond what Filter provides
- Combining multiple operations in custom way
- Loading external calibration data
- Prototyping before creating a reusable custom node

**Decision Tree for Custom Processing:**

1. **Simple math expression?** (e.g., `x * 2 + 5`)
   → Use **Calculator** node

2. **Basic boolean filtering?** (e.g., `x > 100`)
   → Use **Filter** node  

3. **Custom Python logic needed?**
   → Use **PythonEditor** node

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

### Custom Calibration
```
User needs to: Apply calibration from file
Solution: PythonEditor that loads calibration in __init__() and applies in event()
```

### Conditional Processing
```
User needs to: If x > threshold, return process(x), else return 0
Solution: PythonEditor with conditional logic
```

### Complex Math
```
User needs to: Custom formula combining multiple inputs
Solution: PythonEditor (or Calculator if formula is simple)
```

### External Data Lookup
```
User needs to: Load lookup table from file and apply to each event
Solution: PythonEditor (load table in __init__, apply in event())
```

**Agent Guidance for PythonEditor Requests:**

When user requests custom processing:

1. **First, check if Calculator can do it:**
   - Is it a simple mathematical expression?
   - Can it be expressed as: `In * a + b` or `np.sqrt(In**2 + In_1**2)`?
   - If YES → Use Calculator
   - If NO → Continue to step 2

2. **Second, check if Filter can do it:**
   - Is it a boolean condition for event selection?
   - Can it be expressed as: `In > threshold` or `(In > a) & (In < b)`?
   - If YES → Use Filter
   - If NO → Continue to step 3

3. **Third, check if existing nodes can be combined:**
   - Can Sum + Average + Calculator achieve the goal?
   - If YES → Build pipeline with existing nodes
   - If NO → Continue to step 4

4. **Finally, use PythonEditor:**
   - Create the node
   - Explain that user must write code in GUI
   - Provide template structure
   - Give specific example for their use case

**Example Agent Responses:**

**Scenario 1:** "multiply ROI sum by 2.5 and add 10"
```python
# Use Calculator - simple expression
print("Creating Calculator node for: (roi_sum * 2.5) + 10")
calc = chart.createNode('Calculator', 'scaled_sum')
print("⚠️  In Calculator GUI, enter expression: (In * 2.5) + 10")
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
print("  1. Right-click → 'Add Input' → name it 'raw_values'")
print("  2. Right-click → 'Add Output' → name it 'calibrated'")
print("  3. Double-click to edit code")
print("  4. In __init__(): load your calibration file")
print("  5. In event(): apply calibration to raw_values")
print("")
print("Example code structure:")
print("  class EventProcessor():")
print("      def __init__(self):")
print("          self.cal_data = np.loadtxt('cal.txt')")
print("      def event(self, raw_values):")
print("          return raw_values * self.cal_data")
```

**Scenario 3:** "filter events where laser > 100 and detector < 50"
```python
# Use Filter - boolean conditions
print("Creating Filter node for: (laser > 100) AND (detector < 50)")
filter_node = chart.createNode('Filter', 'event_filter')
print("⚠️  In Filter GUI, enter expression:")
print("   (In > 100) & (In_1 < 50)")
amicli.connect_nodes('laser', 'Out', 'event_filter', 'In')
amicli.connect_nodes('detector', 'Out', 'event_filter', 'In.1')
```

---

## Summary: Custom Processing Decision Tree

```
User Request for Custom Processing
         |
         v
    Simple math?
    (x * 2 + 5, sqrt(x^2 + y^2), etc.)
         |
    YES --→ Use Calculator
         |
    NO   |
         v
    Boolean filter?
    (x > 100, (x > a) & (x < b), etc.)
         |
    YES --→ Use Filter
         |
    NO   |
         v
    Combine existing nodes?
    (Sum + Average + Calc, etc.)
         |
    YES --→ Build pipeline
         |
    NO   |
         v
    Use PythonEditor
    (complex logic, external data, etc.)
```

**Agent should prefer Calculator/Filter when possible!**
**PythonEditor is powerful but requires manual GUI coding by user.**
