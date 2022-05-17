import zmq
import queue
import logging
import datetime as dt
import itertools as it
import numpy as np
import pyqtgraph as pg
from pyqtgraph.GraphicsScene.exportDialog import ExportDialog
from pyqtgraph.Qt import QtGui, QtWidgets, QtCore
from networkfox import modifiers
from ami import LogConfig
from ami.data import Deserializer
from ami.comm import ZMQ_TOPIC_DELIM
from ami.flowchart.library.WidgetGroup import generateUi
from ami.flowchart.library.Editors import TraceEditor, HistEditor, \
    LineEditor, CircleEditor, RectEditor, camera, pixmapFromBase64


logger = logging.getLogger(LogConfig.get_package_name(__name__))
colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
symbols = ['o', 's', 't', 'd', '+']
symbols_colors = list(it.product(symbols, colors))


class AsyncFetcher(QtCore.QThread):

    sig = QtCore.Signal()

    def __init__(self, topics, terms, addr, parent=None, ratelimit=None):
        super(__class__, self).__init__(parent)
        self.addr = addr
        self.running = True
        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.sockets = {}
        self.data = {}
        self.timestamps = {}
        self.reply_queue = queue.Queue()
        self.last_updated = "Last Updated: None"
        self.deserializer = Deserializer()
        self.update_topics(topics, terms)
        self.recv_interrupt = self.ctx.socket(zmq.REP)
        self.recv_interrupt.bind("inproc://fetcher_interrupt")
        self.poller.register(self.recv_interrupt, zmq.POLLIN)
        self.send_interrupt = self.ctx.socket(zmq.REQ)
        self.send_interrupt.connect("inproc://fetcher_interrupt")
        if parent is not None:
            if ratelimit is None:
                self.sig.connect(parent.update)
            else:
                self.sig_proxy = pg.SignalProxy(self.sig,
                                                rateLimit=ratelimit,
                                                slot=parent.update)

    @property
    def ready(self):
        return not self.reply_queue.empty()

    @property
    def reply(self):
        try:
            return self.reply_queue.get(block=False)
        except queue.Empty:
            return {}

    def update_topics(self, topics, terms):
        self.topics = topics
        self.terms = terms
        self.names = list(topics.keys())
        self.subs = set(topics.values())
        self.optional = set([value for key, value in topics.items() if type(key) is modifiers.optional])

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
                sock.setsockopt_string(zmq.SUBSCRIBE, sub_topic + ZMQ_TOPIC_DELIM)
                sock.connect(self.addr.view)
                self.poller.register(sock, zmq.POLLIN)
                self.sockets[name] = (sock, 1)  # reference count
            else:
                sock, count = self.sockets[name]
                self.sockets[name] = (sock, count+1)

    def run(self):
        while self.running:
            for sock, flag in self.poller.poll():
                if flag != zmq.POLLIN:
                    continue
                if sock == self.recv_interrupt and sock.recv_pyobj():
                    break
                topic = sock.recv_string()
                topic = topic.rstrip('\0')
                heartbeat = sock.recv_pyobj()
                reply = sock.recv_serialized(self.deserializer, copy=False)
                self.data[self.view_subs[topic]] = reply
                self.timestamps[self.view_subs[topic]] = heartbeat
                # check if the data is ready
                heartbeats = set(self.timestamps.values())
                num_heartbeats = len(heartbeats)
                res = {}

                if self.data.keys() == self.subs and num_heartbeats == 1:
                    for name, topic in self.topics.items():
                        res[name] = self.data[topic]

                elif self.optional.issuperset(self.data.keys()):
                    for name, topic in self.topics.items():
                        if topic in self.data:
                            res[name] = self.data[topic]

                if res:
                    now = dt.datetime.now()
                    now = now.strftime("%T")
                    heartbeat = heartbeats.pop()
                    latency = dt.datetime.now() - dt.datetime.fromtimestamp(heartbeat.timestamp)
                    self.last_updated = f"Last Updated: {now} Latency: {latency}"
                    # put results on the reply queue
                    self.reply_queue.put(res)
                    # send a signal that data is ready
                    self.sig.emit()

    def close(self):
        self.running = False
        # signal asyncfetcher thread to die then wait
        self.send_interrupt.send_pyobj(True)
        self.wait()
        self.poller.unregister(self.recv_interrupt)
        for name, sock_count in self.sockets.items():
            sock, count = sock_count
            self.poller.unregister(sock)
            sock.close()

        self.ctx.destroy()


