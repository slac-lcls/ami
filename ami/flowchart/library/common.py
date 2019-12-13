# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.widgets.SpinBox import SpinBox
from pyqtgraph.WidgetGroup import WidgetGroup
from pyqtgraph.widgets.ColorButton import ColorButton
from ami.flowchart.Node import Node, NodeGraphicsItem
from ami.flowchart.library.DisplayWidgets import ScalarWidget, WaveformWidget, AreaDetWidget
from amitypes import Array1d, Array2d
import asyncio
import re
import numpy as np


MAX = 2147483647
_float_re = re.compile(r'(([+-]?\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)')


def valid_float_string(string):
    match = _float_re.search(string)
    return match.groups()[0] == string if match else False


def format_float(value):
    """Modified form of the 'g' format specifier."""
    string = "{:g}".format(value).replace("e+", "e")
    string = re.sub("e(-?)0*(\\d+)", r"e\1\2", string)
    return string


class FloatValidator(QtGui.QValidator):

    def validate(self, string, position):
        if valid_float_string(string):
            state = QtGui.QValidator.Acceptable
        elif string == "" or string[position-1] in 'e.-+':
            state = QtGui.QValidator.Intermediate
        else:
            state = QtGui.QValidator.Invalid
        return (state, string, position)

    def fixup(self, text):
        match = _float_re.search(text)
        return match.groups()[0] if match else ""


class ScientificDoubleSpinBox(QtGui.QDoubleSpinBox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimum(-np.inf)
        self.setMaximum(np.inf)
        self.validator = FloatValidator()
        self.setDecimals(1000)

    def validate(self, text, position):
        return self.validator.validate(text, position)

    def fixup(self, text):
        return self.validator.fixup(text)

    def valueFromText(self, text):
        return float(text)

    def textFromValue(self, value):
        return format_float(value)

    def stepBy(self, steps):
        text = self.cleanText()
        groups = _float_re.search(text).groups()
        decimal = float(groups[1])
        decimal += steps
        new_string = "{:g}".format(decimal) + (groups[3] if groups[3] else "")
        self.lineEdit().setText(new_string)

    def widgetGroupInterface(self):
        return (lambda w: w.valueChanged,
                QtGui.QDoubleSpinBox.value,
                QtGui.QDoubleSpinBox.setValue)


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
    group = WidgetGroup()
    focused = False
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
            w = ScientificDoubleSpinBox()
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
            w.setFocus()
            if 'checked' in o:
                w.setChecked(o['checked'])
        elif t == 'combo':
            w = QtGui.QComboBox()
            for i in o['values']:
                w.addItem(i)
        elif t == 'color':
            w = ColorButton()
        elif t == 'text':
            w = QtGui.QLineEdit()
            if 'placeholder' in o:
                w.setPlaceholderText(o['placeholder'])
        else:
            raise Exception("Unknown widget type '%s'" % str(t))

        if tip is not None:
            w.setToolTip(tip)

        w.setObjectName(k)

        if t != 'text' and not focused:
            w.setFocus()
            focused = True

        layout.addRow(k, w)
        if hidden:
            w.hide()
            label = layout.labelForField(w)
            label.hide()

        w.rowNum = row
        ctrls[k] = w
        group.addWidget(w, k)
        row += 1

    return widget, group, ctrls


class CtrlNode(Node):
    """Abstract class for nodes with auto-generated control UI"""

    sigStateChanged = QtCore.Signal(object)

    def __init__(self, name, ui=None, terminals={}, **kwargs):
        super(CtrlNode, self).__init__(name=name, terminals=terminals, **kwargs)
        self.widget = None
        self.task = None

        if ui is None:
            if hasattr(self, 'uiTemplate'):
                ui = self.uiTemplate
            else:
                ui = []

        self.init_values(ui)
        self.ui, self.stateGroup, self.ctrls = generateUi(ui)
        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.changed)

            for k, ctrl in self.ctrls.items():
                if isinstance(ctrl, QtGui.QLineEdit):
                    ctrl.textChanged.connect(lambda text: self.stateGroup.sigChanged.emit(k, text))

    def init_values(self, opts):
        for opt in opts:

            if len(opt) != 3:
                continue

            k, t, o = opt
            k = k.replace(" ", "_")

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

    def changed(self, *args, **kwargs):
        self.update(*args, **kwargs)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        if args:
            name, val = args
            name = name.replace(" ", "_")
            setattr(self, name, val)

    def saveState(self):
        state = Node.saveState(self)
        if self.stateGroup:
            state['ctrl'] = self.stateGroup.state()
        return state

    def restoreState(self, state):
        super(CtrlNode, self).restoreState(state)
        if self.stateGroup is not None:
            ctrlstate = state.get('ctrl', {})
            self.stateGroup.setState(ctrlstate)
            for k, ctrl in self.ctrls.items():
                if isinstance(ctrl, QtGui.QLineEdit):
                    ctrl.setText(ctrlstate[k])

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

    def display(self, topics, terms, addr, win, widget=None, **kwargs):

        if self.widget is None and widget:
            self.widget = widget(topics, terms, addr, win, **kwargs)

        if self.task is None and self.widget:
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
