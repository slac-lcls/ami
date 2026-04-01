# Final Implementation Plan: Auto-Generate Worker Config (Dict-Passing Approach)

**Date:** 2026-03-25  
**Goal:** Auto-generate worker config when running `ami-local -l graph.fc` without a data source  
**Approach:** Move script to `ami/fc_to_worker.py`, add entry point, pass dict directly (no temp files!)

---

## Key Features

1. ✅ Move `scripts/fc_to_worker_json.py` → `ami/fc_to_worker.py`
2. ✅ Add `ami-fc-to-source` entry point
3. ✅ Add `--source-type` flag (choices: `static`, `random`)
4. ✅ Default to `random` source (more interesting data)
5. ✅ Pass config dict directly to workers (no temp files, no cleanup!)
6. ✅ ~30 lines of clean code

---

## Implementation Steps

### Step 1: Create `ami/fc_to_worker.py` Module

**Action:** Move `scripts/fc_to_worker_json.py` → `ami/fc_to_worker.py`

**Key Changes:**

1. **Update `generate_worker_json()` to return tuple:**
```python
def generate_worker_json(fc_path, num_events=100, repeat=True, 
                        interval=0.01, init_time=0.1, source_type='random'):
    """
    Generate worker configuration from .fc file.
    
    Args:
        fc_path: Path to .fc file
        num_events: Number of events to generate (default: 100)
        repeat: Whether to loop events (default: True)
        interval: Time between events in seconds (default: 0.01)
        init_time: Initial wait time in seconds (default: 0.1)
        source_type: Type of source - 'static' or 'random' (default: 'random')
        
    Returns:
        tuple: (source_type, worker_config_dict)
    """
    source_config = extract_sources_from_fc(fc_path)
    
    if not source_config:
        print(f"Warning: No source nodes found in {fc_path}", file=sys.stderr)
        print("The .fc file may not have any SourceNode entries.", file=sys.stderr)
    
    worker_json = {
        "interval": interval,
        "init_time": init_time,
        "bound": num_events,
        "repeat": repeat,
        "files": "data.xtc2",
        "config": source_config
    }
    
    return source_type, worker_json
```

2. **Add `--source-type` argument:**
```python
parser.add_argument(
    '--source-type',
    type=str,
    choices=['static', 'random'],
    default='random',
    help='Type of source to generate for (default: random). '
         'static: constant values (all 1s), random: randomized values based on ranges'
)
```

3. **Update main() to use source_type:**
```python
# Generate worker.json
source_type, worker_json = generate_worker_json(
    fc_path,
    num_events=args.num_events,
    repeat=not args.no_repeat,
    interval=args.interval,
    init_time=args.init_time,
    source_type=args.source_type
)

# Write output
output_path = Path(args.output)
with open(output_path, 'w') as f:
    json.dump(worker_json, f, indent=2)

# Print summary
print(f"✓ Generated {args.output} (for {source_type} source)")
print(f"  Sources detected: {len(source_config)}")
for name, config in source_config.items():
    dtype = config.get('dtype', 'unknown')
    print(f"    - {name:30s} ({dtype})")
print(f"  Events: {args.num_events}")
print(f"  Repeat: {not args.no_repeat}")
print()
print("To use with ami-local:")
print(f"  ami-local -n 3 {source_type}://{args.output} -l {args.fc_file}")
```

4. **Keep all existing functions:**
   - `extract_sources_from_fc(fc_path)`
   - `map_amitypes_to_config(ttype)`
   - All other existing functionality

---

### Step 2: Update `setup.py`

**File:** `setup.py` line 54-67

**Add new entry point:**
```python
entry_points={
    'console_scripts': [
        'ami-worker = ami.worker:main',
        'ami-manager = ami.manager:main',
        'ami-node = ami.collector:node_main',
        'ami-global = ami.collector:global_main',
        'ami-client = ami.client:main',
        'ami-console = ami.console:main',
        'ami-local = ami.local:main',
        'ami-remote = ami.remote:main',
        'ami-export = ami.export:main',
        'ami-syncer = ami.sync:main',
        'ami-monitor = ami.monitor:main',
        'ami-fc-to-source = ami.fc_to_worker:main',  # NEW
    ]
},
```

---

### Step 3: Update `ami/local.py`

**Add import** (around line 26):
```python
from ami.fc_to_worker import generate_worker_json
```

**Add `--source-type` argument** (around line 100-150):
```python
parser.add_argument(
    '--source-type',
    type=str,
    choices=['static', 'random'],
    default='random',
    help='Type of auto-generated source when loading .fc without explicit source '
         '(default: random). static: constant values, random: varied data'
)
```

