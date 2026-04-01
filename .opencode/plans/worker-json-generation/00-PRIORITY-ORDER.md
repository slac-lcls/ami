# Execution Priority Order

## Start Here: 01-reimplement-worker-json.md

**WHY THIS FIRST**: This is the only active plan for this feature. It rebuilds the worker JSON auto-generation functionality that was previously implemented but lost during refactoring.

---

## Execution Plan

### 1. ❌ **01-reimplement-worker-json.md** (HIGH PRIORITY)
**What**: Rebuild worker.json auto-generation feature
- Review original implementation design in `completed/auto-generate-worker-json-plan.md`
- Implement export functionality (Flowchart → worker.json)
- Add UI/CLI trigger for export
- Test with example flowcharts

**Estimated Time**: ~2-3 hours  
**Reference**: commit b80ad6e (original implementation)  
**Files**: `ami/flowchart/Flowchart.py`, `ami/flowchart/Editor.py`

---

## Total Estimated Time: 2-3 hours

## Dependencies Graph

```
01-reimplement-worker-json (standalone, no dependencies)
```

## Risk Assessment

- **If implementation fails**: Feature remains unavailable, users must manually create worker.json files
- **Mitigation**: Reference original plan document and commit b80ad6e for implementation details
