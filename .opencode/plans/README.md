# AMI Development Plans

This directory contains active planning documents for the AMI (Analysis Monitoring Interface) project.

**Last Updated:** April 1, 2026  
**Organization Standard:** See `AGENTS.md` - Plan Organization Standards section

---

## 📋 Active Development

### Feature: AI Graph Builder
**Location:** `ai-graph-builder/`  
**Status:** 🚧 BLOCKED - Missing API implementation  
**Start Here:** `ai-graph-builder/active/01-api-mismatch-analysis.md`

Natural language interface for building AMI analysis graphs using OpenCode AI. Currently blocked because the AmiCli class has no methods implemented.

**Progress:** 0/4 plans complete  
**Estimated Time Remaining:** 2.5-3.5 hours

- ❌ 01-api-mismatch-analysis.md (CRITICAL BLOCKER) - ~1-2 hours
- ❌ 02-fix-chat-widget-issues.md - ~20-30 min
- ❌ 03-update-skill-for-chat-mode.md - ~45-55 min
- ❌ 04-add-code-toggle-to-chat-widget.md - ~25-30 min

**Documentation:**
- Comprehensive status: `AMI_GRAPH_BUILDER_STATUS.md` (project root)
- Original plan: `PLAN_AI_GRAPH_BUILDER.md` (project root)
- Skill docs: `skills/ami-graph-builder/SKILL.md`

---

### Feature: Worker JSON Generation
**Location:** `worker-json-generation/`  
**Status:** 🔄 NEEDS REIMPLEMENTATION  
**Start Here:** `worker-json-generation/active/01-reimplement-worker-json.md`

Automatic worker configuration file generation from `.fc` (flowchart) files. Previously implemented (commit b80ad6e) but lost during refactoring.

**Progress:** 0/1 plans complete  
**Estimated Time Remaining:** 2-3 hours

- ❌ 01-reimplement-worker-json.md - ~2-3 hours

---

## 📁 Standalone Plans

### GUI Test Refactoring
**File:** `gui-test-refactoring.md`  
**Status:** ✅ COMPLETED  
**Date:** March 27, 2026

Session-scoped backend implementation for 2.6x performance improvement (40+ sec → 15.5 sec).

**Results:**
- Fixed Prometheus metrics duplication bug
- Smart routing for static vs psana backends
- Commits: a8d6442, 0c88336

---

## 📊 Directory Structure

```
.opencode/plans/
├── README.md                          # This file
├── gui-test-refactoring.md           # Standalone completed plan
│
├── ai-graph-builder/                 # Natural language graph interface
│   ├── README.md                     # Feature overview and quick start
│   ├── 00-PRIORITY-ORDER.md         # Execution strategy
│   ├── active/                       # 4 plans, 0 complete
│   ├── completed/                    # 2 historical implementations
│   └── research/                     # 6 analysis/failure docs
│
└── worker-json-generation/           # Auto-generate worker configs
    ├── README.md                     # Feature overview
    ├── 00-PRIORITY-ORDER.md         # Execution strategy
    ├── active/                       # 1 plan, 0 complete
    └── completed/                    # 1 original design doc
```

---

## 🎯 Plan Status Legend

- ✅ **COMPLETED** - Implementation finished and committed
- 🚧 **BLOCKED** - Critical issue preventing progress
- 🔄 **NEEDS WORK** - Requires reimplementation or fixes
- ❌ **NOT STARTED** - Planned but not yet begun
- 📖 **REFERENCE** - Documentation/guide for active work

---

## 📚 Quick Reference

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

When creating a new plan document, follow the standards in `AGENTS.md`:

1. **Assess scope**: Single file or feature directory?
2. **For complex features**: Create feature directory with README.md + 00-PRIORITY-ORDER.md
3. **Use numbered prefixes**: `01-`, `02-`, `03-` for active plans to show execution order
4. **Include standard header**:
   ```markdown
   # Plan Title
   **Date:** YYYY-MM-DD
   **Status:** Planning/Ready/In Progress/Completed
   **Priority:** CRITICAL/High/Medium/Low
   **Estimated Time:** X-Y hours
   ```
5. **Update this README** when adding new plans
6. **Move to completed/** when done

See `AGENTS.md` - "Plan Organization Standards" section for full details.

---

## 🗃️ Archive

Completed/abandoned plans are in `../.opencode/archive/`:
- Historical architecture plans (phase1/phase2 shared memory)
- Week 3 issue tracking (qapplication-fork-issue)
- Old status documents

---

## 📚 Additional Resources

- **Architecture Guide:** `AGENTS.md` (project root)
- **Main README:** `README.md` (project root)
- **Test Documentation:** `tests/` (TODO: create TEST_README.md)
- **Archive:** `.opencode/archive/`
- **Skills:** `.opencode/skills/` (AI agent skills)

---

**Maintained by:** AI agent (OpenCode)  
**Contact:** For questions about plans, check git history or AGENTS.md  
**Organization Standard:** See `AGENTS.md` - Plan Organization Standards
