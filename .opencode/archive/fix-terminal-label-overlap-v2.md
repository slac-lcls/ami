# Fix Terminal Label Overlap on NodeGraphicsItems (v2)

**Status**: Planning  
**Created**: 2026-03-21  
**Branch**: `subgraph-refactor-clean`  
**Updated**: Added input/output horizontal overlap fix

---

## Problem Statement

Terminal labels on NodeGraphicsItems overlap in TWO scenarios:

### Problem 1: Vertical Overlap (Many Terminals)
When nodes have many terminals, labels overlap vertically because terminal spacing < label height.

### Problem 2: Horizontal Overlap (Input/Output Labels Meet in Middle) ⭐ NEW
When both input and output terminals have long names, their labels overlap in the middle of the node.

**Example**:
```
┌────────────────────────────────────────────────────┐
│                                                    │
● very_long_input_name -------- long_output_name ●  │
│                        ^^^^^^^^                    │
│                     OVERLAP!                       │
└────────────────────────────────────────────────────┘
```

- Input label extends rightward from x=10
- Output label extends leftward from x=100
- **They meet and overlap in the middle!**

---

## Proposed Solution

**Dynamic truncation based on terminal position and node width**:

1. **For input terminals** (left side): Truncate to max ~40-45% of node width
2. **For output terminals** (right side): Truncate to max ~40-45% of node width
3. **Always show full name in tooltip** on hover

This ensures a safe gap in the middle preventing horizontal overlap, while also addressing vertical overlap.

---

## Implementation Details

### Architecture

**File**: `ami/flowchart/Terminal.py`  
**Class**: `TerminalGraphicsItem`

**Key Insight**: We need the node width to calculate appropriate max label width!

### New Method: `_getMaxLabelWidth()`

```python
def _getMaxLabelWidth(self):
    """Calculate maximum label width based on node size and terminal position
    
    Returns:
        Maximum width in pixels for this terminal's label
    """
    # Get parent node bounds
    if self.parentItem():
        node_bounds = self.parentItem().bounds
        node_width = node_bounds.width()
    else:
        # Fallback if no parent
        node_width = 100
    
    # Reserve space: box(10px) + label(40-45% of node) + gap
    box_width = 10
    
    if self.term.isInput():
        # Input labels on left - can use ~45% of node width
        max_width = (node_width * 0.45) - box_width
    else:
        # Output labels on right - can use ~45% of node width  
        max_width = (node_width * 0.45) - box_width
    
    # Ensure minimum readability (at least 30px)
    max_width = max(max_width, 30)
    
    # Cap at reasonable maximum (prevent huge labels on huge nodes)
    max_width = min(max_width, 100)
    
    return max_width
```

### Updated Method: `_truncateLabel()`

```python
def _truncateLabel(self, text, max_width_px):
    """Truncate label text if it exceeds max_width_px, add ellipsis
    
    Args:
        text: Original terminal name
        max_width_px: Maximum width in pixels
        
    Returns:
        tuple: (display_text, was_truncated)
    """
    if not text:
        return ("", False)
    
    # Create temporary text item to measure (including 0.7 scale)
    temp = QtWidgets.QGraphicsTextItem(text)
    temp.setTransform(temp.transform().scale(0.7, 0.7))
    
    # Measure actual width after scaling
    actual_width = temp.boundingRect().width() * 0.7
    
    if actual_width <= max_width_px:
        return (text, False)  # No truncation needed
    
    # Binary search for optimal truncation point
    left, right = 0, len(text)
    best_truncated = text[:1] + "..."
    
    while left <= right:
        mid = (left + right) // 2
        
        if mid == 0:
            break
            
        test_text = text[:mid] + "..."
        temp.setPlainText(test_text)
        test_width = temp.boundingRect().width() * 0.7
        
        if test_width <= max_width_px:
            best_truncated = test_text
            left = mid + 1
        else:
            right = mid - 1
    
    return (best_truncated, True)
```

### Updated Method: `__init__()`

```python
def __init__(self, term, parent=None):
    self.term = term
    GraphicsObject.__init__(self, parent)
    self.brush = fn.mkBrush(0, 0, 0)
    self.box = QtWidgets.QGraphicsRectItem(0, 0, 10, 10, self)
    
    # Get appropriate max width based on terminal position
    max_width = self._getMaxLabelWidth()
    
    # Truncate label if needed
    full_name = self.term.name()
    display_name, was_truncated = self._truncateLabel(full_name, max_width)
    
    # Create label with truncated text
    self.label = QtWidgets.QGraphicsTextItem(display_name, self)
    self.label.setTransform(self.label.transform().scale(0.7, 0.7))
    
    # Always add tooltip with full name (helpful even if not truncated)
    self.label.setToolTip(full_name)
    
    # Visual indicator that label was truncated (optional)
    if was_truncated:
        # Could set different color, style, etc.
        pass
    
    self.newConnection = None
    self.setFiltersChildEvents(True)
    self.setZValue(1)
    self.menu = None
```

