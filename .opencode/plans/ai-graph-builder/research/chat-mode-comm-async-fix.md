# Plan: Fix Comm Message Reception for Proper Source List

**Date**: 2026-03-31  
**Status**: Planning  
**Branch**: `feature/ai-graph-builder`  
**Priority**: 🔥 HIGH - Agent is blind without sources

---

## Status Update (2026-03-31)

✅ **COMPLETED**: Added performance timing instrumentation  
⏳ **NEXT**: Test and analyze timing results before implementing Comm fix  
📊 **Waiting for**: Timing data to identify if Comm fix is the bottleneck

**See**: `performance-timing-guide.md` for testing instructions

---

## Problem Statement

The `chat()` function currently **never receives** the graph state from the GUI, resulting in:
- ❌ `available_sources` is always empty → Agent doesn't know what experiment sources exist
- ❌ `nodes` is always empty → Agent doesn't know current graph
- ❌ `sources` is always empty → Agent doesn't know which sources are in graph  
- ❌ `connections` is always empty → Agent doesn't know how nodes are connected

**Root Cause**: The prototype uses polling with timeout, but never actually receives the Comm messages sent by the GUI.

```python
# Current broken code (Flowchart.py:2078-2100)
comm.send({'type': 'request_state'})

# Polls but never actually receives anything!
for i in range(50):
    time.sleep(0.1)
    # ... no receive code here ...
    if i > 5:  # Always times out after 0.5s
        state = {'available_sources': []}  # Empty!
        break
```

The GUI correctly sends the response (line 1858), but the kernel has no handler to receive it.

---

## Solution Overview

Implement proper async message handling using the IPython Comm API's `on_msg()` callback mechanism.

**Key Insight**: The Comm API already provides async callbacks - we just need to use them instead of polling!

### Architecture Pattern

```python
# GUI Side (already implemented correctly)
def handle_comm_msg(msg):
    if msg_type == "request_state":
        state = ctrl_widget._get_graph_state()
        comm.send({"type": "state_response", "state": state})

comm.on_msg(handle_comm_msg)  # ✅ Already works


# Kernel Side (NEEDS FIXING)
received_data = {'state': None, 'state_received': False}

def handle_gui_message(msg):
    data = msg['content']['data']
    if data.get('type') == 'state_response':
        received_data['state'] = data.get('state')
        received_data['state_received'] = True  # Signal ready!

comm.on_msg(handle_gui_message)  # ❌ MISSING - need to add this
```

---

## Implementation Details

### File to Modify

**`ami/flowchart/Flowchart.py`** - Lines 2013-2229 (the `chat_function_code` triple-quoted string)

### Changes Required

#### Change 1: Add Message Handler Setup (after line 2042)

**Location**: After `comm = Comm(target_name='ami_graph_builder')` and before main loop

**Add**:

```python
# Shared state container for async message reception
received_data = {
    'state': None,
    'state_received': False,
    'execution_complete': False,
    'execution_status': None
}

# Message handler for async reception of GUI responses
def handle_gui_message(msg):
    """
    Async callback for Comm messages from GUI.
    
    This runs asynchronously when GUI sends messages, allowing
    us to avoid polling and properly receive responses.
    """
    try:
        data = msg['content']['data']
        msg_type = data.get('type', '')
        
        if msg_type == 'state_response':
            # Received graph state from GUI
            received_data['state'] = data.get('state', {})
            received_data['state_received'] = True
        
        elif msg_type == 'execution_complete':
            # Code execution finished
            received_data['execution_complete'] = True
            received_data['execution_status'] = data.get('status', 'unknown')
        
        elif msg_type == 'ready':
            # GUI comm handler is ready (initial handshake)
            pass  # No action needed
        
        elif msg_type == 'error':
            # GUI reported an error
            error_msg = data.get('message', 'Unknown error')
            print(f"[GUI Error] {error_msg}")
    
    except Exception as e:
        # Don't crash the handler - just log
        print(f"[Kernel] Error in message handler: {e}")

# Register the async message handler
comm.on_msg(handle_gui_message)
```

