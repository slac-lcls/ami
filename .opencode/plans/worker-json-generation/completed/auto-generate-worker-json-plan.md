# Implementation Plan: Auto-Generate worker.json in ami-local

**Date:** 2026-03-25  
**Goal:** Automatically generate worker.json from .fc file when user runs `ami-local -l graph.fc` without specifying a data source  
**Approach:** Call existing `scripts/fc_to_worker_json.py` script as subprocess

---

## User Decisions

1. **Default event count:** 1000 events with repeat=True ✓
2. **Logging level:** INFO ✓
3. **Script not found:** Warn user ✓
4. **worker.json location:** Use temp file ✓

---

## Overview

### Current Behavior
```bash
# User must manually generate and specify worker.json
python scripts/fc_to_worker_json.py my_graph.fc
ami-local -n 3 static://worker.json -l my_graph.fc
```

### New Behavior
```bash
# Automatically generates worker.json from .fc file
ami-local -n 3 -l my_graph.fc

# Output:
#   INFO: No data source specified, auto-generating from my_graph.fc
#   INFO: Auto-generated static source with 4 sources
#   INFO: Starting ami-local using comm address: ...
```

### Backward Compatibility
```bash
# Explicit source still works (no auto-generation)
ami-local -n 3 static://worker.json -l my_graph.fc

# No .fc file (works as before)
ami-local -n 3 static://worker.json
```

---

## Implementation Details

### File to Modify

**File:** `ami/local.py`  
**Location:** Lines 329-337 (where source parsing happens)  
**Lines to modify:** ~40 lines total

### Current Code (lines 329-337)

```python
if args.source is not None:
    src_url_match = re.match('(?P<prot>.*)://(?P<body>.*)', args.source)
    if src_url_match:
        src_cfg = src_url_match.groups()
    else:
        logger.critical("Invalid data source config string: %s", args.source)
        return 1
else:
    src_cfg = None
```

### New Code

```python
if args.source is not None:
    # Explicit source provided - use it
    src_url_match = re.match('(?P<prot>.*)://(?P<body>.*)', args.source)
    if src_url_match:
        src_cfg = src_url_match.groups()
    else:
        logger.critical("Invalid data source config string: %s", args.source)
        return 1
        
elif args.load is not None:
    # No source specified, but loading .fc file - auto-generate
    logger.info("No data source specified, auto-generating from %s", args.load)
    
    try:
        # Find fc_to_worker_json.py script
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),  # ami/ -> project root
            'scripts', 'fc_to_worker_json.py'
        )
        
        if not os.path.exists(script_path):
            logger.warning("fc_to_worker_json.py not found at %s", script_path)
            logger.info("Continuing without data source. You can add SourceNodes in the GUI.")
            src_cfg = None
        else:
            # Create temp file for auto-generated worker.json
            import tempfile
            temp_worker = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False, prefix='ami_worker_'
            )
            temp_worker_path = temp_worker.name
            temp_worker.close()
            
            # Call script to generate worker.json
            import subprocess
            result = subprocess.run(
                [
                    sys.executable,  # Use same Python interpreter
                    script_path,
                    args.load,
                    '-o', temp_worker_path,
                    '-n', '1000',  # 1000 events for interactive use
                    # Note: repeat=True by default (not passing --no-repeat)
                ],
                capture_output=True,
                text=True,
                timeout=10  # 10 second timeout
            )
            
            if result.returncode == 0:
                # Success - use the generated config
                src_cfg = ('static', temp_worker_path)
                
                # Parse output to show detected sources
                # Script outputs: "Sources detected: N"
                import re
                match = re.search(r'Sources detected: (\d+)', result.stdout)
                if match:
                    num_sources = match.group(1)
                    logger.info("Auto-generated static source with %s sources", num_sources)
                else:
                    logger.info("Auto-generated static source")
                
                # Show source names at debug level
                logger.debug("Script output:\n%s", result.stdout)
            else:
                # Script failed - likely no sources in .fc file
                logger.warning("Could not auto-generate source from %s", args.load)
                if result.stderr:
                    logger.debug("Error: %s", result.stderr)
                logger.info("Continuing without data source. You can add SourceNodes in the GUI.")
                src_cfg = None
                
                # Clean up temp file
                try:
                    os.unlink(temp_worker_path)
                except:
                    pass
                    
    except subprocess.TimeoutExpired:
        logger.warning("Timeout while generating worker config")
        logger.info("Continuing without data source")
        src_cfg = None
    except Exception as e:
        logger.warning("Error during worker config auto-generation: %s", e)
        logger.info("Continuing without data source")
        src_cfg = None
        
else:
    # No source and no .fc file - continue without source
    src_cfg = None
```

### Cleanup Strategy