---

## Visual Examples

### Example 1: Input/Output Overlap (BEFORE)

```
Node width: 100px

┌────────────────────────────────────────────────────┐
│                                                    │
● input_feature_vector ──── output_predictions ●    │
│                      ^^^^^^                        │
│                      OVERLAP!                      │
└────────────────────────────────────────────────────┘

Input label:  70px wide (x=10 to x=80)
Output label: 60px wide (x=40 to x=100)
Overlap:      40px (x=40 to x=80)
```

### Example 1: Input/Output Overlap (AFTER)

```
Node width: 100px
Max label per side: 45% = 45px - 10px (box) = 35px

┌────────────────────────────────────────────────────┐
│                                                    │
● input_feat...              ...predictions ●        │
│              ^^^^^^^^^^^^^^                        │
│              10px GAP - no overlap!                │
└────────────────────────────────────────────────────┘

Input label:  35px wide (x=10 to x=45)
Gap:          10px       (x=45 to x=55)
Output label: 35px wide (x=65 to x=100)
Overlap:      NONE! ✓
```

### Example 2: Many Terminals with Long Names (BEFORE)

```
┌──────────────┐
│              │
● very_long_input_name_1  ← Extends past node
● very_long_input_name_2  ← Overlaps vertically
● very_long_input_name_3  ← Overlaps vertically
│              │
└──────────────┘
```

### Example 2: Many Terminals with Long Names (AFTER)

```
┌──────────────┐
│              │
● very_lo...   ← Truncated, fits
● very_lo...   ← No vertical overlap
● very_lo...   ← No vertical overlap
│              │
└──────────────┘
[Hover shows full names in tooltips]
```

---

## Width Calculation Examples

### Small Node (100px wide):
- Input max: 45px - 10px = **35px**
- Output max: 45px - 10px = **35px**
- Gap in middle: ~30px

### Medium Node (200px wide):
- Input max: 90px - 10px = **80px**
- Output max: 90px - 10px = **80px**
- Gap in middle: ~40px

### Large Node (400px wide, grows with terminals):
- Input max: 180px - 10px = **100px** (capped)
- Output max: 180px - 10px = **100px** (capped)
- Gap in middle: ~200px

---

## Configuration Parameters

### Tunable Constants:

```python
# In TerminalGraphicsItem

# Percentage of node width allocated to each side's labels
LABEL_WIDTH_RATIO = 0.45  # 45% of node width per side

# Terminal box width
TERMINAL_BOX_WIDTH = 10

# Minimum label width (readability)
MIN_LABEL_WIDTH = 30

# Maximum label width (even on huge nodes)
MAX_LABEL_WIDTH = 100

# Label scale factor (unchanged)
LABEL_SCALE = 0.7
```

---

## Testing Strategy

### Test Case 1: Short Labels (No Truncation)
- Node with terminals: "in", "out"
- **Expected**: No truncation, no overlap

### Test Case 2: Long Input Labels Only
- Inputs: "very_long_input_terminal_name"
- Outputs: "out"
- **Expected**: Input truncated to ~35px, output unchanged

### Test Case 3: Long Output Labels Only
- Inputs: "in"
- Outputs: "very_long_output_terminal_name"
- **Expected**: Output truncated to ~35px, input unchanged

### Test Case 4: Both Long (Critical Case!)
- Inputs: "input_feature_vector_with_long_name"
- Outputs: "output_prediction_results_long_name"
- **Expected**: Both truncated, gap in middle, NO OVERLAP

### Test Case 5: Many Terminals + Long Names
- 10 terminals, all with long names
- **Expected**: All truncated, no vertical OR horizontal overlap

### Test Case 6: Varying Node Sizes
- Test on nodes with heights: 100px, 200px, 400px
- **Expected**: Larger nodes allow longer labels (up to cap)

### Test Case 7: Tooltip Verification
- Hover over truncated label
- **Expected**: Tooltip shows full terminal name

---

## Edge Cases to Handle

### 1. Very Short Terminal Names (< 5 characters)
- **Behavior**: No truncation
- **Test**: "in", "x", "out"

