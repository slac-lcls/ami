from qtpy import QtCore
from ami.flowchart.library.Numpy import Projection, Binning
from ami.flowchart.library.Accumulators import PickN
from ami.flowchart.library.Display import ScatterPlot, ScalarPlot
import ami.graph_nodes as gn
import numpy as np


def test_projection(qtbot):

    node = Projection('projection')
    widget = node.ctrlWidget()
    # showing windows steals focus after the tests exit, its not necessary for the test, and is annoying
    # widget.show()
    qtbot.addWidget(widget)

    assert node.values['axis'] == 0
    qtbot.keyPress(node.ctrls['axis'], QtCore.Qt.Key_Up)
    assert node.values['axis'] == 1

    inputs = {"In": node.name()}
    op = node.to_operation(inputs)
    mop = gn.Map(name="projection_operation",
                 conditions_needs=[],
                 inputs=list(inputs.values()),
                 outputs=[node.name()+'.Out'],
                 func=lambda a: np.sum(a, axis=1))

    assert op.name == mop.name
    assert op.condition_needs == mop.condition_needs
    assert op.inputs == mop.inputs
    assert op.outputs == mop.outputs


def test_pickn(qtbot):

    node = PickN('pickn')
    widget = node.ctrlWidget()
    # widget.show()
    qtbot.addWidget(widget)

    assert node.values['N'] == 2
    qtbot.keyPress(node.ctrls['N'], QtCore.Qt.Key_Up)
    assert node.values['N'] == 3

    inputs = {"In": node.name()}
    op = node.to_operation(inputs)
    pop = gn.PickN(name="pickn_operation",
                   condition_needs=[],
                   inputs=list(inputs.values()),
                   outputs=[node.name()+'.Out'],
                   N=3)

    assert op.name == pop.name
    assert op.condition_needs == pop.condition_needs
    assert op.inputs == pop.inputs
    assert op.outputs == pop.outputs
    assert op.N == pop.N


def test_binning(qtbot):

    node = Binning('binning')
    widget = node.ctrlWidget()
    # widget.show()
    qtbot.addWidget(widget)

    assert node.values['bins'] == 10
    qtbot.keyPress(node.ctrls['bins'], QtCore.Qt.Key_Up)
    qtbot.keyPress(node.ctrls['bins'], QtCore.Qt.Key_Up)
    assert node.values['bins'] == 12

    assert node.values['range min'] == 1
    qtbot.keyPress(node.ctrls['range min'], QtCore.Qt.Key_Down)
    assert node.values['range min'] == 0

    assert node.values['range max'] == 100
    for i in range(0, 10):
        qtbot.keyPress(node.ctrls['range max'], QtCore.Qt.Key_Up)
    assert node.values['range max'] == 110

    op = node.to_operation(inputs={"In": node.name()})
    assert len(op) == 2
    assert type(op[0]) == gn.Map
    assert type(op[1]) == gn.Accumulator


def test_scatterplot(qtbot):

    node = ScatterPlot('scatter')
    widget = node.ctrlWidget()
    # widget.show()
    qtbot.addWidget(widget)

    assert node.values['Num Points'] == 100
    qtbot.keyPress(node.ctrls['Num Points'], QtCore.Qt.Key_Up)
    assert node.values['Num Points'] == 101

    inputs = {"X": "X",
              "Y": "Y"}
    op = node.to_operation(inputs)
    assert type(op[0]) == gn.RollingBuffer
    assert type(op[1]) == gn.Map
    assert op[0].N == 101

    node.addInput(removable=True)
    assert len(node.terminals) == 4
    for t in ["X", "Y", "X.1", "Y.1"]:
        assert t in node.terminals
        assert node.terminals[t].isInput()

    assert not node.terminals["X"].isRemovable()
    assert not node.terminals["Y"].isRemovable()
    assert node.terminals["X.1"].isRemovable()
    assert node.terminals["Y.1"].isRemovable()


def test_scalarplot(qtbot):

    node = ScalarPlot('scalar')
    widget = node.ctrlWidget()
    # widget.show()
    qtbot.addWidget(widget)

    assert node.values['Num Points'] == 100
    qtbot.keyPress(node.ctrls['Num Points'], QtCore.Qt.Key_Down)
    qtbot.keyPress(node.ctrls['Num Points'], QtCore.Qt.Key_Down)
    assert node.values['Num Points'] == 98

    inputs = {"Y": "Y"}
    op = node.to_operation(inputs)
    assert type(op) == gn.RollingBuffer
    assert op.N == 98

    node.addInput(removable=True)
    assert len(node.terminals) == 2
    assert "Y" in node.terminals
    assert node.terminals["Y"].isInput()
    assert "Y.1" in node.terminals
    assert node.terminals["Y.1"].isInput()

    assert not node.terminals["Y"].isRemovable()
    assert node.terminals["Y.1"].isRemovable()
