#!/usr/bin/env python

#############################################################################
#
# Copyright (C) 2013 Riverbank Computing Limited.
# Copyright (C) 2010 Nokia Corporation and/or its subsidiary(-ies).
# All rights reserved.
#
# This file is part of the examples of PyQt.
#
# $QT_BEGIN_LICENSE:BSD$
# You may use this file under the terms of the BSD license as follows:
#
# "Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in
#     the documentation and/or other materials provided with the
#     distribution.
#   * Neither the name of Nokia Corporation and its Subsidiary(-ies) nor
#     the names of its contributors may be used to endorse or promote
#     products derived from this software without specific prior written
#     permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
# $QT_END_LICENSE$
#
#############################################################################

import re
from qtpy import QtWidgets, QtCore
from ami.flowchart.library.common import generateUi


class Button(QtWidgets.QToolButton):
    def __init__(self, parent=None, text=""):
        super().__init__(parent)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setText(text)

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(size.height() + 20)
        size.setWidth(max(size.width(), size.height()))
        return size


class CalculatorWidget(QtWidgets.QWidget):
    NumDigitButtons = 10
    sigStateChanged = QtCore.Signal(object, object, object)

    def __init__(self, terms, parent=None, operation=""):
        super().__init__(parent)
        self.terms = terms

        self.display = QtWidgets.QLineEdit(operation, parent=self)
        self.display.setFocus()
        self.display.setAlignment(QtCore.Qt.AlignRight)
        self.display.textChanged.connect(self.stateChanged)

        self.digitButtons = []

        for i in range(CalculatorWidget.NumDigitButtons):
            self.digitButtons.append(self.createButton(str(i), self.digitClicked))

        self.pointButton = self.createButton(".", self.operatorClicked)

        self.backspaceButton = self.createButton("Backspace", self.backspaceClicked)
        self.clearButton = self.createButton("Clear", self.clear)

        self.divisionButton = self.createButton("/", self.operatorClicked)
        self.timesButton = self.createButton("*", self.operatorClicked)
        self.minusButton = self.createButton("-", self.operatorClicked)
        self.plusButton = self.createButton("+", self.operatorClicked)

        # self.lnButton = self.createButton("ln", self.operatorClicked, op="ln(")
        # self.logButton = self.createButton("log", self.operatorClicked, op="log(")
        # self.sqrtButton = self.createButton("sqrt", self.operatorClicked, op="sqrt(")
        # self.powButton = self.createButton(u"x\N{SUPERSCRIPT y}", self.operatorClicked, op="")

        # self.sinButton = self.createButton("sin", self.operatorClicked, op="sin(")
        # self.cosButton = self.createButton("cos", self.operatorClicked, op="cos(")
        # self.tanButton = self.createButton("tan", self.operatorClicked, op="tan(")
        self.EButton = self.createButton("E", self.operatorClicked)

        self.parenOpen = self.createButton("(", self.operatorClicked)
        self.parenClose = self.createButton(")", self.operatorClicked)

        mainLayout = QtWidgets.QGridLayout(self)
        # mainLayout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

        mainLayout.addWidget(self.display, 0, 0, 1, 7)
        mainLayout.addWidget(self.backspaceButton, 1, 2)
        mainLayout.addWidget(self.clearButton, 1, 3)

        mainLayout.addWidget(self.parenOpen, 1, 4)
        mainLayout.addWidget(self.parenClose, 1, 5)

        # mainLayout.addWidget(self.sinButton, 2, 0, 1, 2)
        # mainLayout.addWidget(self.cosButton, 3, 0, 1, 2)
        # mainLayout.addWidget(self.tanButton, 4, 0, 1, 2)

        mainLayout.addWidget(self.EButton, 5, 4)

        for i in range(1, CalculatorWidget.NumDigitButtons):
            row = ((9 - i) / 3) + 2
            column = ((i - 1) % 3) + 2
            mainLayout.addWidget(self.digitButtons[i], row, column)

        mainLayout.addWidget(self.digitButtons[0], 5, 2)
        mainLayout.addWidget(self.pointButton, 5, 3)

        mainLayout.addWidget(self.divisionButton, 2, 5)
        mainLayout.addWidget(self.timesButton, 3, 5)
        mainLayout.addWidget(self.minusButton, 4, 5)
        mainLayout.addWidget(self.plusButton, 5, 5)

        self.layout = mainLayout
        self.setLayout(mainLayout)

        self.setWindowTitle("Calculator")

        self.row = 0
        self.col = 0

        self.variables = {}
        self.variable_widget = QtWidgets.QWidget(parent=self)
        self.variable_layout = QtWidgets.QGridLayout()
        self.variable_widget.setLayout(self.variable_layout)
        self.layout.addWidget(self.variable_widget, 6, 0, 1, 7)

        if terms:
            row = 0
            col = 0

            for term, variable in terms.items():
                self.variables[term] = self.createButton(variable, self.operatorClicked)
                self.variable_layout.addWidget(self.variables[term], row, col)
                if col < 3:
                    col += 1
                else:
                    col = 0
                    row += 1

            self.row = row
            self.col = col

    def stateChanged(self, text):
        self.sigStateChanged.emit("operation", None, text)

    def digitClicked(self):
        clickedButton = self.sender()
        digitValue = int(clickedButton.text())

        if self.display.text() == '0' and digitValue == 0.0:
            return

        self.display.setText(self.display.text() + str(digitValue))

    def updateTerms(self, terms):
        self.terms = terms

    def operatorClicked(self):
        clickedButton = self.sender()
        if clickedButton.op:
            value = clickedButton.op
        else:
            value = clickedButton.text()

        self.display.setText(self.display.text() + value)

    def backspaceClicked(self):
        text = self.display.text()[:-1]
        if not text:
            text = ''

        self.display.setText(text)

    def clear(self):
        self.display.setText('')

    def createButton(self, text, member, op=None):
        button = Button(parent=self, text=text)
        button.op = op
        button.clicked.connect(member)
        return button

    def terminalConnected(self, nodeTermConnected):
        if nodeTermConnected.localTermState['io'] == 'out':
            return

        term = nodeTermConnected.localTerm
        if nodeTermConnected.remoteNodeIsSource:
            variable = nodeTermConnected.remoteNode
        else:
            variable = nodeTermConnected.remoteNode + "." + nodeTermConnected.remoteTerm

        self.variables[term] = self.createButton(variable, self.operatorClicked)
        self.variable_layout.addWidget(self.variables[term], self.row, self.col)
        if self.col < 3:
            self.col += 1
        else:
            self.col = 0
            self.row += 1

    def terminalDisconnected(self, nodeTermDisconnected):
        if nodeTermDisconnected.localTermState['io'] == 'out':
            return

        term = nodeTermDisconnected.localTerm
        widget = self.variables.pop(term)
        self.variable_layout.removeWidget(widget)
        widget.deleteLater()

    def saveState(self):
        return {'operation': self.display.text()}

    def restoreState(self, state):
        self.display.setText(state['operation'])


