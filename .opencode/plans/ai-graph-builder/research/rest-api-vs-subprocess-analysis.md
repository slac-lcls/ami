# Analysis: REST API vs Subprocess for OpenCode Integration

**Date**: 2026-03-31  
**Context**: Chat mode currently takes 12 seconds per agent response  
**Question**: Would switching to REST API improve performance?

---

## Current Approach: Subprocess via CLI

### Implementation

```python
# chat() function spawns subprocess for each request
cmd = [
    'opencode', 'run',
    '--attach', server_url,
    '--format', 'json',
    '--dir', os.getcwd(),
    '--session', session_id,
    prompt
]

proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, text=True)

# Stream JSON events from stdout
for line in proc.stdout:
    event = json.loads(line)
    if event['type'] == 'text':
        print(event['part']['text'], end='', flush=True)
    if 'sessionID' in event:
        session_id = event['sessionID']

proc.wait()
```

### Overhead Per Request

| Component | Estimated Time | Can Optimize? |
|-----------|----------------|---------------|
| Python process spawn | 100-300ms | ✅ Use REST API |
| CLI argument parsing | 10-50ms | ✅ Use REST API |
| OpenCode client init | 50-200ms | ✅ Use REST API |
| Server connection (HTTP) | 10-50ms | ✅ Keep-alive |
| Skill loading | 0-1000ms | ⚠️ Server-side caching |
| AI model inference | 8000-11000ms | ❌ Model-dependent |
| **Total** | **8170-12600ms** | **Potential: 170-600ms savings** |

### Problems

1. **Process spawn overhead**: Every request spawns new Python process
2. **No connection reuse**: New TCP connection each time
3. **Zombie processes**: Risk of orphaned processes if interrupted
4. **Resource usage**: Each process has memory overhead
5. **Slow error feedback**: Have to wait for process exit to get error codes

---

## Proposed Approach: Direct REST API

### What We Know About OpenCode HTTP API

From `opencode --help`:
- ✅ `opencode serve` runs HTTP server (supports --port, --hostname, --cors)
- ✅ `opencode run --attach <url>` connects to HTTP server
- ✅ `opencode attach <url>` suggests HTTP-based protocol
- ✅ Server is already running (confirmed via `ps aux`)
- ❓ **Unknown**: Exact API endpoints and request/response format

### Hypothetical REST API Implementation

```python
import requests

# One-time setup (outside loop)
session = requests.Session()
session.headers.update({'Content-Type': 'application/json'})

# In chat loop - no process spawn
response = session.post(
    f'{server_url}/api/run',  # Endpoint TBD
    json={
        'prompt': prompt,
        'session_id': session_id,
        'format': 'json',
        'skill': 'ami-graph-builder',  # Or in prompt?
        'dir': os.getcwd()
    },
    stream=True,  # For streaming responses
    timeout=30
)

# Stream response (assuming newline-delimited JSON like CLI)
for line in response.iter_lines(decode_unicode=True):
    if line:
        event = json.loads(line)
        if event['type'] == 'text':
            print(event['part']['text'], end='', flush=True)
        if 'sessionID' in event:
            session_id = event['sessionID']
```

### Overhead Per Request

| Component | Estimated Time | Savings vs Subprocess |
|-----------|----------------|----------------------|
| HTTP POST request | 1-10ms | ✅ **90-290ms saved** |
| Server already running | 0ms | ✅ **50-200ms saved** |
| Connection reuse (Keep-Alive) | 0-5ms | ✅ **10-45ms saved** |
| Skill loading | 0-1000ms | ⚠️ Same as before |
| AI model inference | 8000-11000ms | ❌ Same as before |
| **Total** | **8001-12015ms** | **150-535ms faster** |

### Benefits

