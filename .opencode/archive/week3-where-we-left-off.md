# Week 3: Where We Left Off

**Date**: March 31, 2026  
**Status**: Taking a break - persistent event loop error  

---

## Quick Summary

**What's Done**: ✅
- MessageBroker completely removed (~260 lines deleted)
- Flowchart spawns NodeProcesses directly via multiprocessing.Queue
- All terminal lifecycle methods updated
- Process management (spawn, monitor, crash recovery) implemented

**What's Blocking**: ❌
- Event loop error when spawning NodeProcess
- Error: "QCoreApplication::exec: The event loop is already running"
- Crashes immediately when opening any display node

---

## The Problem

```
QCoreApplication::exec: The event loop is already running
Process c_atmopal:raw:image:
Traceback (most recent call last):
  File "ami/client/flowchart.py", line 267, in run_node_process_main
    NodeProcess(...)
  File "ami/client/flowchart.py", line 364, in __init__
    loop.run_until_complete(self.process())
  File "qasync/__init__.py", line 406, in run_until_complete
    raise RuntimeError("Event loop stopped before Future completed.")
```

**Location**: `ami/client/flowchart.py:364`  
**Occurs**: When spawning any display node (Histogram, ImageViewer, etc.)

---

## What We've Tried (All Failed)

1. Various event loop patterns (with loop, without loop, create_task, run_forever)
2. Different QApplication creation strategies
3. Moving theme application timing
4. Always creating fresh QApplication instead of using instance()
5. Using exact old MessageBroker pattern

**Total Attempts**: 7+ different approaches  
**Result**: Same error every time

---

## Current Code State

**Latest Change** (still failing):
```python
# In NodeProcess.__init__() - lines 290-299
self.app = QtWidgets.QApplication([])  # Always create fresh

if THEME:
    qdarktheme.setup_theme(THEME)

loop = QEventLoop(self.app)
asyncio.set_event_loop(loop)

# ... setup widgets ...

# At end of __init__() - lines 362-364
with loop:
    loop.run_until_complete(self.process())
```

**Why We Thought This Would Work**:
- Matches old working MessageBroker pattern exactly
- Always creates fresh QApp (avoids stale fork pointer)
- Theme applied at correct time
- Same event loop usage pattern

**Why It Still Fails**: Unknown! 🤷

---

## Next Steps to Try

### Option 1: Remove Async Entirely (RECOMMENDED)
**Effort**: Low  
**Risk**: Low  
**Chance of Success**: High

Make `process()` synchronous:
```python
def process(self):  # Not async!
    from queue import Empty
    while True:
        try:
            msg = self.msg_queue.get(timeout=0.1)
        except Empty:
            QtWidgets.QApplication.processEvents()  # Process Qt events
            continue
        
        # Handle message...
        if msg.get('type') == 'CloseNode':
            return
```

**Pros**: 
- No asyncio/Qt integration issues
- Simple, straightforward
- Qt events still processed

**Cons**: 
- Different pattern from editor
- Can't use async/await in handlers (but we're not using it anyway!)

### Option 2: Use QTimer Polling
**Effort**: Low-Medium  
**Risk**: Low  
**Chance of Success**: High

```python
def __init__(...):
    self.app = QtWidgets.QApplication([])
    # ... setup widgets ...
    
    # Poll queue with QTimer
    self.timer = QTimer()
    self.timer.timeout.connect(self.check_queue)
    self.timer.start(100)  # Check every 100ms
    
    # Run Qt event loop
    self.app.exec_()

def check_queue(self):
    from queue import Empty
    try:
        msg = self.msg_queue.get_nowait()
        self.handle_message(msg)
    except Empty:
        pass
```

**Pros**: 
- Native Qt pattern
- No asyncio complications

**Cons**: 
- Different from editor pattern
- Need to refactor message handling

### Option 3: Change Multiprocessing Start Method
**Effort**: Very Low  
**Risk**: Medium  
**Chance of Success**: Medium

Try using 'spawn' instead of 'fork':
```python
import multiprocessing as mp
mp.set_start_method('spawn')
```

**Pros**: 
- Very easy to try
- Avoids fork issues entirely

**Cons**: 
- Slower process creation
- May have side effects
- Might not solve the qasync issue

### Option 4: Create Minimal Test Case
**Effort**: Medium  
**Risk**: None (testing only)  
**Chance of Success**: N/A (diagnostic)

Create standalone script:
```python
# test_fork_qt.py
import multiprocessing as mp
from qtpy import QtWidgets
from ami.asyncqt import QEventLoop
import asyncio

def child_process():
    app = QtWidgets.QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    async def test():
        await asyncio.sleep(1)
        return "done"
    
    with loop:
        result = loop.run_until_complete(test())
    print(f"Result: {result}")

if __name__ == '__main__':
    # Parent creates QApp
    app = QtWidgets.QApplication([])
    
    # Fork
    proc = mp.Process(target=child_process)
    proc.start()
    proc.join()
```

**Pros**: 
- Isolates the problem
- Easier to debug

### Option 5: Check Library Versions
**Effort**: Very Low  
**Risk**: None  
**Chance of Success**: Low

```bash
pip list | grep -i "qt\|async"
```

Check if qasync/asyncqt or Qt versions changed recently.

---

## Relevant Files

**Main implementation**:
- `ami/client/flowchart.py` - NodeProcess class
- `ami/flowchart/Flowchart.py` - Process spawning

**Documentation**:
- `.opencode/plans/week3-qapplication-fork-issue.md` - Detailed investigation notes
- `.opencode/plans/phase1-final-simplified.md` - Updated with Week 3 status

---

## Recommendation

**Start with Option 1 (Remove Async)** when you come back:

**Why**:
- Simplest solution
- Highest chance of success
- We're not actually using async features in NodeProcess anyway
- Can always add async back later if needed

**Implementation**:
1. Make `process()` synchronous (remove `async def`)
2. Replace `await run_in_executor()` with direct `msg_queue.get(timeout=0.1)`
3. Add `QApplication.processEvents()` in the loop
4. Remove `with loop: loop.run_until_complete()`
5. Just call `process()` directly, or use `self.app.exec_()` and let QTimer handle it

This avoids the entire qasync/asyncio/Qt integration problem that we've been fighting for hours.

---

## Questions to Consider

1. **Do we actually need async in NodeProcess?**
   - `process()` just polls a Queue and calls sync methods
   - No other async operations happening
   - Answer: Probably not!

2. **Why does the editor pattern work but NodeProcess doesn't?**
   - Maybe different initialization order?
   - Maybe MessageBroker did something we're missing?
   - Maybe qasync behaves differently in forked process?

3. **Is this a qasync bug?**
   - Should qasync handle fork better?
   - Maybe file a bug report after we find workaround?

---

## Git Status

**Branch**: `feature/simplified-architecture`  
**Uncommitted changes**: Week 3 implementation (MessageBroker removal, Queue messaging)

**Don't commit yet** - wait until event loop issue is resolved!

---

## Energy Level

Taking a break is the right call. Fresh eyes often see the solution that tired eyes miss.

**When you come back**:
1. Read this document
2. Try Option 1 (remove async) first
3. If that fails, try Option 2 (QTimer)
4. If both fail, create minimal reproducer (Option 4)

Good luck! 🍀