class FilterWidget(QtWidgets.QWidget):

    sigStateChanged = QtCore.Signal(object, object, object)

    def __init__(self, inputs={}, outputs=[], node=None, parent=None):
        super().__init__(parent)
        self.node = node
        self.inputs = inputs or {}
        self.outputs = outputs or []
        self.layout = QtWidgets.QFormLayout()
        self.setLayout(self.layout)

        addElifBtn = QtWidgets.QPushButton("Add Elif", parent=self)
        addElifBtn.clicked.connect(self.add_elif_condition)

        addElseBtn = QtWidgets.QPushButton("Add Else", parent=self)
        addElseBtn.clicked.connect(self.add_else_condition)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(addElifBtn)
        hbox.addWidget(addElseBtn)
        self.layout.addRow(hbox)

        self.condition_groups = {}
        self.else_condition = None

        self.row = 0
        self.col = 0

        self.variables = {}
        self.variable_widget = QtWidgets.QWidget(parent=self)
        self.variable_layout = QtWidgets.QGridLayout()
        self.variable_widget.setLayout(self.variable_layout)
        self.layout.addRow(self.variable_widget)
        if self.inputs:
            for term, input_name in self.inputs.items():
                self.variables[input_name] = self.createButton(input_name, self.operatorClicked)

            row = 0
            col = 0
            for name, widget in self.variables.items():
                self.variable_layout.addWidget(widget, row, col)
                if col < 3:
                    col += 1
                else:
                    col = 0
                    row += 1

            self.row = row
            self.col = col

            self.add_elif_condition(name="If")

    def createButton(self, text, member, op=None):
        button = Button(parent=self, text=text)
        button.op = op
        button.clicked.connect(member)
        return button

    def operatorClicked(self):
        clickedButton = self.sender()
        if clickedButton.op:
            value = clickedButton.op
        else:
            value = clickedButton.text()

        widget = self.focusWidget()
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(widget.text() + value)

    def add_elif_condition(self, name=''):
        if not name:
            name = f"Elif {len(self.condition_groups)}"

        condition_group = [('condition', 'text', {'values': '', 'group': name})]

        inputs = list(self.inputs.values())
        inputs.append("None")
        for output in sorted(self.outputs):
            condition_group.append((output, 'combo', {'values': inputs, 'value': 'None', 'group': name}))

        self.condition_groups[name] = generateUi(condition_group)
        ui, stateGroup, ctrls, attrs = self.condition_groups[name]
        ctrls[name]['condition'].setFocus()

        if name.startswith("Elif"):
            removeBtn = QtWidgets.QPushButton("Remove", parent=self)
            removeBtn.name = name
            removeBtn.clicked.connect(self.remove_condition)
            ui.layout().addWidget(removeBtn)

        self.layout.addWidget(ui)
        stateGroup.sigChanged.connect(self.state_changed)

        return ui, stateGroup, ctrls, attrs

    def add_else_condition(self, name=''):
        if self.else_condition:
            return self.else_condition

        if not name:
            name = "Else"

        condition_group = []

        inputs = list(self.inputs.values())
        inputs.append("None")
        for output in self.outputs:
            condition_group.append((output, 'combo', {'values': inputs, 'value': 'None', 'group': name}))
        self.else_condition = generateUi(condition_group)
        ui, stateGroup, ctrls, attrs = self.else_condition

        removeBtn = QtWidgets.QPushButton("Remove", parent=self)
        removeBtn.name = name
        removeBtn.clicked.connect(self.remove_condition)
        ui.layout().addWidget(removeBtn)

        self.layout.addWidget(ui)
        stateGroup.sigChanged.connect(self.state_changed)

        return ui, stateGroup, ctrls, attrs

    def remove_condition(self, name=''):
        if self.sender():
            name = self.sender().name

        if name == "Else":
            ui, stateGroup, ctrls, attrs = self.else_condition
        else:
            ui, stateGroup, ctrls, attrs = self.condition_groups[name]

        self.layout.removeWidget(ui)
        ctrls[name]['groupbox'].deleteLater()

        if name == "Else":
            del self.else_condition
            self.else_condition = None
        else:
            del self.condition_groups[name]

        self.sigStateChanged.emit("remove", name, None)
        self.node.sigStateChanged.emit(self.node)

    def terminalAdded(self, term):
        if term.isInput():
            return

        # new output terminal add to combo boxes
        node_name = self.node.name()
        term = term.name()
        self.outputs.append(f"{node_name}.{term}")
        inputs = list(self.inputs.values())
        inputs.append("None")
        for name, group in self.condition_groups.items():
            ui, stateGroup, ctrls, attrs = group
            groupbox = ctrls[name]["groupbox"]
            widget = QtWidgets.QComboBox(parent=groupbox)
            for input in inputs:
                widget.addItem(input, input)
            widget.setCurrentIndex(len(inputs)-1)
            widget_name = f"{node_name}.{term}"
            ctrls[name][widget_name] = widget
            stateGroup.addWidget(widget, name=widget_name, group=name)
            layout = groupbox.layout()
            layout.addRow(widget_name, widget)
            attrs[name][widget_name] = "None"
            stateGroup.widgetChanged(widget)
        if self.else_condition:
            ui, stateGroup, ctrls, attrs = self.else_condition
            groupbox = ctrls["Else"]["groupbox"]
            widget = QtWidgets.QComboBox(parent=groupbox)
            for input in inputs:
                widget.addItem(input, input)
            widget.setCurrentIndex(len(inputs)-1)
            widget_name = f"{node_name}.{term}"
            ctrls["Else"][widget_name] = widget
            stateGroup.addWidget(widget, name=widget_name, group="Else")
            layout = groupbox.layout()
            layout.addRow(widget_name, widget)
            attrs["Else"][widget_name] = "None"
            stateGroup.widgetChanged(widget)

    def terminalRemoved(self, term):
        if term.isInput():
            # Disconnect sent before remove, just return
            return
        elif term.isOutput():
            # remove comboboxes
            node_name = self.node.name()
            widget_name = f"{node_name}.{term.name()}"
            self.outputs.remove(widget_name)
            for name, group in self.condition_groups.items():
                ui, stateGroup, ctrls, attrs = group
                groupbox = ctrls[name]["groupbox"]
                layout = groupbox.layout()
                widget = ctrls[name].pop(widget_name)
                stateGroup.removeWidget(widget)
                layout.removeRow(widget)
                attrs[name].pop(widget_name, None)
                self.sigStateChanged.emit("remove", name, None)
            if self.else_condition:
                ui, stateGroup, ctrls, attrs = self.else_condition
                groupbox = ctrls["Else"]["groupbox"]
                layout = groupbox.layout()
                widget = ctrls["Else"].pop(widget_name)
                stateGroup.removeWidget(widget)
                layout.removeRow(widget)
                attrs["Else"].pop(widget_name, None)
                self.sigStateChanged.emit("remove", "Else", None)

    def terminalConnected(self, nodeTermConnected):
        if nodeTermConnected.localTermState['io'] == 'out':
            return

        new_input = ""
        if nodeTermConnected.remoteNodeIsSource:
            new_input = nodeTermConnected.remoteNode
        else:
            new_input = f"{nodeTermConnected.remoteNode}.{nodeTermConnected.remoteTerm}"

        self.inputs[nodeTermConnected.localTerm] = new_input

        self.variables[new_input] = self.createButton(new_input, self.operatorClicked)
        self.variable_layout.addWidget(self.variables[new_input], self.row, self.col)
        idx = len(self.inputs)-1

        if self.col == 0 and self.row == 0:  # if the connection is the first connection
            self.add_elif_condition(name="If")
        else:
            # go through comboboxes and add entry
            for name, group in self.condition_groups.items():
                ui, stateGroup, ctrls, attrs = group
                for output in self.outputs:
                    widget = ctrls[name][output]
                    widget.insertItem(idx, new_input, new_input)
                    stateGroup.widgetChanged(widget)

        if self.col < 3:
            self.col += 1
        else:
            self.col = 0
            self.row += 1

    def terminalDisconnected(self, nodeTermDisconnected):
        if nodeTermDisconnected.localTermState['io'] == 'out':
            return

        term = nodeTermDisconnected.localTerm

        # go through comboboxes and remove entry
        idx = list(self.inputs.keys()).index(term)
        input_name = self.inputs.pop(term)
        widget = self.variables.pop(input_name)
        self.variable_layout.removeWidget(widget)
        widget.deleteLater()
        for name, group in self.condition_groups.items():
            ui, stateGroup, ctrls, attrs = group
            for output in self.outputs:
                widget = ctrls[name][output]
                if stateGroup.readWidget(widget) == input_name:
                    stateGroup.setWidget(widget, 'None')
                widget.removeItem(idx)

    def state_changed(self, *args, **kwargs):
        attr, group, val = args

        if group == "Else":
            values = self.else_condition[3]
        else:
            values = self.condition_groups[group][3]

        if group:
            values[group][attr] = val
        else:
            values[attr] = val

        self.sigStateChanged.emit(group, values, None)

    def saveState(self):
        state = {'conditions': len(self.condition_groups),
                 'inputs': self.inputs,
                 'outputs': self.outputs}

        for name, group in self.condition_groups.items():
            _, stateGroup, _, _ = group
            state[name] = stateGroup.state()[name]

        if self.else_condition is not None:
            _, stateGroup, _, _ = self.else_condition
            state["Else"] = stateGroup.state()["Else"]

        return state

    def restoreState(self, state):
        conditions = state['conditions']

        self.inputs = state.get('inputs', {})
        self.outputs = state.get('outputs', [])

        for condition in range(0, conditions):
            if condition == 0:
                name = "If"
            else:
                name = f"Elif {condition}"

            if name not in self.condition_groups:
                _, stateGroup, _, values = self.add_elif_condition(name=name)
            else:
                _, stateGroup, _, values = self.condition_groups[name]

            if stateGroup:
                values[name] = state[name]
                stateGroup.setState({name: state[name]})

        name = "Else"
        if name in state:
            _, stateGroup, _, values = self.add_else_condition(name)

            values[name] = state[name]
            stateGroup.setState({name: state[name]})

        deletions = []
        for name, group in self.condition_groups.items():
            if name not in state:
                deletions.append(name)

        for name in deletions:
            self.remove_condition(name)