1. ✅ **Faster**: No process spawn overhead (150-535ms savings)
2. ✅ **Resource efficient**: No new processes, reuse HTTP connection
3. ✅ **Cleaner error handling**: HTTP status codes instead of exit codes
4. ✅ **No zombie processes**: All in-process, no subprocess management
5. ✅ **Better debugging**: Can use standard HTTP debugging tools
6. ✅ **Streaming still works**: HTTP chunked encoding or SSE
7. ✅ **Session continuity**: Still supported via JSON payload

### Challenges

1. ❓ **API discovery**: Need to find actual endpoint URLs and request format
2. ❓ **Authentication**: Does server require auth? (--password flag suggests maybe)
3. ❓ **Streaming format**: SSE, chunked JSON, or WebSocket?
4. ⚠️ **Dependency**: Need `requests` library (already available but may need adding to requirements)
5. ⚠️ **Error handling**: Need to handle HTTP errors, timeouts, connection failures

---

## Performance Impact Analysis

### Current 12-Second Breakdown (Estimated)

Based on typical LLM API latency:

```
User types prompt
↓
[0.0s - 0.5s]   Subprocess spawn + CLI init + connection
[0.5s - 1.5s]   Skill loading (ami-graph-builder + references)
[1.5s - 12.0s]  AI model inference (actual thinking)
[12.0s]         Response complete
```

**If this estimate is correct**: REST API would reduce 12s → **11.5s** (only 0.5s improvement)

### Alternative Breakdown (If Skill Loading is Slow)

```
User types prompt
↓
[0.0s - 0.3s]   Subprocess spawn + CLI init + connection
[0.3s - 10.0s]  Skill loading + processing (if not cached)
[10.0s - 12.0s] AI model inference
[12.0s]         Response complete
```

**If this is correct**: REST API saves 0.3s → **11.7s** (minimal improvement)

### Alternative Breakdown (If Process Spawn is Very Slow)

```
User types prompt
↓
[0.0s - 2.0s]   Subprocess spawn (slow system)
[2.0s - 2.5s]   CLI init + connection + skill loading
[2.5s - 12.0s]  AI model inference
[12.0s]         Response complete
```

**If this is correct**: REST API could save 2.0s → **10.0s** (significant!)

---

## Investigation Needed

### Critical Questions

Before deciding whether to switch to REST API, we need to answer:

#### 1. **Where is the 12 seconds actually spent?**

Add timing instrumentation:

```python
import time

t0 = time.time()
print(f"[{time.time()-t0:.2f}s] Starting request")

proc = subprocess.Popen(...)
print(f"[{time.time()-t0:.2f}s] Process spawned")

# First event received?
for line in proc.stdout:
    if first_event:
        print(f"[{time.time()-t0:.2f}s] First event received")
        first_event = False
    # ...

proc.wait()
print(f"[{time.time()-t0:.2f}s] Request complete")
```

**This will tell us**:
- How long process spawn takes
- How long until first response byte (TTFB)
- How long the AI takes to complete

#### 2. **What is the actual OpenCode HTTP API?**

Options to discover:

**Option A: Check OpenCode documentation**
- Is there API documentation?
- GitHub repo for OpenCode?

**Option B: Network inspection**
```bash
# Run with network tracing
strace -e trace=network opencode run --attach <url> "test prompt"

# Or use tcpdump
sudo tcpdump -i lo -A 'port 4096'
```

**Option C: Ask OpenCode team**
- Is there official API documentation?
- Is direct HTTP access supported/recommended?

**Option D: Use subprocess but optimize it**
- Could we keep subprocess but improve it?
- Pre-warm connection pool?
- Reuse processes?

#### 3. **Is skill loading cached server-side?**

Test:
```bash
# First request
time opencode run --attach <url> "test 1"

# Second request (should be faster if cached)
time opencode run --attach <url> "test 2"
```

If second request is much faster → skill loading is cached, REST API won't help much

If both same speed → skill loads every time, need server-side caching fix

#### 4. **What's the model inference time?**

This is the AI's actual thinking time. Can't be optimized without:
- Using faster model
- Reducing prompt size
- Using streaming better (perception of speed)