**Why this works**: 
- `comm.on_msg()` registers a callback that runs asynchronously when messages arrive
- No polling needed - callback fires when GUI sends response
- Shared `received_data` dict acts as thread-safe storage (CPython GIL protects simple dict ops)

#### Change 2: Replace Polling with Proper Wait (lines 2078-2100)

**Location**: Graph state request section

**Replace current code with**:

```python
# Request current graph state from GUI
print("🔍 Getting graph state...")

# Reset flags
received_data['state_received'] = False
received_data['state'] = None

# Send request to GUI via Comm
comm.send({'type': 'request_state'})

# Wait for async callback to set state_received flag
timeout = 2.0  # seconds
poll_interval = 0.05  # 50ms
start_time = time.time()

while not received_data['state_received']:
    time.sleep(poll_interval)
    
    # Check timeout
    if time.time() - start_time > timeout:
        print("⚠️  Warning: Timeout waiting for graph state")
        print("    Using empty state (agent may not have source info)")
        break

# Use received state or fallback to empty
if received_data['state_received'] and received_data['state'] is not None:
    state = received_data['state']
else:
    # Fallback to empty state
    state = {
        'nodes': [],
        'sources': [],
        'connections': [],
        'available_sources': []
    }
```

**Why this works**:
- Sends request via Comm
- Waits for callback to set `state_received = True`
- Polls the flag (lightweight), not the Comm channel
- Has timeout safety net (same as before)
- Clear feedback if timeout occurs

#### Change 3: Improve Execution Acknowledgment (OPTIONAL)

**Location**: Lines 2202-2212 (after code execution)

**Replace current code with** (optional improvement):

```python
if code:
    print("\\n  💻 Sending code to GUI for execution...\\n")
    
    # Reset execution flags
    received_data['execution_complete'] = False
    received_data['execution_status'] = None
    
    # Send code to GUI via Comm
    comm.send({
        'type': 'execute_code',
        'code': code
    })
    
    # Wait for execution acknowledgment
    timeout = 5.0  # seconds - longer for complex operations
    poll_interval = 0.05  # 50ms
    start_time = time.time()
    
    while not received_data['execution_complete']:
        time.sleep(poll_interval)
        
        if time.time() - start_time > timeout:
            print("  ⚠️  Warning: Execution acknowledgment timeout")
            print("      (Code may have executed successfully anyway)")
            break
    
    # Report result if received
    if received_data['execution_complete']:
        if received_data['execution_status'] != 'success':
            print(f"  ⚠️  Execution status: {received_data['execution_status']}")

else:
    print("\\n  ℹ️  No code generated\\n")
```

**Why this is optional**:
- Execution usually succeeds quickly
- GUI already prints success/error messages
- Main benefit: Kernel knows when execution is done
- Can wait for next operation safely
- Not critical for prototype

---

## Technical Design Decisions

### Why Not True Async/Await?

**Question**: Why not use Python's `async`/`await` instead of polling a flag?

**Answer**: The `input()` call is blocking and not async-compatible. We can't make the main loop async without breaking `input()`.

**Pattern**:
```python
# This works:
while True:
    user_input = input("> ")  # Blocks - OK
    # ... async callback sets flag ...
    while not flag: time.sleep(0.05)  # Wait for flag - OK

# This doesn't work:
async def chat():
    user_input = await async_input("> ")  # input() isn't async
```

### Why Poll the Flag Instead of the Comm?

**Current approach**: Wait for callback to set `state_received = True`

**Alternative**: Try to read from Comm directly

**Why we don't**: 
- Comm API doesn't provide synchronous `receive()` method
- Only provides async `on_msg()` callbacks
- Polling the flag is lightweight and thread-safe
- Clear separation: callback sets data, main loop consumes