def extract_variables_from_condition(condition, return_sanitized=True):
    """Extract variable names from a condition string, excluding numbers and operators."""
    # List of Python keywords to exclude
    python_keywords = ['and', 'or', 'not', 'if', 'else', 'elif', 'for', 'while', 'in',
                      'True', 'False', 'None', 'is', 'as', 'assert', 'break', 'class',
                      'continue', 'def', 'del', 'except', 'finally', 'from', 'global',
                      'import', 'lambda', 'nonlocal', 'pass', 'raise', 'return', 'try',
                      'with', 'yield']

    # This pattern finds variable names but excludes:
    # 1. Python keywords
    # 2. Numeric literals (integers, floats)
    # 3. Operators and symbols
    # Allow for names that can include -, :, and . in them
    pattern = r'\b(?!(?:' + '|'.join(python_keywords) + r')\b)([a-zA-Z_][-a-zA-Z0-9_:.]*)\b'

    # Extract all matches
    potential_vars = re.findall(pattern, condition)

    # Further filter to exclude anything that might be a number
    variables = [var for var in potential_vars if not var.isdigit()]
    if return_sanitized:
        variables = [sanitize_name(var) for var in variables]
    return set(variables)


def check_conditions(conditions_dict, inputs):
    """
    Check that the variables used in the condition map to inputs
    """
    cond_variables = set()
    missing_variables = set()

    # Extract all variables from all conditions
    for key, value in conditions_dict.items():
        if 'condition' in value:
            #sanitized_condition = sanitize_name(value['condition'])
            condition_vars = extract_variables_from_condition(value['condition'])
            cond_variables.update(condition_vars)

    # Get all variables from inputs
    input_variables = set(inputs.values())

    # Find missing variables
    for var in cond_variables:
        if var not in input_variables:
            missing_variables.add(var)

    return len(missing_variables) == 0


