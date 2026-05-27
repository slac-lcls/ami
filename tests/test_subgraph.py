"""
Tests for AMI flowchart subgraph functionality.

These tests verify the visual-only subgraph feature in AMI's flowchart.
Subgraphs are a way to organize nodes visually without modifying the
underlying computation graph.

Note: Tests avoid creating boundary connections due to a known issue with
ConnectionItem viewBox handling when nodes haven't been moved to the subgraph
view yet. Tests also avoid operations that trigger ZMQ messaging (like close())
as these can cause event loop issues in the test environment.
"""

import asyncio

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_make_subgraph_from_selection(qtbot, flowchart):
    """Test creating a visual-only subgraph from selected nodes (isolated node, no boundary connections)."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())  # Ensure widget is created

    # Create a simple isolated processing node (no connections to avoid ConnectionItem viewBox bug)
    fc.createNode("Roi2D")

    # Get the node
    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]
    roi_node_name = roi_node.name()

    await asyncio.sleep(0.1)

    # Create subgraph from isolated Roi2D node (no boundary connections)
    subgraph_name = "test_subgraph"
    fc.makeSubgraphFromSelection(nodes=[roi_node], name=subgraph_name, description="Test subgraph")

    await asyncio.sleep(0.1)

    # Verify subgraph metadata exists
    assert subgraph_name in fc._subgraphs
    sg_data = fc._subgraphs[subgraph_name]

    # Verify subgraph contains the correct nodes
    assert roi_node_name in sg_data["nodes"]

    # Verify placeholder exists
    assert "placeholder" in sg_data
    placeholder = sg_data["placeholder"]
    assert placeholder is not None
    assert placeholder.isSubgraph

    # Verify view was created
    assert "view" in sg_data
    assert sg_data["view"] is not None

    # Verify boundary connections list exists (but should be empty for isolated node)
    assert "boundary_connections" in sg_data
    # No connections since node is isolated
    boundary_conns = sg_data["boundary_connections"]
    assert len(boundary_conns) == 0

    # Verify the node is still in the computation graph
    assert roi_node_name in fc._graph.nodes()


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_subgraph_metadata_structure(qtbot, flowchart):
    """Test that subgraph metadata has the expected structure."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # Create a simple isolated node
    fc.createNode("Roi2D")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]

    await asyncio.sleep(0.1)

    # Create subgraph
    subgraph_name = "test_subgraph"
    fc.makeSubgraphFromSelection(nodes=[roi_node], name=subgraph_name, description="Test description")

    await asyncio.sleep(0.1)

    # Verify subgraph metadata structure
    sg_data = fc._subgraphs[subgraph_name]

    # Check all expected keys exist
    assert "nodes" in sg_data
    assert "placeholder" in sg_data
    assert "view" in sg_data
    assert "boundary_connections" in sg_data
    assert "description" in sg_data

    # Verify types
    assert isinstance(sg_data["nodes"], list)
    assert sg_data["placeholder"] is not None
    assert sg_data["view"] is not None
    assert isinstance(sg_data["boundary_connections"], list)
    assert isinstance(sg_data["description"], str)
    assert sg_data["description"] == "Test description"


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_subgraph_placeholder_is_visual_only(qtbot, flowchart):
    """Test that subgraph placeholder is marked as visual-only and not added to computation graph."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # Create a simple isolated node
    fc.createNode("Roi2D")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]

    await asyncio.sleep(0.1)

    # Create subgraph
    subgraph_name = "test_subgraph"
    fc.makeSubgraphFromSelection(nodes=[roi_node], name=subgraph_name, description="Test")

    await asyncio.sleep(0.1)

    sg_data = fc._subgraphs[subgraph_name]
    placeholder = sg_data["placeholder"]

    # Verify placeholder is marked as visual-only
    assert hasattr(placeholder, "is_visual_only")
    assert placeholder.is_visual_only is True

    # Verify placeholder is NOT in the computation graph
    # (only the child Roi2D node should be in the graph)
    assert placeholder.name() not in fc._graph.nodes()

    # The computation graph should still contain the original Roi2D node
    assert roi_node.name() in fc._graph.nodes()


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_subgraph_helper_nodes(qtbot, flowchart):
    """Test that SubgraphInput and SubgraphOutput helper nodes are created correctly."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # Create a simple isolated node
    fc.createNode("Roi2D")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]

    await asyncio.sleep(0.1)

    # Create subgraph
    subgraph_name = "test_subgraph"
    fc.makeSubgraphFromSelection(nodes=[roi_node], name=subgraph_name, description="Test")

    await asyncio.sleep(0.1)

    sg_data = fc._subgraphs[subgraph_name]
    placeholder = sg_data["placeholder"]

    # Verify helper nodes exist
    assert hasattr(placeholder, "subgraphInputs")
    assert hasattr(placeholder, "subgraphOutputs")

    sg_inputs = placeholder.subgraphInputs
    sg_outputs = placeholder.subgraphOutputs

    assert sg_inputs is not None
    assert sg_outputs is not None

    # Verify helper nodes have the correct parent reference
    assert hasattr(sg_inputs, "rootNode")
    assert hasattr(sg_outputs, "rootNode")
    assert sg_inputs.rootNode == placeholder
    assert sg_outputs.rootNode == placeholder


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_subgraph_with_multiple_nodes(qtbot, flowchart):
    """Test creating a subgraph with multiple internally-connected nodes."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # Create three nodes that will all be in the subgraph
    fc.createNode("Roi2D")
    fc.createNode("Projection")
    fc.createNode("Binning")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]
    proj_nodes = [n for n in all_nodes.keys() if n.startswith("Projection.")]
    proj_node = all_nodes[proj_nodes[-1]]
    bin_nodes = [n for n in all_nodes.keys() if n.startswith("Binning.")]
    bin_node = all_nodes[bin_nodes[-1]]

    # Connect them internally (all connections stay within subgraph)
    roi_out = roi_node._outputs["Out"]
    proj_in = proj_node._inputs["In"]
    roi_out().connectTo(proj_in())

    proj_out = proj_node._outputs["Out"]
    bin_in = bin_node._inputs["In"]
    proj_out().connectTo(bin_in())

    await asyncio.sleep(0.1)

    # Create subgraph with all three nodes
    subgraph_name = "test_subgraph"
    fc.makeSubgraphFromSelection(
        nodes=[roi_node, proj_node, bin_node], name=subgraph_name, description="Multi-node subgraph"
    )

    await asyncio.sleep(0.1)

    # Verify subgraph contains all three nodes
    sg_data = fc._subgraphs[subgraph_name]
    assert len(sg_data["nodes"]) == 3
    assert roi_node.name() in sg_data["nodes"]
    assert proj_node.name() in sg_data["nodes"]
    assert bin_node.name() in sg_data["nodes"]

    # Verify no boundary connections (all connections are internal)
    assert len(sg_data["boundary_connections"]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_import_subgraph(qtbot, flowchart):
    """Test importing a subgraph from exported state dict."""
    import json
    import os

    from ami.flowchart.SubgraphNode import SubgraphNode

    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # Load the export.fc test data
    export_fc_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "export.fc")
    with open(export_fc_path, "r") as f:
        full_state = json.load(f)

    # Build an exported subgraph state from the full_state
    # The export.fc contains a subgraph definition in subgraphs section
    # We need to construct the import format manually for testing
    subgraph_info = full_state["subgraphs"][0]
    subgraph_node_names = subgraph_info["nodes"]

    # Get the nodes that are in the subgraph
    subgraph_nodes = [n for n in full_state["nodes"] if n["name"] in subgraph_node_names]

    # Get connections within the subgraph
    subgraph_connects = []
    for conn in full_state["connects"]:
        if conn[0] in subgraph_node_names and conn[2] in subgraph_node_names:
            subgraph_connects.append(conn)

    # Create a mock exported subgraph state with boundary metadata
    # For testing purposes, we'll create boundary terminals
    export_state = {
        "subgraph_metadata": {
            "name": "subgraph.0",
            "description": "Test subgraph",
            "boundary_inputs": [
                {
                    "placeholder_terminal": "cspad.Out",
                    "internal_node": "ExponentialMovingAverage2D.0",
                    "internal_terminal": "In",
                    "ttype": "amitypes.array.Array2d",
                }
            ],
            "boundary_outputs": [
                {
                    "placeholder_terminal": "ExponentialMovingAverage2D.0.Out",
                    "internal_node": "ExponentialMovingAverage2D.0",
                    "internal_terminal": "Out",
                    "ttype": "amitypes.array.Array2d",
                },
                {
                    "placeholder_terminal": "ExponentialMovingAverage2D.0.Count",
                    "internal_node": "ExponentialMovingAverage2D.0",
                    "internal_terminal": "Count",
                    "ttype": "int",
                },
            ],
        },
        "nodes": subgraph_nodes,
        "connects": subgraph_connects,
    }

    # Import the subgraph
    fc.importSubgraphFromFile(export_state, pos=(200, 200))

    # 1. Verify a subgraph is created in fc._subgraphs
    assert len(fc._subgraphs) == 1

    # 2. Verify the subgraph metadata has expected keys
    sg_name = list(fc._subgraphs.keys())[0]
    sg_data = fc._subgraphs[sg_name]
    assert "nodes" in sg_data
    assert "placeholder" in sg_data
    assert "view" in sg_data
    assert "boundary_connections" in sg_data
    assert "description" in sg_data

    # 3. Verify the placeholder is a SubgraphNode with is_visual_only = True
    placeholder = sg_data["placeholder"]
    assert isinstance(placeholder, SubgraphNode)
    assert placeholder.is_visual_only is True

    # 4. Verify placeholder has correct INPUT terminals
    input_terminals = list(placeholder.inputs())
    assert "cspad.Out" in input_terminals

    # 5. Verify placeholder has correct OUTPUT terminals
    output_terminals = list(placeholder.outputs())
    assert "ExponentialMovingAverage2D.0.Out" in output_terminals
    assert "ExponentialMovingAverage2D.0.Count" in output_terminals

    # 6. Verify all 3 imported nodes are in fc._graph.nodes()
    all_nodes = list(fc._graph.nodes())
    ema_nodes = [n for n in all_nodes if "ExponentialMovingAverage2D" in n]
    img_nodes = [n for n in all_nodes if "ImageViewer" in n]
    plot_nodes = [n for n in all_nodes if "ScalarPlot" in n]
    assert len(ema_nodes) >= 1
    assert len(img_nodes) >= 1
    assert len(plot_nodes) >= 1

    # 7. Verify placeholder name is NOT in fc._graph.nodes()
    assert placeholder.name() not in fc._graph.nodes()

    # 8. Verify sg_data["nodes"] list has 3 entries
    assert len(sg_data["nodes"]) == 3

    # 9. Verify at least one imported node has non-zero position
    has_nonzero_pos = False
    for node_name in sg_data["nodes"]:
        node = fc._graph.nodes[node_name]["node"]
        pos = node.graphicsItem().pos()
        if pos.x() != 0 or pos.y() != 0:
            has_nonzero_pos = True
            break
    assert has_nonzero_pos

    # Final sleep to drain pending coroutines
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_import_subgraph_unique_naming(qtbot, flowchart):
    """Test importing the same subgraph twice creates unique names."""
    import json
    import os

    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # Load the export.fc test data
    export_fc_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "export.fc")
    with open(export_fc_path, "r") as f:
        full_state = json.load(f)

    # Build exported subgraph state
    subgraph_info = full_state["subgraphs"][0]
    subgraph_node_names = subgraph_info["nodes"]
    subgraph_nodes = [n for n in full_state["nodes"] if n["name"] in subgraph_node_names]
    subgraph_connects = []
    for conn in full_state["connects"]:
        if conn[0] in subgraph_node_names and conn[2] in subgraph_node_names:
            subgraph_connects.append(conn)

    export_state = {
        "subgraph_metadata": {
            "name": "subgraph.0",
            "description": "Test subgraph",
            "boundary_inputs": [],
            "boundary_outputs": [],
        },
        "nodes": subgraph_nodes,
        "connects": subgraph_connects,
    }

    # Import the subgraph TWICE
    fc.importSubgraphFromFile(export_state, pos=(200, 200))

    fc.importSubgraphFromFile(export_state, pos=(400, 400))

    # 1. Verify fc._subgraphs has exactly 2 entries
    assert len(fc._subgraphs) == 2

    # 2. Verify the two subgraph names are different
    sg_names = list(fc._subgraphs.keys())
    assert sg_names[0] != sg_names[1]
    # One should be "subgraph.0" and the other should have an additional suffix
    assert "subgraph.0" in sg_names[0] or "subgraph.0" in sg_names[1]

    # 3. Verify imported node names are different between the two subgraphs
    sg1_nodes = set(fc._subgraphs[sg_names[0]]["nodes"])
    sg2_nodes = set(fc._subgraphs[sg_names[1]]["nodes"])
    # No overlapping node names
    assert len(sg1_nodes & sg2_nodes) == 0

    # 4. Both subgraphs have 3 nodes each
    assert len(fc._subgraphs[sg_names[0]]["nodes"]) == 3
    assert len(fc._subgraphs[sg_names[1]]["nodes"]) == 3

    # Final sleep to drain pending coroutines
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_save_restore_with_subgraph(qtbot, flowchart):
    """Test saving and restoring flowchart state with a subgraph."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # 1. Create 3 nodes: Roi2D, Projection, Binning
    fc.createNode("Roi2D")
    fc.createNode("Projection")
    fc.createNode("Binning")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]
    proj_nodes = [n for n in all_nodes.keys() if n.startswith("Projection.")]
    proj_node = all_nodes[proj_nodes[-1]]
    bin_nodes = [n for n in all_nodes.keys() if n.startswith("Binning.")]
    bin_node = all_nodes[bin_nodes[-1]]

    # 2. Connect them internally
    roi_out = roi_node._outputs["Out"]
    proj_in = proj_node._inputs["In"]
    roi_out().connectTo(proj_in())

    proj_out = proj_node._outputs["Out"]
    bin_in = bin_node._inputs["In"]
    proj_out().connectTo(bin_in())

    await asyncio.sleep(0.1)

    # 3. Create subgraph from all 3
    fc.makeSubgraphFromSelection(nodes=[roi_node, proj_node, bin_node], name="test_sg", description="Test")

    # Store original node names
    original_node_names = [roi_node.name(), proj_node.name(), bin_node.name()]

    # 4. Save state
    state = fc.saveState()

    # 5. Verify state["subgraphs"] has 1 entry with name "test_sg"
    assert "subgraphs" in state
    assert len(state["subgraphs"]) == 1
    assert state["subgraphs"][0]["name"] == "test_sg"

    # 6. Clear flowchart
    await fc.clear()

    # Need to wait for Qt event processing after clear
    qtbot.wait(100)

    # 7. Verify fc._subgraphs is empty
    assert len(fc._subgraphs) == 0

    # 8. Restore state (synchronous but may trigger Qt events)
    fc.restoreState(state)

    # Need to wait for Qt event processing and subgraph creation
    qtbot.wait(200)
    await asyncio.sleep(0.1)

    # 9. Verify fc._subgraphs has "test_sg" with 3 nodes
    assert "test_sg" in fc._subgraphs
    assert len(fc._subgraphs["test_sg"]["nodes"]) == 3

    # 10. Verify all 3 original node names are still in fc._graph.nodes()
    current_nodes = list(fc._graph.nodes())
    for name in original_node_names:
        assert name in current_nodes

    # Final sleep to drain pending coroutines (longer for restoreState async operations)
    await asyncio.sleep(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_export_import_roundtrip(qtbot, flowchart):
    """Test exporting and importing a subgraph (manual construction to avoid dialog)."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # 1. Create 2 nodes: Roi2D, Projection
    fc.createNode("Roi2D")
    fc.createNode("Projection")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]
    proj_nodes = [n for n in all_nodes.keys() if n.startswith("Projection.")]
    proj_node = all_nodes[proj_nodes[-1]]

    # 2. Connect: Roi2D.Out → Projection.In
    roi_out = roi_node._outputs["Out"]
    proj_in = proj_node._inputs["In"]
    roi_out().connectTo(proj_in())

    await asyncio.sleep(0.1)

    # 3. Create subgraph
    fc.makeSubgraphFromSelection(nodes=[roi_node, proj_node], name="roundtrip_sg", description="Roundtrip test")

    # 4. Manually construct export state (to avoid dialog in exportSubgraph)
    sg_data = fc._subgraphs["roundtrip_sg"]
    nodes_state = []
    for node_name in sg_data["nodes"]:
        node = fc._graph.nodes[node_name]["node"]
        nodes_state.append({"class": type(node).__name__, "name": node_name, "state": node.saveState()})

    connects = []
    for from_node, to_node, data in fc._graph.edges(data=True):
        if from_node in sg_data["nodes"] and to_node in sg_data["nodes"]:
            connects.append((from_node, data["from_term"], to_node, data["to_term"]))

    export_state = {
        "subgraph_metadata": {
            "name": "roundtrip_sg",
            "description": "Roundtrip test",
            "boundary_inputs": [],
            "boundary_outputs": [],
        },
        "nodes": nodes_state,
        "connects": connects,
    }

    # 6. Verify exported_state has subgraph_metadata with boundary_inputs and boundary_outputs
    assert "subgraph_metadata" in export_state
    assert "boundary_inputs" in export_state["subgraph_metadata"]
    assert "boundary_outputs" in export_state["subgraph_metadata"]

    # 7. Import the exported state
    fc.importSubgraphFromFile(export_state, pos=(400, 400))

    # 9. Now fc._subgraphs should have 2 entries (original + imported)
    assert len(fc._subgraphs) == 2

    # 10. The imported subgraph should have 2 nodes
    imported_sg_names = [name for name in fc._subgraphs.keys() if name != "roundtrip_sg"]
    assert len(imported_sg_names) == 1
    imported_sg_data = fc._subgraphs[imported_sg_names[0]]
    assert len(imported_sg_data["nodes"]) == 2

    # Final sleep to drain pending coroutines (longer for import async operations)
    await asyncio.sleep(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_clear_clears_library(qtbot, flowchart):
    """Test that clearing the flowchart also clears the subgraph library."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # 1. Create a node and make a subgraph from it
    fc.createNode("Roi2D")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]

    fc.makeSubgraphFromSelection(nodes=[roi_node], name="test_lib_sg", description="Library test")

    # 2. Verify the subgraph template is in the library
    assert fc.subgraph_library.hasSubgraph("test_lib_sg") is True

    # 3. Call clear
    await fc.clear()

    # Need to wait for Qt event processing after clear
    qtbot.wait(100)
    await asyncio.sleep(0.1)

    # 4. Verify library is empty
    assert len(fc.subgraph_library.getNames()) == 0

    # 5. Verify fc._subgraphs is empty
    assert len(fc._subgraphs) == 0

    # Final sleep to drain pending coroutines (longer for clear async operations)
    await asyncio.sleep(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
async def test_add_node_to_subgraph_updates_tracking(qtbot, flowchart):
    """Test that adding a node while in subgraph view updates tracking."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())

    # 1. Create an isolated Roi2D node
    fc.createNode("Roi2D")

    all_nodes = dict(fc.nodes(data="node"))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith("Roi2D.")]
    roi_node = all_nodes[roi_nodes[-1]]

    # 2. Create a subgraph from it
    fc.makeSubgraphFromSelection(nodes=[roi_node], name="track_sg", description="Tracking test")

    # 3. Get the subgraph data
    sg_data = fc._subgraphs["track_sg"]

    # 4. Verify sg_data["nodes"] has 1 entry and placeholder.children has 1 entry
    assert len(sg_data["nodes"]) == 1
    assert len(sg_data["placeholder"].children) == 1

    # 5. Switch to the subgraph view
    fc.viewManager().displayView(name="track_sg")

    # 6. Create a new node while in subgraph view
    fc.createNode("Projection")

    # 7. Verify sg_data["nodes"] now has 2 entries
    assert len(sg_data["nodes"]) == 2

    # 8. Verify placeholder.children has 2 entries
    assert len(sg_data["placeholder"].children) == 2

    # 10. The new Projection node name should be in sg_data["nodes"]
    all_nodes_after = dict(fc.nodes(data="node"))
    proj_nodes = [n for n in all_nodes_after.keys() if n.startswith("Projection.")]
    assert len(proj_nodes) >= 1
    proj_node_name = proj_nodes[-1]
    assert proj_node_name in sg_data["nodes"]

    # 11. Switch back
    fc.viewManager().displayView(name="root")

    # Final sleep to drain pending coroutines
    await asyncio.sleep(0.2)