### Thread Safety

**Question**: Is `received_data` dict thread-safe?

**Answer**: Yes, for our simple use case:
- CPython GIL protects simple dict operations
- We only read/write individual keys
- No complex operations that could be interrupted
- Callback and main loop don't conflict

**If needed**: Could use `threading.Event()` for more robust signaling, but overkill for prototype.

---

## Testing Plan

### Setup
```bash
ami-local random://
# Click Console button
>>> chat()
```

### Test 1: Verify State Reception

**Request**:
```
> which sources are available
```

**Expected Behavior**:
- Should NOT timeout (no "⚠️ Warning: Timeout" message)
- Agent should see and list actual random sources
- Check console output for source names

**Success Criteria**:
- ✅ No timeout warning
- ✅ `state_received` becomes `True`
- ✅ Agent prompt contains actual source names
- ✅ Agent can reference sources in response

### Test 2: Use Source in Code Generation

**Request**:
```
> create a scatter plot with <actual_source_name>
```
(Use actual source name from Test 1)

**Expected Behavior**:
- Agent generates code using correct source name from available_sources
- Code executes successfully
- Node appears in flowchart

**Success Criteria**:
- ✅ Agent uses exact source name from `available_sources`
- ✅ No "source doesn't exist" errors
- ✅ Code executes
- ✅ Scatter plot node created

### Test 3: Multi-source Request

**Request**:
```
> correlate the two available sources
```

**Expected Behavior**:
- Agent sees both sources from `available_sources`
- Generates scatter plot using both
- Asks clarification if >2 sources exist

**Success Criteria**:
- ✅ Agent aware of multiple sources
- ✅ Uses correct source names in code
- ✅ OR asks which sources to use

### Test 4: Graph State Awareness

**Steps**:
1. Manually create a node in GUI (e.g., Sum node)
2. In chat:
   ```
   > what nodes are in the graph
   ```

**Expected Behavior**:
- Agent sees the Sum node in `state['nodes']`
- Can describe current graph state
- Knows what's already been created

**Success Criteria**:
- ✅ Agent aware of manually created node
- ✅ Mentions node in response
- ✅ Can build on existing graph

### Test 5: Timeout Handling

**Setup**: Simulate slow response (if possible) or very large state

**Expected Behavior**:
- If timeout occurs, prints clear warning
- Falls back to empty state gracefully
- Agent continues (with limited info)

**Success Criteria**:
- ✅ Timeout warning is clear
- ✅ No crash or hang
- ✅ Can continue conversation

---

## Debug Output (Temporary)

To verify the fix is working, temporarily add debug output:

```python
# In handle_gui_message callback:
if msg_type == 'state_response':
    received_data['state'] = data.get('state', {})
    received_data['state_received'] = True
    
    # TEMP DEBUG
    avail = data.get('state', {}).get('available_sources', [])
    print(f"[DEBUG] Received state with {len(avail)} sources")
    if avail:
        print(f"[DEBUG] Sources: {', '.join(avail[:5])}")

# After wait loop:
if received_data['state_received']:
    state = received_data['state']
    
    # TEMP DEBUG
    print(f"[DEBUG] State received in {time.time() - start_time:.3f}s")
    print(f"[DEBUG] Available sources: {len(state.get('available_sources', []))}")
```

**Remove after**: Confirming it works in first test

---

## Success Criteria

### Minimum (Must Have)
- [ ] No timeout warnings during normal operation
- [ ] `available_sources` contains actual experiment sources
- [ ] Agent can see and use source names
- [ ] Generated code uses correct source names from state
- [ ] No crashes or hangs

### Ideal (Should Have)
- [ ] < 100ms latency for state response
- [ ] Execution acknowledgment received (if implementing Change 3)
- [ ] Clear error messages if issues occur
- [ ] Graceful timeout fallback

---

## Rollback Plan