class PlotWidget(QtWidgets.QWidget):

    def __init__(self, topics=None, terms=None, addr=None, uiTemplate=None, parent=None, **kwargs):
        super().__init__(parent)
        self.node = kwargs.get('node', None)
        self.units = kwargs.get('units', {})

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr, parent=self)
            self.fetcher.start()

        self.layout = QtWidgets.QGridLayout()
        self.setLayout(self.layout)

        self.graphics_layout = pg.GraphicsLayoutWidget(parent=self)
        self.plot_view = self.graphics_layout.addPlot()
        if self.node:
            # node is passed in on subprocess
            self.viewbox_proxy = pg.SignalProxy(self.plot_view.vb.sigRangeChangedManually,
                                                delay=0.5,
                                                slot=lambda args: self.node.sigStateChanged.emit(self.node))
            self.plot_view.autoBtn.clicked.connect(lambda args: self.node.sigStateChanged.emit(self.node))

        self.plot_view.showGrid(True, True)

        ax = self.plot_view.getAxis('bottom')
        ax.enableAutoSIPrefix(enable=bool(self.units))
        # ax.setZValue(100)

        ay = self.plot_view.getAxis('left')
        ay.enableAutoSIPrefix(enable=bool(self.units))
        # ay.setZValue(100)

        self.plot_view.setMenuEnabled(False)

        self.configure_btn = pg.ButtonItem(pg.icons.getPixmap('ctrl'), 14, parentItem=self.plot_view)
        self.configure_btn.clicked.connect(self.configure_plot)

        self.export_btn = pg.ButtonItem(pixmapFromBase64(camera), 24, parentItem=self.plot_view)
        self.exporter = ExportDialog(self.plot_view.vb.scene())
        self.export_btn.clicked.connect(self.export_plot)

        self.plot = {}  # { name : PlotDataItem }
        self.trace_ids = {}  # { trace_idx : name }
        self.trace_attrs = {}
        self.legend_editors = {}
        self.annotation_editors = {}
        self.annotation_traces = {}

        self.terms = terms

        self.last_updated = QtWidgets.QLabel(parent=self)
        self.pixel_value = QtWidgets.QLabel(parent=self)

        self.layout.addWidget(self.graphics_layout, 0, 0, 1, -1)
        self.layout.addWidget(self.last_updated, 1, 0)
        self.layout.addWidget(self.pixel_value, 1, 1)

        self.hover_proxy = pg.SignalProxy(self.graphics_layout.sceneObj.sigMouseMoved,
                                          rateLimit=30,
                                          slot=self.cursor_hover_evt)

        if uiTemplate is None:
            uiTemplate = [('Title', 'text'),
                          ('Show Grid', 'check', {'checked': True}),
                          # ('Auto Range', 'check', {'checked': True}),
                          # x axis
                          ('Label', 'text', {'group': 'X Axis'}),
                          ('Log Scale', 'check', {'group': 'X Axis', 'checked': False}),
                          # y axis
                          ('Label', 'text', {'group': 'Y Axis'}),
                          ('Log Scale', 'check', {'group': 'Y Axis', 'checked': False})]

        self.uiTemplate = uiTemplate
        self.ui, self.stateGroup, self.ctrls, self.plot_attrs = generateUi(self.uiTemplate)

        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

        ctrl_layout = self.ui.layout()

        self.legend = None
        if kwargs.get('legend', True):
            self.legend = self.plot_view.addLegend()
            self.legend_layout = QtGui.QFormLayout()

            self.legend_groupbox = QtWidgets.QGroupBox()
            self.legend_groupbox.setTitle("Legend")
            self.legend_groupbox.setLayout(self.legend_layout)
            ctrl_layout.addWidget(self.legend_groupbox)
            self.ctrls["Legend"] = self.legend_groupbox

        self.annotation_layout = QtGui.QFormLayout()
        self.annotation_groupbox = QtWidgets.QGroupBox()
        self.annotation_groupbox.setTitle("Annotations")
        self.annotation_groupbox.setLayout(self.annotation_layout)
        ctrl_layout.addWidget(self.annotation_groupbox)
        self.ctrls["Annotations"] = self.annotation_groupbox

        self.annotation_type = QtGui.QComboBox(parent=self.annotation_groupbox)
        self.annotation_type.addItem("Line", LineEditor)
        self.annotation_type.addItem("Circle", CircleEditor)
        self.annotation_type.addItem("Rect", RectEditor)
        self.annotation_layout.addWidget(self.annotation_type)

        self.add_annotation_btn = QtWidgets.QPushButton("Add", self.annotation_groupbox)
        self.add_annotation_btn.clicked.connect(self.add_annotation)
        self.annotation_layout.addWidget(self.add_annotation_btn)

        self.apply_btn = QtWidgets.QPushButton("Apply", self.ui)
        self.apply_btn.clicked.connect(self.apply_clicked)
        ctrl_layout.addWidget(self.apply_btn)

        self.win = QtGui.QMainWindow()
        scrollArea = QtWidgets.QScrollArea(parent=self.win)
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(self.ui)
        self.win.setCentralWidget(scrollArea)
        if self.node:
            self.win.setWindowTitle(self.node.name() + ' configuration')

    def update_legend_layout(self, idx, data_name, name=None, **kwargs):
        restore = kwargs.get('restore', False)

        if idx in self.trace_ids:
            self.trace_ids[idx] = data_name

        if idx not in self.trace_ids:
            if name is None:
                name = data_name

            self.trace_ids[idx] = data_name
            w = QtGui.QLineEdit(name)
            self.ctrls[idx] = w
            self.stateGroup.addWidget(w, idx)
            self.legend_layout.addRow(idx, w)

            editor = self.editor(node=self.node, parent=self.legend_groupbox, **kwargs)
            if restore:
                state = kwargs.get("editor_state", {})
                editor.restoreState(state)
            self.legend_editors[idx] = editor
            self.legend_layout.addWidget(editor)
        elif restore:
            editor = self.legend_editors[idx]
            state = kwargs.get("editor_state", {})
            editor.restoreState(state)

        return self.ctrls[idx].text()

    def add_annotation(self, name=None, state=None):
        if name:
            editor_class, idx = name.split('.')
            editor = eval(editor_class)(node=self.node, parent=self.annotation_groupbox, name=name)
            editor.restoreState(state)
        else:
            editor_class = self.annotation_type.currentData()
            idx = len(self.annotation_editors)
            name = f"{editor_class.__name__}.{idx}"
            editor = editor_class(node=self.node, parent=self.annotation_groupbox, name=name)

        editor.sigRemoved.connect(self.remove_annotation)
        self.annotation_editors[name] = editor
        self.annotation_layout.addWidget(editor)

    def remove_annotation(self, name):
        if name in self.annotation_traces:
            item = self.annotation_traces[name]
            self.plot_view.removeItem(item)
            self.legend.removeItem(item)
            del self.annotation_traces[name]

        editor = self.annotation_editors[name]
        self.annotation_layout.removeWidget(editor.ui)
        editor.deleteLater()
        del self.annotation_editors[name]
        if self.node:
            self.node.sigStateChanged.emit(self.node)

    def editor(self, node, parent, **kwargs):
        return TraceEditor(node=node, parent=parent, **kwargs)

    def state_changed(self, *args, **kwargs):
        name, group, val = args
        if group:
            self.plot_attrs[group][name] = val
        else:
            self.plot_attrs[name] = val

        if self.node:
            self.node.sigStateChanged.emit(self.node)

    def apply_clicked(self):
        title = self.plot_attrs.get('Title', None)
        if title:
            self.plot_view.setTitle(title)

        x_axis = self.plot_attrs.get('X Axis', {})
        y_axis = self.plot_attrs.get('Y Axis', {})

        x_lbl = x_axis.get('Label', None)
        if x_lbl:
            self.plot_view.setLabel('bottom', x_lbl)

        y_lbl = y_axis.get('Label', None)
        if y_lbl:
            self.plot_view.setLabel('left', y_lbl)

        xlog_scale = x_axis.get('Log Scale', False)
        ylog_scale = y_axis.get('Log Scale', False)
        self.plot_view.setLogMode(x=xlog_scale, y=ylog_scale)

        show_grid = self.plot_attrs.get('Show Grid', True)
        self.plot_view.showGrid(x=show_grid, y=show_grid, alpha=1.0)

        # if "Auto Range" in self.plot_attrs:
        #     auto_range = self.plot_attrs["Auto Range"]
        #     if auto_range:
        #         self.plot_view.vb.enableAutoRange()
        #     else:
        #         self.plot_view.vb.disableAutoRange()

        if 'Legend' in self.ctrls:
            self.legend.clear()
            for idx, name in self.trace_ids.items():
                if name in self.plot:
                    item = self.plot[name]
                    attrs = self.legend_editors[idx].attrs
                    self.legend.addItem(item, self.ctrls[idx].text())
                    if 'pen' in attrs:
                        item.setPen(attrs['pen'])
                    self.trace_attrs[name] = attrs

        for name, editor in self.annotation_editors.items():
            x, y = editor.trace_data()
            pen = editor.attrs['pen']
            point = editor.attrs['point']
            if name not in self.annotation_traces:
                self.annotation_traces[name] = self.plot_view.plot(x, y, pen=pen,
                                                                   name=editor.ctrls["name"].text(),
                                                                   **point)
            else:
                item = self.annotation_traces[name]
                item.setData(x, y, pen=pen, **point)
                if self.legend:
                    self.legend.addItem(item, editor.ctrls["name"].text())

    def saveState(self):
        state = {}

        if self.stateGroup:
            state['ctrl'] = self.stateGroup.state()

            legend = {}

            for trace_id, trace_editor in self.legend_editors.items():
                editor_state = trace_editor.saveState()
                ctrl = self.ctrls[trace_id]
                legend[trace_id] = (self.trace_ids[trace_id], ctrl.text(), editor_state)

            if legend:
                state['legend'] = legend

            annotations = {}

            for name, editor in self.annotation_editors.items():
                annotations[name] = editor.saveState()

            if annotations:
                state['annotations'] = annotations

        state['viewbox'] = self.plot_view.vb.getState()

        return state

    def restoreState(self, state):
        if self.stateGroup is not None:
            ctrlstate = state.get('ctrl', {})
            self.stateGroup.setState(ctrlstate)

            legendstate = state.get('legend', {})

            for k, v in legendstate.items():
                if len(v) == 3:
                    data_name, name, editor_state = v
                    self.update_legend_layout(k, data_name, name, editor_state=editor_state, restore=True)

            annotation_state = state.get('annotations', {})
            if annotation_state:
                for name, annotation in annotation_state.items():
                    self.add_annotation(name,  annotation)
            else:
                for name in list(self.annotation_traces.keys()):
                    self.remove_annotation(name)

            self.apply_clicked()

        if 'viewbox' in state:
            self.plot_view.vb.setState(state['viewbox'])

    def configure_plot(self):
        self.win.resize(800, 1000)
        self.win.show()

    def export_plot(self):
        self.exporter.updateItemList()
        self.exporter.show()

    def cursor_hover_evt(self, evt):
        view = self.plot_view.getViewBox()
        pos = evt[0]
        pos = view.mapSceneToView(pos)
        self.pixel_value.setText(f"x={pos.x():.5g}, y={pos.y():.5g}")

    def data_updated(self, data):
        pass

    def update(self):
        while self.fetcher.ready:
            self.last_updated.setText(self.fetcher.last_updated)
            self.data_updated(self.fetcher.reply)

    def close(self):
        if self.fetcher:
            self.fetcher.close()

    def itemPos(self, attr):
        if hasattr(self, attr):
            item = getattr(self, attr)
            rect = self.plot_view.mapRectFromItem(item, item.boundingRect())
            return rect

    def resizeEvent(self, ev):
        super().resizeEvent(ev)

        if hasattr(self, 'plot_view'):
            self.configure_btn.setPos(0, 0)

            rect = self.itemPos('configure_btn')
            x = rect.topRight().x()
            self.export_btn.setPos(x, -5.5)


