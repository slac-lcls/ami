# Week 3 Bug Fix: QApplication Fork Issue

**Date**: March 31, 2026  
**Issue**: "QCoreApplication::exec: The event loop is already running" error in NodeProcess  
**Status**: RESOLVED  

---

## Problem Summary

After implementing Week 3 (removing MessageBroker and having Flowchart spawn NodeProcesses directly), display nodes would crash immediately on spawn with:

```
QCoreApplication::exec: The event loop is already running
RuntimeError: Event loop stopped before Future completed.
```

The error occurred at line 368 in `ami/client/flowchart.py` when calling `loop.run_until_complete(self.process())`.

---

## Root Cause Analysis

### The Fork Problem

When using `multiprocessing.Process` on Unix systems (default method is `fork`):

1. **Parent Process (Flowchart)**: Has a QApplication running (created in `run_editor_window()`)
2. **Fork occurs**: Child process created via `mp.Process(target=run_node_process_main, ...)`
3. **Child Process (NodeProcess)**: Inherits parent's memory state via copy-on-write
4. **Critical Issue**: Child inherits the parent's QApplication singleton pointer

### Why This Breaks

```python
# In NodeProcess.__init__() - BROKEN CODE
app = QtWidgets.QApplication.instance()  # Returns parent's stale pointer!
if app is None:
    app = QtWidgets.QApplication([])
```

**What happens**:
- `QApplication.instance()` is a static method returning a global singleton pointer
- After fork, child has a **copy** of this pointer from parent's memory
- The pointer points to parent's QApplication (different process, invalid!)
- Creating QEventLoop from this invalid QApplication causes Qt errors
- Qt's event loop becomes confused: "event loop already running" (in parent)
- qasync's `run_until_complete()` fails: "loop stopped before future completed"

### Why Old Code Worked

```python
# Old MessageBroker code - WORKING
if loop is None:
    self.app = QtWidgets.QApplication([])  # ALWAYS creates new!
    if THEME:
        qdarktheme.setup_theme(THEME)
    loop = QEventLoop(self.app)
```

The old code:
- **Always** created a fresh `QApplication([])` without checking `instance()`
- Qt allows creating a new QApplication - it replaces the singleton
- This overwrites the stale forked pointer with a valid new one
- Theme applied at correct time (after QApp, before QEventLoop)

---

## Investigation Process

### Attempts That Failed

1. **Try 1**: Use `with loop:` context manager
   - Still crashed - didn't fix the underlying QApp issue
   
2. **Try 2**: Create loop before widgets
   - Still crashed - QApp.instance() still returned stale pointer
   
3. **Try 3**: Use `create_task()` + `run_forever()` instead of `run_until_complete()`
   - Still crashed - same root cause
   
4. **Try 4**: Don't use `with loop:` at all
   - Still crashed - QApp issue remained

5. **Try 5**: Move everything inside `with loop:`
   - Still crashed - setup timing wasn't the issue

6. **Try 6**: Create loop at top of `__init__()` and store as `self.loop`
   - Still crashed - QApp.instance() was the problem all along

### The Breakthrough

Compared our implementation line-by-line with old working code:

**Key Difference Found**:
```python
# Old (WORKS)
self.app = QtWidgets.QApplication([])

# Current (BREAKS)  
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication([])
```

