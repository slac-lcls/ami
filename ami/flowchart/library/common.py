# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.widgets.SpinBox import SpinBox
from pyqtgraph.WidgetGroup import WidgetGroup
from pyqtgraph.widgets.ColorButton import ColorButton
from ami.flowchart.Node import Node
from ami.flowchart.library.DisplayWidgets import ScalarWidget, WaveformWidget, AreaDetWidget
import amitypes
import asyncio


MAX = 2147483647


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

    def ctrlWidget(self):
        return self.ui

    def changed(self, *args, **kwargs):
        self.update(*args, **kwargs)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
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

        self.widget = None

    def display(self, topics, addr, win, widget=None, **kwargs):

        if self.widget is None and widget:
            self.widget = widget(topics, addr, win, **kwargs)

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
        elif ttype is amitypes.Array1d:
            self.widgetType = WaveformWidget
        elif ttype is amitypes.Array2d:
            self.widgetType = AreaDetWidget

        self._input_vars["In"] = self.name()

    def display(self, topics, addr, win, **kwargs):
        if self.widgetType:
            return super(SourceNode, self).display(topics, addr, win, self.widgetType, **kwargs)

    def isSource(self):
        return True
