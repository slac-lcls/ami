# Plan: Update Skill Documentation for Chat Mode Only

**Date:** April 1, 2026  
**Status:** Ready for approval  
**Estimated time:** 30-40 minutes

---

## Context

The AMI graph builder has evolved:
- **Old approach:** IPython magic commands (`%build_graph`, `%bg`) in QtConsole
- **New approach:** Chat Mode widget (Ctrl+Shift+C) with Qt interface
- **Current problem:** Skill documentation describes magic commands that no longer work

## Current State

**Magic commands status:**
- ✅ Code exists in `graph_builder.py` (functions `register_graph_builder_magic`, `build_graph`)
- ❌ NOT registered in `Flowchart.py` (commented out in backup-qtconsole-implementation)
- ❌ NOT working in current implementation

**Skill documentation:**
- Entirely focused on IPython magic commands
- References `%build_graph` and `%bg` throughout
- Mentions IPython console, kernel, magic functions
- All examples show magic command invocation

**Result:** Agent is trained on an interface that doesn't exist!

---

## Goals

1. **Update skill documentation** to describe Chat Mode instead of magic commands
2. **Remove magic command code** from `graph_builder.py` (dead code cleanup)
3. **Update invocation examples** to show Chat Mode interactions
4. **Clarify execution environment** (Qt widget, not IPython)

---

## Changes to Skills Documentation

### File: `skills/ami-graph-builder/SKILL.md`

### Change 1: Update Header/Description (Line 3)

**Current:**
```yaml
description: AI assistant for building AMI analysis graphs using natural language via IPython magic commands
```

**New:**
```yaml
description: AI assistant for building AMI analysis graphs using natural language via Chat Mode
```

### Change 2: Update "How You're Invoked" Section (Lines 15-24)

**Current:**
```markdown
## How You're Invoked

Users invoke you through the `%build_graph` (or `%bg`) magic command in the AMI IPython console. Your job is to:

1. Understand the user's natural language request
2. Map it to AMI graph building operations
3. Return code in structured JSON format
4. Provide helpful guidance about GUI configuration

**Note:** Users should avoid ending requests with `?` because IPython treats it as a help operator. The natural language can be a question without the `?` symbol (e.g., "can we correlate laser and delta_t" works fine without the `?`).
```

**New:**
```markdown
## How You're Invoked

Users invoke you through the **Chat Mode** widget (Ctrl+Shift+C) in AMI. They type natural language requests in the chat interface, and you respond with both explanations and executable code.

Your job is to:

1. Understand the user's natural language request in the chat
2. Explain what you're going to do (conversational response)
3. Generate code in structured JSON format
4. Provide helpful guidance about GUI configuration

**Note:** Users can ask questions naturally, including using `?` at the end. The chat interface handles all question formats.
```

### Change 3: Update Response Format Section (Around Line 26)

Add clarification about conversational text:

**Current:**
```markdown
## Response Format (CRITICAL)

You **MUST** return your final response as a JSON object in a code block.
```

**New:**
```markdown
## Response Format (CRITICAL)

You can provide conversational text to explain what you're doing, followed by a JSON object in a code block.

**Example response structure:**
```
I'll help you create a scatter plot to visualize the correlation between laser and detector.
Let me set that up for you...

```json
{
  "explanation": "Creates scatter plot correlating laser intensity with detector signal",
  "code": "..."
}
```
```

The conversational text appears in the chat, then the code executes automatically.
```

### Change 4: Update Examples (Lines 100-170)

Replace all `%build_graph` examples with Chat Mode examples.

**Current:**
```markdown
### Example 1: Ambiguous Request (Ask Questions)

User request: `%build_graph show me the detector`
```

**New:**
```markdown
### Example 1: Ambiguous Request (Ask Questions)

**Chat interaction:**
```
User: show me the detector

Agent: I found multiple detectors in your experiment. Which one would you like to view?
```

**Your response:**
```markdown

### Change 5: Update "Key Principles" Section (Around Line 1071)

**Current:**
```markdown
- The code executes in an IPython environment with AMI session active
```

**New:**
```markdown
- The code executes in the AMI session with access to the flowchart API
- Execution happens automatically after you return the code
- Users see both your explanatory text and the code execution results
```

### Change 6: Add Chat Mode Context Section

Add new section after "Response Format":

```markdown
## Chat Mode Context

**Environment:**
- Users interact via a Qt chat widget (not IPython console)
- You can provide conversational responses that appear in the chat
- Code in JSON blocks executes automatically
- Users see execution status and any print() output

**User Experience:**
- User types natural language in chat input field
- You respond with explanation + code
- Code executes immediately
- User sees results in both chat and graph

**Tips:**
- Be conversational - explain what you're doing
- Use the `explanation` field for technical details
- Use conversational text for friendly guidance
- Warnings help users understand assumptions
```

### Change 7: Update All Code Examples

Search and replace throughout:
- Remove references to `%build_graph` and `%bg`
- Show examples as chat interactions
- Update user prompts to be conversational

**Example transformation:**

**Old:**
```markdown
User request: `%build_graph create a scatter plot for laser vs detector`
```

**New:**
```markdown
**User:** create a scatter plot for laser vs detector

**Agent:** I'll create a scatter plot to help you visualize the correlation between laser and detector signals.
```

---

## Remove Magic Command Code