**Realization**: 
- After fork, `QApplication.instance()` returns non-None (parent's pointer)
- But that pointer is **invalid** in the child process
- Must **always create fresh QApplication** in forked process

---

## The Solution

### Change 1: Always Create Fresh QApplication

```python
# In NodeProcess.__init__() - line 291
# BEFORE (BROKEN):
# app = QtWidgets.QApplication.instance()
# if app is None:
#     app = QtWidgets.QApplication([])

# AFTER (FIXED):
self.app = QtWidgets.QApplication([])
```

### Change 2: Apply Theme at Correct Time

```python
# In NodeProcess.__init__() - lines 293-295
# Apply theme AFTER QApp creation, BEFORE QEventLoop
if THEME:
    qdarktheme.setup_theme(THEME)

# Create event loop
loop = QEventLoop(self.app)
asyncio.set_event_loop(loop)
```

### Change 3: Use Exact Old Pattern for Loop

```python
# In NodeProcess.__init__() - lines 362-364
# BEFORE (BROKEN):
# self.loop.create_task(self.process())
# try:
#     self.loop.run_forever()
# except KeyboardInterrupt:
#     pass

# AFTER (FIXED):
with loop:
    loop.run_until_complete(self.process())
```

### Change 4: Simplify CloseNode Handling

```python
# In NodeProcess.process() - lines 406-408
elif msg_type == "CloseNode":
    logger.info(f"NodeProcess {self.name} received close message, exiting")
    return  # Exit process - run_until_complete() will complete
    # No need for loop.stop() - just returning completes the coroutine
```

---

## Key Lessons Learned

### 1. Qt and Multiprocessing Don't Mix Well

- Qt is **NOT fork-safe**
- QApplication singleton doesn't work across fork boundaries
- Must create fresh QApplication in forked child process
- Never use `QApplication.instance()` in forked child

### 2. Timing Matters

The correct order in forked process:
1. Create fresh `QApplication([])`
2. Apply theme (if needed)
3. Create `QEventLoop(app)`
4. Create widgets
5. Run event loop

### 3. Trust the Old Working Code

When debugging:
- Compare **line-by-line** with known working implementation
- Even small differences matter (instance() vs constructor)
- Don't assume old pattern is outdated - it worked for a reason!

### 4. Fork Behavior is Subtle

- Child inherits parent's memory (copy-on-write)
- Static/global variables are copied, including singletons
- Pointers to objects in parent become invalid in child
- Must reinitialize framework-level objects (like QApplication)

---

## Testing Results

After fix applied:

✅ No "QCoreApplication::exec: The event loop is already running" error  
✅ No "RuntimeError: Event loop stopped before Future completed" error  
✅ Display nodes spawn successfully  
✅ Node windows appear correctly  
✅ State saves to shared memory  
✅ Crash recovery works  
✅ All Week 1 & Week 2 functionality intact  

---

## Code Changes Summary

| File | Lines | Change |
|------|-------|--------|
| `ami/client/flowchart.py` | 291 | Always create fresh QApplication |
| `ami/client/flowchart.py` | 293-295 | Apply theme after QApp, before loop |
| `ami/client/flowchart.py` | 362-364 | Use `with loop: run_until_complete()` |
| `ami/client/flowchart.py` | 408 | Simplify CloseNode (just return) |
| `ami/client/flowchart.py` | 261-263 | Remove theme from wrapper |

**Net change**: -5 lines (cleaner code!)

---

## Related Issues

### Multiprocessing Start Methods

Python multiprocessing has three start methods:
- **fork** (Unix default): Copies parent memory, fast but can have issues with threads/frameworks
- **spawn**: Starts fresh Python interpreter, slower but safer
- **forkserver**: Hybrid approach

Our fix works with `fork` (the default). If issues persist, could try:
```python
import multiprocessing as mp
mp.set_start_method('spawn')
```

But this wasn't necessary - fixing QApplication.instance() was sufficient.

### Alternative Solutions Considered

1. **Don't use Qt in forked process**: Not feasible - need Qt for GUI
2. **Use spawn instead of fork**: Slower, unnecessary once root cause found
3. **Synchronous queue polling**: Would work but loses async benefits
4. **QTimer polling**: Different architecture, unnecessary change

---

## Prevention Guidelines

### When Forking with Qt

**DO**:
- Always create fresh `QApplication([])` in child
- Initialize Qt objects in child process, not parent
- Use proper event loop patterns from Qt/qasync docs

**DON'T**:
- Use `QApplication.instance()` in forked child
- Reuse parent's Qt objects
- Assume singleton patterns work across fork

### Code Review Checklist

When working with multiprocessing + Qt:
- [ ] Is QApplication created fresh in each process?
- [ ] Are we checking `instance()` instead of creating new?
- [ ] Is theme/setup done at correct time?
- [ ] Does event loop pattern match working examples?

---

## References

- **Old working code**: Commit `c3c434c` (`MessageBroker` implementation)
- **Qt fork safety**: https://doc.qt.io/qt-5/threads-qobject.html
- **Python multiprocessing**: https://docs.python.org/3/library/multiprocessing.html
- **qasync documentation**: https://github.com/CabbageDevelopment/qasync

---

## Timeline

- **March 31, 11:16**: First error observed after Week 3 implementation
- **March 31, 11:16-11:31**: Multiple failed attempts using different event loop patterns
- **March 31, 11:31-11:45**: Deep dive comparing with old code
- **March 31, 11:45**: Breakthrough - identified `QApplication.instance()` issue
- **March 31, 11:50**: Fix implemented and tested
- **March 31, 11:55**: All tests passing ✅

**Total debug time**: ~40 minutes  
**Root cause**: Single line - using `.instance()` instead of creating fresh QApp  

---

## Conclusion

This was a subtle but critical bug caused by Qt's singleton pattern not being fork-safe. The fix was simple once identified: always create a fresh QApplication in the forked child process instead of trying to reuse the parent's instance.

The debugging process highlighted the importance of:
1. Line-by-line comparison with working code
2. Understanding framework-specific limitations (Qt not fork-safe)
3. Not assuming "modern" patterns (like `.instance()`) are always better
4. Trusting proven working code patterns

This issue is now documented for future reference when working with Qt and multiprocessing in Python.