---

## Decision Matrix

| Scenario | Bottleneck | Solution | Expected Improvement |
|----------|------------|----------|---------------------|
| **A**: Process spawn is 2s+ | Subprocess overhead | ✅ Switch to REST API | 🚀 **10s** (2s saved) |
| **B**: Process spawn is 0.5s | Subprocess overhead | ✅ Switch to REST API | ⚡ **11.5s** (0.5s saved) |
| **C**: Skill loading is 8s+ | Server-side caching | 🔧 Fix skill caching | 🚀 **4s** (8s saved!) |
| **D**: Model inference is 10s+ | AI processing | 🤔 Use faster model | ⚠️ May reduce quality |
| **E**: Prompt is huge | Prompt size | ✏️ Reduce skill docs | ⚡ Small improvement |

---

## Recommendations

### Step 1: Profile Current Performance ⭐ **DO THIS FIRST**

Add timing instrumentation to understand where 12s is spent:

```python
import time

def timed_opencode_call(prompt, session_id):
    """Call OpenCode with detailed timing"""
    times = {}
    
    t0 = time.time()
    times['start'] = 0.0
    
    # Build command
    cmd = ['opencode', 'run', '--attach', server_url, ...]
    times['cmd_built'] = time.time() - t0
    
    # Spawn process
    proc = subprocess.Popen(...)
    times['proc_spawned'] = time.time() - t0
    
    # Wait for first byte
    first_line = True
    for line in proc.stdout:
        if first_line:
            times['first_byte'] = time.time() - t0
            first_line = False
        # ... process line ...
    
    proc.wait()
    times['complete'] = time.time() - t0
    
    # Report timing
    print(f"\n⏱️  Timing breakdown:")
    print(f"  Process spawn: {times['proc_spawned']:.2f}s")
    print(f"  Time to first byte: {times['first_byte']:.2f}s")
    print(f"  Total time: {times['complete']:.2f}s")
    print(f"  AI inference: {times['complete'] - times['first_byte']:.2f}s")
    
    return times
```

**This will definitively answer**: Is it worth switching to REST API?

### Step 2: Based on Profiling Results

#### If subprocess spawn > 1s → **Switch to REST API** ✅

Benefit: 1-2s improvement (10-11s total)

**Action items**:
1. Discover OpenCode HTTP API (network trace or docs)
2. Implement REST API version
3. Test performance improvement
4. Estimated effort: 2-4 hours

#### If subprocess spawn < 500ms → **Don't switch to REST API** ❌

Benefit: <0.5s improvement (11.5s+ total, marginal)

**Better investments**:
1. Investigate skill loading caching (bigger potential)
2. Reduce skill documentation size
3. Use faster model
4. Improve streaming UX (feels faster)

#### If skill loading > 5s → **Fix server-side caching** 🔧

This has the biggest potential improvement!

**Action items**:
1. Verify skill isn't cached between requests
2. Contact OpenCode team about skill caching
3. Or implement local caching wrapper
4. Potential: 5-8s improvement (4-7s total!)

### Step 3: Quick Wins While Investigating

Even without REST API, we can improve UX:

#### Optimization 1: Async State Request (Already Planned)

Our Comm fix will save 0.5s of wasted timeout → **11.5s**

#### Optimization 2: Better Streaming Feedback

```python
# Show progress during long waits
print("🤖 Thinking", end='', flush=True)
start = time.time()

for line in proc.stdout:
    # Print dots every 2 seconds to show it's alive
    if time.time() - start > 2:
        print(".", end='', flush=True)
        start = time.time()
    # ... process line ...
```

Doesn't actually speed things up, but **feels faster** (user knows it's working)

#### Optimization 3: Reduce Skill Documentation

Current: ~3600 lines of docs loaded each request

Could reduce to:
- Core instructions only: ~500 lines
- Load detailed references on-demand
- Potential: 0.5-2s improvement

---

