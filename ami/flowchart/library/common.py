# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from ami.flowchart.Node import Node, NodeGraphicsItem
from ami.flowchart.library.DisplayWidgets import generateUi, ScalarWidget, WaveformWidget, AreaDetWidget
from amitypes import Array1d, Array2d
import asyncio


MAX = 2147483647


class CtrlNode(Node):
    """Abstract class for nodes with auto-generated control UI"""

    sigStateChanged = QtCore.Signal(object)

    def __init__(self, name, ui=None, terminals={}, **kwargs):
        super().__init__(name=name, terminals=terminals, **kwargs)
        self.widget = None
        self.task = None

        if ui is None:
            if hasattr(self, 'uiTemplate'):
                ui = self.uiTemplate
            else:
                ui = []

        self.ui, self.stateGroup, self.ctrls = generateUi(ui)
        self.init_values(ui)
        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

    def init_values(self, opts):
        for opt in opts:
            assert(len(opt) == 3)

            k, t, o = opt
            k = k.replace(" ", "_")

            if 'group' in o:
                k = k+'_'+o['group']
            if 'value' in o:
                setattr(self, k, o['value'])
            elif 'values' in o:
                setattr(self, k, o['values'][0])
            elif 'index' in o:
                setattr(self, k, o['values'][o['index']])
            elif 'checked' in o:
                setattr(self, k, o['checked'])

            if t == "text" and 'value' not in o:
                setattr(self, k, "")

    def ctrlWidget(self):
        return self.ui

    def state_changed(self, *args, **kwargs):
        self.update(*args, **kwargs)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        if args:
            name, val = args
            name = name.replace(" ", "_")
            setattr(self, name, val)

    def saveState(self):
        state = super().saveState()
        if self.stateGroup:
            state['ctrl'] = self.stateGroup.state()

        if self.widget and hasattr(self.widget, 'saveState'):
            state['widget'] = self.widget.saveState()

        return state

    def restoreState(self, state):
        super().restoreState(state)
        if self.stateGroup is not None:
            ctrlstate = state.get('ctrl', {})
            self.stateGroup.setState(ctrlstate)
            for k, ctrl in self.ctrls.items():
                if isinstance(ctrl, QtGui.QLineEdit):
                    ctrl.setText(ctrlstate[k])

        if self.widget is not None and 'widget' in state:
            self.widget.restoreState(state['widget'])

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

        self.widget = None

    def display(self, topics=None, terms=None, addr=None, win=None, widget=None, **kwargs):
        if self.widget is None and widget:
            self.widget = widget(topics, terms, addr, win, node=self, **kwargs)

        if self.task is None and self.widget and topics and terms and addr:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget


class SourceNode(CtrlNode):

    def __init__(self, **kwargs):
        kwargs['viewable'] = True
        kwargs['allowAddCondition'] = False
        super(SourceNode, self).__init__(**kwargs)

        self.widgetType = None

        terminals = kwargs['terminals']
        ttype = terminals['Out']['ttype']

        if ttype is int or ttype is float or ttype is bool:
            self.widgetType = ScalarWidget
        elif ttype is Array1d:
            self.widgetType = WaveformWidget
        elif ttype is Array2d:
            self.widgetType = AreaDetWidget

        self._input_vars["In"] = self.name()

    def display(self, topics, terms, addr, win, **kwargs):
        if self.widgetType:
            return super().display(topics, terms, addr, win, self.widgetType, **kwargs)

    def isSource(self):
        return True


class MathGraphicsItem(NodeGraphicsItem):

    def buildMenu(self, reset=False):
        super().buildMenu(reset)
        actions = self.menu.actions()
        addInput = actions[2]

        addFloat = QtGui.QAction("Add float", self.menu)
        addFloat.triggered.connect(self.node.addFloat)
        self.menu.insertAction(addInput, addFloat)

        addWaveform = QtGui.QAction("Add waveform", self.menu)
        addWaveform.triggered.connect(self.node.addWaveform)
        self.menu.insertAction(addInput, addWaveform)

        addImage = QtGui.QAction("Add image", self.menu)
        addImage.triggered.connect(self.node.addImage)
        self.menu.insertAction(addWaveform, addImage)

        self.menu.removeAction(addInput)


class MathNode(Node):

    def __init__(self, name):
        super().__init__(name,
                         terminals={'Float': {'io': 'in', 'ttype': float, 'removable': True},
                                    'Waveform': {'io': 'in', 'ttype': Array1d, 'removable': True},
                                    'Image': {'io': 'in', 'ttype': Array2d, 'removable': True},
                                    'Out': {'io': 'out', 'ttype': Array2d}},
                         allowAddInput=True)
        self.sigTerminalAdded.connect(self.setOutput)
        self.sigTerminalRemoved.connect(self.setOutput)

    def graphicsItem(self, brush=None):
        if self._graphicsItem is None:
            self._graphicsItem = MathGraphicsItem(self, brush)
        return self._graphicsItem

    def isConnected(self):
        if len(self.terminals) < 3:
            return False

        return super(MathNode, self).isConnected()

    def addFloat(self):
        self.addTerminal('Float', io='in', ttype=float, removable=True)

    def addWaveform(self):
        self.addTerminal('Waveform', io='in', ttype=Array1d, removable=True)

    def addImage(self):
        self.addTerminal('Image', io='in', ttype=Array2d, removable=True)

    def setOutput(self):
        inputs = set()

        for name, term in self._inputs.items():
            inputs.add(term()._type)

        if Array2d in inputs:
            output_type = Array2d
        elif Array1d in inputs:
            output_type = Array1d
        elif float in inputs:
            output_type = float
        else:
            raise Exception("Unable to set output type!")

        self._outputs['Out']()._type = output_type