**When to clean up temp worker.json:**
- The temp file is created with `delete=False` so it persists
- Should be cleaned up when ami-local exits

**Options:**

A. **Register cleanup handler**
```python
import atexit

if src_cfg and src_cfg[0] == 'static' and 'ami_worker_' in src_cfg[1]:
    # Register cleanup for auto-generated file
    atexit.register(lambda: os.unlink(src_cfg[1]) if os.path.exists(src_cfg[1]) else None)
```

B. **Clean up in signal handler** (where procs are cleaned up)
```python
# In cleanup() function or _sig_handler()
# Add cleanup of temp worker.json
```

C. **Let OS clean up** (files in /tmp get cleaned eventually)
- Simpler but leaves files around

**Recommendation:** Option A - Use atexit to clean up temp file

---

## Step-by-Step Implementation

### Step 1: Add imports (if not already present)

**Location:** Top of `ami/local.py` (around line 1-20)

**Check if already imported:**
- `import tempfile` - Already imported (line 8) ✓
- `import subprocess` - Need to add
- `import atexit` - Need to add

**Add:**
```python
import subprocess
import atexit
```

### Step 2: Modify source parsing logic

**Location:** `ami/local.py` lines 329-337

**Replace existing code with new code shown above**

### Step 3: Add cleanup registration

**Location:** Right after setting `src_cfg` (around line 365)

**Add:**
```python
# After the if/elif/else block that sets src_cfg
if src_cfg and src_cfg[0] == 'static' and src_cfg[1].startswith('/tmp/ami_worker_'):
    # Register cleanup for auto-generated temp file
    temp_file_to_cleanup = src_cfg[1]
    atexit.register(lambda: _cleanup_temp_file(temp_file_to_cleanup))
```

### Step 4: Add cleanup helper function

**Location:** Near other helper functions (around line 232-239)

**Add:**
```python
def _cleanup_temp_file(filepath):
    """Clean up temporary worker.json file."""
    try:
        if os.path.exists(filepath):
            os.unlink(filepath)
            logger.debug("Cleaned up temporary file: %s", filepath)
    except Exception as e:
        logger.debug("Could not clean up temporary file %s: %s", filepath, e)
```

---

## Error Handling

### Case 1: Script not found

**Condition:** `scripts/fc_to_worker_json.py` doesn't exist

**Action:**
- Log warning: "fc_to_worker_json.py not found at {path}"
- Log info: "Continuing without data source. You can add SourceNodes in the GUI."
- Set `src_cfg = None`
- Continue normally

**User sees:**
```
WARNING: fc_to_worker_json.py not found at /path/to/scripts/fc_to_worker_json.py
INFO: Continuing without data source. You can add SourceNodes in the GUI.
INFO: Starting ami-local using comm address: ...
```

### Case 2: .fc file has no sources

**Condition:** Script runs but finds no SourceNodes

**Action:**
- Script exits with error code 1
- Log warning: "Could not auto-generate source from {file}"
- Log info: "Continuing without data source. You can add SourceNodes in the GUI."
- Set `src_cfg = None`
- Continue normally

**User sees:**
```
INFO: No data source specified, auto-generating from my_graph.fc
WARNING: Could not auto-generate source from my_graph.fc
INFO: Continuing without data source. You can add SourceNodes in the GUI.
INFO: Starting ami-local using comm address: ...
```

### Case 3: Script times out

**Condition:** Script takes >10 seconds (unlikely but possible)

**Action:**
- Catch `subprocess.TimeoutExpired`
- Log warning: "Timeout while generating worker config"
- Log info: "Continuing without data source"
- Set `src_cfg = None`

### Case 4: Unexpected error

**Condition:** Any other exception

**Action:**
- Catch general `Exception`
- Log warning: "Error during worker config auto-generation: {error}"
- Log info: "Continuing without data source"
- Set `src_cfg = None`

### Case 5: Script succeeds

**Condition:** Script exits with code 0

**Action:**
- Parse stdout to get number of sources
- Log info: "Auto-generated static source with N sources"
- Log debug: Full script output
- Set `src_cfg = ('static', temp_worker_path)`
- Register cleanup handler

**User sees:**
```
INFO: No data source specified, auto-generating from my_graph.fc
INFO: Auto-generated static source with 4 sources
INFO: Starting ami-local using comm address: ...
```

---

## Testing Plan

### Test 1: Normal case - .fc file with sources

**Setup:**
```bash
# Create or use existing .fc file with sources
cp tests/graphs/ATM_crix_new.fc /tmp/test_graph.fc
```

**Test:**
```bash
ami-local -n 3 -l /tmp/test_graph.fc
```

