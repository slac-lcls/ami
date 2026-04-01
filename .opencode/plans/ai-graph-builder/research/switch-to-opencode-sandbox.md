# Switch AMI Graph Builder to use opencode-sandbox

## Executive Summary

**Goal:** Fix OpenCode database corruption by switching to ephemeral sessions

**Changes:**
1. Replace `opencode serve` → `opencode-sandbox --incognito serve`
2. Restore random port selection (was changed to fixed port 4096 for debugging)
3. Use ephemeral database that's deleted on AMI exit

**Impact:**
- ✅ No database corruption (fresh state each AMI session)
- ✅ No port conflicts (random port per session)
- ✅ Automatic cleanup (--incognito removes temp files on exit)
- ⚠️ No conversation history across AMI restarts (acceptable trade-off)

**File to modify:** `ami/client/flowchart.py` (lines 56-70, ~7 line change)

**Testing:** Basic smoke test with `ami-local` and `%bg` commands

---

## Problem Statement

The OpenCode server started by AMI for the AI graph builder feature has encountered database corruption issues. The current implementation uses `opencode serve` directly, which maintains persistent state in:

```
/sdf/scratch/users/s/seshu/seshu-opencode-sandbox/home/.local/share/opencode/opencode.db
```

While `PRAGMA integrity_check` reports the database as "ok", there may be issues with:
- Large database size (107MB) causing performance issues
- Concurrent access conflicts
- WAL (Write-Ahead Logging) file corruption
- Session state bloat from repeated warm-up requests

## Proposed Solution

Switch from `opencode serve` to `opencode-sandbox serve` with the `--incognito` flag for ephemeral sessions.

### Benefits of opencode-sandbox

1. **Isolated environment**: Runs in Apptainer container with controlled filesystem access
2. **Ephemeral mode**: `--incognito` flag creates temporary scratch directories deleted on exit
3. **Fresh state**: Each AMI session starts with clean database (no accumulated cruft)
4. **Security**: Sandboxed execution prevents unintended filesystem access
5. **Already available**: Tool is installed at `/sdf/group/lcls/ds/dm/apps/dev/bin/opencode-sandbox`

### Trade-offs to Consider

#### Advantages of --incognito mode:
- ✅ No database corruption from previous sessions
- ✅ No accumulated state/cruft
- ✅ Predictable behavior (fresh start every time)
- ✅ Automatic cleanup on exit
- ✅ Smaller memory footprint (no 107MB database)

#### Disadvantages of --incognito mode:
- ❌ **No conversation history across AMI restarts**: Each time AMI GUI is closed and reopened, the graph builder starts fresh
- ❌ **Warmup cost repeated**: Cannot cache skill loading across sessions
- ❌ **No persistent learning**: Agent can't reference previous sessions

#### Alternative: Persistent sandbox (without --incognito)
- ✅ Keeps conversation history across AMI restarts
- ✅ Can reference previous graph building sessions
- ✅ Warmup cache survives restarts
- ❌ Still uses persistent database (may accumulate issues over time)
- ❌ Requires manual cleanup if corruption occurs

## Implementation Strategy

### Random Port Selection

**Return to random port allocation** (as in original implementation) instead of fixed port 4096:

**Why random ports:**
- ✅ Avoids conflicts with other services or stale AMI instances
- ✅ Safer for multi-user systems (each user gets different port)
- ✅ No cleanup needed if previous AMI crashed without releasing port
- ✅ Matches original design from commit 8856d3c4

**Port range: 49152-65535** (IANA ephemeral port range)
- Well-known ports: 0-1023 (avoid)
- Registered ports: 1024-49151 (avoid)
- Ephemeral ports: 49152-65535 (safe for temporary services)

**Implementation:**
```python
import random
opencode_port = random.randint(49152, 65535)
```

This is simpler than:
- ❌ Parsing stdout to get OS-assigned port (blocking/complexity)
- ❌ Using fixed port 4096 (port conflicts)
- ❌ Using port 0 and complex discovery mechanism

## Recommended Approach

**Use `opencode-sandbox --incognito serve` with random port** because:

1. **Session scope is appropriate**: Graph building is typically session-scoped (within one experiment)
   - Users don't usually need to reference graph building conversations from weeks ago
   - Current session history is maintained within the running AMI session
   - Only loses history when AMI GUI is fully closed/restarted

2. **Reliability > Convenience**: Fresh state prevents mysterious errors
   - Database corruption is hard to diagnose
   - Users won't know to run `opencode db` commands to fix issues
   - Better to start clean than debug corrupted state

3. **Warmup cost is acceptable**: 
   - Currently ~6s initial warmup (done in background)
   - Only happens once per AMI session startup
   - Small price for reliability

4. **Escape hatch available**: If persistent history becomes critical, we can:
   - Add a configuration option to disable `--incognito`
   - Document how to manually clean database if needed
   - Start with safety first, relax later if needed

## Implementation Plan

### Files to Modify

#### 1. `ami/client/flowchart.py` (lines 56-105)

