# -*- coding: utf-8 -*-
"""
WidgetGroup.py -  WidgetGroup class for easily managing lots of Qt widgets
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more information.

This class addresses the problem of having to save and restore the state
of a large group of widgets.
"""
from qtpy import QtCore, QtGui, QtWidgets
from pyqtgraph.widgets.ColorButton import ColorButton
from pyqtgraph.widgets.SpinBox import SpinBox
import weakref
import inspect
import re
import numpy as np

import os
import logging
logger = logging.getLogger(__name__)

__all__ = ['WidgetGroup']

MAX = 2147483647


def splitterState(w):
    s = str(w.saveState().toPercentEncoding())
    return s


def restoreSplitter(w, s):
    if type(s) is list:
        w.setSizes(s)
    elif type(s) is str:
        w.restoreState(QtCore.QByteArray.fromPercentEncoding(s))
    else:
        print("Can't configure QSplitter using object of type", type(s))
    if w.count() > 0:  # make sure at least one item is not collapsed
        for i in w.sizes():
            if i > 0:
                return
        w.setSizes([50] * w.count())


def comboState(w):
    ind = w.currentIndex()
    data = w.itemData(ind)
    return data


def setComboState(w, v):
    if type(v) is int:
        # ind = w.findData(QtCore.QVariant(v))
        ind = w.findData(v)
        if ind > -1:
            w.setCurrentIndex(ind)
            return

    idx = w.findText(str(v))
    if w.currentIndex() == idx:
        w.currentIndexChanged.emit(idx)
    else:
        w.setCurrentIndex(idx)