**Replace source parsing logic** (lines 329-337):
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
        # Generate worker config directly (returns tuple: source_type, config)
        source_type, worker_config = generate_worker_json(
            args.load,
            num_events=1000,
            repeat=True,
            interval=0.01,
            init_time=0.1,
            source_type=args.source_type
        )
        
        if not worker_config.get('config'):
            # No sources found in .fc file
            logger.warning("No source nodes found in %s", args.load)
            logger.info("Continuing without data source. You can add SourceNodes in the GUI.")
            src_cfg = None
        else:
            # Pass the config dict directly to workers (no temp file needed!)
            src_cfg = (source_type, worker_config)
            num_sources = len(worker_config['config'])
            logger.info("Auto-generated %s source with %d sources", source_type, num_sources)
            
    except FileNotFoundError:
        logger.error("Flowchart file not found: %s", args.load)
        return 1
    except json.JSONDecodeError as e:
        logger.error("Invalid .fc file format: %s", e)
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

**Update help text** (line 175):
```python
help='data source configuration (examples: static://test.json, random://test.json, '
     'psana://exp=xcsdaq13:run=14). If omitted and -l/--load is specified, worker '
     'config will be auto-generated from the .fc file.'
```

**Note:** No cleanup helper function needed! Workers receive dict directly via `source[1]` (see `ami/worker.py:322-323`).

---

### Step 4: Remove old script

**Action:** Delete `scripts/fc_to_worker_json.py`

---

## Why Dict-Passing Works

In `ami/worker.py` lines 322-323:
```python
if isinstance(source[1], dict):
    src_cfg = source[1]
```

The worker already supports receiving a dict directly instead of a file path. This means:
- ✅ No temp file creation
- ✅ No file I/O overhead
- ✅ No cleanup logic needed
- ✅ Simpler, cleaner code

---

## User Experience Examples

### Auto-generation with ami-local

```bash
# Auto-generate with random source (default)
ami-local -n 3 -l graph.fc
# Output: "Auto-generated random source with 4 sources"

# Auto-generate with static source
ami-local -n 3 -l graph.fc --source-type static
# Output: "Auto-generated static source with 4 sources"
```

### CLI tool usage

```bash
# Generate for random source (default)
ami-fc-to-source graph.fc
# Outputs worker.json, displays: "✓ Generated worker.json (for random source)"

# Generate for static source
ami-fc-to-source graph.fc --source-type static

# Custom options
ami-fc-to-source graph.fc -o my_worker.json -n 100 --source-type random

# Then use manually
ami-local -n 3 random://my_worker.json -l graph.fc
```

---

## Static vs Random Sources

### Static Source (`static://`)
- **Data:** All constant values (1s)
- **Use case:** Testing graph structure, debugging connections
- **Performance:** Deterministic, reproducible

### Random Source (`random://`)  
- **Data:** Randomized values based on configured ranges
  - Scalars: Random values in specified range
  - Images: Gaussian noise (pedestal ± width)
  - Waveforms: Random waveforms
- **Use case:** Testing algorithms, realistic data flow, interactive exploration
- **Performance:** More interesting for development

**Default choice:** `random` for auto-generation (more realistic data).

---

## Arguments for `ami-fc-to-source`

### Positional
- `fc_file` - Path to .fc flowchart file

### Optional
- `-o`, `--output` - Output file (default: `worker.json`)
- `-n`, `--num-events` - Number of events (default: `100`)
- `--no-repeat` - Don't loop events
- `--interval` - Time between events in seconds (default: `0.01`)
- `--init-time` - Initial wait time in seconds (default: `0.1`)
- `--show-sources` - Show detected sources and exit
- `--source-type` - Source type: `static` or `random` (default: `random`) **[NEW]**

---

## Testing Plan

### Test 1: Auto-generate with random source (default)
```bash
ami-local -n 3 -l tests/graphs/ATM_crix_new.fc
```
**Expected:**
- Logs: "Auto-generated random source with 4 sources"
- AMI starts successfully
- Data varies (not all 1s)

### Test 2: Auto-generate with static source
```bash
ami-local -n 3 -l tests/graphs/ATM_crix_new.fc --source-type static
```
**Expected:**
- Logs: "Auto-generated static source with 4 sources"
- AMI starts successfully
- Data is constant (all 1s)

### Test 3: CLI tool - random source
```bash
ami-fc-to-source tests/graphs/ATM_crix_new.fc
cat worker.json  # Verify format
ami-local -n 3 random://worker.json -l tests/graphs/ATM_crix_new.fc
```
**Expected:**
- worker.json created
- Message shows "for random source"
- Works with random:// URL

### Test 4: CLI tool - static source
```bash
ami-fc-to-source tests/graphs/ATM_crix_new.fc --source-type static
ami-local -n 3 static://worker.json -l tests/graphs/ATM_crix_new.fc
```
**Expected:**
- worker.json created
- Message shows "for static source"
- Works with static:// URL

