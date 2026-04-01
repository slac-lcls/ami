# AMI Graph Builder - Documentation Guide

**Last Updated:** April 1, 2026  
**Branch:** `feature/ai-graph-builder`

This guide helps you navigate the AMI Graph Builder documentation.

---

## 📖 Quick Navigation

### Start Here

**New to the project?** → Read **`AMI_GRAPH_BUILDER_STATUS.md`**
- Complete status and restart plan
- What worked, what failed, and why
- Clear recommendation for next steps

### Detailed Plans

**Want implementation details?** → See these files:

1. **`PLAN_AI_GRAPH_BUILDER.md`** - Original implementation plan
   - Phases 1-3 implementation (magic commands, View Source, skills)
   - Detailed code examples and architecture
   - QtConsole approach (now abandoned) with lessons learned

2. **`PLAN_CHAT_WIDGET_CLEAN_START.md`** - New clean restart plan
   - Qt widget approach (proposed)
   - Phase-by-phase implementation steps
   - Estimated 6-8 hours to completion

### Detailed Learnings

**Want to understand what we learned?** → See **`.opencode/plans/STATUS_UPDATE.md`**
- Timeline of all 7+ fix attempts
- Root cause analysis with evidence
- Architectural deep-dive
- Key lessons for future projects

---

## 📚 Document Summary

### Main Documents (Project Root)

| File | Purpose | Length | Status |
|------|---------|--------|--------|
| **AMI_GRAPH_BUILDER_STATUS.md** | Current status, comprehensive | 684 lines | ✅ Updated |
| **PLAN_AI_GRAPH_BUILDER.md** | Original implementation plan | 2,440 lines | ✅ Updated |
| **PLAN_CHAT_WIDGET_CLEAN_START.md** | New Qt widget plan | ~2,265 lines | ✅ Complete |
| **DOCUMENTATION_GUIDE.md** | This file | Short | ✅ Current |

### Reference Documents (.opencode/plans/)

| File | Purpose | Use Case |
|------|---------|----------|
| **STATUS_UPDATE.md** | Detailed lessons learned | Deep-dive into failures |
| **AMI_STATUS_COMPREHENSIVE.md** | Full status (backup) | Reference copy |

### Historical Documents (Backups)

| File | Purpose |
|------|---------|
| `AMI_GRAPH_BUILDER_STATUS.md.backup` | Pre-update version (March 31) |
| `PLAN_AI_GRAPH_BUILDER.md.backup` | Pre-update version (March 31) |

### Archived Documents (.opencode/archive/)

Old session notes, testing guides, and experimental docs have been archived.

---

## 🎯 What to Read Based on Your Goal

### Goal: "I need to understand current status"
→ **Read:** `AMI_GRAPH_BUILDER_STATUS.md` (start here!)
- Executive summary
- What works, what doesn't
- Clear recommendation

### Goal: "I want to implement the Qt widget"
→ **Read:** `PLAN_CHAT_WIDGET_CLEAN_START.md`
- Detailed phase-by-phase plan
- Code examples
- Testing scenarios

### Goal: "I want to understand why QtConsole failed"
→ **Read:** `.opencode/plans/STATUS_UPDATE.md`
- Timeline of attempts
- Technical analysis
- Root cause with evidence

### Goal: "I want to see the original magic command implementation"
→ **Read:** `PLAN_AI_GRAPH_BUILDER.md`
- Phases 1-3 details
- graph_builder.py design
- Complete code examples

### Goal: "I want to learn from our mistakes"
→ **Read:** Both:
1. `AMI_GRAPH_BUILDER_STATUS.md` - Lessons learned section
2. `.opencode/plans/STATUS_UPDATE.md` - Detailed analysis

---

## 🔍 Key Findings at a Glance

### What Works ✅

1. **Magic Commands** (`%build_graph`, `%bg`)
   - File: `ami/flowchart/graph_builder.py` (729 lines)
   - Status: ✅ Complete, functional, keep 100%

2. **Skills Documentation**
   - Location: `skills/ami-graph-builder/`
   - Content: 91+ nodes documented
   - Status: ✅ Complete, valuable, keep 100%

3. **OpenCode Server Startup**
   - Starts at AMI launch
   - Pre-loads skill for warmup
   - Status: ✅ Working, keep pattern

### What Failed ❌

1. **QtConsole Chat Interface**
   - Code: ~1,300 lines in Flowchart.py & flowchart.py
   - Problem: `input()` blocks event loop → Comm callbacks can't fire
   - Result: 0% success rate for source list delivery
   - Status: ❌ Fundamentally broken, revert all