## Proposed Plan

### Phase 1: Investigation (30 minutes)

1. **Add timing instrumentation** to current subprocess approach
2. **Run test requests** and collect timing data
3. **Analyze bottleneck**: subprocess, skill loading, or AI inference?

### Phase 2: Decision (Based on Phase 1 Results)

**If subprocess spawn > 1s**:
- → Proceed with REST API investigation (Phase 3A)

**If skill loading > 5s**:
- → Investigate server-side skill caching (Phase 3B)

**If AI inference > 10s**:
- → Focus on UX improvements (Phase 3C)
- → Consider model optimization (longer term)

### Phase 3A: REST API Implementation (4-6 hours)

1. **Discover API format** (network trace or documentation)
2. **Implement HTTP client** using `requests`
3. **Test streaming** (ensure it works like subprocess)
4. **Measure improvement** (should see 1-2s reduction)
5. **Update error handling** (HTTP status codes)

### Phase 3B: Skill Caching Investigation (2-4 hours)

1. **Verify skill loading time** (first vs subsequent requests)
2. **Contact OpenCode team** about caching strategy
3. **Implement workaround** if needed (local skill cache)
4. **Measure improvement** (could see 5-8s reduction!)

### Phase 3C: UX Improvements (1-2 hours)

1. **Add progress indicators** (dots, spinner, time elapsed)
2. **Show partial results** as they stream in
3. **Async state request** (our Comm fix - already planned)
4. **Optimize prompt** (reduce documentation size)

---

## Open Questions for User

### 1. **Profiling First?**

Should we add timing instrumentation **before** deciding on REST API?

**Recommended**: Yes - make data-driven decision

### 2. **Acceptable Latency?**

What's the target response time?
- **4-5s**: Requires aggressive optimization (skill caching + REST API + model)
- **8-10s**: Achievable with skill caching OR REST API
- **11-11.5s**: Just Comm fix (already planned)

### 3. **REST API Investigation Effort**

If we proceed with REST API:
- Should we ask OpenCode team for API docs first?
- Or dive into network tracing to reverse-engineer it?
- Estimated effort: 30min (ask) vs 2-3hr (reverse-engineer)

### 4. **Combined Approach?**

Should we:
- **Option A**: Just fix Comm (0.5s improvement, low effort)
- **Option B**: Comm + REST API (1-2s improvement, medium effort)
- **Option C**: Comm + Skill Caching (5-8s improvement, unknown effort)
- **Option D**: All of the above (maximum improvement, high effort)

**Recommended**: Start with Comm fix + profiling, then decide next steps based on data

---

## Summary

### Key Insights

1. ✅ **OpenCode has HTTP-based protocol** (confirmed via `--attach`, `serve`, `--cors` flags)
2. ✅ **REST API is technically feasible** (requests library available)
3. ❓ **But we don't know if it's worth it yet** (need profiling data)
4. ⚠️ **Real bottleneck might be skill loading or AI inference**, not subprocess

### Recommended Immediate Actions

1. **Add timing instrumentation** to understand 12s breakdown
2. **Fix Comm async issue** (already planned, saves 0.5s)
3. **Profile and decide** based on data:
   - If subprocess > 1s → REST API
   - If skill loading > 5s → Caching
   - If AI > 10s → UX improvements

### Expected Outcomes

| Optimization | Effort | Improvement | New Total |
|--------------|--------|-------------|-----------|
| Comm fix (planned) | Low | 0.5s | 11.5s |
| REST API | Medium | 0.5-2s | 10-11s |
| Skill caching | Unknown | 5-8s | 4-7s ⭐ |
| Faster model | Low | Variable | Unknown ⚠️ |
| **All combined** | **High** | **6-10s** | **2-6s** 🚀 |

---

**Status**: ✅ ANALYSIS COMPLETE - Awaiting user decision on next steps  
**Recommendation**: Profile first, then decide  
**Last Updated**: 2026-03-31
