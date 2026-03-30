# Source Node Replacement - Current Status

## Changes Made

### 1. Pass flowchart parameter to node constructors

**ami/flowchart/Flowchart.py:**
- Line 149: Pass `flowchart=self` when creating nodes via `createNode()`
- Line 237: Pass `flowchart=self` when creating replacement SourceNodes
- Lines 197-251: Added `replaceSourceNode()` method

**ami/flowchart/FlowchartGraphicsView.py:**
- Line 397: Pass `flowchart=self.widget.chart` when creating SourceNodes via dropEvent

**ami/flowchart/Node.py:**
- Line 105: Accept and store `flowchart` parameter in Node.__init__()
- Lines 952-989: Added buildReplaceMenu(), _buildReplaceSubmenu(), replaceTriggered()
- Added debug logging to buildReplaceMenu() to diagnose issues

**ami/flowchart/NodeLibrary.py:**
- Lines 140-170: Added getSourcesByType() method

## Known Issues

1. **"it still doesn't seem to be working"** - need more details on what behavior is observed
   - Does the menu not appear?
   - Is the menu empty?
   - Does it crash?
   
2. **Debug logging added** - should provide more info when right-clicking source nodes

## Debug Output to Check

When right-clicking a source node, look for these debug messages:

```
ami.flowchart.Node - DEBUG - buildReplaceMenu called for node: <node_name>
ami.flowchart.Node - DEBUG -   Current type: <type>, current name: <name>
ami.flowchart.Node - DEBUG -   Matching sources: <sources>
ami.flowchart.Node - DEBUG -   Building replace menu with <N> alternatives
```

If you see:
- `Node has no _flowchart attribute` → flowchart parameter not being passed correctly
- `_flowchart is None` → flowchart parameter is None when it shouldn't be  
- `source_library is None` → source library not initialized yet
- `No matching sources found` → getSourcesByType() returning empty (expected if no alternatives of same type)

## Next Steps

1. Launch AMI and test right-click on source node
2. Check console output for debug messages
3. Report what messages appear and what behavior is observed
4. Based on that, we can diagnose the specific issue

## Testing

The basic functionality works:
- ✅ getSourcesByType() tested and working
- ✅ Node accepts flowchart parameter
- ✅ replaceSourceNode() logic implemented

What needs verification:
- ⏳ flowchart parameter actually reaches nodes in real GUI
- ⏳ source_library is populated when menu is built
- ⏳ Menu appears in GUI
- ⏳ Replacement actually works end-to-end
