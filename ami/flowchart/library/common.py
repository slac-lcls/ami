# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.widgets.SpinBox import SpinBox
from pyqtgraph.WidgetGroup import WidgetGroup
from pyqtgraph.widgets.ColorButton import ColorButton
from ami.flowchart.Node import Node
import numpy as np

try:
    import metaarray
    HAVE_METAARRAY = True
except ImportError:
    HAVE_METAARRAY = False


def generateUi(opts):
    """Convenience function for generating common UI types"""
    if len(opts) == 0:
        return None, None, None

    widget = QtGui.QWidget()
    layout = QtGui.QFormLayout()
    layout.setSpacing(0)
    widget.setLayout(layout)
    ctrls = {}
    row = 0
    for opt in opts:
        if len(opt) == 2:
            k, t = opt
            o = {}
        elif len(opt) == 3:
            k, t, o = opt
        else:
            raise Exception("Widget specification must be (name, type) or (name, type, {opts})")

        hidden = o.pop('hidden', False)
        tip = o.pop('tip', None)

        if t == 'intSpin':
            w = QtGui.QSpinBox()
            if 'max' in o:
                w.setMaximum(o['max'])
            if 'min' in o:
                w.setMinimum(o['min'])
            if 'value' in o:
                w.setValue(o['value'])
        elif t == 'doubleSpin':
            w = QtGui.QDoubleSpinBox()
            if 'max' in o:
                w.setMaximum(o['max'])
            if 'min' in o:
                w.setMinimum(o['min'])
            if 'value' in o:
                w.setValue(o['value'])
        elif t == 'spin':
            w = SpinBox()
            w.setOpts(**o)
        elif t == 'check':
            w = QtGui.QCheckBox()
            if 'checked' in o:
                w.setChecked(o['checked'])
        elif t == 'combo':
            w = QtGui.QComboBox()
            for i in o['values']:
                w.addItem(i)
        elif t == 'color':
            w = ColorButton()
        else:
            raise Exception("Unknown widget type '%s'" % str(t))

        if tip is not None:
            w.setToolTip(tip)
        w.setObjectName(k)
        layout.addRow(k, w)
        if hidden:
            w.hide()
            label = layout.labelForField(w)
            label.hide()

        ctrls[k] = w
        w.rowNum = row
        row += 1
    group = WidgetGroup(widget)
    return widget, group, ctrls


class CtrlNode(Node):
    """Abstract class for nodes with auto-generated control UI"""

    sigStateChanged = QtCore.Signal(object)

    def __init__(self, name, ui=None, terminals=None, **kwargs):
        self.widget = None
        self.task = None

        if ui is None:
            if hasattr(self, 'uiTemplate'):
                ui = self.uiTemplate
            else:
                ui = []
        if terminals is None:
            terminals = {'In': {'io': 'in'}, 'Out': {'io': 'out'}}
        super(CtrlNode, self).__init__(name=name, terminals=terminals, **kwargs)

        self.ui, self.stateGroup, self.ctrls = generateUi(ui)
        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.changed)

    def ctrlWidget(self):
        return self.ui

    def changed(self, *args, **kwargs):
        self.update(*args, **kwargs)
        self.sigStateChanged.emit(self)

    def saveState(self):
        state = Node.saveState(self)
        if self.stateGroup:
            state['ctrl'] = self.stateGroup.state()
        return state

    def restoreState(self, state):
        Node.restoreState(self, state)
        if self.stateGroup is not None:
            self.stateGroup.setState(state.get('ctrl', {}))

    def hideRow(self, name):
        w = self.ctrls[name]
        label = self.ui.layout().labelForField(w)
        w.hide()
        label.hide()

    def showRow(self, name):
        w = self.ctrls[name]
        label = self.ui.layout().labelForField(w)
        w.show()
        label.show()

    def clear(self):
        if self.task:
            self.task.cancel()
            self.task = None


class PlottingCtrlNode(CtrlNode):
    """Abstract class for CtrlNodes that can connect to plots."""

    def __init__(self, name, ui=None, terminals=None, addr=""):
        super(PlottingCtrlNode, self).__init__(name, addr=addr, ui=ui, terminals=terminals)
        self.plotTerminal = self.addOutput('plot', optional=True)

    def connected(self, term, remote):
        CtrlNode.connected(self, term, remote)
        if term is not self.plotTerminal:
            return
        node = remote.node()
        node.sigPlotChanged.connect(self.connectToPlot)
        self.connectToPlot(node)

    def disconnected(self, term, remote):
        CtrlNode.disconnected(self, term, remote)
        if term is not self.plotTerminal:
            return
        remote.node().sigPlotChanged.disconnect(self.connectToPlot)
        self.disconnectFromPlot(remote.node().getPlot())

    def connectToPlot(self, node):
        """Define what happens when the node is connected to a plot"""
        raise Exception("Must be re-implemented in subclass")

    def disconnectFromPlot(self, plot):
        """Define what happens when the node is disconnected from a plot"""
        raise Exception("Must be re-implemented in subclass")

    def process(self, In, display=True):
        out = CtrlNode.process(self, In, display)
        out['plot'] = None
        return out


class UniOpNode(Node):
    """Generic node for performing any operation like Out = In.fn()"""
    def __init__(self, name, addr):
        super(UniOpNode, self).__init__(name, addr=addr, terminals={
            'In': {'io': 'in'},
            'Out': {'io': 'out'}
        })


def metaArrayWrapper(fn):
    def newFn(self, data, *args, **kargs):
        if HAVE_METAARRAY and (hasattr(data, 'implements') and data.implements('MetaArray')):
            d1 = fn(self, data.view(np.ndarray), *args, **kargs)
            info = data.infoCopy()
            if d1.shape != data.shape:
                for i in range(data.ndim):
                    if 'values' in info[i]:
                        info[i]['values'] = info[i]['values'][:d1.shape[i]]
            return metaarray.MetaArray(d1, info=info)
        else:
            return fn(self, data, *args, **kargs)
    return newFn