**Expected:**
- ✓ Logs: "Auto-generated static source with 4 sources"
- ✓ AMI starts successfully
- ✓ Sources are available (timing:raw:eventcodes, etc.)
- ✓ Temp file created in /tmp/ami_worker_*.json
- ✓ Temp file cleaned up on exit

### Test 2: Explicit source (backward compatibility)

**Test:**
```bash
python scripts/fc_to_worker_json.py /tmp/test_graph.fc -o /tmp/my_worker.json
ami-local -n 3 static:///tmp/my_worker.json -l /tmp/test_graph.fc
```

**Expected:**
- ✓ No auto-generation happens
- ✓ Uses explicit source
- ✓ Works exactly as before

### Test 3: .fc file with no sources

**Setup:**
```bash
# Create .fc file with no SourceNodes
echo '{"nodes": [], "connects": []}' > /tmp/empty_graph.fc
```

**Test:**
```bash
ami-local -n 3 -l /tmp/empty_graph.fc
```

**Expected:**
- ✓ Logs: "Could not auto-generate source from /tmp/empty_graph.fc"
- ✓ Logs: "Continuing without data source. You can add SourceNodes in the GUI."
- ✓ AMI starts without source
- ✓ User can add sources in GUI

### Test 4: No .fc file (backward compatibility)

**Test:**
```bash
ami-local -n 3 static:///tmp/my_worker.json
```

**Expected:**
- ✓ No auto-generation happens
- ✓ Works exactly as before
- ✓ No changes to existing behavior

### Test 5: Script not found

**Setup:**
```bash
# Temporarily rename script
mv scripts/fc_to_worker_json.py scripts/fc_to_worker_json.py.bak
```

**Test:**
```bash
ami-local -n 3 -l /tmp/test_graph.fc
```

**Expected:**
- ✓ Logs: "fc_to_worker_json.py not found at ..."
- ✓ Logs: "Continuing without data source. You can add SourceNodes in the GUI."
- ✓ AMI starts without source

**Cleanup:**
```bash
mv scripts/fc_to_worker_json.py.bak scripts/fc_to_worker_json.py
```

### Test 6: Debug logging

**Test:**
```bash
ami-local -n 3 -l /tmp/test_graph.fc --log-level DEBUG
```

**Expected:**
- ✓ Shows full script output at DEBUG level
- ✓ Shows detected source names

### Test 7: Cleanup verification

**Test:**
```bash
# Start ami-local
ami-local -n 3 -l /tmp/test_graph.fc &
PID=$!

# Check temp file exists
ls /tmp/ami_worker_*.json

# Kill ami-local
kill $PID

# Wait a moment
sleep 1

# Check temp file was cleaned up
ls /tmp/ami_worker_*.json  # Should be gone
```

**Expected:**
- ✓ Temp file exists while running
- ✓ Temp file deleted after exit

---

## Documentation Updates

### Update 1: ami-local help text

**Location:** `ami/local.py` line 175

**Current:**
```python
help='data source configuration (exampes: static://test.json, psana://exp=xcsdaq13:run=14)'
```

**New:**
```python
help='data source configuration (examples: static://test.json, psana://exp=xcsdaq13:run=14). '
     'If omitted and -l/--load is specified, worker.json will be auto-generated from the .fc file.'
```

### Update 2: README or user guide

**Add section:**
```markdown
## Auto-Generated Data Sources

When loading a .fc flowchart file without specifying a data source, AMI will automatically
generate a static data source configuration based on the SourceNodes in the flowchart.

Example:
```bash
# Automatically generates worker.json from graph sources
ami-local -n 3 -l my_graph.fc

# Equivalent to:
python scripts/fc_to_worker_json.py my_graph.fc
ami-local -n 3 static://worker.json -l my_graph.fc
```

The auto-generated source will:
- Generate 1000 events by default
- Repeat indefinitely (loop back to start)
- Use static/random data matching the types in your .fc file

If your .fc file has no SourceNodes, AMI will start without a data source and you can
add SourceNodes through the GUI.
```

---

## Code Review Checklist

Before implementation, verify:

- [ ] Imports added: `subprocess`, `atexit`
- [ ] Script path calculation correct (relative to ami module)
- [ ] Temp file created with appropriate prefix/suffix
- [ ] Timeout set (10 seconds)
- [ ] All error cases handled gracefully
- [ ] Cleanup registered with atexit
- [ ] Backward compatibility preserved
- [ ] Logging at appropriate levels (INFO/WARNING/DEBUG)
- [ ] Help text updated
- [ ] No breaking changes to existing functionality

---

## Edge Cases

### Edge Case 1: Multiple invocations

**Scenario:** User runs ami-local twice with same .fc file

**Behavior:** Each creates its own temp file, cleans up on exit