### Test 5: Explicit source (backward compat)
```bash
ami-local -n 3 random://worker.json -l test.fc
```
**Expected:** No auto-generation, uses explicit source

### Test 6: No sources in .fc
```bash
echo '{"nodes": [], "connects": []}' > /tmp/empty_graph.fc
ami-local -n 3 -l /tmp/empty_graph.fc
```
**Expected:** Warning, continues without source

### Test 7: Invalid .fc file
```bash
ami-local -n 3 -l /nonexistent.fc
```
**Expected:** Error message, graceful failure

### Test 8: Show sources flag
```bash
ami-fc-to-source tests/graphs/ATM_crix_new.fc --show-sources
```
**Expected:** Lists detected sources, exits without creating file

---

## Files Modified Summary

### 1. NEW: `ami/fc_to_worker.py` 
**Source:** Move from `scripts/fc_to_worker_json.py`

**Changes:**
- Add `--source-type` argument (choices: static, random, default: random)
- Update `generate_worker_json()` to return `(source_type, config)` tuple
- Update output messages to show source type
- Keep all existing functions unchanged

### 2. MODIFY: `ami/local.py` (~40 lines)
**Changes:**
- Add import: `from ami.fc_to_worker import generate_worker_json`
- Add `--source-type` argument (default: random)
- Add auto-generation logic (lines 329-337 → ~40 lines)
- Pass dict directly: `src_cfg = (source_type, worker_config)`
- Update help text for `source` argument

**No cleanup logic needed!**

### 3. MODIFY: `setup.py` (1 line)
**Changes:**
- Add entry point: `'ami-fc-to-source = ami.fc_to_worker:main'`

### 4. DELETE: `scripts/fc_to_worker_json.py`
**Action:** Remove old script

---

## Code Size Comparison

### Original Plan (Subprocess + Temp File)
- ~80 lines of code
- Imports: subprocess, tempfile, atexit, json
- Subprocess overhead
- File I/O operations
- Cleanup helper function

### Original Plan (Temp File Only)
- ~60 lines of code
- Imports: tempfile, atexit, json
- File I/O operations
- Cleanup helper function

### Final Plan (Dict Passing)
- **~30 lines of code**
- Imports: Just `generate_worker_json`
- No file I/O
- No cleanup needed
- Clean and simple!

---

## Benefits

✅ **Simplest approach:** Pass dict directly, no temp files  
✅ **Minimal code:** ~30 lines vs ~60-80 lines  
✅ **Fewer imports:** No tempfile, atexit, or json needed  
✅ **No cleanup:** Workers receive dict directly  
✅ **Faster:** No file I/O overhead  
✅ **More realistic:** Random data by default  
✅ **Flexible:** Both static and random supported  
✅ **Consistent:** Follows AMI entry point pattern  
✅ **User-friendly:** 1 command instead of 2  

---

## Migration Notes

**Users need to:**
1. Reinstall AMI: `pip install -e .`
2. Update workflows:
   - Old: `python scripts/fc_to_worker_json.py graph.fc`
   - New: `ami-fc-to-source graph.fc`

**Breaking changes:**
- `scripts/fc_to_worker_json.py` removed
- Must use `ami-fc-to-source` CLI tool

---

## Implementation Checklist

### Phase 1: Code Changes
- [ ] Move `scripts/fc_to_worker_json.py` → `ami/fc_to_worker.py`
- [ ] Add `--source-type` argument to `ami/fc_to_worker.py`
- [ ] Update `generate_worker_json()` to return tuple
- [ ] Update output messages in `ami/fc_to_worker.py`
- [ ] Add entry point to `setup.py`
- [ ] Add import to `ami/local.py`
- [ ] Add `--source-type` argument to `ami/local.py`
- [ ] Add auto-generation logic to `ami/local.py`
- [ ] Update help text in `ami/local.py`
- [ ] Delete `scripts/fc_to_worker_json.py`

### Phase 2: Testing
- [ ] Test auto-generate with random (default)
- [ ] Test auto-generate with static
- [ ] Test CLI tool with random
- [ ] Test CLI tool with static
- [ ] Test explicit source (backward compat)
- [ ] Test no sources in .fc
- [ ] Test invalid .fc file
- [ ] Test `--show-sources` flag

### Phase 3: Validation
- [ ] Verify no temp files created
- [ ] Verify no cleanup code needed
- [ ] Verify backward compatibility
- [ ] Verify error handling
- [ ] Run all tests

---

## Summary

This plan implements auto-generation by:
1. Moving script to `ami/fc_to_worker.py` as proper module
2. Adding `ami-fc-to-source` entry point
3. Adding `--source-type` flag (static/random, default: random)
4. Passing config dict directly to workers (no temp files!)
5. ~30 lines of clean, simple code

**Key insight:** Workers already support dict input via `source[1]`, so no temp files or cleanup needed!

**Ready for implementation!**
