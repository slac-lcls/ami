# Plan: Show Agent Text Events in Chat Widget

**Date:** April 1, 2026  
**Status:** Ready to implement  
**Estimated time:** 15-20 minutes

---

## Problem

Currently, when the agent responds with code, the chat widget only shows:
- System messages
- The generated code
- Execution status

**Missing:** The agent's conversational text explaining what it's doing!

## Example

**What the agent actually sends:**
```
Event 1: {"type":"text","part":{"text":"I'll help you find image sources..."}}
Event 2: {"type":"text","part":{"text":"Looking at your available sources..."}}
Event 3: {"type":"text","part":{"text":"```json\n{\"code\":\"...\"}\n```"}}
```

**What we currently show:**
```
[System] Response received, processing...
[System] Found 2 code block(s)
--- Generated Code 1 ---
<code>
--- End Code ---
[System] Executing code...
[System] ✅ Execution successful!
```

**What we should show:**
```
[System] Response received, processing...

Agent:
I'll help you find image sources...
Looking at your available sources...

--- Generated Code 1 ---
<code>
--- End Code ---

[System] Executing code...
[System] ✅ Execution successful!
```

---

## Solution

Update `_on_response_received()` to show ALL agent text events, not just code.

### Current Flow
```python
def _on_response_received(self, response_str):
    codes = self._extract_code(response_str)
    
    if codes:
        # Show and execute code
    else:
        # Show text
```

### New Flow
```python
def _on_response_received(self, response_str):
    # 1. Always show agent's conversational text first
    self._show_agent_text(response_str)
    
    # 2. Then extract and execute code
    codes = self._extract_code(response_str)
    if codes:
        # Show and execute code
```

---

## Implementation

### File: `ami/flowchart/chat_widget.py`

#### Step 1: Add `_show_agent_text()` helper method

Insert after `_extract_text()` method (~line 420):

```python
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
```

#### Step 2: Update `_on_response_received()` method

Replace the current method (~lines 248-292) with:

```python
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
```

#### Step 3: Remove duplicate explanation/warnings display

In `_extract_code()` method, remove lines 361-369 (explanation and warnings display):

**Remove these lines:**
```python
# Show explanation if provided
if "explanation" in response:
    self._append_output(f"Explanation: {response['explanation']}")

# Show warnings if provided
if "warnings" in response:
    for warning in response["warnings"]:
        self._append_output(f"⚠️  {warning}")
```

**Reason:** The JSON response will be shown as part of the conversational text now, so we don't need to duplicate it.

---

## Testing

### Test Case 1: Question with Code Response
**Input:** "show me image sources"

**Expected Output:**
```
You: show me image sources

[System] Sending request to agent...
[System] Response received, processing...

Agent:
I'll help you find image sources in your AMI graph.
Let me check what sources are available...

[System] Found 1 code block(s)

--- Generated Code 1 ---
<code to find image sources>
--- End Code ---

[System] Executing code...
[System] ✅ Execution successful!
```

### Test Case 2: Text-Only Response
**Input:** "what is AMI?"

**Expected Output:**
```
You: what is AMI?

[System] Sending request to agent...
[System] Response received, processing...

Agent:
AMI stands for Analysis Monitoring Interface. It's a distributed system
for processing LCLS experiment data in real-time using computation graphs.

[System] No code to execute
```

### Test Case 3: Agent Asks Questions
**Input:** "create a plot"

**Expected Output:**
```
You: create a plot

[System] Sending request to agent...
[System] Response received, processing...

Agent has questions:
What's unclear about your request

  Q: What type of plot would you like?
     - Scatter plot
     - Line plot
     - Histogram
     
[System] No code to execute
```

---

## Benefits

✅ **Better UX** - User sees agent's thinking/explanation  
✅ **Natural conversation** - Feels like chatting with the agent  
✅ **Context** - Understand why code does what it does  
✅ **Questions visible** - See when agent needs clarification  
✅ **Non-breaking** - Code execution still works the same  

---

## Edge Cases Handled

1. **Empty text events** - Skipped with `if text.strip()`
2. **Code blocks in text** - Filtered out with `if "```json" in text`
3. **JSON parse errors** - Caught and skipped gracefully
4. **No text events** - Simply doesn't display "Agent:" section
5. **Multiple text events** - All shown in order

---

## Files Modified

- `ami/flowchart/chat_widget.py`
  - Add `_show_agent_text()` method (~30 lines)
  - Update `_on_response_received()` (~20 lines changed)
  - Remove duplicate display in `_extract_code()` (~9 lines removed)
  - **Net change:** ~40 lines

---

## Estimated Time

- Implementation: 10 minutes
- Testing: 5-10 minutes
- **Total: 15-20 minutes**

---

## Dependencies

None - standalone change to chat_widget.py

---

## Rollback Plan

If this doesn't work well, simply revert the changes:
```bash
git checkout HEAD -- ami/flowchart/chat_widget.py
```

---

## Next Steps After This

Once text display is working, we could consider:
1. Capture and display print() output from code execution
2. Syntax highlighting for code blocks
3. Persistent command history
4. Copy code to clipboard button

But those are future enhancements - this plan focuses on showing agent text.

---

## Approval Status

**User approved:** ✅ Yes  
**Ready to implement:** ✅ Yes  
**Conflicts with other work:** ❌ No  

---

**Implementation can proceed when ready!**
