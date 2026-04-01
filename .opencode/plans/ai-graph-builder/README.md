# AI Graph Builder

Natural language interface for building AMI analysis graphs using OpenCode AI and IPython magic commands.

## Current Status: BLOCKED - Missing API Implementation

The chat widget is built and functional, but agent-generated code cannot execute because the `AmiCli` class has no methods implemented. The agent calls methods that don't exist (`create_node()`, `connect_nodes()`, etc.), causing 100% of executions to fail with AttributeError.

## Quick Start

**Start here**: `active/01-api-mismatch-analysis.md`

This is the critical blocking issue. Until the AmiCli API methods are implemented, nothing else can be tested or validated.

## Execution Order

1. ❌ **01-api-mismatch-analysis.md** - CRITICAL BLOCKER - Implement AmiCli API methods (~1-2 hours)
   - Investigates Flowchart API (createNode, connectTerminals, etc.)
   - Implements create_node(), connect_nodes(), ensure_source() on AmiCli class
   - Unblocks: All other plans (nothing works without this)

2. ❌ **02-fix-chat-widget-issues.md** - Fix UX issues (~20-30 min)
   - Display agent explanatory text in widget (currently goes to stdout)
   - Add ensure_source as method wrapper on amicli
   - Depends on: 01 (need API to test fixes)

3. ❌ **03-update-skill-for-chat-mode.md** - Clean up documentation (~45-55 min)
   - Remove all IPython magic command references from skill docs
   - Update to Chat Mode only
   - Remove ~200 lines of dead magic command code
   - Can run in parallel with 02

4. ❌ **04-add-code-toggle-to-chat-widget.md** - Polish UX (~25-30 min)
   - Add "Show generated code" checkbox (default: unchecked)
   - Users see conversational responses, not code blocks
   - Power users can toggle to see code
   - Depends on: 02 (builds on widget fixes)

**Total Estimated Time**: 2.5-3.5 hours

## Implementation History

### What Works ✅
- OpenCode server startup and warmup (12s faster first request)
- Chat widget UI with background threading (non-blocking)
- Code extraction from agent responses (JSON parsing)
- Session error handling with automatic retry
- Integration with Flowchart via toolbar button (Ctrl+Shift+C)

### What's Broken ❌
- **AmiCli API** - No methods exist (CRITICAL BLOCKER)
- Agent text display - Shows in stdout instead of widget
- ensure_source - Exists as standalone function, not AmiCli method

### What Was Tried (Failures Documented)
- **QtConsole approach** - FAILED - `input()` blocks event loop, preventing Comm callbacks
  - See `research/chat-mode-comm-async-fix.md` for detailed failure analysis
  - Multiple fix attempts (async handlers, polling, warmup) all failed
  - Root cause: Architectural limitation, not timing issue

## Related Documentation

- `AMI_GRAPH_BUILDER_STATUS.md` (project root) - Comprehensive 684-line status document
- `PLAN_AI_GRAPH_BUILDER.md` (project root) - Original 2,440-line plan + failure analysis
- `DOCUMENTATION_GUIDE.md` (project root) - Navigation guide for all docs
- `skills/ami-graph-builder/SKILL.md` - AI agent skill documentation (37KB, 91+ nodes)
  - **WARNING**: Documents API that doesn't exist - needs update after 01 is complete

## Key Files

**Modified** (Current implementation):
- `ami/client/flowchart.py` (643→683 lines) - Server startup + warmup
- `ami/flowchart/Flowchart.py` (1,570→1,612 lines) - AmiCli class (INCOMPLETE)
- `ami/flowchart/Editor.py` (413→419 lines) - Toolbar button
- `ami/flowchart/chat_widget.py` (NEW, 528 lines) - Chat widget

**Preserved** (Working infrastructure):
- `ami/flowchart/graph_builder.py` (729 lines) - OpenCodeBridge, ensure_source()
- `skills/ami-graph-builder/` - AI skill documentation

## Backup & Recovery

- **Backup tag**: `backup-qtconsole-implementation` (commit e3738e7)
- **Reverted files** (Phase 0 - clean slate):
  - `ami/flowchart/Flowchart.py` (2,745→1,570 lines reverted)
  - `ami/client/flowchart.py` (725→643 lines reverted)
  - Deleted test files (test.py, test2.py, test.fc, test2.fc)

## Next Steps After All Plans Complete

1. **End-to-end testing** with real user queries
2. **User documentation** - How to use Chat Mode
3. **Demo video** - Show natural language graph building
4. **Performance tuning** - Optimize OpenCode server warmup
5. **Error handling** - Better error messages for invalid queries
