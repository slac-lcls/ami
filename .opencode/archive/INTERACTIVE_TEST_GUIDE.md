# Interactive Testing Guide - Subgraph Refactor

## Overview
This guide covers manual testing of the subgraph refactor features that require GUI interaction.

**Status**: Testing phase after commit c16ec5d

---

## Prerequisites

1. Start AMI in local mode:
   ```bash
   cd /sdf/home/s/seshu/dev/ami
   ami-local random://
   ```

2. Existing test file with subgraph: `subgraph.fc` (contains 1 subgraph)

---

## Test 1: Export Standalone Subgraph ⏳

**Goal**: Verify that existing subgraphs can be exported to standalone `.fc` files

### Steps:
1. Load flowchart with subgraph:
   - File → Open → Select `subgraph.fc`
   - Verify subgraph placeholder appears on canvas

2. Export the subgraph:
   - Right-click on subgraph placeholder
   - Select "Export Subgraph..." from context menu
   - **Expected**: Dialog appears with:
     - Name field (prefilled with "combined.0")
     - Description field (prefilled with existing description)
   - Edit name to "test_export"
   - Edit description to "Test export functionality"
   - Click OK
   - **Expected**: File save dialog appears
   - Save as `test_export.fc`

3. Verify exported file:
   ```bash
   python -c "import json; data = json.load(open('test_export.fc')); print('Keys:', list(data.keys())); print('Metadata:', data.get('subgraph_metadata', 'MISSING'))"
   ```
   - **Expected output**:
     - Has `subgraph_metadata` key
     - Name: "test_export"
     - Description: "Test export functionality"
     - Has `nodes` and `connects` keys

### Result: ⬜ PASS / FAIL

**Notes**:


---

## Test 2: Import Subgraph from Library ⏳

**Goal**: Verify that `.fc` files can be loaded into the subgraph library

### Steps:
1. Open library manager:
   - Click "Manage Libraries" button (or menu item)
   - **Expected**: Unified Library Editor dialog opens
   - **Expected**: Two tree sections visible:
     - Left: "Nodes" (Python files)
     - Right: "Subgraphs" (Flowchart files)

2. Load subgraph file:
   - In right pane, click "Load Files" button
   - Navigate to `test_export.fc`
   - Select and open
   - **Expected**: File appears in right tree with name "test_export"

3. Apply to library:
   - Select "test_export" in tree
   - Click "Apply" button at bottom
   - Close dialog

4. Verify in main UI:
   - **Expected**: Left dock should have third section labeled "Subgraphs"
   - **Expected**: "test_export" appears in subgraph tree
   - Try search box: type "test"
   - **Expected**: Only "test_export" shows (others filtered)

### Result: ⬜ PASS / FAIL

**Notes**:


---

## Test 3: Drag-and-Drop from Library ⏳

**Goal**: Verify that subgraphs can be dragged from library to canvas, creating independent instances

### Steps:
1. Clear canvas (File → New or select all and delete)

2. First instance:
   - Drag "test_export" from library tree to canvas (top-left area)
   - **Expected**: Subgraph placeholder appears at drop location
   - **Expected**: Name is "test_export.0" (auto-renamed)

3. Second instance:
   - Drag "test_export" again to canvas (bottom-right area)
   - **Expected**: Second placeholder appears at drop location
   - **Expected**: Name is "test_export.1" (unique)

4. Third instance:
   - Drag once more to middle of canvas
   - **Expected**: Third placeholder appears
   - **Expected**: Name is "test_export.2"

5. Verify independence:
   - Double-click first instance to view its internals
   - Modify a node inside (change a parameter)
   - Close subgraph view
   - Double-click second instance
   - **Expected**: Second instance nodes are unchanged (independent state)

### Result: ⬜ PASS / FAIL

**Notes**:


---

## Test 4: Runtime Connections ⏳

**Goal**: Verify that connections to subgraph placeholders create direct graph edges (Phase 3 logic)

