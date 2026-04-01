# OpenCode Database Cleanup Solution

## Problem

The OpenCode server database was growing large (107MB) and potentially causing corruption issues. The initial plan was to use `opencode-sandbox --incognito` for ephemeral sessions, but this encountered a user ID issue with the Apptainer container:

```
FATAL: Couldn't determine user account information: user: unknown userid 16163
```

## Root Cause

The sandboxed container uses `--containall` which requires user information from `/etc/passwd`, but the numeric UID 16163 is not in that database (LDAP/external authentication setup).

## Final Solution

Instead of using the sandbox, implement automatic database cleanup:

**Approach: Detect and delete large databases at startup**

1. Check database size before starting OpenCode server
2. If > 100MB, delete the database and WAL files
3. Server starts fresh with clean state
4. Return to random port allocation (as originally designed)

### Implementation

**File:** `ami/client/flowchart.py` (lines 56-95)

```python
# Start OpenCode server for AI graph builder
import random

opencode_port = random.randint(49152, 65535)  # Ephemeral port range
opencode_url = f"http://127.0.0.1:{opencode_port}"
os.environ["OPENCODE_SERVER_URL"] = opencode_url
logger.debug(f"Starting OpenCode server on port {opencode_port}")

# Clean up database if it's too large (prevents corruption from accumulation)
try:
    db_path_result = subprocess.run(
        ["opencode", "db", "path"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,  # Python 3.6 compatible
        timeout=2,
    )
    if db_path_result.returncode == 0:
        db_path = db_path_result.stdout.strip()
        if os.path.exists(db_path):
            db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
            if db_size_mb > 100:  # If larger than 100MB
                logger.info(
                    f"OpenCode database is {db_size_mb:.1f}MB, removing to prevent corruption"
                )
                os.remove(db_path)
                # Also remove WAL files
                for suffix in ["-shm", "-wal"]:
                    wal_file = db_path + suffix
                    if os.path.exists(wal_file):
                        os.remove(wal_file)
except Exception as e:
    logger.debug(f"Could not check/clean OpenCode database: {e}")

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

## Benefits

1. **Automatic maintenance**: No manual intervention needed
2. **Prevents corruption**: Large databases are pruned automatically  
3. **Random ports**: Avoids conflicts with stale servers
4. **Simple**: No container/sandbox complexity
5. **Python 3.6 compatible**: Uses `universal_newlines` instead of `text`
6. **Graceful degradation**: Failures to clean DB don't block server startup

## Trade-offs

- ❌ Not truly ephemeral (database persists between runs under 100MB)
- ✅ But 100MB threshold prevents corruption issues
- ✅ Conversation history preserved across AMI restarts (as long as DB < 100MB)
- ✅ No container user ID issues

## Why 100MB Threshold?

- Current database was 107MB (too large)
- Fresh database is ~few KB
- Typical session should be < 10MB
- 100MB indicates many accumulated sessions
- Conservative enough to allow multi-day experiments

## Alternative Approaches Considered

### 1. opencode-sandbox --incognito (REJECTED)
**Reason**: User ID 16163 not in container's /etc/passwd

**Error:**
```
FATAL: Couldn't determine user account information: user: unknown userid 16163
```

**Fix would require**: Modifying container or LDAP setup (not practical)

### 2. opencode-sandbox --no-sandbox (REJECTED)
**Reason**: Just calls regular `opencode`, no incognito mode available

**Would be equivalent to**: Regular `opencode` (no benefit)

### 3. Manual database cleanup script (REJECTED)
**Reason**: Requires user intervention, easy to forget

**Better**: Automatic cleanup at startup

### 4. Delete database every time (REJECTED)
**Reason**: Loses conversation history unnecessarily

**Better**: Only delete when too large

## Testing

The changes restore the original random port approach and add database cleanup:

```bash
# Check database size
opencode db path
ls -lh /sdf/scratch/users/s/seshu/seshu-opencode-sandbox/home/.local/share/opencode/

# Start AMI - will clean DB if > 100MB
ami-local -n 1 random://examples/worker.json

# Verify OpenCode server started
# Check logs for "OpenCode database is ...MB, removing" message (if cleaned)
# Or "OpenCode server started at http://127.0.0.1:<port>" (random port)

# Test graph builder
%bg create a scatter plot
```

## Migration from Fixed Port

**Before:**
```python
opencode_port = 4096  # Fixed port for debugging
```

**After:**
```python
opencode_port = random.randint(49152, 65535)  # Random port (original design)
```

This matches the original implementation from commit 8856d3c4, before the fixed port was added for debugging.

## Files Modified

- **ami/client/flowchart.py** (lines 56-95): Add database cleanup and random port
- **test_opencode_sandbox.py**: Test script (not used, sandbox approach abandoned)

## Success Criteria

- ✅ OpenCode server starts with random port
- ✅ Large databases automatically cleaned
- ✅ No "unknown userid" errors
- ✅ Graph builder works normally
- ✅ Python 3.6 compatible

## Future Improvements

If database growth continues to be an issue:

1. **Lower threshold**: Change from 100MB to 50MB or 20MB
2. **Age-based cleanup**: Delete databases older than X days
3. **Session isolation**: Use separate databases per AMI instance
4. **Fix container**: Work with sysadmin to fix Apptainer user ID issue

For now, the 100MB threshold + automatic cleanup should prevent corruption issues while preserving reasonable conversation history.
