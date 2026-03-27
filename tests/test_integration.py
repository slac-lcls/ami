"""
Integration tests for AMI GUI + Backend workflows.

These tests verify complete user workflows:
- Create graph in GUI → Save .fc → Execute on backend
- Load .fc in GUI → Modify → Save
"""

import asyncio
import pytest
import os
import json
import time
from ami.flowchart.library.common import SourceNode


@pytest.mark.asyncio
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
@pytest.mark.parametrize('start_ami', ['static'], indirect=True)
async def test_create_in_gui_save_execute_on_backend(qtbot, flowchart, start_ami, tmp_path):
    """
    Full workflow:
    1. Create graph in GUI
    2. Save to .fc file
    3. Load and execute on backend
    4. Verify results
    """
    fc, broker = flowchart
    comm = start_ami
    qtbot.addWidget(fc.widget())  # Ensure widget is created
    
    # Step 1: Create graph in GUI
    # Create a source node
    node_name = 'cspad'
    node_type = fc.source_library.getSourceType(node_name)
    source_node = SourceNode(name=node_name, terminals={'Out': {'io': 'out', 'ttype': node_type}})
    fc.addNode(node=source_node)
    
    # Create a processing node (Roi2D)
    fc.createNode('Roi2D')
    
    # Get nodes and connect them
    cspad_node = fc.nodes(data='node')['cspad']
    roi_node = fc.nodes(data='node')['Roi2D.0']
    
    cspad_out = cspad_node._outputs['Out']
    roi_in = roi_node._inputs['In']
    cspad_out().connectTo(roi_in())
    
    # Wait for connection to register
    await asyncio.sleep(0.1)
    
    # Verify graph was created
    assert len(fc._graph.edges()) == 1
    
    # Step 2: Save to .fc file
    fc_path = tmp_path / 'integration_test.fc'
    widget = fc.widget()
    widget.setCurrentFile(str(fc_path))
    widget.saveClicked()
    
    # Verify file was created
    assert fc_path.exists()
    
    # Verify saved file has correct content
    with open(fc_path) as f:
        data = json.load(f)
        node_names = [node['name'] for node in data['nodes']]
        assert 'cspad' in node_names
        assert 'Roi2D.0' in node_names
    
    # Step 3: Apply graph to backend (the integration point!)
    await widget.applyClicked()
    
    # Step 4: Verify graph was submitted to backend successfully
    comm_handler = widget.graphCommHandler
    version = await comm_handler.graphVersion
    assert version > 0, "Graph should have been applied to backend"


@pytest.mark.asyncio
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
async def test_load_atm_crix_modify_save(qtbot, flowchart, tmp_path):
    """
    Workflow: Load ATM_crix_new.fc → Modify in GUI → Save
    """
    fc, broker = flowchart
    qtbot.addWidget(fc.widget())
    
    # Load the .fc file
    fc_path = 'tests/graphs/ATM_crix_new.fc'
    await fc.loadFile(fc_path)
    await asyncio.sleep(0.2)
    
    # Verify loaded correctly
    nodes = fc.nodes(data='node')
    initial_node_count = len(nodes)
    assert initial_node_count > 4  # At least 4 source nodes + processing nodes
    
    # Verify sources were loaded
    assert 'timing:raw:eventcodes' in nodes
    assert 'c_atmopal:raw:image' in nodes
    
    # Modify: add a new node
    fc.createNode('Projection')
    await asyncio.sleep(0.1)
    
    # Verify modification
    nodes = fc.nodes(data='node')
    assert 'Projection.0' in nodes
    assert len(nodes) == initial_node_count + 1
    
    # Save to new file
    new_fc_path = tmp_path / 'modified_atm_crix.fc'
    widget = fc.widget()
    widget.setCurrentFile(str(new_fc_path))
    widget.saveClicked()
    
    # Verify save
    assert new_fc_path.exists()
    
    with open(new_fc_path) as f:
        data = json.load(f)
        node_names = [node['name'] for node in data['nodes']]
        assert 'Projection.0' in node_names
        # Verify sources are still there
        assert any('timing:raw:eventcodes' in name for name in node_names)