class WidgetGroup(QtCore.QObject):
    """This class takes a list of widgets and keeps an internal record of their
    state that is always up to date.

    Allows reading and writing from groups of widgets simultaneously.
    """

    # List of widget types that can be handled by WidgetGroup.
    # The value for each type is a tuple (change signal function, get function, set function, [auto-add children])
    # The change signal function that takes an object and returns a signal that is emitted any time the state of
    # the widget changes, not just when it is changed by user interaction. (for example, 'clicked' is not a
    # valid signal here)
    # If the change signal is None, the value of the widget is not cached.
    # Custom widgets not in this list can be made to work with WidgetGroup by giving them a
    # 'widgetGroupInterface' method which returns the tuple.
    classes = {
        QtWidgets.QSpinBox: (lambda w: w.valueChanged,
                             QtWidgets.QSpinBox.value,
                             QtWidgets.QSpinBox.setValue),
        QtWidgets.QDoubleSpinBox: (lambda w: w.valueChanged,
                                   QtWidgets.QDoubleSpinBox.value,
                                   QtWidgets.QDoubleSpinBox.setValue),
        QtWidgets.QSplitter: (None,
                              splitterState,
                              restoreSplitter,
                              True),
        QtWidgets.QCheckBox: (lambda w: w.stateChanged,
                              QtWidgets.QCheckBox.isChecked,
                              QtWidgets.QCheckBox.setChecked),
        QtWidgets.QComboBox: (lambda w: w.currentIndexChanged,
                              comboState,
                              setComboState),
        QtWidgets.QGroupBox: (lambda w: w.toggled,
                              QtWidgets.QGroupBox.isChecked,
                              QtWidgets.QGroupBox.setChecked,
                              True),
        QtWidgets.QLineEdit: (lambda w: w.textChanged,
                              lambda w: str(w.text()),
                              QtWidgets.QLineEdit.setText),
        QtWidgets.QRadioButton: (lambda w: w.toggled,
                                 QtWidgets.QRadioButton.isChecked,
                                 QtWidgets.QRadioButton.setChecked),
        QtWidgets.QSlider: (lambda w: w.valueChanged,
                            QtWidgets.QSlider.value,
                            QtWidgets.QSlider.setValue),
        # PushButtonSelectFile: (lambda w: w.path_is_changed,
        #                       PushButtonSelectFile.fname,
        #                       PushButtonSelectFile.set_fname),
    }

    sigChanged = QtCore.Signal(object, object, object)

    def __init__(self, widgetList=None):
        """
        Initialize WidgetGroup, adding specified widgets into this group.
        widgetList can be:
         - a list of widget specifications (widget, [name], [scale])
         - a dict of name: widget pairs
         - any QObject, and all compatible child widgets will be added recursively.

        The 'scale' parameter for each widget allows QSpinBox to display a different value than the
        value recorded in the group state (for example, the program may set a spin box value
        to 100e-6 and have it displayed as 100 to the user)
        """
        super().__init__()
        # Make sure widgets don't stick around just because they are listed here
        self.widgetList = weakref.WeakKeyDictionary()
        self.scales = weakref.WeakKeyDictionary()
        self.cache = {}  # (name, group):value pairs
        self.uncachedWidgets = weakref.WeakKeyDictionary()
        if isinstance(widgetList, QtCore.QObject):
            self.autoAdd(widgetList)
        elif isinstance(widgetList, list):
            for w in widgetList:
                self.addWidget(*w)
        elif isinstance(widgetList, dict):
            for name, w in widgetList.items():
                self.addWidget(w, name)
        elif widgetList is None:
            return
        else:
            raise Exception("Wrong argument type %s" % type(widgetList))

    def addWidget(self, w, name=None, scale=None, group=None):
        if not self.acceptsType(w):
            raise Exception("Widget type %s not supported by WidgetGroup" % type(w))
        if name is None:
            name = str(w.objectName())
        if name == '':
            raise Exception("Cannot add widget '%s' without a name." % str(w))
        if group:
            self.widgetList[w] = (name, group)
        else:
            self.widgetList[w] = name
        self.scales[w] = scale
        self.readWidget(w)

        logger.debug('WidgetGroup.addWidget for type=%s' % (str(type(w))))
        if type(w) in WidgetGroup.classes:
            signal = WidgetGroup.classes[type(w)][0]
        else:
            signal = w.widgetGroupInterface()[0]

        if signal is not None:
            if inspect.isfunction(signal) or inspect.ismethod(signal):
                signal = signal(w)
            signal.connect(self.mkChangeCallback(w))
        else:
            self.uncachedWidgets[w] = None

    def findWidget(self, name, group=None):
        for w in self.widgetList:
            n = self.widgetList[w]
            if type(n) is tuple:
                if n == (name, group):
                    return w
            elif n == name:
                return w
        return None

    def interface(self, obj):
        t = type(obj)
        logger.debug('WidgetGroup.interface for type %s' % str(t))
        if t in WidgetGroup.classes:
            return WidgetGroup.classes[t]
        else:
            return obj.widgetGroupInterface()

    def checkForChildren(self, obj):
        """Return true if we should automatically search the children of this object for more."""
        iface = self.interface(obj)
        return (len(iface) > 3 and iface[3])

    def autoAdd(self, obj):
        # Find all children of this object and add them if possible.
        accepted = self.acceptsType(obj)
        if accepted:
            # print "%s  auto add %s" % (self.objectName(), obj.objectName())
            self.addWidget(obj)

        if not accepted or self.checkForChildren(obj):
            for c in obj.children():
                self.autoAdd(c)

    def acceptsType(self, obj):
        for c in WidgetGroup.classes:
            if isinstance(obj, c):
                return True
        if hasattr(obj, 'widgetGroupInterface'):
            return True
        return False

    def setScale(self, widget, scale):
        val = self.readWidget(widget)
        self.scales[widget] = scale
        self.setWidget(widget, val)

    def mkChangeCallback(self, w):
        return lambda *args: self.widgetChanged(w, *args)

    def widgetChanged(self, w, *args):
        n = self.widgetList[w]
        g = None
        if type(n) is tuple:
            n, g = n

        val = self.readWidget(w)
        logger.debug('WidgetGroup.widgetChanged for type %s  args=%s  val=%s' % (str(type(w)), str(args), str(val)))
        self.sigChanged.emit(n, g, val)

    def state(self):
        for w in self.uncachedWidgets:
            self.readWidget(w)
        return self.cache.copy()

    def setState(self, s):
        for w in self.widgetList:
            n = self.widgetList[w]
            g = None
            if type(n) is tuple:
                n, g = n

            v = None
            if g and g in s:
                if n in s[g]:
                    v = s[g][n]

            if n in s:
                v = s[n]

            if v is not None:
                self.setWidget(w, v)

    def readWidget(self, w):
        logger.debug('WidgetGroup.readWidget for type %s' % str(type(w)))
        if type(w) in WidgetGroup.classes:
            getFunc = WidgetGroup.classes[type(w)][1]
        else:
            getFunc = w.widgetGroupInterface()[1]

        if getFunc is None:
            return None

        # if the getter function provided in the interface is a bound method,
        # then just call the method directly. Otherwise, pass in the widget as the first arg
        # to the function.
        if inspect.ismethod(getFunc) and getFunc.__self__ is not None:
            val = getFunc()
        else:
            val = getFunc(w)

        if self.scales[w] is not None:
            val /= self.scales[w]
        n = self.widgetList[w]
        if type(n) is tuple:
            n, g = n
            if g not in self.cache:
                self.cache[g] = {}
            self.cache[g][n] = val
        else:
            self.cache[n] = val

        logger.debug('WidgetGroup.readWidget name: %s  val: %s' % (str(n), str(val)))

        return val

    def setWidget(self, w, v):
        if self.scales[w] is not None:
            v *= self.scales[w]

        logger.debug('WidgetGroup.setWidget for type=%s value=%s' % (str(type(w)), str(v)))
        if type(w) in WidgetGroup.classes:
            setFunc = WidgetGroup.classes[type(w)][2]
        else:
            setFunc = w.widgetGroupInterface()[2]

        # if the setter function provided in the interface is a bound method,
        # then just call the method directly. Otherwise, pass in the widget as the first arg
        # to the function.
        if inspect.ismethod(setFunc) and setFunc.__self__ is not None:
            logger.debug('WidgetGroup.setWidget setFunc(v) v: "%s"' % str(v))
            setFunc(v)
        else:
            logger.debug('WidgetGroup.setWidget setFunc(w, v)')
            setFunc(w, v)


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