class ObjectWidget(pg.LayoutWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent)

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr, parent=self)
            self.fetcher.start()

        self.label = self.addLabel()
        self.label.setMinimumSize(360, 180)
        self.label.setWordWrap(True)

    def update(self):
        while self.fetcher.ready:
            for k, v in self.fetcher.reply.items():

                if type(v) is np.ndarray:
                    txt = "variable: %s\ntype: %s\nvalue: %s\nshape: %s\ndtype: %s" % (k, type(v), v, v.shape, v.dtype)
                else:
                    txt = "variable: %s\ntype: %s\nvalue: %s" % (k, type(v), v)
                self.label.setText(txt)

    def close(self):
        if self.fetcher:
            self.fetcher.close()


class ScalarWidget(QtWidgets.QLCDNumber):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent)

        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr, parent=self)
            self.fetcher.start()

        self.setMinimumSize(300, 100)
        self.setDigitCount(10)

    def update(self):
        while self.fetcher.ready:
            for k, v in self.fetcher.reply.items():
                self.display(float(v))

    def close(self):
        if self.fetcher:
            self.fetcher.close()


class ImageWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        uiTemplate = [('Title', 'text'),
                      ('Show Grid', 'check', {'checked': True}),
                      # x axis
                      ('Label', 'text', {'group': 'X Axis'}),
                      ('Log Scale', 'check', {'group': 'X Axis', 'checked': False}),
                      # y axis
                      ('Label', 'text', {'group': 'Y Axis'}),
                      ('Log Scale', 'check', {'group': 'Y Axis', 'checked': False}),
                      # histogram
                      ('Auto Range', 'check', {'group': 'Histogram', 'checked': True}),
                      ('Auto Levels', 'check', {'group': 'Histogram', 'checked': True}),
                      ('Log Scale', 'check', {'group': 'Histogram', 'checked': False})]

        display = kwargs.pop("display", True)
        if display:
            uiTemplate.append(('Flip', 'check', {'group': 'Display', 'checked': False}))
            uiTemplate.append(('Rotate Counter Clockwise', 'combo',
                               {'group': 'Display', 'value': '0',
                                'values': ['0', '90', '180', '270']}))

        super().__init__(topics, terms, addr, uiTemplate=uiTemplate, parent=parent, legend=False, **kwargs)
        self.graphics_layout.useOpenGL(False)
        self.flip = False
        self.rotate = 0
        self.log_scale_histogram = False
        self.auto_levels = True

        self.view = self.plot_view.getViewBox()

        self.imageItem = pg.ImageItem()
        self.imageItem.setZValue(-99)
        self.view.addItem(self.imageItem)

        self.histogramLUT = pg.HistogramLUTItem(self.imageItem)
        self.histogramLUT.gradient.loadPreset('thermal')
        self.histogram_connected = False
        self.graphics_layout.addItem(self.histogramLUT)
        if self.node:
            self.histogramLUT.sigLookupTableChanged.connect(
                lambda args: self.node.sigStateChanged.emit(self.node))

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

    def apply_clicked(self):
        super().apply_clicked()

        if 'Display' in self.plot_attrs:
            self.flip = self.plot_attrs['Display']['Flip']
            self.rotate = int(self.plot_attrs['Display']['Rotate Counter Clockwise'])/90

        self.auto_levels = self.plot_attrs['Histogram']['Auto Levels']
        if not self.auto_levels:
            self.histogram_connected = True
            self.histogramLUT.sigLevelChangeFinished.connect(
                lambda args: self.node.sigStateChanged.emit(self.node))
        else:
            if self.histogram_connected:
                self.histogramLUT.sigLevelChangeFinished.disconnect()
                self.histogram_connected = False

        self.log_scale_histogram = self.plot_attrs['Histogram']['Log Scale']

        autorange_histogram = self.plot_attrs['Histogram']['Auto Range']
        if autorange_histogram:
            self.histogramLUT.autoHistogramRange()
        else:
            self.histogramLUT.vb.disableAutoRange()

    def data_updated(self, data):
        for k, v in data.items():
            if self.flip:
                v = np.flip(v)
            if self.rotate != 0:
                v = np.rot90(v, self.rotate)
            if self.log_scale_histogram:
                v = np.log10(v)

            if v.any():
                self.imageItem.setImage(v, autoLevels=self.auto_levels)

    def saveState(self):
        state = super().saveState()
        state['histogramLUT'] = self.histogramLUT.saveState()
        if not getattr(self, "Auto_Range_Histogram", True):
            state['histogramLUT_viewbox'] = self.histogramLUT.vb.getState()
        return state

    def restoreState(self, state):
        super().restoreState(state)

        if 'histogramLUT' in state:
            self.histogramLUT.restoreState(state['histogramLUT'])

        if 'histogramLUT_viewbox' in state:
            self.histogramLUT.vb.setState(state['histogramLUT_viewbox'])


