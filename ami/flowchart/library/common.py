# -*- coding: utf-8 -*-
from qtpy import QtCore

from ami.flowchart.Node import Node
from ami.flowchart.library.WidgetGroup import generateUi
from ami.flowchart.library.DisplayWidgets import ScalarWidget, WaveformWidget, ImageWidget, \
        ObjectWidget, MultiWaveformWidget
from amitypes import Array1d, Array2d, MultiChannelWaveformTypes


class CtrlNode(Node):
    """Abstract class for nodes with auto-generated control UI"""

    sigStateChanged = QtCore.Signal(object)

    def __init__(self, name, ui=None, terminals={}, **kwargs):
        super().__init__(name=name, terminals=terminals, **kwargs)
        self.widget = None
        self.widget_state = None
        self.geometry = None

        if ui is None:
            if hasattr(self, 'uiTemplate'):
                ui = self.uiTemplate
            else:
                ui = []

        self.ui, self.stateGroup, self.ctrls, self.values = generateUi(ui)
        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

    def ctrlWidget(self, parent=None):
        if parent and self.ui:
            self.ui.setParent(parent)
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

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl or restore_widget

    def saveState(self):
        state = super().saveState()
        if self.stateGroup:
            state['ctrl'] = self.stateGroup.state()

        if self.widget and hasattr(self.widget, 'saveState'):
            state['widget'] = self.widget.saveState()

        if self.geometry:
            state['geometry'] = bytes(self.geometry.toHex()).decode('ascii')

        return state

    def restoreState(self, state):
        super().restoreState(state)

        if self.stateGroup is not None:
            ctrlstate = state.get('ctrl', {})
            self.stateGroup.setState(ctrlstate)

        if self.widget is not None and 'widget' in state:
            self.widget.restoreState(state['widget'])

        if 'geometry' in state:
            self.geometry = QtCore.QByteArray.fromHex(bytes(state['geometry'], 'ascii'))

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

    def close(self, emit=True):
        super().close(emit)

        if self.widget:
            self.widget.close()

        self.widget = None

    def display(self, topics, terms, addr, win, widget=None, **kwargs):

        if self.widget is None and widget:
            self.widget = widget(topics, terms, addr, parent=win, node=self, **kwargs)

        return self.widget


class SourceNode(CtrlNode):

    def __init__(self, **kwargs):
        kwargs['viewable'] = True
        kwargs['allowOptional'] = False
        super().__init__(**kwargs)

        self.widgetType = None
        self.setWidgetType()
        self._input_vars["In"] = self.name()

    def display(self, topics, terms, addr, win, **kwargs):
        if self.widgetType:
            return super().display(topics, terms, addr, win, self.widgetType, **kwargs)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def isSource(self):
        return True

    def input_vars(self):
        return self._input_vars

    def setWidgetType(self):
        if 'Out' in self.terminals:
            ttype = self.terminals['Out']._type
            if ttype is int or ttype is float or ttype is bool:
                self.widgetType = ScalarWidget
            elif ttype is Array1d:
                self.widgetType = WaveformWidget
            elif ttype is Array2d:
                self.widgetType = ImageWidget
            elif ttype in MultiChannelWaveformTypes:
                self.widgetType = MultiWaveformWidget
            else:
                self.widgetType = ObjectWidget

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': self.widgetType.__name__, 'terms': terms, 'topics': topics}

    def saveState(self):
        state = super().saveState()
        state['source_kwargs'] = self._graphicsItem.source_kwargs
        return state

    def restoreState(self, state):
        super().restoreState(state)
        self.setWidgetType()
        try:
            self._graphicsItem.source_kwargs = state['source_kwargs']
        except:
            pass


class GroupedNode(CtrlNode):

    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.sigTerminalConnected.connect(self.setType)

    def addInput(self, **kwargs):
        group = self.nextGroupName()
        kwargs['group'] = group
        super().addInput(**kwargs)
        super().addOutput(**kwargs)

    def setType(self, localTerm, remoteTerm):
        pass

    def find_output_term(self, localTerm):
        group = localTerm.group()
        if group:
            group = self._groups[group]
            for name in group:
                term = self.terminals[name]
                if term.isOutput():
                    return term
        else:
            return self.terminals['Out']