### Steps:
1. Setup:
   - Clear canvas
   - Drag one instance of "test_export" to canvas
   - Add a source node (e.g., waveform source)
   - **Expected**: Placeholder has input terminals visible

2. Make connection:
   - Drag from source output → placeholder input
   - **Expected**: Connection line appears
   - **Expected**: Terminals turn white (connected color)

3. Check console logs:
   - **Expected logs** (if debug prints enabled):
     ```
     🔗 Subgraph boundary connection detected
     ➡️ Creating direct edge: source_name → internal_node_name
     📝 Updating _input_vars for internal_node_name
     ✅ Direct edge created successfully
     ```

4. Verify graph state:
   - Click "Apply" button to compile graph
   - **Expected**: No errors
   - **Expected**: Graph compiles successfully
   - **Expected**: Data flows from source through subgraph

### Result: ⬜ PASS / FAIL

**Notes**:


---

## Test 5: Runtime Disconnections ⏳

**Goal**: Verify that disconnections remove graph edges correctly (Phase 4 logic)

### Steps:
1. Disconnect:
   - Right-click the connection made in Test 4
   - Select "Remove connection" or drag to disconnect
   - **Expected**: Connection line disappears
   - **Expected**: Terminals turn black (disconnected color)

2. Check console logs:
   - **Expected logs** (if debug prints enabled):
     ```
     ❌ Subgraph boundary disconnection detected
     ➡️ Removing direct edge: source_name → internal_node_name
     📝 Cleaning up _input_vars for internal_node_name
     ✅ Direct edge removed successfully
     ```

3. Reconnect:
   - Drag from source output → placeholder input again
   - **Expected**: Connection restores (white terminals)

4. Verify:
   - Click "Apply"
   - **Expected**: Graph compiles successfully

### Result: ⬜ PASS / FAIL

**Notes**:


---

## Test 6: Hover Display ⏳

**Goal**: Verify that hovering over subgraph placeholder shows description in hover dock

### Steps:
1. Hover over placeholder:
   - Move mouse over subgraph placeholder (don't click)
   - **Expected**: Bottom dock (hover panel) shows:
     - "Subgraph: test_export"
     - Description: "Test export functionality"
     - Node count: "X nodes"

2. Hover over regular node:
   - Move mouse over a regular node
   - **Expected**: Standard node info appears (not subgraph format)

3. Verify description persistence:
   - Create new subgraph from selection with custom description
   - Hover over it
   - **Expected**: Custom description appears

### Result: ⬜ PASS / FAIL

**Notes**:


---

## Test 7: Save/Load Persistence ✅ (Already Verified)

**Status**: Already tested and working according to progress doc

- ✅ Save/load regular flowcharts
- ✅ Save/load flowcharts with subgraphs
- ✅ Descriptions persist across save/load
- ✅ Library tree updates after load

---

## Summary Checklist

- [ ] Test 1: Export Standalone Subgraph
- [ ] Test 2: Import Subgraph from Library
- [ ] Test 3: Drag-and-Drop from Library
- [ ] Test 4: Runtime Connections
- [ ] Test 5: Runtime Disconnections
- [ ] Test 6: Hover Display
- [x] Test 7: Save/Load Persistence (verified)

---

## Known Issues / Observations

**Record any issues found during testing:**

1. 

2. 

3. 

---

## Next Steps After Testing

1. If all tests pass:
   - Update progress document with results
   - Remove debug logging if desired
   - Create final commit
   - Consider merging to main branch

2. If issues found:
   - Document in "Known Issues" above
   - Create bug fixes
   - Re-test
   - Commit fixes separately

---

## Quick Commands

**Start testing environment:**
```bash
cd /sdf/home/s/seshu/dev/ami
ami-local random://
```

**Load test file:**
```bash
# In AMI GUI: File → Open → subgraph.fc
```

**Verify exported file structure:**
```bash
python -c "import json; data = json.load(open('test_export.fc')); print(json.dumps(data.get('subgraph_metadata', {}), indent=2))"
```

**Check git status:**
```bash
git status
git log --oneline -3
```
