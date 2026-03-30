# Subgraph Library Template Update Workflow

## Question
**What happens if we modify the original instance for the subgraph, do those changes apply to the one in the library?**

## Answer
**No, changes do NOT automatically propagate.** Library templates are snapshots, not live references.

---

## How It Works

### When Subgraph is Added to Library
```
Create Subgraph → Snapshot State → Store in Library Template
                                         ↓
                                    (frozen copy)
```

**The library template stores:**
- Node types and configurations
- Internal connections
- Node states (positions, parameters, etc.)

**This is a one-time snapshot** - future changes to the flowchart don't affect it.

---

## Timeline Example

```
Time 1: Create Subgraph "MyFilter"
        ├─ Node A (threshold=10)
        ├─ Node B (gain=2.5)
        └─ Connection: A → B
        
        → Auto-added to library as template

Time 2: Modify "MyFilter" in flowchart
        ├─ Node A (threshold=20)  ← Changed!
        ├─ Node B (gain=5.0)      ← Changed!
        ├─ Node C                 ← Added!
        └─ Connections: A → B → C
        
        → Library template STILL has old version:
          - threshold=10, gain=2.5
          - No Node C

Time 3: Drag from library to create new instance
        → Gets original template (threshold=10, gain=2.5)
        → Does NOT include Node C
```

---

## Solution: Manual Update

### Context Menu Action
Right-click on subgraph placeholder → **"Update Library Template"**

This menu item:
- Only appears if subgraph is in the library
- Creates a fresh snapshot of current state
- Replaces the old template in the library
- Updates the UI tree
- Shows status message: "Updated subgraph template: MyFilter"

### When to Use
- After modifying nodes inside a subgraph
- When you want new instances to use the updated version
- Before sharing the flowchart (so others get current templates)

---

## Workflow

### Option 1: Quick Iteration (In-Session)
```
1. Create subgraph → Auto-added to library
2. Drag to create instance → Uses current template
3. Modify original subgraph
4. Right-click → "Update Library Template"
5. Drag to create another instance → Uses updated template
```

### Option 2: Persistent Export
```
1. Create subgraph → Auto-added to library
2. Modify and refine
3. Right-click → "Update Library Template"
4. Right-click → "Export Subgraph..." → Save to .fc file
5. In other flowcharts: "Manage Subgraph Library" → Load .fc file
```

---

## Benefits of Snapshot Approach

### Stability
- Library templates don't change unexpectedly
- Instances created at different times are consistent
- User has explicit control over when to update

### Clarity
- Clear distinction between "working version" and "template version"
- User knows exactly when library changes
- Status messages provide feedback

### Performance
- No overhead tracking changes to nodes
- No complex reference management
- Simple snapshot/restore mechanism

---

## Implementation Details

### Method Signature
```python
def _addSubgraphToLibrary(self, subgraph_name, update=False):
    """
    Args:
        subgraph_name: Name of the subgraph in self._subgraphs
        update: If True, replace existing template
                If False, skip if template exists
    """
```

### Conditional Menu Item
```python
# Only show "Update Library Template" if subgraph is in library
if self.node.flowchart.subgraph_library.hasSubgraph(self.node.name()):
    update_action = menu.addAction("Update Library Template")
    update_action.triggered.connect(self.updateLibraryTemplate)
```

### User Feedback
```python
action = "Updated" if update else "Added"
self.widget().updateStatus(f"{action} subgraph template: {subgraph_name}")
```

---

## Alternative Approaches Considered

### Live Updates (Rejected)
- **Pros**: Always current, no manual step
- **Cons**: Complex, unexpected behavior, performance overhead
- **Why rejected**: Users would lose control, unclear when template changes

### Auto-update on Export (Rejected)
- **Pros**: Natural workflow, tied to file save
- **Cons**: Doesn't help in-session workflow, not discoverable
- **Why rejected**: Export is optional, not always used

### Manual Refresh (Selected ✓)
- **Pros**: User control, explicit, clear feedback, simple
- **Cons**: Requires manual action
- **Why selected**: Balances control with simplicity

---

## User Experience

### Discovery
- User modifies subgraph in flowchart
- Drags from library to create new instance
- Sees old version, realizes template needs updating
- Right-clicks, sees "Update Library Template"

### Confirmation
- Clicks "Update Library Template"
- Sees status: "Updated subgraph template: MyFilter"
- Next drag-drop gets new version
- Clear cause-and-effect

### Edge Cases
- If subgraph not in library: Menu item doesn't appear
- If no widget: Update silently skipped (defensive coding)
- If update succeeds: UI tree refreshed automatically