### What We're Building ✅

1. **Qt Widget Chat Interface**
   - File: `ami/flowchart/chat_widget.py` (new, ~250 lines)
   - Architecture: Same process, direct access, background threads
   - Benefits: 77% less code, will actually work
   - Status: 📝 Planned, ready to implement

---

## 📊 Comparison Table

| Aspect | Magic Commands | QtConsole Chat | Qt Widget Chat |
|--------|---------------|----------------|----------------|
| **Status** | ✅ Working | ❌ Failed | 📝 Planned |
| **Code size** | 729 lines | +1,424 lines | +320 lines |
| **Complexity** | Low | High | Low |
| **Use case** | Quick commands | Conversations | Conversations |
| **Works?** | ✅ Yes | ❌ No (0%) | ✅ Yes (expected) |
| **Keep?** | ✅ Yes | ❌ No (revert) | ✅ Yes (implement) |

---

## 🚀 Next Steps

### Immediate

1. ✅ Read `AMI_GRAPH_BUILDER_STATUS.md`
2. ⏳ Get approval for clean restart
3. ⏳ Execute Phase 0 (revert to master)

### Implementation (6-8 hours)

1. Phase 0: Revert to master (5 min)
2. Phase 1: Re-add server startup (15 min)
3. Phase 2: Create ChatWidget (3 hours)
4. Phase 3: Integration (30 min)
5. Phase 4: Code execution (1 hour)
6. Phase 5: Testing (1.5 hours)
7. Phase 6: Polish & docs (1 hour)

### Success Criteria

- [ ] Chat widget opens with Ctrl+Shift+C
- [ ] Agent receives source list (100% success)
- [ ] Code executes automatically
- [ ] Nodes appear in flowchart
- [ ] Multi-turn conversations work
- [ ] UI stays responsive (no blocking)

---

## 📝 Version History

### April 1, 2026 - Major Update
- **Status:** Comprehensive rewrite with lessons learned
- **Plan:** Added QtConsole failure analysis and Qt widget proposal
- **New:** Created DOCUMENTATION_GUIDE.md (this file)
- **New:** Created PLAN_CHAT_WIDGET_CLEAN_START.md
- **Decision:** Clean restart with Qt widget approach

### March 31, 2026 - QtConsole Implementation
- Implemented QtConsole chat interface (~1,300 lines)
- Multiple fix attempts (async, warmup, timing)
- Result: Fundamentally broken, 0% success rate

### March 30, 2026 - Original Implementation
- Phases 1-3 complete (magic commands, View Source, skills)
- 729 lines in graph_builder.py
- OpenCode server integration
- All working perfectly

---

## 🔗 Related Files

### Implementation Files
- `ami/flowchart/graph_builder.py` - Magic commands (keep)
- `ami/flowchart/Flowchart.py` - Will revert to master
- `ami/client/flowchart.py` - Will revert to master
- `ami/flowchart/chat_widget.py` - Will create

### Skills & Documentation
- `skills/ami-graph-builder/SKILL.md` - Agent instructions
- `skills/ami-graph-builder/references/` - Node documentation
- `AGENTS.md` - Architecture guide for AI agents

### Test Files (Delete)
- `test.py` - Temporary test file
- `test2.py` - Temporary test file

---

## 💡 Key Lessons

1. **Event loops and blocking don't mix** - Use Qt widgets, not `input()`
2. **IPC adds complexity** - Avoid when same-process works fine
3. **Simpler is better** - 77% code reduction is a strong signal
4. **Know when to restart** - Sunk cost is not a reason to continue
5. **Keep what works** - graph_builder.py is gold, keep it all

---

## 📞 Questions?

**Where should I start?**
→ `AMI_GRAPH_BUILDER_STATUS.md` - Executive summary and clear recommendation

**How do I implement the new approach?**
→ `PLAN_CHAT_WIDGET_CLEAN_START.md` - Step-by-step implementation plan

**Why did the old approach fail?**
→ `.opencode/plans/STATUS_UPDATE.md` - Detailed technical analysis

**What should I keep vs. revert?**
→ `AMI_GRAPH_BUILDER_STATUS.md` - Section "What We're Keeping (100%)"

---

**Last Updated:** April 1, 2026  
**Maintained by:** OpenCode AI  
**Branch:** `feature/ai-graph-builder`
