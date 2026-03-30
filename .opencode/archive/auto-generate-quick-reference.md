# Quick Reference: Auto-Generate Worker Config

## TL;DR

```bash
# Old way (2 commands):
python scripts/fc_to_worker_json.py graph.fc
ami-local -n 3 static://worker.json -l graph.fc

# New way (1 command):
ami-local -n 3 -l graph.fc
```

---

## `ami-fc-to-source` Command

### Basic Usage
```bash
# Generate worker.json (random source by default)
ami-fc-to-source graph.fc

# Generate for static source
ami-fc-to-source graph.fc --source-type static

# Custom output and options
ami-fc-to-source graph.fc -o my_config.json -n 1000

# Just show detected sources
ami-fc-to-source graph.fc --show-sources
```

### Arguments
- `fc_file` - Path to .fc flowchart file (required)
- `-o, --output` - Output file (default: worker.json)
- `-n, --num-events` - Number of events (default: 100)
- `--no-repeat` - Don't loop events
- `--interval` - Time between events (default: 0.01s)
- `--init-time` - Initial wait time (default: 0.1s)
- `--show-sources` - Show detected sources and exit
- `--source-type` - Source type: `static` or `random` (default: `random`)

---

## `ami-local` Auto-Generation

### Auto-Generate (No Explicit Source)
```bash
# Auto-generate with random source (default)
ami-local -n 3 -l graph.fc

# Auto-generate with static source
ami-local -n 3 -l graph.fc --source-type static
```

### Explicit Source (No Auto-Generation)
```bash
# Use existing worker.json
ami-local -n 3 static://worker.json -l graph.fc
ami-local -n 3 random://worker.json -l graph.fc

# Use psana
ami-local -n 3 psana://exp=xcsdaq13:run=14 -l graph.fc
```

### When Auto-Generation Happens
- ✅ `ami-local -l graph.fc` (no source specified)
- ❌ `ami-local static://config.json -l graph.fc` (explicit source)
- ❌ `ami-local -l graph.fc` (no sources in .fc file - logs warning, continues)

---

## Source Types

### Random Source (`random://`)
**Default for auto-generation**
- Generates randomized values
- Scalars: random values in configured range
- Images/Waveforms: Gaussian noise (pedestal ± width)
- **Use for:** Algorithm testing, realistic data, interactive exploration

### Static Source (`static://`)
- Generates constant values (all 1s)
- Deterministic behavior
- **Use for:** Testing graph structure, debugging connections

---

## Examples

### Example 1: Quick Interactive Testing
```bash
# Just load a .fc file - auto-generates random data
ami-local -l my_analysis.fc
```

### Example 2: Generate Config for Later Use
```bash
# Generate config once
ami-fc-to-source my_analysis.fc -o my_config.json -n 5000

# Use it multiple times
ami-local -n 3 random://my_config.json -l my_analysis.fc
```

### Example 3: Compare Static vs Random
```bash
# Test with static data (all 1s)
ami-local -l graph.fc --source-type static

# Test with random data (varied values)
ami-local -l graph.fc --source-type random
```

### Example 4: Inspect Sources
```bash
# See what sources are in a .fc file
ami-fc-to-source my_graph.fc --show-sources
```

---

## What Gets Auto-Generated

### Source Type Mapping
| .fc Source Type | Worker Config |
|-----------------|---------------|
| Array2d | Image (512x512, pedestal=5, width=1) |
| Array1d | Waveform (length=1024) |
| Array3d | Image (100x512x512) |
| int | Scalar (range=[0,100], integer) |
| float | Scalar (range=[0.0,100.0]) |
| Other | Scalar (range=[0,100]) |

### Default Parameters
- **Events:** 1000 (for ami-local auto-gen), 100 (for ami-fc-to-source)
- **Repeat:** True (loops forever)
- **Interval:** 0.01s between events
- **Init time:** 0.1s initial wait

---

## Troubleshooting

### No sources detected
```bash
$ ami-local -l graph.fc
# Output: "No source nodes found in graph.fc"
# Result: Continues without source, can add sources in GUI
```

### Want to use explicit source
```bash
# Just provide the source argument
ami-local -n 3 static://config.json -l graph.fc
# Auto-generation is skipped
```

### Want different event count
```bash
# For ami-fc-to-source: use -n flag
ami-fc-to-source graph.fc -n 10000

# For ami-local: use ami-fc-to-source first, then load config
ami-fc-to-source graph.fc -n 10000 -o config.json
ami-local -n 3 random://config.json -l graph.fc
```

---

## Migration from Old Script

### Old Script Location
`scripts/fc_to_worker_json.py` **[DELETED]**

### New Command
`ami-fc-to-source` (entry point)

### Update Your Scripts
```bash
# Before:
python scripts/fc_to_worker_json.py graph.fc

# After:
ami-fc-to-source graph.fc
```

### Reinstall Required
```bash
pip install -e .
```

---

## Technical Notes

### How It Works
1. Reads .fc file and extracts SourceNodes
2. Maps amitypes to worker config (Image, Waveform, Scalar, etc.)
3. Returns `(source_type, config_dict)` tuple
4. ami-local passes dict directly to workers (no temp files!)

### Why No Temp Files?
Workers already support receiving dict via `source[1]`:
```python
if isinstance(source[1], dict):
    src_cfg = source[1]
```

### Performance
- No subprocess overhead
- No file I/O for auto-generation
- Instant startup

---

## Quick Command Reference

```bash
# Show help
ami-fc-to-source --help
ami-local --help

# Generate worker.json
ami-fc-to-source graph.fc                    # random (default)
ami-fc-to-source graph.fc --source-type static

# Auto-generate in ami-local
ami-local -l graph.fc                         # random (default)
ami-local -l graph.fc --source-type static

# Show sources
ami-fc-to-source graph.fc --show-sources

# Explicit source (no auto-gen)
ami-local -n 3 random://config.json -l graph.fc
```
