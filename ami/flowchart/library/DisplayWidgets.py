import re
import zmq
import logging
import asyncio
import zmq.asyncio
import datetime as dt
import itertools as it
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtWidgets, QtCore
from pyqtgraph.widgets.SpinBox import SpinBox
from pyqtgraph.WidgetGroup import WidgetGroup
from pyqtgraph.widgets.ColorButton import ColorButton
from ami import LogConfig


logger = logging.getLogger(LogConfig.get_package_name(__name__))

colors = ['b', 'g', 'r']
symbols = ['o', 's', 't', 'd', '+']
symbols_colors = list(it.product(symbols, colors))
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
    groupboxes = {}
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

        if 'group' in o:
            groupbox_name = o['group']
            if groupbox_name not in groupboxes:
                groupbox = QtWidgets.QGroupBox()
                groupbox_layout = QtGui.QFormLayout()
                groupbox.setLayout(groupbox_layout)
                groupboxes[groupbox_name] = (groupbox, groupbox_layout)
                groupbox.setTitle(groupbox_name)
                layout.addWidget(groupbox)
                ctrls[groupbox_name] = groupbox
            else:
                groupbox, groupbox_layout = groupboxes[groupbox_name]

            groupbox_name = groupbox_name.replace(' ', '_')
            w.group = groupbox_name
            groupbox_layout.addRow(k, w)
            ctrls[k+"_"+groupbox_name] = w
            group.addWidget(w, k+"_"+groupbox_name)
        else:
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


class AsyncFetcher(object):

    def __init__(self, topics, terms, addr):
        self.addr = addr
        self.ctx = zmq.asyncio.Context()
        self.poller = zmq.asyncio.Poller()
        self.sockets = {}
        self.data = {}
        self.last_updated = "Last Updated: None"
        self.update_topics(topics, terms)

    @property
    def reply(self):
        if self.data.keys() == set(self.subs):
            return {name: self.data[topic] for name, topic in self.topics.items()}
        else:
            return {}

    def update_topics(self, topics, terms):
        self.topics = topics
        self.terms = terms
        self.names = list(topics.keys())
        self.subs = list(topics.values())

        for name, sock_count in self.sockets.items():
            sock, count = sock_count
            self.poller.unregister(sock)
            sock.close()

        self.sockets = {}
        self.view_subs = {}

        for term, name in terms.items():
            if name not in self.sockets:
                topic = topics[name]
                sub_topic = "view:%s:%s" % (self.addr.name, topic)
                self.view_subs[sub_topic] = topic
                sock = self.ctx.socket(zmq.SUB)
                sock.setsockopt_string(zmq.SUBSCRIBE, sub_topic)
                sock.connect(self.addr.view)
                self.poller.register(sock, zmq.POLLIN)
                self.sockets[name] = (sock, 1)  # reference count
            else:
                sock, count = self.sockets[name]
                self.sockets[name] = (sock, count+1)

    async def fetch(self):
        for sock, flag in await self.poller.poll():
            if flag != zmq.POLLIN:
                continue
            topic = await sock.recv_string()
            await sock.recv_pyobj()
            reply = await sock.recv_pyobj()
            now = dt.datetime.now()
            now = now.strftime("%H:%M:%S")
            self.last_updated = f"Last Updated: {now}"
            self.data[self.view_subs[topic]] = reply


class ScalarWidget(QtWidgets.QLCDNumber):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent)

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr)

        self.setGeometry(QtCore.QRect(320, 180, 191, 81))
        self.setDigitCount(10)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            for k, v in self.fetcher.reply.items():
                self.display(v)


class AreaDetWidget(pg.ImageView):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent)

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr)

        handles = self.roi.getHandles()
        self.roi.removeHandle(handles[1])
        self.last_updated = pg.LabelItem(parent=self.getView())
        self.pixel_value = pg.LabelItem(parent=self.getView())
        self.proxy = pg.SignalProxy(self.scene.sigMouseMoved,
                                    rateLimit=30,
                                    slot=self.cursor_hover_evt)

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.view.mapSceneToView(pos)
        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape
            if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                x = int(pos.x())
                y = int(pos.y())
                z = self.imageItem.image[x, y]
                self.pixel_value.setText(f"x={x}, y={y}, z={z:.5g}")
                self.pixel_value.item.moveBy(0, 12)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            for k, v in self.fetcher.reply.items():
                self.setImage(v, autoLevels=False, autoHistogramRange=False)


