# Execution Priority Order

## Start Here: 01-api-mismatch-analysis.md

**WHY THIS FIRST**: Nothing else matters if code can't execute. The AmiCli class has ZERO methods implemented, so 100% of agent responses will crash with `AttributeError: 'AmiCli' object has no attribute 'create_node'`.

This is a **CRITICAL BLOCKER** that prevents any testing or validation of the chat widget.

---

## Then Execute In Order:

### 1. ❌ **01-api-mismatch-analysis.md** (CRITICAL - BLOCKING)
**What**: Implement missing AmiCli API methods
- Investigate Flowchart API: `chart.createNode()`, `chart.connectTerminals()`, etc.
- Implement `create_node(node_type, label=None)` on AmiCli class
- Implement `connect_nodes(src, src_term, dst, dst_term)` on AmiCli class
- Implement `ensure_source(source_name)` wrapper method
- Add other documented methods: `disconnect_nodes()`, `node_info()`, etc.

**Estimated Time**: ~1-2 hours  
**Location**: `ami/flowchart/Flowchart.py` AmiCli class (line ~1213)  
**Unblocks**: ALL other plans (nothing works without this)

---

### 2. ❌ **02-fix-chat-widget-issues.md** (High Priority - UX)
**What**: Fix chat widget display issues
- Extract and display `explanation`, `warnings`, `next_steps` from JSON responses
- Show agent text in widget instead of stdout
- Add `ensure_source` as AmiCli method (wrapper around standalone function)

**Estimated Time**: ~20-30 minutes  
**Depends On**: 01 (need working API to test these fixes)  
**Files**: `ami/flowchart/chat_widget.py` (lines 399-440, execution namespace)

---

### 3. ❌ **03-update-skill-for-chat-mode.md** (Medium Priority - Cleanup)
**What**: Remove obsolete IPython magic command code and docs
- Update `skills/ami-graph-builder/SKILL.md` (remove magic command references)
- Remove ~200 lines of dead magic command code from `graph_builder.py`
- Update all examples to show chat interactions
- Clean up skill documentation

**Estimated Time**: ~45-55 minutes  
**Depends On**: None (can run in parallel with 02)  
**Files**: `skills/ami-graph-builder/SKILL.md`, `ami/flowchart/graph_builder.py`

---

### 4. ❌ **04-add-code-toggle-to-chat-widget.md** (Low Priority - Polish)
**What**: Add code visibility toggle to chat widget
- Add checkbox "Show generated code" (default: unchecked)
- Users see agent text and execution status by default
- Power users can toggle to see actual code blocks
- Smart behavior: show code on errors even if toggle is off

**Estimated Time**: ~25-30 minutes  
**Depends On**: 02 (builds on widget display fixes)  
**Files**: `ami/flowchart/chat_widget.py`

---

## Total Estimated Time: 2.5 - 3.5 hours

## Dependencies Graph

```
01-api-mismatch (CRITICAL BLOCKER)
  ├──> 02-fix-chat-widget (UX fixes)
  │      └──> 04-add-code-toggle (polish)
  │
  └──> 03-update-skill (cleanup, can run in parallel with 02)
```

## Why This Order?

1. **01 is mandatory** - Without API methods, code execution fails 100% of the time
2. **02 improves UX** - Makes the widget actually usable once code can execute
3. **03 cleans up** - Removes confusing dead code, can happen anytime
4. **04 polishes** - Better UX for end users, but not essential for functionality

## Risk Assessment

- **If 01 fails**: Entire feature is unusable, investigate Flowchart API constraints
- **If 02 fails**: Feature works but UX is poor (text in stdout instead of widget)
- **If 03 fails**: Feature works but codebase has confusing dead code
- **If 04 fails**: Feature works but users see raw code instead of clean chat

**Recommendation**: Focus on 01, then 02. Plans 03-04 are nice-to-have.
