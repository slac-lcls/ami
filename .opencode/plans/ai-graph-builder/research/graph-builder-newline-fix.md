# Graph Builder Newline Fix

## Issue

The AMI graph builder was failing with a syntax error when executing multi-line Python code:

```
[Graph Builder] Error: unexpected character after line continuation character (<string>, line 1)
SyntaxError: unexpected character after line continuation character
```

**Root Cause:** The agent returns code in JSON format with escaped newlines (`\\n` in JSON, which becomes `\n` as a string after parsing). When this code string was passed to `IPython.ex()`, Python tried to execute it with literal backslash-n characters instead of actual newlines, causing a syntax error.

## Example Failure

**Agent response (JSON):**
```json
{
  "code": "print('Step 1')\\nscatter = chart.createNode('ScatterPlot', 'plot1')\\nprint('Done')"
}
```

**After JSON parsing (Python string):**
```python
"print('Step 1')\nscatter = chart.createNode('ScatterPlot', 'plot1')\nprint('Done')"
```
This is a literal backslash-n, NOT a newline character!

**Attempted execution:**
```python
ipython_shell.ex("print('Step 1')\nscatter = chart.createNode('ScatterPlot', 'plot1')\nprint('Done')")
# SyntaxError! Python sees: print('Step 1')\nscatter...
```

## Solution

**File:** `ami/flowchart/graph_builder.py`

**Location:** `extract_code_from_response()` function, around line 546

### Changes Made

1. **Decode escaped newlines** - Convert `\n` strings to actual newlines
2. **Add AST validation** - Catch syntax errors before execution with helpful error messages
3. **Return None on syntax errors** - Don't execute broken code

### Implementation

```python
# Get code and decode escaped newlines from JSON representation
code = response.get("code", "")
if not code:
    return ""

# Decode \n from JSON string to actual newlines
code = code.replace('\\n', '\n')

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
        for i, line in enumerate(code.split('\n'), 1):
            marker = ">>>" if i == e.lineno else "   "
            print(f"  {marker} {i}: {line}")
    else:
        print("[Graph Builder] Generated code:")
        for i, line in enumerate(code.split('\n'), 1):
            print(f"      {i}: {line}")
    print("")
    print("[Graph Builder] Not executing - this is likely an agent bug")
    print("[Graph Builder] Please report this issue")
    return None

return code
```

## Benefits

### 1. Fixes the Immediate Issue
✅ Multi-line code now executes correctly
✅ Newlines are properly converted from JSON escape sequences

### 2. Better Error Handling
✅ AST validation catches syntax errors before execution
✅ Clear error messages with line numbers
✅ Shows the problematic code with markers (`>>>`) pointing to the error

### 3. Improved Debugging
✅ When agent generates bad code, users see exactly what's wrong
✅ No cryptic Python tracebacks
✅ Clear indication that it's an agent bug, not user error

### 4. Safety
✅ Doesn't execute broken code
✅ Prevents partial execution that could leave graph in inconsistent state

## Testing

Created `test_graph_builder_newline_fix.py` with 4 test cases:

1. ✅ **Multi-line code with newlines** - Escaped `\n` properly converted
2. ✅ **Single-line code** - Still works without newlines
3. ✅ **Syntax error detection** - AST validation catches errors
4. ✅ **Empty code handling** - Gracefully handles empty strings

**Result:** 4/4 tests passed

## What About Other Escaped Characters?

**Decision:** Only handle `\n` for now.

**Rationale:**
- JSON parsing already handles most escape sequences correctly (`\'`, `\"`, `\\`, etc.)
- Emojis (used in output) work fine as UTF-8
- No evidence of issues with other characters in generated code
- Over-engineering could introduce bugs
- Can add more later if needed

## What About IPython-Specific Syntax?

**Decision:** AST validation with soft failure (warn but continue).

**Current implementation:** Hard failure (don't execute on syntax error).

**Rationale:**
- Agent generates pure Python, not IPython magics
- All examples in SKILL.md are valid Python
- AST validation provides safety and better error messages
- If IPython-specific syntax becomes needed, we can soften the validation

**Future option:** Make validation configurable or softer:
```python
except SyntaxError as e:
    print("[Graph Builder] Warning: AST validation failed")
    print("[Graph Builder] Attempting execution anyway (may be IPython-specific)...")
    return code  # Execute anyway
```

## No Changes to SKILL.md

The AI agent skill instructions remain unchanged:
- Agent still generates code with `\\n` in JSON (correct JSON format)
- The Python code now properly decodes these before execution
- Clean separation between JSON representation and Python execution

## Example Before/After

### Before (Broken)

```
User: %bg show me the cspad

[Graph Builder] Processing: show me the cspad
[Graph Builder] Invoking AI agent...
[Graph Builder] Executing generated code...
[Graph Builder] Error: unexpected character after line continuation character
SyntaxError: unexpected character after line continuation character
```

### After (Working)

```
User: %bg show me the cspad

[Graph Builder] Processing: show me the cspad
[Graph Builder] Invoking AI agent...
[Graph Builder] The cspad detector source is available
[Graph Builder] Next steps:
  - Click on the cspad node to view the raw detector image
[Graph Builder] Executing generated code...
Ensuring cspad source exists...
✓ cspad source is ready!
👉 Click on the "cspad" node in the flowchart to view the detector image
[Graph Builder] Done!
```

## Related Files

- **Modified:** `ami/flowchart/graph_builder.py` (lines 546-580)
- **Test:** `test_graph_builder_newline_fix.py`
- **Documentation:** `.opencode/skills/ami-graph-builder/SKILL.md` (no changes needed)

## Date

March 30, 2026