**OK:** ✓ No conflicts

### Edge Case 2: Script path on Windows

**Scenario:** Running on Windows (unlikely for LCLS)

**Behavior:** `os.path.join` handles path separators correctly

**OK:** ✓ Should work

### Edge Case 3: Relative vs absolute .fc path

**Scenario:** `ami-local -l graphs/test.fc` vs `ami-local -l /abs/path/test.fc`

**Behavior:** Script receives path as-is, handles both

**OK:** ✓ Script already handles this

### Edge Case 4: Concurrent ami-local instances

**Scenario:** Multiple ami-local processes with auto-generation

**Behavior:** Each gets unique temp file (tempfile.NamedTemporaryFile with prefix)

**OK:** ✓ No conflicts

### Edge Case 5: .fc file updated while running

**Scenario:** User modifies .fc file after ami-local starts

**Behavior:** No impact - worker.json already generated

**OK:** ✓ Expected behavior

---

## Performance Impact

### Overhead

- **Script execution time:** ~100-500ms (parsing .fc, writing JSON)
- **Total startup delay:** <1 second
- **Acceptable:** ✓ Yes - one-time cost at startup

### Resource Usage

- **Temp file size:** ~1-5 KB (small JSON file)
- **Memory:** Negligible (subprocess)
- **Disk I/O:** Minimal (one temp file write)
- **Impact:** ✓ Negligible

---

## Risks and Mitigations

### Risk 1: Script not found in deployment

**Risk:** Script missing in installed package

**Mitigation:**
- Graceful fallback (warn, continue without source)
- User can still use explicit source
- Could add to setup.py if needed

**Severity:** Low (graceful degradation)

### Risk 2: Script has bugs

**Risk:** Script generates invalid worker.json

**Mitigation:**
- Script already tested and working
- Static source validates config
- Worker will error if config invalid
- User can see error and fix

**Severity:** Low (existing script is stable)

### Risk 3: Temp file not cleaned up

**Risk:** Disk fills with temp files over time

**Mitigation:**
- atexit handler cleans up
- Files in /tmp cleaned by OS periodically
- Unique names prevent conflicts

**Severity:** Very low

### Risk 4: Breaking existing workflows

**Risk:** Auto-generation interferes with existing usage

**Mitigation:**
- Only activates when no source specified
- Explicit source takes precedence
- Fully backward compatible
- If it fails, falls back to old behavior

**Severity:** Very low (backward compatible)

---

## Success Criteria

After implementation, verify:

1. ✓ `ami-local -l graph.fc` auto-generates worker.json and works
2. ✓ Logs clearly show what's happening
3. ✓ Temp file cleaned up on exit
4. ✓ Explicit source still works (backward compat)
5. ✓ No source + no .fc file works (backward compat)
6. ✓ Error cases handled gracefully
7. ✓ All 7 test cases pass

---

## Implementation Checklist

### Phase 1: Code Changes

- [ ] Add imports (`subprocess`, `atexit`)
- [ ] Add `_cleanup_temp_file()` helper function
- [ ] Modify source parsing logic (lines 329-337)
- [ ] Add cleanup registration (after src_cfg is set)
- [ ] Update help text

### Phase 2: Testing

- [ ] Test normal case (with sources)
- [ ] Test explicit source (backward compat)
- [ ] Test no sources in .fc file
- [ ] Test no .fc file (backward compat)
- [ ] Test script not found
- [ ] Test debug logging
- [ ] Test cleanup on exit

### Phase 3: Documentation

- [ ] Update help text
- [ ] Add README section
- [ ] Update user guide (if exists)

### Phase 4: Review

- [ ] Code review checklist complete
- [ ] All tests passing
- [ ] No breaking changes
- [ ] Performance acceptable

---

## Estimated Timeline

- **Phase 1 (Code):** 1 hour
- **Phase 2 (Testing):** 30 minutes
- **Phase 3 (Documentation):** 15 minutes
- **Phase 4 (Review):** 15 minutes

**Total: ~2 hours**

---

## Summary

This plan implements auto-generation of worker.json by:
1. Calling existing `scripts/fc_to_worker_json.py` as subprocess
2. Using temp file for generated config
3. Cleaning up on exit with atexit
4. Graceful error handling
5. Full backward compatibility

**Benefits:**
- ✅ Reduces user steps from 2-3 → 1
- ✅ Reuses existing, tested code
- ✅ Backward compatible
- ✅ Simple implementation
- ✅ Low risk

**User experience:**
```bash
# Before: 2 commands
python scripts/fc_to_worker_json.py graph.fc
ami-local -n 3 static://worker.json -l graph.fc

# After: 1 command
ami-local -n 3 -l graph.fc
```

Ready for implementation!