class PixelDetWidget(pg.ImageView):

    sigClicked = QtCore.Signal(object, object)

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        self.plot = pg.PlotItem()
        self.plot.hideAxis('left')
        self.plot.hideAxis('bottom')
        super().__init__(parent=parent, view=self.plot)

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr)

        self.last_updated = pg.LabelItem(parent=self.plot)
        self.point = self.plot.plot([0], [0], symbolBrush=(200, 0, 0), symbol='+', symbolSize=25)
        self.pixel_value = pg.LabelItem(parent=self.getView())
        self.proxy = pg.SignalProxy(self.scene.sigMouseMoved,
                                    rateLimit=30,
                                    slot=self.cursor_hover_evt)

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.plot.getViewBox().mapSceneToView(pos)
        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape
            if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                x = int(pos.x())
                y = int(pos.y())
                z = self.imageItem.image[x, y]
                self.pixel_value.setText(f"x={x}, y={y}, z={z:.5g}")
                self.pixel_value.item.moveBy(0, 12)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            for k, v in self.fetcher.reply.items():
                self.setImage(v)

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            view = self.plot.getViewBox()
            if self.imageItem.image is not None:
                shape = self.imageItem.image.shape
                pos = view.mapSceneToView(ev.pos())
                if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                    x = int(pos.x())
                    y = int(pos.y())
                    self.update_cursor(x, y)
                    self.sigClicked.emit(x, y)
        else:
            ev.ignore()

    def update_cursor(self, x, y):
        self.plot.removeItem(self.point)
        self.point = self.plot.plot([x], [y], symbolBrush=(200, 0, 0), symbol='+', symbolSize=25)


class PlotWidget(pg.GraphicsLayoutWidget):

    def __init__(self, topics=None, terms=None, addr=None, uiTemplate=None, parent=None, **kwargs):
        super().__init__(parent)
        self.node = kwargs.get('node', None)

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr)

        self.plot_view = self.addPlot()

        ax = self.plot_view.getAxis('bottom')
        ax.enableAutoSIPrefix(enable=False)

        ay = self.plot_view.getAxis('left')
        ay.enableAutoSIPrefix(enable=False)

        self.plot_view.setMenuEnabled(False)

        self.configure_btn = pg.ButtonItem(pg.pixmaps.getPixmap('ctrl'), 14, parentItem=self.plot_view)
        self.configure_btn.clicked.connect(self.configure_plot)
        self.configure_btn.show()

        self.plot = {}  # { name : PlotDataItem }
        self.trace_ids = {}  # { trace_idx : name }
        self.terms = terms

        self.last_updated = pg.LabelItem(parent=self.plot_view.getViewBox())

        self.pixel_value = pg.LabelItem(parent=self.plot_view.getViewBox())
        self.proxy = pg.SignalProxy(self.sceneObj.sigMouseMoved,
                                    rateLimit=30,
                                    slot=self.cursor_hover_evt)

        if uiTemplate is None:
            uiTemplate = [('Title', 'text'),
                          ('Show Grid', 'check', {'checked': False}),
                          ('Auto Range', 'check', {'checked': True}),
                          # x axis
                          ('Label', 'text', {'group': 'X Axis'}),
                          ('Log Scale', 'check', {'group': 'X Axis', 'checked': False}),
                          # y axis
                          ('Label', 'text', {'group': 'Y Axis'}),
                          ('Log Scale', 'check', {'group': 'Y Axis', 'checked': False})]

        self.uiTemplate = uiTemplate
        self.init_values(self.uiTemplate)
        self.ui, self.stateGroup, self.ctrls = generateUi(self.uiTemplate)

        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

        ctrl_layout = self.ui.layout()

        if kwargs.get('legend', True):
            self.legend = self.plot_view.addLegend()

            self.legend_layout = QtGui.QFormLayout()

            groupbox = QtWidgets.QGroupBox()
            groupbox.setTitle("Legend")
            groupbox.setCheckable(True)
            groupbox.setLayout(self.legend_layout)
            ctrl_layout.addWidget(groupbox)
            self.ctrls["Legend"] = groupbox

        self.apply_btn = QtWidgets.QPushButton("Apply", self.ui)
        self.apply_btn.clicked.connect(self.apply_clicked)
        ctrl_layout.addWidget(self.apply_btn)

    def update_legend_layout(self, idx, data_name, name=None):
        if idx not in self.trace_ids:
            if name is None:
                name = data_name
            self.trace_ids[idx] = data_name
            w = QtGui.QLineEdit(name)
            w.trace_id = idx
            self.ctrls[idx] = w
            self.stateGroup.addWidget(w, idx)
            setattr(self, idx, name)
            self.legend_layout.addRow(idx, w)

        return self.ctrls[idx].text()

    def init_values(self, opts):
        for opt in opts:

            if len(opt) < 3:
                continue

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

    def state_changed(self, *args, **kwargs):
        if args:
            name, val = args
            name = name.replace(" ", "_")
            setattr(self, name, val)

        if self.node:
            self.node.sigStateChanged.emit(self.node)

    def apply_clicked(self):
        title = getattr(self, "Title", "")
        self.plot_view.setTitle(title)

        x_axis_lbl = getattr(self, "Label_X_Axis", "")
        self.plot_view.setLabel('bottom', x_axis_lbl)

        xlog_scale = getattr(self, "Log_Scale_X_Axis", False)
        ylog_scale = getattr(self, "Log_Scale_Y_Axis", False)
        self.plot_view.setLogMode(x=xlog_scale, y=ylog_scale)

        y_axis_lbl = getattr(self, "Label_Y_Axis", "")
        self.plot_view.setLabel('left', y_axis_lbl)

        show_grid = getattr(self, "Show_Grid", False)
        self.plot_view.showGrid(x=show_grid, y=show_grid, alpha=1.0)

        auto_range = getattr(self, "Auto_Range", False)
        if auto_range:
            self.plot_view.vb.enableAutoRange()
        else:
            self.plot_view.vb.disableAutoRange()

        if 'Legend' in self.ctrls:
            if self.ctrls['Legend'].isChecked():
                self.plot_view.vb.removeItem(self.legend)
                self.legend = self.plot_view.addLegend()

                for idx, name in self.trace_ids.items():
                    if name in self.plot:
                        item = self.plot[name]
                        self.legend.removeItem(name)
                        self.legend.addItem(item, self.ctrls[idx].text())
            else:
                self.plot_view.vb.removeItem(self.legend)
                self.legend = None

    def saveState(self):
        if self.stateGroup:
            state = self.stateGroup.state()

            for k, ctrl in self.ctrls.items():
                if isinstance(ctrl, QtGui.QLineEdit):
                    state[k] = ctrl.text()
                    if hasattr(ctrl, 'trace_id'):
                        state[k] = (self.trace_ids[ctrl.trace_id], ctrl.text())
            return state

    def restoreState(self, state):
        if self.stateGroup is not None:
            for k, v in state.items():
                if k.startswith('trace'):
                    self.update_legend_layout(k, *v)
                    state[k] = v[1]

            self.stateGroup.setState(state)

            for k, ctrl in self.ctrls.items():
                if isinstance(ctrl, QtGui.QLineEdit):
                    ctrl.setText(state[k])

            for ctrl, ctrlstate in state.items():
                self.state_changed(ctrl, ctrlstate)

            self.apply_clicked()

    def configure_plot(self):
        self.ui.show()

    def cursor_hover_evt(self):
        pass

    def data_updated(self, data):
        pass

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                self.data_updated(self.fetcher.reply)


class HistogramWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        i = 0

        num_terms = int(len(self.terms)/2)
        for i in range(0, num_terms):
            x = "Bins"
            y = "Counts"

            if i > 0:
                x += f".{i}"
                y += f".{i}"

            x = self.terms[x]
            y = self.terms[y]
            name = y

            x = data[x]
            y = data[y]

            if name not in self.plot:
                _, color = symbols_colors[i]
                legend_name = self.update_legend_layout(f"trace.{i}", name)
                self.plot[name] = self.plot_view.plot(x, y, name=legend_name, brush=color,
                                                      stepMode=True, fillLevel=0)
            else:
                self.plot[name].setData(x=x, y=y)


class Histogram2DWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        uiTemplate = [('Title', 'text'),
                      # x axis
                      ('Label', 'text', {'group': 'X Axis'}),
                      ('Log Scale', 'check', {'group': 'X Axis', 'checked': False}),
                      # y axis
                      ('Label', 'text', {'group': 'Y Axis'}),
                      ('Log Scale', 'check', {'group': 'Y Axis', 'checked': False}),
                      # z axis
                      ('Log Scale', 'check', {'group': 'Z Axis', 'checked': False})]

        super().__init__(topics, terms, addr, uiTemplate, parent, legend=False, **kwargs)

        self.Show_Grid = True
        self.Auto_Range = True

        self.view = self.plot_view.getViewBox()
        self.plot_view.showGrid(True, True)

        ax = self.plot_view.getAxis('bottom')
        ax.setZValue(100)

        ay = self.plot_view.getAxis('left')
        ay.setZValue(100)

        self.imageItem = pg.ImageItem()
        self.view.addItem(self.imageItem)

        self.histogramLUT = pg.HistogramLUTItem(self.imageItem)
        self.addItem(self.histogramLUT)

        self.transform = QtGui.QTransform()
        self.xbins = None
        self.ybins = None

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.view.mapSceneToView(pos)
        inverse = self.transform.inverted()[0]
        pos = pos*inverse

        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape

            if 0 <= pos.x() <= shape[0] and \
               0 <= pos.y() <= shape[1]:
                idxx = int(pos.x())
                idxy = int(pos.y())
                x = self.xbins[idxx]
                y = self.ybins[idxy]
                z = self.imageItem.image[idxx, idxy]
                self.pixel_value.setText(f"x={x:.5g}, y={y:.5g}, z={z:.5g}")
                self.pixel_value.item.moveBy(0, 12)

    def data_updated(self, data):
        xbins = self.terms['XBins']
        ybins = self.terms['YBins']
        counts = self.terms['Counts']

        self.xbins = data[xbins]
        self.ybins = data[ybins]
        counts = data[counts]
        if self.Log_Scale_Z_Axis:
            counts = np.log10(counts)
        xscale = (self.xbins[-1] - self.xbins[0])/self.xbins.shape
        yscale = (self.ybins[-1] - self.ybins[0])/self.ybins.shape

        self.imageItem.setImage(counts)
        self.imageItem.setZValue(-99)
        self.transform = QtGui.QTransform(xscale, 0, 0, yscale, self.xbins[0], self.ybins[0])
        self.imageItem.setTransform(self.transform)


class ScatterWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        num_terms = int(len(self.terms)/2)

        for i in range(0, num_terms):
            x = "X"
            y = "Y"
            if i > 0:
                x += ".%d" % i
                y += ".%d" % i

            x = self.terms[x]
            y = self.terms[y]
            name = " vs ".join((y, x))

            x = data[x]
            y = data[y]

            if name not in self.plot:
                legend_name = self.update_legend_layout(f"trace.{i}", name)
                self.plot[name] = pg.ScatterPlotItem(name=legend_name)
                self.plot_view.addItem(self.plot[name])
                self.legend.addItem(self.plot[name], name=legend_name)

            scatter = self.plot[name]
            symbol, color = symbols_colors[i]
            scatter.setData(x=x, y=y, symbol=symbol, brush=color)


class WaveformWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        i = 0

        for term, name in self.terms.items():
            if name not in self.plot:
                legend_name = self.update_legend_layout(f"trace.{i}", name)
                symbol, color = symbols_colors[i]
                i += 1
                self.plot[name] = self.plot_view.plot(y=np.array(data[name]), name=legend_name,
                                                      symbol=symbol, symbolBrush=color)
            else:
                self.plot[name].setData(y=np.array(data[name]))


class LineWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        num_terms = int(len(self.terms)/2)

        for i in range(0, num_terms):
            x = "X"
            y = "Y"

            if i > 0:
                x += ".%d" % i
                y += ".%d" % i

            x = self.terms[x]
            y = self.terms[y]
            name = " vs ".join((y, x))

            x = data[x]
            y = data[y]

            if name not in self.plot:
                legend_name = self.update_legend_layout(f"trace.{i}", name)
                symbol, color = symbols_colors[i]
                i += 1
                self.plot[name] = self.plot_view.plot(x=x, y=y, name=legend_name, symbol=symbol, symbolBrush=color)
            else:
                self.plot[name].setData(x=x, y=y)


class FitWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        x = self.terms["X"]
        y = self.terms["Y"]
        name = " vs ".join((y, x))

        x = data[x]
        y = data[y]
        i = 0

        if name not in self.plot:
            legend_name = self.update_legend_layout(f"trace.0", name)
            self.plot[name] = pg.ScatterPlotItem(name=legend_name)
            self.plot_view.addItem(self.plot[name])
            self.legend.addItem(self.plot[name], name=legend_name)

        scatter = self.plot[name]
        symbol, color = symbols_colors[i]
        scatter.setData(x=x, y=y, symbol=symbol, brush=color)

        fit = self.terms["Fit"]
        fit = data[fit]
        name = self.terms["Fit"]

        if name not in self.plot:
            legend_name = self.update_legend_layout(f"trace.1", name)
            symbol, color = symbols_colors[1]
            self.plot[name] = self.plot_view.plot(x=x, y=fit, name=legend_name)
        else:
            self.plot[name].setData(x=x, y=fit)


class ArrayWidget(QtWidgets.QWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent)

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr)

        self.terms = terms
        self.update_rate = kwargs.get('update_rate', 30)
        self.grid = QtGui.QGridLayout(self)
        self.table = pg.TableWidget()
        self.last_updated = QtWidgets.QLabel(parent=self)
        self.grid.addWidget(self.table, 0, 0)
        self.grid.setRowStretch(0, 10)
        self.grid.addWidget(self.last_updated, 1, 0)

    async def update(self):
        while True:
            await self.fetcher.fetch()
            self.last_updated.setText(self.fetcher.last_updated)
            if self.fetcher.reply:
                self.array_updated(self.fetcher.reply)
            await asyncio.sleep(self.update_rate)

    def array_updated(self, data):
        for term, name in self.terms.items():
            self.table.setData(data[name])
