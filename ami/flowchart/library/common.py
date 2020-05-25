# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore

from ami.flowchart.Node import Node
from ami.flowchart.library.WidgetGroup import generateUi
from ami.flowchart.library.DisplayWidgets import ScalarWidget, WaveformWidget, ImageWidget, \
        TextWidget, ObjectWidget
from amitypes import Array1d, Array2d
import asyncio


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

        self.ui, self.stateGroup, self.ctrls, self.values = generateUi(ui)
        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

    def ctrlWidget(self):
        return self.ui

    def state_changed(self, *args, **kwargs):
        self.update(*args, **kwargs)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        name, group, val = args
        if group:
            self.values[group][name] = val
        else:
            self.values[name] = val

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

        if self.widget:
            self.widget.close()

        self.widget = None

    def display(self, topics, terms, addr, win, widget=None, **kwargs):
        if self.widget is None and widget:
            self.widget = widget(topics, terms, addr, parent=win, node=self, **kwargs)

        if self.task is None and self.widget and addr:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget


class SourceNode(CtrlNode):

    def __init__(self, **kwargs):
        kwargs['viewable'] = True
        kwargs['allowAddCondition'] = False
        super(SourceNode, self).__init__(**kwargs)

        self.widgetType = None
        self.setWidgetType()
        self._input_vars["In"] = self.name()

    def display(self, topics, terms, addr, win, **kwargs):
        if self.widgetType:
            return super().display(topics, terms, addr, win, self.widgetType, **kwargs)

    def isSource(self):
        return True

    def setWidgetType(self):
        if 'Out' in self.terminals:
            ttype = self.terminals['Out']._type
            if ttype is int or ttype is float or ttype is bool:
                self.widgetType = ScalarWidget
            elif ttype is Array1d:
                self.widgetType = WaveformWidget
            elif ttype is Array2d:
                self.widgetType = ImageWidget
            elif ttype is str:
                self.widgetType = TextWidget
            else:
                self.widgetType = ObjectWidget

    def restoreState(self, state):
        super().restoreState(state)
        self.setWidgetType()