class PixelDetWidget(ImageWidget):

    sigClicked = QtCore.Signal(object, object)

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent, display=False, **kwargs)
        self.point = self.plot_view.plot([0], [0], symbolBrush=(200, 0, 0), symbol='+', symbolSize=25)

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            if self.imageItem.image is not None:
                shape = self.imageItem.image.shape
                pos = self.view.mapSceneToView(ev.pos())
                if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                    ev.accept()

                    x = int(pos.x())
                    y = int(pos.y())
                    self.update_cursor(x, y)
                    self.sigClicked.emit(x, y)

        super().mousePressEvent(ev)

    def update_cursor(self, x, y):
        self.plot_view.removeItem(self.point)
        self.point = self.plot_view.plot([x], [y], symbolBrush=(200, 0, 0), symbol='+', symbolSize=25)


class HistogramWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.graphics_layout.useOpenGL(False)
        self.num_terms = int(len(terms)/2) if terms else 0

    def editor(self, node, parent, **kwargs):
        return HistEditor(node=node, parent=parent, **kwargs)

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"Bins.{i}" if i > 0 else "Bins"]
            y = self.terms[f"Counts.{i}" if i > 0 else "Counts"]
            name = y

            x = data[x]
            y = data[y]

            if name not in self.plot:
                _, color = symbols_colors[i]
                idx = f"trace.{i}"
                legend_name = self.update_legend_layout(idx, name, color=color)
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                self.plot[name] = self.plot_view.plot(x, y, name=legend_name, brush=color,
                                                      stepMode=True, fillLevel=0)
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(x=x, y=y, **attrs)


