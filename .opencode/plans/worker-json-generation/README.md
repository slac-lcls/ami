# Worker JSON Generation

Automatic worker configuration file generation from `.fc` (flowchart) files.

## Current Status: NEEDS REIMPLEMENTATION

Previously implemented in commit b80ad6e but needs to be redone. The feature was removed or lost during subsequent refactoring.

## Quick Start

**Start here**: `active/01-reimplement-worker-json.md`

This plan rebuilds the worker JSON auto-generation feature based on the original design document.

## Execution Order

1. ❌ **01-reimplement-worker-json.md** - Rebuild feature (~2-3 hours)
   - Review original implementation (see `completed/auto-generate-worker-json-plan.md`)
   - Implement worker.json generation from .fc files
   - Add CLI flag or GUI button for export
   - Test with examples/basic.ami

**Total Estimated Time**: 2-3 hours

## Implementation History

### Original Implementation
- **Commit**: b80ad6e (March 25, 2026)
- **Status**: Removed or lost during refactoring
- **Design**: See `completed/auto-generate-worker-json-plan.md` for original plan

### Why Reimplementation Needed
The original implementation was lost or removed. Need to rebuild from scratch using the original design document as a reference.

## Related Documentation

- `completed/auto-generate-worker-json-plan.md` - Original design and implementation plan
- `examples/worker.json` - Example worker configuration format
- `ami/flowchart/Flowchart.py` - Flowchart serialization/deserialization

## Key Files

**To Modify**:
- `ami/flowchart/Flowchart.py` - Add export_worker_json() method
- `ami/flowchart/Editor.py` - Add "Export Worker JSON" button (if GUI-based)
- `ami/client/flowchart.py` - Add CLI flag support (if CLI-based)

**Reference**:
- `examples/worker.json` - Target output format
- `ami/worker.py` - Worker class that consumes worker.json

## Success Criteria

- ✅ Can generate worker.json from any .fc file
- ✅ Generated JSON matches format of examples/worker.json
- ✅ Worker can successfully load and execute the generated JSON
- ✅ Feature accessible via GUI button OR CLI flag
