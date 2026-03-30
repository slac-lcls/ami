# AMI Development Plans

This directory contains active planning documents for the AMI (Analysis Monitoring Interface) project.

**Last Updated:** March 27, 2026  
**Active Branch:** `refactor-gui-tests`

---

## 📋 Active Plans

### 1. GUI Test Refactoring
- **File:** `gui-test-refactoring.md`
- **Status:** ✅ COMPLETED (but still needs work)
- **Date:** March 27, 2026
- **Description:** GUI test refactoring with session-scoped backend for 2.6x performance improvement
- **Commits:** a8d6442, 0c88336
- **Results:**
  - Tests run 2.6x faster (40+ sec → 15.5 sec)
  - Session-scoped backend shared across tests
  - Fixed Prometheus metrics duplication bug
  - Smart routing for static vs psana backends

### 2. Auto-Generate Worker JSON
- **File:** `auto-generate-worker-json-FINAL.md`
- **Status:** 🔄 NEEDS REIMPLEMENTATION
- **Date:** March 25, 2026
- **Description:** Automatic worker configuration generation from .fc files
- **Note:** Previously implemented (commit b80ad6e) but needs to be redone
- **Reference:** `auto-generate-worker-json-plan.md` for original design

### 3. Auto-Generate Worker JSON (Plan)
- **File:** `auto-generate-worker-json-plan.md`
- **Status:** 📖 REFERENCE
- **Date:** March 25, 2026
- **Description:** Original planning document for worker JSON auto-generation
- **Use:** Reference for reimplementation work

---

## 📁 Directory Structure

```
.opencode/
├── plans/              # Active plans (this directory)
│   ├── README.md       # This file
│   ├── gui-test-refactoring.md
│   ├── auto-generate-worker-json-FINAL.md
│   └── auto-generate-worker-json-plan.md
│
└── archive/            # Completed/abandoned plans
    ├── asyncio-removal-plan.md (ABANDONED)
    ├── subgraph-*.md (COMPLETED - commits c16ec5d, 7fadf3b, etc.)
    ├── terminal-label-overlap-*.md (COMPLETED - commit 173401b)
    ├── gui-test-*.md (various completed test work)
    └── ... (45 total archived files)
```

---

## 🎯 Plan Status Legend

- ✅ **COMPLETED** - Implementation finished and committed
- 🔄 **NEEDS WORK** - Requires additional work or reimplementation
- 📖 **REFERENCE** - Documentation/guide for active work
- ❌ **ABANDONED** - Plan abandoned (archived for reference)
- 🗄️ **ARCHIVED** - Completed work (in archive/ directory)

---

## 📊 Recent Cleanup (March 27, 2026)

Archived **28 files** to keep plans directory focused:

**Completed Implementations (15 files):**
- Asyncio removal (ABANDONED but archived)
- Subgraph refactoring (commits 1008466 → c16ec5d)
- Terminal label overlap fixes (commit 173401b)
- GUI test fixes and improvements
- Various auto-generation work

**Summary/Status Documents (6 files):**
- FINAL-SUMMARY.md, commit-summary.md, etc.

**Not Implemented/Superseded (7 files):**
- popup-handling-regression-tests.md (not needed)
- add-dump-graph-button.md (not needed)
- flowchart-from-file-*.md (never implemented)
- Various superseded design docs

---

## 🔍 Quick Reference

### Key AMI Architecture
```
AMI Components:
├── Worker (ami/worker.py)          - Event processing, graph execution
├── Collector (ami/collector.py)    - Result aggregation
├── Manager (ami/manager.py)        - Control point, broadcasts to clients
└── Client (ami/client/)            - GUI interface (Qt-based)

Flowchart Architecture:
├── ami/flowchart/Flowchart.py      - Core flowchart logic
├── ami/flowchart/Node.py           - Node base classes
├── ami/flowchart/Terminal.py       - Terminal connections
└── ami/flowchart/library/          - Node type definitions
```

### Running Tests
```bash
# All GUI tests
pytest tests/test_gui.py -v

# Specific test
pytest tests/test_gui.py::test_broker_sub -v

# With coverage
pytest tests/test_gui.py --cov=ami --cov-report=html
```

### Running AMI
```bash
# Local mode with random data
ami-local -n 3 random://examples/worker.json

# Load from .fc file
ami-local -l examples/basic.ami

# With psana data
ami-local -f interval=1 -b 1 psana://exp=rix101331225,run=156
```

---

## 📝 Creating New Plans

When creating a new plan document:

1. **Use descriptive filename:** `feature-name-plan.md`
2. **Include header with:**
   - Status (Planning/In Progress/Completed/Abandoned)
   - Date
   - Goal/Objective
   - Estimated time
3. **Structure:**
   - Executive Summary
   - Background/Problem
   - Proposed Solution
   - Implementation Plan (phases)
   - Success Criteria
   - Checklist
4. **Update this README** when adding new plans
5. **Archive when completed** - move to `../archive/`

---

## 🗃️ Archive Policy

Plans are archived when:
- ✅ Implementation is complete and committed
- ❌ Plan is abandoned or superseded
- 📝 Summary/status docs are no longer active

Archived plans remain accessible in `../archive/` for historical reference.

---

## 📚 Additional Resources

- **Architecture Guide:** `/sdf/home/s/seshu/dev/ami/AGENTS.md`
- **Main README:** `/sdf/home/s/seshu/dev/ami/README.md`
- **Test Documentation:** `/sdf/home/s/seshu/dev/ami/tests/` (TODO: create TEST_README.md)
- **Archive:** `/sdf/home/s/seshu/dev/ami/.opencode/archive/`

---

**Maintained by:** AI agent (OpenCode)  
**Contact:** For questions about plans, check git history or AGENTS.md