class Histogram2DWidget(ImageWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent, display=False, axis=True, **kwargs)

        self.xbins = None
        self.ybins = None
        self.transform = QtGui.QTransform()

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

    def data_updated(self, data):
        xbins = self.terms['XBins']
        ybins = self.terms['YBins']
        counts = self.terms['Counts']

        self.xbins = data[xbins]
        self.ybins = data[ybins]
        counts = data[counts]
        if self.log_scale_histogram:
            counts = np.log10(counts)
        xscale = (self.xbins[-1] - self.xbins[0])/self.xbins.shape
        yscale = (self.ybins[-1] - self.ybins[0])/self.ybins.shape

        self.imageItem.setImage(counts, autoLevels=self.auto_levels)
        self.transform = QtGui.QTransform(xscale, 0, 0, yscale, self.xbins[0], self.ybins[0])
        self.imageItem.setTransform(self.transform)


class ScatterWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.num_terms = int(len(terms)/2) if terms else 0

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))

            x = data[x]
            y = data[y]

            if name not in self.plot:
                symbol, color = symbols_colors[i]
                idx = f"trace.{i}"
                legend_name = self.update_legend_layout(idx, name, symbol=symbol, color=color, style='None')
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                self.plot[name] = self.plot_view.plot(x=x, y=y, name=legend_name, pen=None, **attrs['point'])
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(x=x, y=y, **attrs['point'])


class WaveformWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        i = len(self.plot)

        for term, name in self.terms.items():
            if name not in data:
                continue
            if name not in self.plot:
                _, color = symbols_colors[i]
                idx = f"trace.{i}"
                i += 1
                legend_name = self.update_legend_layout(idx, name, symbol='None', line_color=color)
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                self.plot[name] = self.plot_view.plot(y=data[name], name=legend_name,
                                                      pen=attrs['pen'],
                                                      **attrs['point'])
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(y=data[name], **attrs['point'])


class MultiWaveformWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        name = self.terms['In']
        waveforms = data[name]
        for chan in range(waveforms.shape[0] if isinstance(data, np.ndarray) else len(waveforms)):
            cname = f'{name}:{chan}'
            if cname not in self.plot:
                _, color = symbols_colors[chan]
                idx = f"trace.{chan}"
                legend_name = self.update_legend_layout(idx, cname, symbol='None', line_color=color)
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[cname] = attrs
                self.plot[cname] = self.plot_view.plot(y=waveforms[chan], name=legend_name,
                                                       pen=attrs['pen'],
                                                       **attrs['point'])
            else:
                attrs = self.trace_attrs[cname]
                self.plot[cname].setData(y=waveforms[chan], **attrs['point'])


class LineWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.num_terms = int(len(terms)/2) if terms else 0

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))

            if x not in data or y not in data:
                continue

            x = data[x]
            y = data[y]
            # sort the data using the x-axis, otherwise the drawn line is messed up
            x, y = zip(*sorted(zip(x, y)))

            if name not in self.plot:
                _, color = symbols_colors[i]
                idx = f"trace.{i}"
                i += 1
                legend_name = self.update_legend_layout(idx, name, symbol='None', line_color=color)
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                self.plot[name] = self.plot_view.plot(x=x, y=y,
                                                      name=legend_name, pen=attrs['pen'], **attrs['point'])
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(x=x, y=y, **attrs['point'])


class TimeWidget(LineWidget):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.graphics_layout.useOpenGL(False)
        ax = pg.DateAxisItem(orientation='bottom')
        self.plot_view.setAxisItems({'bottom': ax})