**Current code:**
```python
# Use fixed port for easier debugging
opencode_port = 4096
opencode_url = f"http://127.0.0.1:{opencode_port}"
os.environ["OPENCODE_SERVER_URL"] = opencode_url
logger.debug(f"Starting OpenCode server on port {opencode_port}")
try:
    # Start server with visible output for debugging
    subprocess.Popen(
        ["opencode", "serve", "--port", str(opencode_port)],
        # Don't suppress output so we can see errors
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL,
    )
    logger.info(f"OpenCode server started at {opencode_url}")
```

**Original implementation (before fixed port):**
```python
# Start OpenCode server for AI graph builder
import random

opencode_port = random.randint(49152, 65535)
opencode_url = f"http://127.0.0.1:{opencode_port}"
os.environ["OPENCODE_SERVER_URL"] = opencode_url
logger.debug(f"Starting OpenCode server on port {opencode_port}")
try:
    subprocess.Popen(
        ["opencode", "serve", "--port", str(opencode_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info(f"OpenCode server started at {opencode_url}")
except Exception as e:
    logger.warning(f"Could not start OpenCode server: {e}")
```

**New code (opencode-sandbox + random port):**
```python
# Start OpenCode server for AI graph builder
import random

opencode_port = random.randint(49152, 65535)  # Ephemeral port range
opencode_url = f"http://127.0.0.1:{opencode_port}"
os.environ["OPENCODE_SERVER_URL"] = opencode_url
logger.debug(f"Starting OpenCode server on port {opencode_port}")
try:
    subprocess.Popen(
        [
            "opencode-sandbox",
            "--incognito",  # Ephemeral session (deleted on exit)
            "--",
            "serve",
            "--port", str(opencode_port)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info(f"OpenCode server started at {opencode_url}")
except Exception as e:
    logger.warning(f"Could not start OpenCode server: {e}")
```

**Changes needed:**
1. Replace fixed port `4096` with random port: `random.randint(49152, 65535)`
2. Replace `opencode` with `opencode-sandbox`
3. Add `--incognito` flag before `--` separator
4. Add `--` separator to distinguish sandbox args from opencode args
5. Restore `stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL` (suppress output)
6. Restore exception handling for graceful fallback

**Rationale for random port range:**
- 49152-65535 is the IANA ephemeral port range
- Avoids conflicts with well-known ports
- Same approach as original implementation
- Much simpler than parsing stdout (no blocking needed)

#### 2. `ami/flowchart/graph_builder.py` (line 52-65)

**Current code:**
```python
cmd = [
    "opencode",
    "run",
    "--attach",
    self.url,
    "--format",
    "json",
    "--dir",
    os.getcwd(),
]
```

**Decision: NO CHANGE NEEDED**

The client commands (`opencode run --attach`) don't need sandboxing because:
- They just connect to the existing server via HTTP
- No database access (server handles that)
- Short-lived processes (only run during graph building requests)
- No filesystem risk (working directory is the AMI repo)

### Testing Plan

#### 1. Basic Functionality Test
```bash
# Terminal 1: Start test server with random port
PORT=$(python3 -c "import random; print(random.randint(49152, 65535))")
opencode-sandbox --incognito -- serve --port $PORT &
SERVER_PID=$!

# Terminal 2: Test connection
opencode run --attach http://127.0.0.1:$PORT "hello"

# Cleanup
kill $SERVER_PID

# Verify: Response received successfully
```

#### 2. Integration Test with AMI
```bash
# Start AMI with modified code
ami-local -n 1 random://examples/worker.json

# In AMI console:
%bg show me a random source

# Verify:
# - Server starts without errors
# - Graph builder responds to request
# - Code executes successfully
```

#### 3. Database Cleanup Test
```bash
# Before starting AMI
ls /tmp/${USER}-opencode-sandbox-* 2>/dev/null || echo "No temp dirs"

# Start AMI, use graph builder
ami-local -n 1 random://examples/worker.json
# Use %bg commands...

# In another terminal (while AMI running)
ls /tmp/${USER}-opencode-sandbox-*
# Verify: Temp directory exists

# Exit AMI
# Verify: Temp directory deleted automatically
ls /tmp/${USER}-opencode-sandbox-* 2>/dev/null || echo "Cleaned up!"
```

#### 4. Session Continuity Test (within session)
```bash
# Start AMI
ami-local -n 1 random://examples/worker.json

# In console:
%bg create a scatter plot for laser vs detector

# Then (in same session):
%bg now filter that plot where laser > 5

# Verify: Agent remembers "that plot" from previous request
# (session continuity maintained within running AMI session)
```

#### 5. Cross-Session Test (verify no persistence)
```bash
# Session 1
ami-local -n 1 random://examples/worker.json
%bg create scatter plot named myplot
# Exit AMI

# Session 2
ami-local -n 1 random://examples/worker.json
%bg tell me about myplot

# Verify: Agent doesn't remember myplot (fresh session)
# This is EXPECTED with --incognito
```

### Exact Code Change (Diff)

**File:** `ami/client/flowchart.py` (lines 56-70)