class ScientificDoubleSpinBox(QtWidgets.QDoubleSpinBox):

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
                QtWidgets.QDoubleSpinBox.value,
                QtWidgets.QDoubleSpinBox.setValue)


class PushButtonSelectFile(QtWidgets.QPushButton):
    path_is_changed = QtCore.Signal()  # ('QString')

    def __init__(self, *args,
                 parent=None,
                 path='select',
                 mode='r',
                 fltr='*.text *.txt *.data *.dat\n *', **kwargs):
        super().__init__(path, parent=parent)
        self.mode = mode
        self.fltr = fltr
        self.setToolTip('Click on button and select file')
        self.setMinimumWidth(500)
        # self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.clicked.connect(self.on_but)
        logging.debug('PushButtonSelectFile.__init__ for path %s' % path)

    def on_but(self):
        logger.info('PushButtonSelectFileemit.on_but %s' % self.text())
        path_old = self.fname()

        resp = QtWidgets.QFileDialog.getSaveFileName(None, 'Output file', path_old, filter=self.fltr)\
            if self.mode == 'w' else\
            QtWidgets.QFileDialog.getOpenFileName(None, 'Input file', path_old, filter=self.fltr)

        logger.debug('response: %s len=%d' % (resp, len(resp)))

        path, filt = resp
        dname, fname = os.path.split(path)

        if self.mode == 'r' and not os.path.exists(path):
            logger.info('pass does not exist: %s' % path)
            return

        elif dname == '' or fname == '':
            logger.info('input directiry name "%s" or file name "%s" is empty... use default values' % (dname, fname))
            return

        elif path == path_old:
            logger.info('path has not been changed: %s' % str(path))
            return

        else:
            self.set_fname(path)
            logger.info('PushButtonSelectFileemit.on_but signal for selected file: %s' % path)
            self.path_is_changed.emit()

    def fname(self):
        return str(self.text())

    def set_fname(self, s=None):
        logging.info('PushButtonSelectFile.set_fname: %s' % str(s))
        if s is None:
            return
        self.setText(str(s))

    def widgetGroupInterface(self):
        logging.info('PushButtonSelectFile.widgetGroupInterface fname: %s' % self.fname())
        return (lambda w: w.path_is_changed,
                self.fname,
                self.set_fname)