### File: `ami/flowchart/graph_builder.py`

### Change 1: Remove `register_graph_builder_magic` function

**Current:** Lines 187-300+ (entire function)

**Action:** Delete the entire function (keep other code)

**Reason:** Dead code - never called, magic commands not used

### Change 2: Remove magic command documentation

**Current:** Lines 1-50 (module docstring references magic commands)

**Update module docstring to:**
```python
"""
AI-Assisted Graph Building for AMI

This module provides the OpenCode bridge and helper functions for building 
AMI analysis graphs using natural language via the Chat Mode widget.

Key components:
- OpenCodeBridge: Interface to OpenCode server for AI assistance
- get_graph_state(): Extract graph state for agent context
- ensure_source(): Smart source node creation with validation
"""
```

### Change 3: Keep only essential functions

**Keep:**
- `OpenCodeBridge` class (used by chat widget)
- `get_graph_state()` function (used by chat widget)
- `ensure_source()` function (used by agent code)
- Helper functions for graph manipulation

**Remove:**
- `register_graph_builder_magic()` function
- `build_graph()` magic function
- `invoke_agent_for_graph_building()` (for magic commands)
- `build_agent_prompt()` (for magic commands)  
- `extract_code_from_response()` (for magic commands)

**Note:** Chat widget has its own `_extract_code()` method

---

## Files Modified

### Primary Changes:
1. `skills/ami-graph-builder/SKILL.md`
   - Update invocation method (IPython → Chat Mode)
   - Update all examples
   - Add Chat Mode context section
   - Remove IPython-specific notes
   - **Estimate:** ~50-100 lines changed

2. `ami/flowchart/graph_builder.py`
   - Remove magic command registration function (~120 lines)
   - Remove helper functions for magic commands (~80 lines)
   - Update module docstring (~10 lines)
   - **Estimate:** ~200 lines removed

### Verification:
- Check that no other code references removed functions
- Verify chat widget still works
- Test a few chat interactions

---

## Testing Plan

### Test 1: Chat Widget Works
1. Start AMI
2. Press Ctrl+Shift+C
3. Type: "create a scatter plot"
4. Verify: Agent responds with explanation + code
5. Verify: Code executes successfully

### Test 2: Agent Understanding
1. Type: "what sources are available?"
2. Verify: Agent explains available sources
3. Verify: Response format matches new skill docs

### Test 3: No Magic Command References
1. Review skill documentation
2. Verify: No `%build_graph` or `%bg` references
3. Verify: No IPython console references
4. Verify: All examples use Chat Mode format

---

## Risks & Mitigation

### Risk 1: Breaking existing code
**Risk:** Other code might reference removed functions  
**Mitigation:** Grep for function names before removing  
**Likelihood:** Low (magic commands were never activated)

### Risk 2: Agent confusion
**Risk:** Agent might still expect magic command format  
**Mitigation:** Clear skill documentation, test with various prompts  
**Likelihood:** Low (agent adapts to new docs quickly)

### Risk 3: User confusion
**Risk:** Users might look for magic commands  
**Mitigation:** Clear documentation, only one method available  
**Likelihood:** Very low (magic commands never worked)

---

## Pre-Implementation Verification

Before removing code, verify nothing references it:

```bash
# Check for magic command references
grep -r "register_graph_builder_magic" ami/ --include="*.py"
grep -r "build_graph" ami/ --include="*.py" | grep -v "graph_builder.py"
grep -r "%build_graph\|%bg" ami/ --include="*.py"

# Expected: No results (or only in graph_builder.py itself)
```

---

## Rollback Plan

If issues arise:

```bash
# Restore skill documentation
git checkout HEAD -- skills/ami-graph-builder/SKILL.md

# Restore graph_builder.py
git checkout HEAD -- ami/flowchart/graph_builder.py
```

---

## Benefits

✅ **Accurate documentation** - Describes how system actually works  
✅ **Less confusion** - One clear invocation method  
✅ **Code cleanup** - Remove ~200 lines of dead code  
✅ **Better agent performance** - Trained on correct interface  
✅ **Simpler maintenance** - One code path to maintain  

---

## Implementation Order

1. **Verify no dependencies** (grep for function references)
2. **Update skill documentation** (SKILL.md)
3. **Remove magic command code** (graph_builder.py)
4. **Test chat widget** (verify still works)
5. **Test agent responses** (verify format matches new docs)

---

## Estimated Time

- Dependency verification: 5 minutes
- Skill documentation updates: 20-25 minutes
- Code removal: 10 minutes
- Testing: 10-15 minutes
- **Total: 45-55 minutes**

---

## Questions for User

Before implementing:

1. **Confirm scope:** Remove ALL magic command code, or keep it as "future feature"?
   - **Recommendation:** Remove - it's dead code and Chat Mode is working

2. **Documentation style:** Keep skill docs technical or make more conversational?
   - **Recommendation:** Keep technical but update examples to Chat Mode

3. **Backward compatibility:** Any concern about removing magic command code?
   - **Recommendation:** No concern - it was never active

---

## Approval Checklist

- [ ] User confirms: Remove magic command code
- [ ] User confirms: Update skill docs for Chat Mode only
- [ ] User confirms: Remove all IPython references
- [ ] Dependencies verified (no references to removed code)
- [ ] Ready to implement

---

**Status:** Awaiting user approval to proceed
