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