def gen_filter_func(values, inputs, outputs):
    assert (len(values) >= 1)

    cond_ok = check_conditions(values, inputs)
    if not cond_ok:
        raise ValueError("Condition variables not found in the input variables.")
    cond = sanitize_condition(values['If']['condition'])

    filter_func = """
def func(*args, **kwargs):
\t(%s,) = args
\tif %s:
\t\treturn %s
""" % (', '.join(inputs.values()), cond,
       ', '.join(map(lambda x: sanitize_condition(values['If'].get(x)),
                     outputs)))

    for k, condition in values.items():
        if not k.startswith("Elif"):
            continue

        cond = sanitize_condition(condition['condition'])

        elif_condition = """
\telif %s:
\t\treturn %s
        """ % (cond,
               ', '.join(map(lambda x: sanitize_condition(condition.get(x)),
                             outputs)))

        filter_func += elif_condition

    if "Else" in values:
        else_condition = """
\telse:
\t\treturn %s
        """ % ', '.join(map(lambda x: sanitize_condition(values['Else'].get(x)),
                            outputs))
        filter_func += else_condition

    filter_func += "\n\treturn %s" % (', '.join([str(None)]*len(outputs)))
    return filter_func


def sanitize_name(name, space=True):
    """ 
    Sanitize a variable name by replacing spaces and special characters with 
    underscores.
    """
    if name:
        return name.translate(sanitizer_space if space else sanitizer)
    else:
        return str(name)