### 2. Unicode Characters in Names
- **Behavior**: Handle correctly (text width calculation)
- **Test**: "入力", "выход", "🔥input"

### 3. Node Without Parent (Initialization)
- **Behavior**: Use fallback width (100px)
- **Test**: Create terminal before adding to node

### 4. Extremely Narrow Nodes (< 50px)
- **Behavior**: Use MIN_LABEL_WIDTH = 30px
- **Test**: Node with 50px width

### 5. Very Wide Nodes (> 500px)
- **Behavior**: Cap at MAX_LABEL_WIDTH = 100px
- **Test**: Node with 500px width

---

## Implementation Steps

### Phase 1: Core Truncation Logic
1. Add `_getMaxLabelWidth()` method
2. Update `_truncateLabel()` to return (text, was_truncated)
3. Handle edge cases (empty string, very short max width)

### Phase 2: Modify Constructor
4. Update `__init__()` to call `_getMaxLabelWidth()`
5. Use dynamic max width for truncation
6. Add tooltip with full terminal name

### Phase 3: Testing
7. Manual testing with all test cases
8. Visual verification in ami-local
9. Performance testing with many terminals (20+)

### Phase 4: Documentation
10. Add docstrings to new/modified methods
11. Document configuration constants
12. Add comments explaining width calculation logic

---

## Questions for User

Before implementation, please confirm:

### 1. Width Allocation
**Current plan**: Each side gets 45% of node width (90% total, 10% gap)

Options:
- **A) 45% per side** (10% gap) - RECOMMENDED
- **B) 40% per side** (20% gap) - More conservative
- **C) 48% per side** (4% gap) - Minimal gap

Which do you prefer?

### 2. Ellipsis Character
- **A) "..."** (three ASCII dots) - Standard
- **B) "…"** (Unicode ellipsis U+2026) - Slightly prettier

### 3. Visual Indication of Truncation
Should truncated labels have visual indication?
- **A) No** (tooltip only) - Clean, simple
- **B) Different color** (e.g., slightly grayed)
- **C) Asterisk** (e.g., "input_fea...*")

### 4. Minimum Label Width
**Current**: 30px minimum

Is this appropriate, or prefer different value?
- Smaller (20px) = more aggressive truncation
- Larger (40px) = better readability on small nodes

---

## Success Criteria

- [ ] Input and output labels never overlap horizontally
- [ ] Labels truncated to appropriate width based on node size
- [ ] Ellipsis appended to truncated labels
- [ ] Full terminal name shows in tooltip on hover
- [ ] No vertical overlap when nodes have many terminals
- [ ] Minimum 10px gap between input/output labels
- [ ] Backward compatible with existing flowcharts
- [ ] Performance acceptable with 20+ terminals
- [ ] Works correctly on nodes of varying widths (100px - 500px)

---

## Code Changes Summary

### Files Modified:
- `ami/flowchart/Terminal.py` (~60 lines added/modified)
  - Add `_getMaxLabelWidth()` method (25 lines)
  - Update `_truncateLabel()` method (30 lines)
  - Modify `__init__()` method (5 lines changed)

### Files NOT Modified:
- `ami/flowchart/Node.py` (no changes needed)

### Backward Compatibility:
✅ **Full compatibility** - Only visual changes, no API changes  
✅ **Existing flowcharts** load without modification  
✅ **No layout changes** - Node positions unchanged  
✅ **Graceful degradation** - Falls back to 100px if no parent

---

## Performance Considerations

### Binary Search Complexity:
- **Time**: O(log n) where n = label length
- **Typical**: log₂(30) ≈ 5 iterations per label
- **With 20 terminals**: 100 iterations total at initialization
- **Impact**: Negligible (<1ms total)

### Memory:
- **Per terminal**: +1 QGraphicsTextItem for measurement (temporary)
- **Impact**: Minimal, temp objects garbage collected

---

## Rollback Plan

If issues arise:
1. Revert changes to `Terminal.py`
2. Labels return to original behavior (may overlap but show full text)

**Risk**: Very low - changes isolated to label display only.

---

## Future Enhancements (Out of Scope)

1. **Adaptive font size**: Reduce font size instead of truncating
2. **Smart abbreviation**: Use domain-specific abbreviations (e.g., "input" → "in")
3. **Angled labels**: Rotate labels 45° to fit more text
4. **Multi-line labels**: Wrap long labels to multiple lines
5. **User preferences**: Allow per-user label truncation settings

---

**Status**: Ready for user approval and implementation

**Estimated Effort**: 2-3 hours (including testing)
