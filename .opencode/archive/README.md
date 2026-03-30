# AMI Development Plans

This directory contains planning documents and development notes for the AMI (Analysis Monitoring Interface) project.

## 🎯 Current Status

**Active Branch**: `subgraph-refactor-clean`  
**Latest Commit**: `5ef6f9b` - "Fix subgraph import and improve UX"  
**Last Updated**: March 18, 2026  

👉 **See `current-status.md` for comprehensive current state, known issues, and next steps**

## Active Plans

### Current Status (START HERE)
- **File**: `current-status.md` ⭐
- **Status**: Current
- **Description**: Comprehensive overview of current implementation, recent changes, known issues, and development guidelines
- **Key Info**:
  - Recent bug fixes (signal=True, view switching)
  - UX improvements (hierarchical tree, grid snapping)
  - Known issue: Placeholder cleanup bug
  - Branch history and architecture overview

### Signal Parameter Understanding
- **File**: `signal-parameter-understanding.md`
- **Status**: Reference
- **Description**: Guide on when to use `signal=True` vs `signal=False` for terminal connections
- **Use Cases**:
  - `signal=True`: Real data flow connections (populates `_input_vars`, creates graph edges)
  - `signal=False`: Visual-only connections (helper boundary connections)

### Subgraph Refactoring
- **File**: `subgraph-refactoring.md`
- **Status**: Completed (archived)
- **Description**: Original refactoring plan - now superseded by visual-only architecture (commit c16ec5d)
- **Note**: See `current-status.md` for current implementation

### Subgraph Refactor Progress
- **File**: `subgraph-refactor-progress.md`
- **Status**: Archived
- **Description**: Progress tracking during refactor - now complete
- **Note**: Final status in `current-status.md`

## Completed/Archived Plans

### Subgraph Library Implementation
- **File**: `subgraph-library.md`
- **Status**: ✅ Implemented
- **Description**: Subgraph library system with save/load/reuse functionality
- **Outcome**: Fully implemented with hierarchical tree UI

### Phase 2 Unified Implementation
- **File**: `phase2-unified-implementation.md`
- **Status**: ✅ Completed
- **Description**: Unified subgraph creation for selection and import workflows
- **Outcome**: Successfully merged into visual-only architecture

### Add Dump Graph Button
- **File**: `add-dump-graph-button.md`
- **Status**: ✅ Removed
- **Description**: Debugging tool for visualizing graph structure
- **Outcome**: Removed in cleanup (commit 5ef6f9b)

### Clean Subgraph Implementation
- **File**: `clean-subgraph-implementation.md`
- **Status**: Archived
- **Description**: Early implementation notes
- **Note**: Superseded by refactor

## Plan Status Legend

- ⭐ **Current**: Active working document
- ✅ **Implemented**: Feature complete
- 📝 **Reference**: Documentation/guide
- 🗄️ **Archived**: Historical reference only
- ⏸️ **Paused**: Temporarily on hold

## Quick Reference

### Architecture
```
Visual-Only Subgraph Design:
- Placeholder nodes: NOT in self._graph
- Helper nodes: NOT in self._graph  
- Internal nodes: IN self._graph
- Execution edges: External → Internal (direct)
```

### Key Files
- `ami/flowchart/Flowchart.py` - Core flowchart and subgraph logic
- `ami/flowchart/SubgraphNode.py` - Placeholder and helper nodes
- `ami/flowchart/Editor.py` - Unified library editor
- `ami/flowchart/SubgraphLibrary.py` - Library management
- `ami/flowchart/FlowchartGraphicsView.py` - View management

### Recent Changes (5ef6f9b)
- ✅ Fixed import bug (signal=True for internal connections)
- ✅ Fixed view switching (stay on root after import)
- ✅ Hierarchical library tree (grouped by source file)
- ✅ Grid snapping for placeholders
- ✅ Improved view cleanup
- ⚠️ Known issue: Placeholder cleanup via X button

### Important Commits
- `5ef6f9b` - Current HEAD (fixes + UX improvements)
- `c16ec5d` - Visual-only architecture refactor
- `c8a57f9` - Previous approach (helpers in graph) - on `subgraph` branch

## Guidelines for Creating Plans

1. **Use Markdown format** for all plan documents
2. **Include clear objectives** at the start of each plan
3. **Track progress** with checkboxes for tasks
4. **Document decisions** and architectural choices
5. **Update current-status.md** when major changes occur
6. **Reference commits** when documenting implementations

## Navigation

- **New to the project?** → Start with `current-status.md`
- **Need architecture details?** → See `current-status.md` > Architecture Overview
- **Working on connections?** → See `signal-parameter-understanding.md`
- **Looking for history?** → Check archived plans and commit references

---

Last updated: March 18, 2026