sanitizer_space = str.maketrans(" .:|-", "_____")
sanitizer = str.maketrans(".:|-", "____")


def sanitize_condition(condition_str):
    """
    Clean up a condition string by replacing variable names with their sanitized 
    versions while ensuring that numeric literals are preserved.
    Challenge: variables can contain dots, colons and dashes, which are 
    sanitized to underscores. At the same time, we want to preserve numeric 
    literals (like 1.11) and not accidentally sanitize them.
    
    :param condition_str: The raw condition string to be cleaned.
    """
    if condition_str is None or condition_str == 'None':
        return "None"

    safe_str = condition_str
    
    raw_vars = extract_variables_from_condition(condition_str, return_sanitized=False)
    
    cleaned_condition = condition_str
    for raw in sorted(raw_vars, key=len, reverse=True):
        sanitized = sanitize_name(raw, space=False)
        # Use re.escape so dots/colons are treated as literal text in the regex
        # Use \b to ensure we match the exact variable name
        pattern = r'\b' + re.escape(raw) + r'\b'
        cleaned_condition = re.sub(pattern, sanitized, cleaned_condition)
            
    return cleaned_condition


if __name__ == '__main__':

    import sys

    app = QtWidgets.QApplication(sys.argv)
    terms = {}
    for i in range(0, 9):
        terms[f'In.{i}'] = f'Input.{i}'

    calc = FilterWidget(terms)
    calc.show()
    sys.exit(app.exec_())