def generateUi(opts):
    """Convenience function for generating common UI types"""
    if len(opts) == 0:
        return None, None, None, None

    widget = QtWidgets.QWidget()
    layout = QtWidgets.QFormLayout()
    # layout.setSpacing(0)
    widget.setLayout(layout)
    ctrls = {}
    row = 0
    widgetgroup = WidgetGroup()
    groupboxes = {}
    default_values = {}
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
        val = o.get('value', None)

        parent = None
        if 'group' in o:
            name = o['group']
            if name not in groupboxes:
                groupbox = QtWidgets.QGroupBox(parent=widget)
                groupbox_layout = QtWidgets.QFormLayout()
                groupbox.setLayout(groupbox_layout)
                groupboxes[name] = (groupbox, groupbox_layout)
                groupbox.setTitle(name)
                layout.addWidget(groupbox)
                ctrls[name] = {'groupbox': groupbox}
                default_values[name] = {}

            groupbox, groupbox_layout = groupboxes[name]
            parent = groupbox
        else:
            parent = widget

        if t == 'intSpin':
            w = QtWidgets.QSpinBox(parent=parent)
            if 'max' in o:
                w.setMaximum(o['max'])
            else:
                w.setMaximum(MAX)
            if 'min' in o:
                w.setMinimum(o['min'])
            else:
                w.setMinimum(-MAX)
            if 'value' in o:
                w.setValue(o['value'])
            else:
                val = 0
        elif t == 'doubleSpin':
            w = ScientificDoubleSpinBox(parent=parent)
            if 'max' in o:
                w.setMaximum(o['max'])
            if 'min' in o:
                w.setMinimum(o['min'])
            if 'value' in o:
                w.setValue(o['value'])
            else:
                val = 0.0
        elif t == 'spin':
            w = SpinBox(parent=widget)
            w.setOpts(**o)
        elif t == 'check':
            w = QtWidgets.QCheckBox(parent=parent)
            w.setFocus()
            if 'checked' in o:
                val = o['checked']
                w.setChecked(o['checked'])
            else:
                val = False
        elif t == 'combo':
            w = QtWidgets.QComboBox(parent=parent)
            for i in o['values']:
                w.addItem(str(i), i)
            if 'value' in o:
                setComboState(w, o['value'])
        elif t == 'color':
            w = ColorButton(parent=parent)
            if 'value' in o:
                w.setColor(o['value'])
        elif t == 'text':
            w = QtWidgets.QLineEdit(parent=parent)
            if 'placeholder' in o:
                w.setPlaceholderText(o['placeholder'])
            if 'value' in o:
                w.setText(o['value'])
        elif t == 'file_in':
            w = PushButtonSelectFile(parent=parent, mode='r', fltr='*.text *.txt *.data *.dat *.npy\n *')
            logger.info('file_in widget: %s' % str(w))
            if 'value' in o:
                w.set_fname(o['value'])
        elif t == 'file_out':
            w = PushButtonSelectFile(parent=parent, mode='w', fltr='*.text *.txt *.data *.dat *.npy\n *')
            logger.info('file_out widget: %s' % str(w))
            if 'value' in o:
                w.set_fname(o['value'])
        else:
            raise Exception("Unknown widget type '%s'" % str(t))

        if tip is not None:
            w.setToolTip(tip)

        w.setObjectName(k)

        if t != 'text' and not focused:
            w.setFocus()
            focused = True

        if 'group' in o:
            name = o['group']
            groupbox, groupbox_layout = groupboxes[name]
            groupbox_layout.addRow(k, w)
            ctrls[name][k] = w
            widgetgroup.addWidget(w, name=k, group=name)
            default_values[name][k] = val
        else:
            layout.addRow(k, w)
            if hidden:
                w.hide()
                label = layout.labelForField(w)
                label.hide()

            w.rowNum = row
            ctrls[k] = w
            default_values[k] = val
            widgetgroup.addWidget(w, k)
            row += 1

    return widget, widgetgroup, ctrls, default_values