**If issues occur**:
1. Changes are isolated to the `chat_function_code` string
2. Can easily revert to polling behavior (current code)
3. No GUI-side changes needed
4. No persistent state or config changes

**Fallback**: Keep polling with empty state (current behavior)

---

## Future Improvements (Out of Scope)

These are improvements for later, not part of this fix:

1. **True async/await**: Replace input() with prompt_toolkit for async input
2. **Streaming state updates**: Push state changes from GUI without request
3. **Bidirectional events**: GUI notifies kernel of graph changes in real-time
4. **Connection pooling**: Reuse Comm connections more efficiently
5. **Compression**: Compress large state payloads for faster transfer

---

## Related Issues

This fix addresses:
- **Issue**: Agent doesn't know available sources
- **Issue**: Agent can't validate source names
- **Issue**: Agent generates code with wrong source names
- **Issue**: Graph state context not passed to agent

This enables:
- Source-aware code generation
- Better agent responses
- Multi-turn conversations with context
- Validation of user requests against available data

---

## References

**Relevant Code**:
- `ami/flowchart/Flowchart.py:1400-1465` - `_get_graph_state()` (GUI side, already working)
- `ami/flowchart/Flowchart.py:1836-1891` - GUI Comm handler (already working)
- `ami/flowchart/Flowchart.py:2013-2229` - `chat()` function (needs fixing)

**Documentation**:
- `CHAT_MODE_PROTOTYPE_TEST.md` - Testing guide
- `AMI_GRAPH_BUILDER_STATUS.md` - Overall status
- `.opencode/archive/graph-builder-docs/PROTOTYPE_COMPLETE.md` - Prototype notes

**IPython Comm API**:
- https://ipython.readthedocs.io/en/stable/development/messaging.html
- `ipykernel.comm.Comm` class documentation

---

## Questions Before Implementation

### 1. Scope

Should we implement:
- **Change 1 + Change 2** (fix state reception) - Required
- **Change 3** (execution acknowledgment) - Optional improvement

**Recommendation**: Start with Changes 1 & 2, add Change 3 if time permits and testing goes well.

### 2. Timeout Values

**Current proposal**:
- State request: 2.0 seconds
- Execution acknowledgment: 5.0 seconds

**Questions**:
- Are these reasonable? (GUI response should be <100ms typically)
- Should we make them configurable?
- Should we have different timeouts for first request vs subsequent?

**Recommendation**: Start with 2.0s and 5.0s, adjust based on testing.

### 3. Debug Output

Should we:
- **Add temporary debug output** to verify fix (remove later)
- **Add permanent logging** at INFO level
- **No debug output** (cleaner but harder to verify)

**Recommendation**: Add temporary debug output, remove after confirming it works.

### 4. Error Handling

For timeout case:
- **Current**: Print warning, use empty state, continue
- **Alternative**: Retry once before giving up
- **Alternative**: Prompt user to retry

**Recommendation**: Keep current approach (warning + fallback), it's simple and safe.

---

## Timeline Estimate

**Implementation**: 30-60 minutes
- Change 1: 15-20 min (add handler setup)
- Change 2: 10-15 min (replace polling)
- Change 3: 15-20 min (execution ack, if doing it)

**Testing**: 30-45 minutes
- Basic functionality: 10 min
- Source awareness: 10 min
- Multi-turn context: 10 min
- Edge cases: 10-15 min

**Debug/Polish**: 30 minutes contingency

**Total**: 1.5-2.5 hours

---

## Next Steps

1. **Review this plan** - Any questions or concerns?
2. **Approve scope** - Which changes to include?
3. **Implement** - Make the code changes
4. **Test** - Run through test plan
5. **Verify** - Confirm sources appear in agent prompts
6. **Clean up** - Remove debug output
7. **Document** - Update status docs

---

**Status**: ✅ PLAN COMPLETE - Ready for review and implementation  
**Last Updated**: 2026-03-31