```diff
     # Start OpenCode server for AI graph builder
-    # Use fixed port for easier debugging
-    opencode_port = 4096
+    import random
+
+    opencode_port = random.randint(49152, 65535)  # Ephemeral port range
     opencode_url = f"http://127.0.0.1:{opencode_port}"
     os.environ["OPENCODE_SERVER_URL"] = opencode_url
     logger.debug(f"Starting OpenCode server on port {opencode_port}")
     try:
-        # Start server with visible output for debugging
         subprocess.Popen(
-            ["opencode", "serve", "--port", str(opencode_port)],
-            # Don't suppress output so we can see errors
-            # stdout=subprocess.DEVNULL,
-            # stderr=subprocess.DEVNULL,
+            [
+                "opencode-sandbox",
+                "--incognito",  # Ephemeral session (deleted on exit)
+                "--",
+                "serve",
+                "--port", str(opencode_port)
+            ],
+            stdout=subprocess.DEVNULL,
+            stderr=subprocess.DEVNULL,
         )
         logger.info(f"OpenCode server started at {opencode_url}")
+    except Exception as e:
+        logger.warning(f"Could not start OpenCode server: {e}")
```

**Lines changed:** ~7 lines
**Complexity:** Low (single file, straightforward change)

### Rollback Plan

If issues arise, revert is simple:

```python
# Revert ami/client/flowchart.py to current state:
opencode_port = 4096
subprocess.Popen(
    ["opencode", "serve", "--port", str(opencode_port)],
)
```

No other changes needed - the rest of the code is unaffected.

### Documentation Updates

#### Update AMI Graph Builder docs

**File:** `.opencode/skills/ami-graph-builder/SKILL.md` or `USAGE_TIPS.md`

Add note about session scope:

```markdown
## Session Scope

The graph builder maintains conversation history within each AMI session.
When you close and restart AMI, the agent starts fresh with no memory
of previous sessions.

**Within a session:**
- ✅ Agent remembers previous requests
- ✅ You can refer back: "now filter that plot"
- ✅ Conversation context maintained

**Across sessions:**
- ❌ No memory of previous AMI sessions
- ❌ Fresh start each time AMI launches
- ✅ Clean state (no corrupted history)
```

## Alternative Approaches Considered

### Option 1: Fix database corruption directly
- **Rejected**: Root cause unclear, may recur
- **Rejected**: Users won't know how to diagnose/fix
- **Rejected**: Adds maintenance burden

### Option 2: Use opencode-sandbox without --incognito
- **Deferred**: Can try if --incognito proves too limiting
- **Deferred**: Still need to handle eventual corruption
- **Deferred**: Start with safest option first

### Option 3: Implement custom database cleanup
- **Rejected**: Overly complex
- **Rejected**: OpenCode already provides --incognito
- **Rejected**: Not our responsibility to manage OpenCode internals

### Option 4: Use separate database per AMI session
- **Rejected**: Requires modifying OpenCode configuration
- **Rejected**: Still need cleanup mechanism
- **Rejected**: --incognito already does this better

## Migration Steps

1. **Update code** in `ami/client/flowchart.py`
2. **Test locally** with test plan above
3. **Update documentation** about session scope
4. **Announce change** to users (if applicable)
5. **Monitor** for any issues with incognito mode

## Success Criteria

After implementation:
- ✅ OpenCode server starts successfully via opencode-sandbox
- ✅ Graph builder responds to requests
- ✅ No database corruption errors
- ✅ Temp directories cleaned up automatically on AMI exit
- ✅ Session continuity works within running AMI session
- ✅ Fresh state on each AMI restart

## Questions for User

Before implementing, please confirm:

1. **Session scope acceptable?** 
   - Is it OK that conversation history is lost when AMI restarts?
   - Or do you need persistent history across AMI sessions?

2. **Warmup cost acceptable?**
   - Currently ~6s warmup per AMI startup (done in background)
   - With --incognito, cannot cache across restarts
   - Is this acceptable?

3. **Sandbox overhead acceptable?**
   - Apptainer adds slight overhead (minimal, ~100ms startup)
   - Worth it for isolation and reliability?

4. **Fallback strategy?**
   - Should we add a flag to disable --incognito if needed?
   - Or is --incognito always the right choice?

5. **Testing scope?**
   - Test only with `ami-local` random source?
   - Or also test with real experiment data?

## Related Files

- **Primary:** `ami/client/flowchart.py` (server startup, lines 56-105)
- **Reference:** `ami/flowchart/graph_builder.py` (client connection, no changes)
- **Docs:** `.opencode/skills/ami-graph-builder/SKILL.md`
- **Docs:** `.opencode/skills/ami-graph-builder/USAGE_TIPS.md`
- **Tool:** `/sdf/group/lcls/ds/dm/apps/dev/bin/opencode-sandbox`

## Timeline

- **Planning**: 30 min (this document)
- **Implementation**: 15 min (1 file, 5 line change)
- **Testing**: 30 min (run through test plan)
- **Documentation**: 15 min (update session scope notes)
- **Total**: ~1.5 hours
