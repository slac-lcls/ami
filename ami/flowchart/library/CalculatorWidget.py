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

        if terms:
            self.variable_widget = QtWidgets.QWidget(parent=self)
            self.variable_layout = QtWidgets.QGridLayout()

            self.variables = []

            for _, term in terms.items():
                self.variables.append(self.createButton(term, self.operatorClicked))

            row = 0
            col = 0
            for i in range(0, len(terms)):
                self.variable_layout.addWidget(self.variables[i], row, col)
                if col < 3:
                    col += 1
                else:
                    col = 0
                    row += 1

            self.variable_widget.setLayout(self.variable_layout)
            self.layout.addWidget(self.variable_widget, 6, 0, 1, 7)

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

    def saveState(self):
        return {'operation': self.display.text()}

    def restoreState(self, state):
        self.display.setText(state['operation'])


class FilterWidget(QtWidgets.QWidget):

    sigStateChanged = QtCore.Signal(object, object, object)

    def __init__(self, inputs={}, outputs=[], parent=None):
        super().__init__(parent)
        self.inputs = inputs
        self.outputs = outputs
        self.layout = QtWidgets.QFormLayout()
        self.setLayout(self.layout)

        addBtn = QtWidgets.QPushButton("Add", parent=self)
        addBtn.clicked.connect(self.add_condition)

        removeBtn = QtWidgets.QPushButton("Remove", parent=self)
        removeBtn.clicked.connect(self.remove_condition)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(addBtn)
        hbox.addWidget(removeBtn)
        self.layout.addRow(hbox)

        self.values = {}
        self.condition_groups = {}

        if self.inputs:
            self.variable_widget = QtWidgets.QWidget(parent=self)
            self.variable_layout = QtWidgets.QGridLayout()
            self.variables = []

            for _, term in self.inputs.items():
                self.variables.append(self.createButton(term, self.operatorClicked))

            row = 0
            col = 0
            for i in range(0, len(self.inputs)):
                self.variable_layout.addWidget(self.variables[i], row, col)
                if col < 3:
                    col += 1
                else:
                    col = 0
                    row += 1

            self.variable_widget.setLayout(self.variable_layout)
            self.layout.addRow(self.variable_widget)

            self.add_condition()

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

    def add_condition(self, name=''):
        if len(self.condition_groups) >= len(self.outputs):
            return

        if not name:
            name = f"Condition {len(self.condition_groups)}"

        condition_group = [('condition', 'text', {'values': '', 'group': name})]

        inputs = list(self.inputs.values())
        inputs.append("None")
        for output in self.outputs:
            condition_group.append((output, 'combo', {'values': inputs, 'value': 'None', 'group': name}))

        self.condition_groups[name] = generateUi(condition_group)
        ui, stateGroup, ctrls, attrs = self.condition_groups[name]
        ctrls[name]['condition'].setFocus()
        self.values[name] = attrs[name]

        self.layout.addWidget(ui)
        stateGroup.sigChanged.connect(self.state_changed)

        return ui, stateGroup, ctrls, attrs

    def remove_condition(self):
        condition = len(self.condition_groups)-1
        if condition == 0:
            return

        name = f"Condition {condition}"
        ui, stateGroup, ctrls, attrs = self.condition_groups[name]
        self.layout.removeWidget(ui)
        ctrls[name]['groupbox'].deleteLater()
        del self.condition_groups[name]

    def state_changed(self, *args, **kwargs):
        attr, group, val = args

        if group:
            self.values[group][attr] = val
        else:
            self.values[attr] = val

        self.sigStateChanged.emit(attr, group, val)

    def saveState(self):
        state = {'conditions': len(self.condition_groups),
                 'inputs': self.inputs,
                 'outputs': self.outputs}

        for name, group in self.condition_groups.items():
            _, stateGroup, _, _ = group
            state[name] = stateGroup.state()[name]

        return state

    def restoreState(self, state):
        print(f'restoring {state}')
        conditions = state['conditions']
        if not self.inputs:
            self.inputs = state.get('inputs', {})
        if not self.outputs:
            self.outputs = state.get('outputs', [])

        for condition in range(0, conditions):
            name = f"Condition {condition}"
            if name not in self.condition_groups:
                _, stateGroup, _, _ = self.add_condition(name=name)
            else:
                _, stateGroup, _, _ = self.condition_groups[name]

            self.values[name] = state[name]
            stateGroup.setState({name: state[name]})


def gen_filter_func(values, inputs, outputs):
    assert (len(values) >= 1)

    cond = sanitize_name(values['Condition 0']['condition'], space=False)

    filter_func = """
def func(*args, **kwargs):
\t(%s,) = args
\tif %s:
\t\treturn %s
""" % (', '.join(inputs), cond,
       ', '.join(map(lambda x: sanitize_name(values['Condition 0'].get(x)),
                     outputs)))

    for condition in range(0, len(values)):
        if condition == 0:
            continue

        condition = values['Condition %d' % condition]
        cond = sanitize_name(condition['condition'], space=False)

        elif_condition = """
\telif %s:
\t\treturn %s
        """ % (cond,
               ', '.join(map(lambda x: sanitize_name(condition.get(x)),
                             outputs)))

        filter_func += elif_condition

    filter_func += "\n\treturn %s" % (', '.join([str(None)]*len(outputs)))
    return filter_func


def sanitize_name(name, space=True):
    return name.translate(sanitizer_space if space else sanitizer)


sanitizer_space = str.maketrans(" .:|-", "_____")


sanitizer = str.maketrans(".:|-", "____")


if __name__ == '__main__':

    import sys

    app = QtWidgets.QApplication(sys.argv)
    terms = {}
    for i in range(0, 9):
        terms[f'In.{i}'] = f'Input.{i}'

    calc = FilterWidget(terms)
    calc.show()
    sys.exit(app.exec_())
