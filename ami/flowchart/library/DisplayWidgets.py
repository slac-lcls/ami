import datetime as dt
import itertools as it
import logging
import os
import queue
import resource

import numpy as np
import prometheus_client as pc
import pyqtgraph as pg
import zmq
from networkfox import modifiers
from pyqtgraph.exporters import ImageExporter
from pyqtgraph.GraphicsScene.exportDialog import ExportDialog
from qtpy import QtCore, QtGui, QtWidgets

from ami import LogConfig
from ami.data import Deserializer
from ami.flowchart.library.Editors import (
    STYLE,
    CircleEditor,
    HistEditor,
    LineEditor,
    RectEditor,
    TraceEditor,
    camera,
    disk,
    line_styles,
    pixmapFromBase64,
)
from ami.flowchart.library.WidgetGroup import generateUi

logger = logging.getLogger(LogConfig.get_package_name(__name__))
colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
symbols = ["o", "s", "t", "d", "+"]
symbols_colors = list(it.product(symbols, colors))

# Annotation kinds offered by PlotWidget's "Annotations" group (add_annotation/add_plot_annotation),
# keyed by the lowercase name used in the MCP add_plot_annotation/update_plot_annotation tools.
ANNOTATION_KINDS = {"line": LineEditor, "rect": RectEditor, "circle": CircleEditor}


def _widget_group_schema(state_group):
    """Return {group_name_or_None: {setting names in that group}} for a WidgetGroup, derived
    from its own widgetList rather than a hardcoded list -- so validating a get_plot_config/
    set_plot_config/set_trace_style request naturally matches whatever a particular
    PlotWidget subclass's uiTemplate (or a TraceEditor/HistEditor's) actually exposes, which
    differs between e.g. plain PlotWidget and ImageWidget.
    """
    schema = {}
    if not state_group:
        return schema
    for n in state_group.widgetList.values():
        name, group = n if isinstance(n, tuple) else (n, None)
        schema.setdefault(group, set()).add(name)
    return schema


def _validate_against_schema(values, schema, label="setting"):
    """Raise KeyError listing the valid names if values has a key (top-level or, for a grouped
    key whose value is itself a dict, within that group) that schema doesn't recognize.
    """
    top_level = schema.get(None, set()) | {g for g in schema if g is not None}
    unknown = set(values) - top_level
    if unknown:
        raise KeyError(f"Unknown {label}(s) {sorted(unknown)}; valid: {sorted(top_level)}")
    for key, value in values.items():
        if key in schema and isinstance(value, dict):
            bad = set(value) - schema[key]
            if bad:
                raise KeyError(f"Unknown {key} {label}(s) {sorted(bad)}; valid: {sorted(schema[key])}")


def _merge_style(current, update):
    """Shallow-merge a partial trace style update into the current editor state, one level
    deep for grouped keys (e.g. {"Point": {"Brush": [255, 0, 0]}}) so a caller can change just
    one group's field (e.g. Point.Brush) without needing to resend the rest of that group
    (e.g. Point.symbol/Size).
    """
    merged = dict(current)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _annotation_style_groups(editor):
    """The subset of an AnnotationEditor's own setting groups that are appearance (style)
    rather than position -- always some of "Point"/"Line"/"Fill", regardless of the editor's
    position group names (which differ per kind: "From"/"To" for a line, "Top Left"/
    "Bottom Right" for a rect, "Center"/"Radius" for a circle).
    """
    schema = _widget_group_schema(editor.stateGroup)
    return {g for g in ("Point", "Line", "Fill") if g in schema}


class AsyncFetcher(QtCore.QThread):
    sig = QtCore.Signal()

    def __init__(self, topics, terms, addr, parent=None, ratelimit=None):
        super(__class__, self).__init__(parent)
        self.addr = addr
        self.running = True
        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.data = {}
        self.reply_queue = queue.Queue()
        self.heartbeat_timestamp = 0
        self.deserializer = Deserializer()
        self.update_topics(topics, terms)

        self.recv_interrupt = self.ctx.socket(zmq.REP)
        self.recv_interrupt.bind("inproc://fetcher_interrupt")
        self.poller.register(self.recv_interrupt, zmq.POLLIN)
        self.send_interrupt = self.ctx.socket(zmq.REQ)
        self.send_interrupt.connect("inproc://fetcher_interrupt")
        self.export = self.ctx.socket(zmq.SUB)
        self.export.connect(addr.export)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "heartbeat")
        self.view = self.ctx.socket(zmq.REQ)
        self.view.connect(addr.view)

        if parent is not None:
            if ratelimit is None:
                self.sig.connect(parent.update)
            else:
                self.sig_proxy = pg.SignalProxy(self.sig, rateLimit=ratelimit, slot=parent.update)

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
        # Store original mappings
        self.terms = terms
        self.input_to_feature = topics  # Renamed for clarity

        # Build reverse mapping: feature_name → input_name (for unpacking batch data)
        self.feature_to_input = {feature: input_name for input_name, feature in topics.items()}

        # Separate required vs optional features
        self.required_features = {feature for key, feature in topics.items() if not isinstance(key, modifiers.optional)}
        self.optional_features = {feature for key, feature in topics.items() if isinstance(key, modifiers.optional)}

        # Pre-build request list (computed once, not per heartbeat)
        self.feature_requests = [f"view:{self.addr.name}:{feature}" for feature in self.feature_to_input.keys()]

    def run(self):
        while self.running:
            _ = self.export.recv_string()  # topic - unused but required by protocol
            graph = self.export.recv_string()
            heartbeat = self.export.recv_pyobj()

            if graph != self.addr.name:
                continue

            if self.heartbeat_timestamp >= heartbeat.timestamp:
                continue

            self.heartbeat_timestamp = heartbeat.timestamp

            # Build and send batch request (simplified - use pre-built list)
            self.view.send_pyobj(self.feature_requests, flags=zmq.NOBLOCK)

            # Receive batch response
            response = self.view.recv_serialized(self.deserializer, copy=False)
            batch_heartbeat = response["heartbeat"]
            batch_data = response["data"]  # Keys are graph feature names

            # Map from graph feature names → input names for widget consumption
            # NO STRING PARSING NEEDED!
            input_data = {}
            for feature_name, data_value in batch_data.items():
                if feature_name in self.feature_to_input:
                    input_name = self.feature_to_input[feature_name]
                    input_data[input_name] = data_value

            # Filter out invalid data that widgets can't handle (silently drop)
            valid_input_data = {}
            for input_name, data_value in input_data.items():
                # Skip None values
                if data_value is None:
                    continue
                # Skip 0-dimensional numpy arrays (scalars like array(nan))
                if isinstance(data_value, np.ndarray) and data_value.ndim == 0:
                    continue
                # Keep valid data
                valid_input_data[input_name] = data_value

            # Determine which features we actually received (after validation)
            received_features = {feat for inp, feat in self.input_to_feature.items() if inp in valid_input_data}

            # Check if data is complete
            reply = {}

            if received_features == self.required_features:
                # All required features present (and valid)
                reply = valid_input_data
            elif self.optional_features and received_features >= self.required_features:
                # All required + some valid optional features
                reply = valid_input_data

            if reply:
                self.reply_queue.put((batch_heartbeat.timestamp, reply))
                self.sig.emit()

            # Check for interrupt
            try:
                if self.recv_interrupt.recv_pyobj(flags=zmq.NOBLOCK):
                    break
            except zmq.error.Again:
                continue

    def close(self):
        self.running = False
        # signal asyncfetcher thread to die then wait
        self.send_interrupt.send_pyobj(True)
        self.wait()
        self.poller.unregister(self.recv_interrupt)
        self.export.close()
        self.view.close()
        self.ctx.destroy()


class CSVDialog(QtWidgets.QWidget):
    """Floating dialog for importing CSV reference overlays and exporting trace data."""

    def __init__(self, plot_widget, parent=None):
        super().__init__(parent, QtCore.Qt.Tool)
        self.plot_widget = plot_widget
        self.setWindowTitle("CSV References")
        self.resize(520, 320)

        tabs = QtWidgets.QTabWidget()

        # --- Import References tab ---
        import_widget = QtWidgets.QWidget()
        import_layout = QtWidgets.QVBoxLayout(import_widget)

        self.ref_table = QtWidgets.QTableWidget(0, 3)
        self.ref_table.setHorizontalHeaderLabels(["Name", "File", ""])
        self.ref_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.ref_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.ref_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.ref_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.ref_table.verticalHeader().setVisible(False)
        self.ref_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        add_btn = QtWidgets.QPushButton("Add CSV Reference\u2026")
        add_btn.clicked.connect(self._add_reference)

        import_layout.addWidget(self.ref_table)
        import_layout.addWidget(add_btn)

        # --- Export References tab ---
        export_widget = QtWidgets.QWidget()
        export_layout = QtWidgets.QVBoxLayout(export_widget)

        export_layout.addWidget(QtWidgets.QLabel("Select traces to export:"))

        self.export_list = QtWidgets.QListWidget()

        btn_row = QtWidgets.QHBoxLayout()
        select_all_btn = QtWidgets.QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        select_none_btn = QtWidgets.QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(select_none_btn)
        btn_row.addStretch()

        export_btn = QtWidgets.QPushButton("Export Selected to CSV\u2026")
        export_btn.clicked.connect(self._export_csv)

        export_layout.addWidget(self.export_list)
        export_layout.addLayout(btn_row)
        export_layout.addWidget(export_btn)

        tabs.addTab(import_widget, "Import References")
        tabs.addTab(export_widget, "Export References")

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(tabs)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_ref_table()
        self._refresh_export_list()

    def _update_ref_table(self):
        refs = self.plot_widget.csv_references
        self.ref_table.setRowCount(len(refs))
        for i, (name, path) in enumerate(refs.items()):
            self.ref_table.setItem(i, 0, QtWidgets.QTableWidgetItem(name))
            path_item = QtWidgets.QTableWidgetItem(os.path.basename(path))
            path_item.setToolTip(path)
            self.ref_table.setItem(i, 1, path_item)
            remove_btn = QtWidgets.QPushButton("Remove")
            remove_btn.clicked.connect(lambda checked, n=name: self._remove_reference(n))
            self.ref_table.setCellWidget(i, 2, remove_btn)

    def _add_reference(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open CSV Reference", "", "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            self.plot_widget.load_csv_reference(path)
            self._update_ref_table()
            self._refresh_export_list()

    def _remove_reference(self, name):
        self.plot_widget.remove_csv_reference(name)
        self._update_ref_table()
        self._refresh_export_list()

    def _refresh_export_list(self):
        self.export_list.clear()
        for name in self.plot_widget.plot:
            item = QtWidgets.QListWidgetItem(name)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            self.export_list.addItem(item)
        for name in self.plot_widget.csv_references:
            item = QtWidgets.QListWidgetItem(f"[ref] {name}")
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            self.export_list.addItem(item)

    def _select_all(self):
        for i in range(self.export_list.count()):
            self.export_list.item(i).setCheckState(QtCore.Qt.Checked)

    def _select_none(self):
        for i in range(self.export_list.count()):
            self.export_list.item(i).setCheckState(QtCore.Qt.Unchecked)

    def _export_csv(self):
        selected = []
        for i in range(self.export_list.count()):
            item = self.export_list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                selected.append(item.text())
        if not selected:
            QtWidgets.QMessageBox.warning(self, "No Traces Selected", "Please select at least one trace to export.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv);;All Files (*)")
        if path:
            if not path.endswith(".csv"):
                path += ".csv"
            self.plot_widget.export_traces_to_csv(selected, path)


class PlotWidget(QtWidgets.QWidget):
    latency = pc.Gauge("ami_plot_latency_secs", "Plot Latency", ["hutch", "graph_name", "process"])
    memory = pc.Gauge("ami_plot_memory_mb", "Plot Memory", ["hutch", "graph_name", "process"])

    def __init__(self, topics=None, terms=None, addr=None, uiTemplate=None, parent=None, **kwargs):
        super().__init__(parent)
        self.node = kwargs.get("node", None)
        self.units = kwargs.get("units", {})
        self.hutch = kwargs.get("hutch", "")
        self.name = kwargs.get("name", None)
        self.graph_name = addr.name if addr else ""

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
            self.viewbox_proxy = pg.SignalProxy(
                self.plot_view.vb.sigRangeChangedManually,
                delay=0.5,
                slot=lambda args: self.node.sigStateChanged.emit(self.node),
            )
            self.plot_view.autoBtn.clicked.connect(lambda args: self.node.sigStateChanged.emit(self.node))

        if "Background" in STYLE:
            self.graphics_layout.setBackground(STYLE["Background"])

        _show_grid = STYLE.get(self.__class__.__name__, {}).get("ShowGrid", True)
        self.plot_view.showGrid(_show_grid, _show_grid)

        ax = self.plot_view.getAxis("bottom")
        ax.enableAutoSIPrefix(enable=bool(self.units))
        # ax.setZValue(100)

        ay = self.plot_view.getAxis("left")
        ay.enableAutoSIPrefix(enable=bool(self.units))
        # ay.setZValue(100)

        _init_font_size = STYLE.get("FontSize", 9)
        _font = QtGui.QFont()
        _font.setPointSize(_init_font_size)
        ax.textHeight = QtGui.QFontMetrics(_font).height()
        ax.setStyle(tickFont=_font)
        ay.setStyle(tickFont=_font)

        self.plot_view.setMenuEnabled(False)

        self.configure_btn = pg.ButtonItem(pg.icons.getGraphPixmap("ctrl"), 14, parentItem=self.plot_view)
        self.configure_btn.clicked.connect(self.configure_plot)

        self.export_btn = pg.ButtonItem(pixmapFromBase64(camera), 24, parentItem=self.plot_view)
        self.exporter = ExportDialog(self.plot_view.vb.scene())
        self.export_btn.clicked.connect(self.export_plot)

        self.csv_btn = pg.ButtonItem(pixmapFromBase64(disk), 18, parentItem=self.plot_view)
        self.csv_dialog = CSVDialog(self, parent=self)
        self.csv_btn.clicked.connect(self.csv_dialog.show)

        self.plot = {}  # { name : PlotDataItem }
        self.trace_ids = {}  # { trace_idx : name }
        self.trace_attrs = {}  # { name : legend_editors[trace_idx].attrs }
        self.legend_editors = {}  # { trace_idx : TraceEditor() }
        self.annotation_editors = {}
        self.annotation_traces = {}
        self.reference_traces = {}  # { name : PlotDataItem }
        self.csv_references = {}  # { name : filepath }

        self.terms = terms

        # Screenshot settings
        self.screenshot_enabled = False
        self.screenshot_dir = "./screenshots"
        self.screenshot_counter = 0

        # Pending render_plot request (ami/mcp_server.py via NodeScreenshotRequest), answered
        # from the next data_updated in update() so the image always has live data in it.
        # callback(png=..., error=...) — exactly one of the two is given.
        self._screenshot_callback = None

        # Pending get_plot_config/set_plot_config/set_trace_style requests (ami/mcp_server.py
        # via NodeWidgetRequest), answered from the next data_updated in update() -- same
        # timing as the screenshot callback above, so a brand-new plot has had a chance to
        # draw at least one trace before get_config/set_trace needs to find it. List of
        # (op, args, callback); callback(result=..., error=...) -- exactly one is given.
        self._widget_request_queue = []

        self.last_updated = QtWidgets.QLabel(parent=self)
        self.pixel_value = QtWidgets.QLabel(parent=self)

        self.layout.addWidget(self.graphics_layout, 0, 0, 1, -1)
        self.layout.addWidget(self.last_updated, 1, 0)
        self.layout.addWidget(self.pixel_value, 1, 1)

        self.hover_proxy = pg.SignalProxy(
            self.graphics_layout.sceneObj.sigMouseMoved,
            rateLimit=30,
            slot=self.cursor_hover_evt,
        )

        if uiTemplate is None:
            uiTemplate = [
                ("Title", "text"),
                ("Font Size", "intSpin", {"value": STYLE.get("FontSize", 9), "min": 1, "max": 72}),
                ("Show Grid", "check", {"checked": _show_grid}),
                # x axis
                ("Label", "text", {"group": "X Axis"}),
                ("Log Scale", "check", {"group": "X Axis", "checked": False}),
                ("Auto Range", "check", {"group": "X Axis", "checked": True}),
                ("Min", "doubleSpin", {"group": "X Axis", "value": 0.0}),
                ("Max", "doubleSpin", {"group": "X Axis", "value": 100.0}),
                # y axis
                ("Label", "text", {"group": "Y Axis"}),
                ("Log Scale", "check", {"group": "Y Axis", "checked": False}),
                ("Auto Range", "check", {"group": "Y Axis", "checked": True}),
                ("Min", "doubleSpin", {"group": "Y Axis", "value": 0.0}),
                ("Max", "doubleSpin", {"group": "Y Axis", "value": 100.0}),
                # screenshots
                (
                    "Record Screenshots",
                    "check",
                    {"group": "Screenshots", "checked": False},
                ),
                (
                    "Screenshot Directory",
                    "text",
                    {"group": "Screenshots", "value": "./screenshots"},
                ),
            ]

        self.uiTemplate = uiTemplate
        self.ui, self.stateGroup, self.ctrls, self.plot_attrs = generateUi(self.uiTemplate)

        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

        # Setup range control connections
        self._setup_range_controls()

        ctrl_layout = self.ui.layout()

        self.legend = None
        if kwargs.get("legend", True):
            self.legend = self.plot_view.addLegend()
            self.legend_layout = QtWidgets.QFormLayout()

            self.legend_groupbox = QtWidgets.QGroupBox()
            self.legend_groupbox.setTitle("Legend")
            self.legend_groupbox.setLayout(self.legend_layout)
            ctrl_layout.addWidget(self.legend_groupbox)
            self.ctrls["Legend"] = self.legend_groupbox

        self.annotation_layout = QtWidgets.QFormLayout()
        self.annotation_groupbox = QtWidgets.QGroupBox()
        self.annotation_groupbox.setTitle("Annotations")
        self.annotation_groupbox.setLayout(self.annotation_layout)
        ctrl_layout.addWidget(self.annotation_groupbox)
        self.ctrls["Annotations"] = self.annotation_groupbox

        self.annotation_type = QtWidgets.QComboBox(parent=self.annotation_groupbox)
        self.annotation_type.addItem("Line", LineEditor)
        self.annotation_type.addItem("Circle", CircleEditor)
        self.annotation_type.addItem("Rect", RectEditor)
        self.annotation_layout.addWidget(self.annotation_type)

        self.add_annotation_btn = QtWidgets.QPushButton("Add", self.annotation_groupbox)
        self.add_annotation_btn.clicked.connect(self.add_annotation)
        self.annotation_layout.addWidget(self.add_annotation_btn)

        self.ref_editors = {}  # { ref_name : TraceEditor }
        self.ref_layout = QtWidgets.QFormLayout()
        self.ref_groupbox = QtWidgets.QGroupBox()
        self.ref_groupbox.setTitle("References")
        self.ref_groupbox.setLayout(self.ref_layout)
        ctrl_layout.addWidget(self.ref_groupbox)

        self.apply_btn = QtWidgets.QPushButton("Apply", self.ui)
        self.apply_btn.clicked.connect(self.apply_clicked)
        ctrl_layout.addWidget(self.apply_btn)

        self.win = QtWidgets.QMainWindow()
        scrollArea = QtWidgets.QScrollArea(parent=self.win)
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(self.ui)
        self.win.setCentralWidget(scrollArea)
        if self.node:
            self.win.setWindowTitle(self.node.name() + " configuration")

    def _setup_single_axis_controls(self, axis_name):
        """Setup Auto Range checkbox to enable/disable Min/Max spinboxes for one axis.

        Args:
            axis_name: str - "X Axis" or "Y Axis"
        """
        if axis_name not in self.ctrls:
            return

        auto = self.ctrls[axis_name].get("Auto Range")
        min_ctrl = self.ctrls[axis_name].get("Min")
        max_ctrl = self.ctrls[axis_name].get("Max")

        if auto and min_ctrl and max_ctrl:

            def auto_toggled(checked):
                min_ctrl.setEnabled(not checked)
                max_ctrl.setEnabled(not checked)

            auto.toggled.connect(auto_toggled)
            # Set initial state
            min_ctrl.setEnabled(not auto.isChecked())
            max_ctrl.setEnabled(not auto.isChecked())

    def _setup_range_controls(self):
        """Connect Auto Range checkboxes to enable/disable min/max spinboxes."""
        self._setup_single_axis_controls("X Axis")
        self._setup_single_axis_controls("Y Axis")

    def _update_single_axis_spinboxes(self, axis_name, min_val, max_val):
        """Update min/max spinbox values for one axis.

        Args:
            axis_name: str - "X Axis" or "Y Axis"
            min_val: float - Minimum value to set
            max_val: float - Maximum value to set
        """
        if axis_name not in self.ctrls:
            return

        if "Min" in self.ctrls[axis_name]:
            self.ctrls[axis_name]["Min"].setValue(min_val)
        if "Max" in self.ctrls[axis_name]:
            self.ctrls[axis_name]["Max"].setValue(max_val)

    def _update_range_spinboxes(self):
        """Update min/max spinbox values from current viewbox state."""
        viewbox_ranges = self.plot_view.vb.viewRange()
        # viewbox_ranges = [[xmin, xmax], [ymin, ymax]]

        x_min, x_max = viewbox_ranges[0]
        y_min, y_max = viewbox_ranges[1]

        self._update_single_axis_spinboxes("X Axis", x_min, x_max)
        self._update_single_axis_spinboxes("Y Axis", y_min, y_max)

    def update_legend_layout(self, idx, data_name, name=None, **kwargs):
        restore = kwargs.get("restore", False)

        if idx in self.trace_ids:
            self.trace_ids[idx] = data_name

        if idx not in self.trace_ids:
            if name is None:
                name = data_name

            self.trace_ids[idx] = data_name
            w = QtWidgets.QLineEdit(name)
            self.ctrls[idx] = w
            self.stateGroup.addWidget(w, idx)
            self.legend_layout.addRow(idx, w)

            editor = self.editor(parent=self.legend_groupbox, widget=self, **kwargs)
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

    def _next_annotation_name(self, editor_class):
        """A "<EditorClass>.<N>" name not already in annotation_editors, with N one past the
        highest existing index for that class -- NOT len(annotation_editors), which reuses an
        already-removed annotation's name (e.g. add "Line.0", remove it, add again: the next
        one must be "Line.1", not a second "Line.0" that collides with -- and silently
        replaces -- a *different* still-existing annotation of that name).
        """
        prefix = editor_class.__name__ + "."
        existing = [
            int(name[len(prefix) :])
            for name in self.annotation_editors
            if name.startswith(prefix) and name[len(prefix) :].isdigit()
        ]
        return f"{prefix}{max(existing, default=-1) + 1}"

    def add_annotation(self, name=None, state=None):
        if name:
            editor_class_name, _, idx = name.partition(".")
            editor_class = {cls.__name__: cls for cls in ANNOTATION_KINDS.values()}[editor_class_name]
            editor = editor_class(node=self.node, parent=self.annotation_groupbox, name=name)
            editor.restoreState(state)
        else:
            editor_class = self.annotation_type.currentData()
            name = self._next_annotation_name(editor_class)
            editor = editor_class(node=self.node, parent=self.annotation_groupbox, name=name)

        editor.sigRemoved.connect(self.remove_annotation)
        self.annotation_editors[name] = editor
        self.annotation_layout.addWidget(editor)
        return name

    def remove_annotation(self, name):
        if name in self.annotation_traces:
            item = self.annotation_traces[name]
            self.plot_view.removeItem(item)
            self.legend.removeItem(item)
            del self.annotation_traces[name]

        editor = self.annotation_editors[name]
        self.annotation_layout.removeWidget(editor)
        editor.deleteLater()
        del self.annotation_editors[name]
        if self.node:
            self.node.sigStateChanged.emit(self.node)

    def editor(self, parent, **kwargs):
        return TraceEditor(parent=parent, **kwargs)

    def state_changed(self, *args, **kwargs):
        name, group, val = args
        if group:
            self.plot_attrs[group][name] = val
        else:
            self.plot_attrs[name] = val

    def _apply_axis_range(self, axis_name, axis_attrs):
        """Apply range settings for a single axis (X or Y).

        Args:
            axis_name: str - "X" or "Y"
            axis_attrs: dict - Axis attributes from self.plot_attrs
        """
        auto_range = axis_attrs.get("Auto Range", True)

        # Determine axis constant and setter method
        if axis_name == "X":
            axis_const = pg.ViewBox.XAxis
            set_range = self.plot_view.setXRange
        else:  # Y
            axis_const = pg.ViewBox.YAxis
            set_range = self.plot_view.setYRange

        if auto_range:
            self.plot_view.vb.enableAutoRange(axis=axis_const)
        else:
            min_val = axis_attrs.get("Min", 0.0)
            max_val = axis_attrs.get("Max", 100.0)

            # Validation: swap if min > max
            if min_val > max_val:
                min_val, max_val = max_val, min_val

            set_range(min_val, max_val, padding=0)
            self.plot_view.vb.disableAutoRange(axis=axis_const)

    def apply_clicked(self):
        font_size = self.plot_attrs.get("Font Size", 9)
        font_size_title = {"size": f"{font_size}pt"}

        title = self.plot_attrs.get("Title", None)
        if title:
            self.plot_view.setTitle(title, **font_size_title)

        x_axis = self.plot_attrs.get("X Axis", {})
        y_axis = self.plot_attrs.get("Y Axis", {})

        x_lbl = x_axis.get("Label", None)
        if x_lbl:
            # Mutate labelStyle directly so setLabel (called with no CSS kwargs)
            # does not hit the `self.labelStyle = args` replacement on AxisItem.setLabel
            # line 342, which would wipe the 'color' key set by setPen/setTextPen.
            ax = self.plot_view.getAxis("bottom")
            ax.labelStyle["font-size"] = f"{font_size}pt"
            ax.labelStyle["color"] = ax.textPen().color().name()
            self.plot_view.setLabel("bottom", x_lbl)

        y_lbl = y_axis.get("Label", None)
        if y_lbl:
            ay = self.plot_view.getAxis("left")
            ay.labelStyle["font-size"] = f"{font_size}pt"
            ay.labelStyle["color"] = ay.textPen().color().name()
            self.plot_view.setLabel("left", y_lbl)

        # Apply tick font AFTER labels so that when setStyle triggers _updateHeight(),
        # the label QGraphicsTextItem already has correct HTML and a valid bounding rect.
        # Also set textHeight on both axes (left was previously missing).
        _font = QtGui.QFont()
        _font.setPointSize(font_size)
        ax = self.plot_view.getAxis("bottom")
        ax.textHeight = QtGui.QFontMetrics(_font).height()
        ax.setStyle(tickFont=_font)
        ay = self.plot_view.getAxis("left")
        ay.textHeight = QtGui.QFontMetrics(_font).height()
        ay.setStyle(tickFont=_font)

        xlog_scale = x_axis.get("Log Scale", False)
        ylog_scale = y_axis.get("Log Scale", False)
        self.plot_view.setLogMode(x=xlog_scale, y=ylog_scale)

        show_grid = self.plot_attrs.get("Show Grid", True)
        self.plot_view.showGrid(x=show_grid, y=show_grid, alpha=1.0)

        # Apply axis range settings
        self._apply_axis_range("X", x_axis)
        self._apply_axis_range("Y", y_axis)

        if "Legend" in self.ctrls:
            self.legend.clear()
            for idx, name in self.trace_ids.items():
                if name in self.plot:
                    item = self.plot[name]
                    attrs = self.legend_editors[idx].attrs
                    self.legend.addItem(item, self.ctrls[idx].text())
                    if "pen" in attrs:
                        item.setPen(attrs["pen"])
                    self.trace_attrs[name] = attrs

        for name, editor in self.annotation_editors.items():
            x, y = editor.trace_data()
            pen = editor.attrs["pen"]
            point = editor.attrs["point"]
            if name not in self.annotation_traces:
                # addItem(ignoreBounds=True), not plot_view.plot() (which calls addItem with
                # the default ignoreBounds=False) -- a threshold line/box is deliberately
                # drawn far outside the data's own range (e.g. a threshold spanning the whole
                # plot uses endpoints like X=+-1e9), and counting it in auto-range would blow
                # the view out to that scale, hiding the actual data it's meant to annotate.
                # PlotItem.addItem still adds it to the legend (via its own `name=` handling)
                # same as plot_view.plot() did.
                item = pg.PlotDataItem(x, y, pen=pen, name=editor.ctrls["name"].text(), **point)
                self.plot_view.addItem(item, ignoreBounds=True)
                self.annotation_traces[name] = item
            else:
                item = self.annotation_traces[name]
                item.setData(x, y, pen=pen, **point)
                if self.legend:
                    self.legend.addItem(item, editor.ctrls["name"].text())

        for ref_name, editor in self.ref_editors.items():
            if ref_name in self.reference_traces:
                item = self.reference_traces[ref_name]
                if editor.attrs:
                    x, y = item.getData()
                    pen = editor.attrs.get("pen")
                    point = editor.attrs.get("point", {})
                    item.setData(x, y, pen=pen, **point)
                legend_label = editor.name_edit.text() if hasattr(editor, "name_edit") else ref_name
                if self.legend:
                    self.legend.addItem(item, legend_label)

        # Handle screenshot configuration
        if "Screenshots" in self.plot_attrs:
            self.screenshot_enabled = self.plot_attrs["Screenshots"].get("Record Screenshots", False)
            self.screenshot_dir = self.plot_attrs["Screenshots"].get("Screenshot Directory", "./screenshots")

            # Create directory if it doesn't exist and screenshots are enabled
            if self.screenshot_enabled:
                os.makedirs(self.screenshot_dir, exist_ok=True)

        self.node.sigStateChanged.emit(self.node)

    def saveState(self):
        state = {}

        if self.stateGroup:
            state["ctrl"] = self.stateGroup.state()

            legend = {}

            for trace_id, trace_editor in self.legend_editors.items():
                editor_state = trace_editor.saveState()
                ctrl = self.ctrls[trace_id]
                legend[trace_id] = (self.trace_ids[trace_id], ctrl.text(), editor_state)

            if legend:
                state["legend"] = legend

            annotations = {}

            for name, editor in self.annotation_editors.items():
                annotations[name] = editor.saveState()

            if annotations:
                state["annotations"] = annotations

        state["viewbox"] = self.plot_view.vb.getState()
        # Save screenshot settings
        state["screenshot_enabled"] = self.screenshot_enabled
        state["screenshot_dir"] = self.screenshot_dir
        state["screenshot_counter"] = self.screenshot_counter
        # Save CSV reference paths and editor states
        state["csv_references"] = dict(self.csv_references)
        state["ref_editors"] = {n: e.saveState() for n, e in self.ref_editors.items()}
        state["ref_legend_names"] = {
            n: e.name_edit.text() for n, e in self.ref_editors.items() if hasattr(e, "name_edit")
        }

        return state

    def restoreState(self, state):
        if self.stateGroup is not None:
            ctrlstate = state.get("ctrl", {})
            self.stateGroup.setState(ctrlstate)

            legendstate = state.get("legend", {})

            for k, v in legendstate.items():
                if len(v) == 3:
                    data_name, name, editor_state = v
                    self.update_legend_layout(k, data_name, name, editor_state=editor_state, restore=True)

            # Remove every existing annotation first -- restoring into a widget that already
            # has annotations (e.g. a NodeWidgetStateUpdate pushed to an open window) must end
            # up with exactly the saved set, not the saved set *added* to what's already there
            # (duplicate editors/traces for shared names, stale ones for anything removed since
            # this state was saved). Iterate annotation_editors, not the smaller
            # annotation_traces (editors added but not yet drawn by apply_clicked() wouldn't be
            # in there, and would survive this "clear everything" step).
            for name in list(self.annotation_editors.keys()):
                self.remove_annotation(name)
            for name, annotation in state.get("annotations", {}).items():
                self.add_annotation(name, annotation)

            self.apply_clicked()

        if "viewbox" in state:
            self.plot_view.vb.setState(state["viewbox"])

        # Restore screenshot settings
        self.screenshot_enabled = state.get("screenshot_enabled", False)
        self.screenshot_dir = state.get("screenshot_dir", "./screenshots")
        self.screenshot_counter = state.get("screenshot_counter", 0)

        # Restore CSV reference overlays
        for name in list(self.csv_references.keys()):
            self.remove_csv_reference(name)
        for name, path in state.get("csv_references", {}).items():
            if os.path.exists(path):
                self.load_csv_reference(path, name=name)
            else:
                logger.warning(f"CSV reference file not found, skipping: {path}")
        for name, editor_state in state.get("ref_editors", {}).items():
            if name in self.ref_editors:
                self.ref_editors[name].restoreState(editor_state)
                if name in self.reference_traces:
                    attrs = self.ref_editors[name].attrs
                    if attrs and "pen" in attrs:
                        self.reference_traces[name].setPen(attrs["pen"])
        for name, label in state.get("ref_legend_names", {}).items():
            if name in self.ref_editors and hasattr(self.ref_editors[name], "name_edit"):
                self.ref_editors[name].name_edit.setText(label)

    def configure_plot(self):
        # Update min/max spinboxes with current viewbox ranges
        self._update_range_spinboxes()
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
            heartbeat_timestamp, reply = self.fetcher.reply
            self.data_updated(reply)

            # Dump screenshot after data update
            self._dump_screenshot()

            # Answer any pending render_plot screenshot request (ami/mcp_server.py) now that
            # there's fresh data on screen, rather than mid-update with a blank/stale plot.
            if self._screenshot_callback is not None:
                callback, self._screenshot_callback = self._screenshot_callback, None
                try:
                    callback(png=self.screenshot_png())
                except Exception as e:
                    callback(error=str(e))

            # Answer any pending get_plot_config/set_plot_config/set_trace_style requests
            # (ami/mcp_server.py) the same way.
            if self._widget_request_queue:
                pending, self._widget_request_queue = self._widget_request_queue, []
                for op, args, callback in pending:
                    try:
                        callback(result=self.handle_widget_request(op, args))
                    except Exception as e:
                        callback(error=str(e))

            now = dt.datetime.now()
            now = now.strftime("%T")
            ru = resource.getrusage(resource.RUSAGE_SELF)
            rss = ru.ru_maxrss / 1024
            latency = dt.datetime.now() - dt.datetime.fromtimestamp(heartbeat_timestamp)

            # Build status text with optional screenshot counter
            status_text = f"Last Updated: {now} Latency: {latency} RSS: {rss} MB"
            if self.screenshot_enabled and self.screenshot_counter > 0:
                status_text += f" | Screenshots: {self.screenshot_counter:,}"
            self.last_updated.setText(status_text)

            self.latency.labels(self.hutch, self.graph_name, self.name).set(latency.total_seconds())
            self.memory.labels(self.hutch, self.graph_name, self.name).set(rss)

    def screenshot_png(self):
        """Render the current plot (including any ROI/overlay items) to PNG bytes.

        Same ImageExporter used by _dump_screenshot and the GUI's own export button, so the
        image matches exactly what the window shows. Raises if the scene can't be rendered.
        """
        image = ImageExporter(self.plot_view.vb.scene()).export(toBytes=True)
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        return bytes(buf.data())

    def request_screenshot(self, callback):
        """Request a PNG of the next data_updated frame.

        callback is invoked with either png=<bytes> or error=<str> (never both), from the Qt
        thread, the next time this widget redraws. Only one request is tracked at a time; a
        newer request replaces an older, not-yet-answered one.
        """
        self._screenshot_callback = callback

    def request_widget_op(self, op, args, callback):
        """Queue a get_plot_config/set_plot_config/set_trace_style request (ami/mcp_server.py)
        to run after the next data_updated frame -- same timing as request_screenshot, so a
        brand-new plot has had a chance to draw at least one trace first.

        callback is invoked with either result=<...> or error=<str> (never both), from the Qt
        thread.
        """
        self._widget_request_queue.append((op, args, callback))

    def _config_schema(self):
        """Valid plot-level setting names (and, for grouped ones like "X Axis", the valid
        names within that group) for THIS widget instance's uiTemplate -- excludes the
        per-trace legend-label entries (named by trace_ids's "trace.N" keys) that also live in
        the same stateGroup, and the "Screenshots" group (screenshot_enabled/screenshot_dir
        have their own purpose unrelated to plot appearance; not part of this API).
        """
        schema = _widget_group_schema(self.stateGroup)
        schema.pop("Screenshots", None)
        schema[None] = {n for n in schema.get(None, set()) if n not in self.trace_ids}
        return schema

    def handle_widget_request(self, op, args):
        """Run one get_plot_config/set_plot_config/set_trace_style/add_plot_annotation/
        update_plot_annotation/remove_plot_annotation operation and return its result, or
        raise (caught by the caller in update()/request_widget_op's queue).
        """
        if op == "get_config":
            return self._get_plot_config()
        elif op == "set_config":
            return self._set_plot_config(args.get("settings") or {})
        elif op == "set_trace":
            return self._set_trace_style(args.get("trace"), args.get("label"), args.get("style"))
        elif op == "add_annotation":
            return self._add_annotation_op(args.get("kind"), args.get("points"), args.get("label"), args.get("style"))
        elif op == "set_annotation":
            return self._set_annotation_op(args.get("id"), args.get("points"), args.get("label"), args.get("style"))
        elif op == "remove_annotation":
            return self._remove_annotation_op(args.get("id"))
        else:
            raise ValueError(f"Unknown plot widget request op '{op}'")

    def _get_plot_config(self):
        schema = self._config_schema()
        ctrl = self.stateGroup.state() if self.stateGroup else {}
        plot_cfg = {}
        for name in schema.get(None, set()):
            if name in ctrl:
                plot_cfg[name] = ctrl[name]
        for group in schema:
            if group is not None and group in ctrl:
                plot_cfg[group] = dict(ctrl[group])

        traces = {}
        for idx, data_name in self.trace_ids.items():
            label = self.ctrls[idx].text() if idx in self.ctrls else data_name
            style = self.legend_editors[idx].saveState() if idx in self.legend_editors else {}
            traces[data_name] = {"label": label, "style": style}

        return {"plot": plot_cfg, "traces": traces, "annotations": self._annotations_config()}

    def _set_plot_config(self, settings):
        _validate_against_schema(settings, self._config_schema(), label="plot setting")
        if self.stateGroup:
            self.stateGroup.setState(settings)
        self.apply_clicked()
        return self._get_plot_config()

    def _set_trace_style(self, trace, label, style):
        idx = None
        for i, data_name in self.trace_ids.items():
            if data_name == trace:
                idx = i
                break
        if idx is None:
            available = {dn: self.ctrls[i].text() for i, dn in self.trace_ids.items() if i in self.ctrls}
            raise KeyError(f"No trace named '{trace}' on this plot; available traces (data name: label): {available}")

        if label is not None:
            self.ctrls[idx].setText(label)

        if style:
            editor = self.legend_editors[idx]
            _validate_against_schema(style, _widget_group_schema(editor.stateGroup), label="trace style")
            editor.restoreState(_merge_style(editor.saveState(), style))

        self.apply_clicked()
        return self._get_plot_config()

    def _annotation_config(self, name):
        """{"kind", "label", "points", "style"} for one annotation -- "points" and "style" are
        split out of its saved state (editor.saveState()'s flat {group: {field: value}, ...})
        by group name: "Point"/"Line"/"Fill" are style, anything else (its two kind-specific
        position groups, e.g. "From"/"To" for a line) is points. "label" is its ungrouped
        "name" field (the legend text), not the dict key `name` (its id, e.g. "LineEditor.0").
        """
        editor = self.annotation_editors[name]
        saved = editor.saveState()
        style_groups = _annotation_style_groups(editor)
        points = {g: v for g, v in saved.items() if isinstance(v, dict) and g not in style_groups}
        style = {g: v for g, v in saved.items() if g in style_groups}
        kind = next((k for k, cls in ANNOTATION_KINDS.items() if isinstance(editor, cls)), type(editor).__name__)
        return {"kind": kind, "label": saved.get("name", name), "points": points, "style": style}

    def _annotations_config(self):
        return {name: self._annotation_config(name) for name in self.annotation_editors}

    def _apply_annotation_fields(self, editor, points, label, style):
        """Validate and apply a partial points/label/style update to an annotation editor
        (shared by add_plot_annotation/update_plot_annotation) -- restoreState()/setState()
        only touches the keys given, leaving the rest of the editor's current state (defaults
        for a new annotation, its existing values for an update) alone.
        """
        fields = {}
        if points:
            fields.update(points)
        if style:
            fields.update(style)
        if label is not None:
            fields["name"] = label
        if fields:
            _validate_against_schema(fields, _widget_group_schema(editor.stateGroup), label="annotation field")
            editor.restoreState(fields)

    def _add_annotation_op(self, kind, points, label, style):
        if not isinstance(kind, str) or kind.lower() not in ANNOTATION_KINDS:
            raise KeyError(f"Unknown annotation kind '{kind}'; valid: {sorted(ANNOTATION_KINDS)}")
        editor_class = ANNOTATION_KINDS[kind.lower()]
        name = self._next_annotation_name(editor_class)
        editor = editor_class(node=self.node, parent=self.annotation_groupbox, name=name)
        editor.sigRemoved.connect(self.remove_annotation)
        self.annotation_editors[name] = editor
        self.annotation_layout.addWidget(editor)
        try:
            self._apply_annotation_fields(editor, points, label, style)
        except Exception:
            self.remove_annotation(name)
            raise
        self.apply_clicked()
        result = self._get_plot_config()
        result["id"] = name
        return result

    def _set_annotation_op(self, name, points, label, style):
        if name not in self.annotation_editors:
            raise KeyError(f"No annotation named '{name}' on this plot; existing: {sorted(self.annotation_editors)}")
        self._apply_annotation_fields(self.annotation_editors[name], points, label, style)
        self.apply_clicked()
        return self._get_plot_config()

    def _remove_annotation_op(self, name):
        if name not in self.annotation_editors:
            raise KeyError(f"No annotation named '{name}' on this plot; existing: {sorted(self.annotation_editors)}")
        self.remove_annotation(name)
        return self._get_plot_config()

    def _dump_screenshot(self):
        """
        Automatically save a screenshot of the current plot.
        Called from update() when screenshot_enabled is True.
        """
        if not self.screenshot_enabled:
            return

        try:
            # Ensure directory exists
            os.makedirs(self.screenshot_dir, exist_ok=True)

            # Generate filename with timestamp and node name
            timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]  # Include milliseconds
            node_name = self.name if self.name else "plot"
            # Sanitize node name for filesystem
            node_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in node_name)
            filename = f"{timestamp}_{node_name}.png"
            filepath = os.path.join(self.screenshot_dir, filename)

            with open(filepath, "wb") as f:
                f.write(self.screenshot_png())

            self.screenshot_counter += 1
            logger.debug(f"Screenshot saved: {filepath} (count: {self.screenshot_counter})")

        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")

    def load_csv_reference(self, path, name=None):
        """Load a CSV file as a reference overlay trace on the plot."""
        try:
            try:
                data = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding=None)
                cols = data.dtype.names
                if cols and len(cols) >= 2:
                    x = data[cols[0]].astype(float)
                    y = data[cols[1]].astype(float)
                elif cols and len(cols) == 1:
                    y = data[cols[0]].astype(float)
                    x = np.arange(len(y), dtype=float)
                else:
                    raise ValueError("no columns parsed")
            except Exception:
                raw = np.genfromtxt(path, delimiter=",")
                if raw.ndim == 1:
                    x = np.arange(len(raw), dtype=float)
                    y = raw.astype(float)
                elif raw.ndim == 2 and raw.shape[1] >= 2:
                    x = raw[:, 0]
                    y = raw[:, 1]
                else:
                    logger.error(f"Cannot parse CSV reference {path}: unexpected shape")
                    return
        except Exception as e:
            logger.error(f"Failed to load CSV reference {path}: {e}")
            return

        if name is None:
            name = os.path.splitext(os.path.basename(path))[0]

        base_name = name
        i = 1
        while name in self.csv_references:
            name = f"{base_name}_{i}"
            i += 1

        ref_colors = [(255, 165, 0), (128, 0, 200), (0, 200, 200), (255, 20, 147), (200, 200, 0)]
        color = ref_colors[len(self.reference_traces) % len(ref_colors)]
        trace = self.plot_view.plot(x, y, pen=pg.mkPen(color, width=2))
        self.reference_traces[name] = trace
        self.csv_references[name] = path

        r, g, b = color[:3]
        ref_uiTemplate = [
            (
                "symbol",
                "combo",
                {
                    "values": ["o", "t", "t1", "t2", "t3", "s", "p", "h", "star", "+", "d", "None"],
                    "value": "None",
                    "group": "Point",
                },
            ),
            ("Brush", "color", {"value": (0, 0, 255), "group": "Point"}),
            ("Size", "intSpin", {"min": 1, "value": 14, "group": "Point"}),
            ("color", "color", {"group": "Line", "value": (r, g, b)}),
            ("width", "intSpin", {"min": 1, "value": 1, "group": "Line"}),
            ("style", "combo", {"values": list(line_styles.keys()), "value": "Solid", "group": "Line"}),
        ]
        name_edit = QtWidgets.QLineEdit(name)
        editor = TraceEditor(parent=self.ref_groupbox, widget=self, uiTemplate=ref_uiTemplate)
        editor.name_edit = name_edit
        self.ref_layout.addRow(name, name_edit)
        self.ref_layout.addRow(editor)
        self.ref_editors[name] = editor
        if self.legend:
            self.legend.addItem(trace, name)
        return name

    def set_csv_references(self, references):
        """Make the reference overlays match references ({ name : filepath })."""
        for name, path in list(self.csv_references.items()):
            if references.get(name) != path:
                self.remove_csv_reference(name)
        for name, path in references.items():
            if name not in self.csv_references:
                self.load_csv_reference(path, name=name)

    def remove_csv_reference(self, name):
        """Remove a CSV reference overlay trace from the plot."""
        if name in self.reference_traces:
            item = self.reference_traces.pop(name)
            self.plot_view.removeItem(item)
            if self.legend:
                self.legend.removeItem(item)
        self.csv_references.pop(name, None)
        if name in self.ref_editors:
            editor = self.ref_editors.pop(name)
            if hasattr(editor, "name_edit"):
                self.ref_layout.removeRow(editor.name_edit)
            self.ref_layout.removeRow(editor)

    def export_traces_to_csv(self, selected_names, path):
        """Write selected live and reference traces to a CSV file."""
        data_dict = {}
        for label in selected_names:
            if label.startswith("[ref] "):
                name = label[len("[ref] ") :]
                item = self.reference_traces.get(name)
            else:
                item = self.plot.get(label)
            if item is None:
                continue
            xdata, ydata = item.getData()
            if xdata is not None:
                data_dict[f"{label}_x"] = xdata
            if ydata is not None:
                data_dict[f"{label}_y"] = ydata
        if not data_dict:
            return
        max_len = max(len(v) for v in data_dict.values())
        cols = [np.pad(v.astype(float), (0, max_len - len(v)), constant_values=np.nan) for v in data_dict.values()]
        try:
            np.savetxt(path, np.column_stack(cols), delimiter=",", header=",".join(data_dict.keys()), comments="")
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")

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

        if hasattr(self, "plot_view"):
            self.configure_btn.setPos(0, 0)

            rect = self.itemPos("configure_btn")
            x = rect.topRight().x()
            self.export_btn.setPos(x, -5.5)

            rect = self.itemPos("export_btn")
            x = rect.topRight().x()
            self.csv_btn.setPos(x, -2.5)


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
            heartbeat_timestamp, reply = self.fetcher.reply
            for k, v in reply.items():
                if type(v) is np.ndarray:
                    txt = "variable: %s\ntype: %s\nvalue: %s\nshape: %s\ndtype: %s" % (
                        k,
                        type(v),
                        v,
                        v.shape,
                        v.dtype,
                    )
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
            heartbeat_timestamp, reply = self.fetcher.reply
            for k, v in reply.items():
                self.display(float(v))

    def close(self):
        if self.fetcher:
            self.fetcher.close()


class ImageWidget(PlotWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        uiTemplate = [
            ("Title", "text"),
            ("Font Size", "intSpin", {"value": STYLE.get("FontSize", 9), "min": 1, "max": 72}),
            ("Show Grid", "check", {"checked": STYLE.get(self.__class__.__name__, {}).get("ShowGrid", True)}),
            # x axis
            ("Label", "text", {"group": "X Axis"}),
            ("Log Scale", "check", {"group": "X Axis", "checked": False}),
            # y axis
            ("Label", "text", {"group": "Y Axis"}),
            ("Log Scale", "check", {"group": "Y Axis", "checked": False}),
            # histogram
            ("Auto Range", "check", {"group": "Histogram", "checked": True}),
            ("Auto Levels", "check", {"group": "Histogram", "checked": True}),
            ("Log Scale", "check", {"group": "Histogram", "checked": False}),
        ]

        display = kwargs.pop("display", True)
        if display:
            uiTemplate.append(("Lock Aspect Ratio", "check", {"group": "Display", "checked": True}))
            uiTemplate.append(("Flip", "check", {"group": "Display", "checked": False}))
            uiTemplate.append(
                (
                    "Rotate Counter Clockwise",
                    "combo",
                    {
                        "group": "Display",
                        "value": "0",
                        "values": ["0", "90", "180", "270"],
                    },
                )
            )

        super().__init__(
            topics,
            terms,
            addr,
            uiTemplate=uiTemplate,
            parent=parent,
            legend=False,
            **kwargs,
        )
        # self.graphics_layout.useOpenGL(False)
        self.flip = False
        self.rotate = 0
        self.log_scale_histogram = False
        self.auto_levels = False
        self.ratio = 1  # Update if we happen to have detectors that do not have square pixels
        self.lock = True

        self.view = self.plot_view.getViewBox()

        self.imageItem = pg.ImageItem()
        self.imageItem.setZValue(-99)
        self.view.addItem(self.imageItem)
        self.view.invertY()
        self.view.setAspectLocked(lock=self.lock, ratio=self.ratio)

        self.histogramLUT = pg.HistogramLUTItem(self.imageItem)

        if "ImageWidget" in STYLE:
            style = STYLE["ImageWidget"]
        else:
            style = {}
            style["gradient"] = "thermal"

        self.histogramLUT.gradient.loadPreset(style["gradient"])

        self.histogram_connected = False
        self.graphics_layout.addItem(self.histogramLUT)
        if self.node:
            self.histogramLUT.sigLookupTableChanged.connect(lambda args: self.node.sigStateChanged.emit(self.node))

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.view.mapSceneToView(pos)
        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape
            i = int(pos.y())  # image is row-major
            j = int(pos.x())  # image is row-major
            if 0 <= i < shape[0] and 0 <= j < shape[1]:
                z = self.imageItem.image[i, j]
                self.pixel_value.setText(f"x={j}, y={i}, z={z:.5g}")

    def apply_clicked(self):
        if "Display" in self.plot_attrs:
            self.flip = self.plot_attrs["Display"]["Flip"]
            self.rotate = int(self.plot_attrs["Display"]["Rotate Counter Clockwise"]) / 90
            self.lock = self.plot_attrs["Display"]["Lock Aspect Ratio"]

        self.auto_levels = self.plot_attrs["Histogram"]["Auto Levels"]
        if not self.auto_levels:
            self.histogram_connected = True
            self.histogramLUT.sigLevelChangeFinished.connect(lambda args: self.node.sigStateChanged.emit(self.node))
        else:
            if self.histogram_connected:
                self.histogramLUT.sigLevelChangeFinished.disconnect()
                self.histogram_connected = False

        self.log_scale_histogram = self.plot_attrs["Histogram"]["Log Scale"]

        autorange_histogram = self.plot_attrs["Histogram"]["Auto Range"]
        if autorange_histogram:
            self.histogramLUT.autoHistogramRange()
        else:
            self.histogramLUT.vb.disableAutoRange()

        self.view.setAspectLocked(lock=self.lock, ratio=self.ratio)

        super().apply_clicked()

    def data_updated(self, data):
        for k, v in data.items():
            if self.flip:
                v = np.flip(v)
            if self.log_scale_histogram:
                v = np.log10(v)
            if self.rotate != 0:
                v = np.rot90(v, self.rotate)

            if v.any():
                self.imageItem.setImage(v, autoLevels=self.auto_levels)

    def saveState(self):
        state = super().saveState()
        state["histogramLUT"] = self.histogramLUT.saveState()
        if not getattr(self, "Auto_Range_Histogram", True):
            state["histogramLUT_viewbox"] = self.histogramLUT.vb.getState()
        return state

    def restoreState(self, state):
        super().restoreState(state)

        if "histogramLUT" in state:
            self.histogramLUT.restoreState(state["histogramLUT"])

        if "histogramLUT_viewbox" in state:
            self.histogramLUT.vb.setState(state["histogramLUT_viewbox"])


class PixelDetWidget(ImageWidget):
    sigClicked = QtCore.Signal(object, object)

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent, display=False, **kwargs)
        self.point = self.plot_view.plot([0], [0], symbolBrush=(200, 0, 0), symbol="+", symbolSize=25)

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
        self.point = self.plot_view.plot([x], [y], symbolBrush=(200, 0, 0), symbol="+", symbolSize=25)


class HistogramWidget(PlotWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.graphics_layout.useOpenGL(False)  # pyqtgraph broken
        self.num_terms = int(len(terms) / 2) if terms else 0

    def editor(self, parent, **kwargs):
        return HistEditor(parent=parent, **kwargs)

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
                self.plot[name] = self.plot_view.plot(
                    x,
                    y,
                    name=legend_name,
                    brush=attrs["Brush"],
                    stepMode=True,
                    fillLevel=0,
                )
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(x=x, y=y, brush=attrs["Brush"])


class Histogram2DWidget(ImageWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent, display=False, axis=True, **kwargs)

        self.lock = False
        self.view.setAspectLocked(False)

        self.xbins = None
        self.ybins = None
        self.transform = QtGui.QTransform()

    def cursor_hover_evt(self, evt):
        pos = evt[0]
        pos = self.view.mapSceneToView(pos)
        inverse = self.transform.inverted()[0]
        pos = inverse.map(pos)

        if self.imageItem.image is not None:
            shape = self.imageItem.image.shape

            if 0 <= pos.x() <= shape[0] and 0 <= pos.y() <= shape[1]:
                idxx = int(pos.x())
                idxy = int(pos.y())
                x = self.xbins[idxx]
                y = self.ybins[idxy]
                z = self.imageItem.image[idxx, idxy]
                self.pixel_value.setText(f"x={x:.5g}, y={y:.5g}, z={z:.5g}")

    def data_updated(self, data):
        xbins = self.terms["XBins"]
        ybins = self.terms["YBins"]
        counts = self.terms["Counts"]

        self.xbins = data[xbins]
        self.ybins = data[ybins]
        counts = data[counts]
        if self.log_scale_histogram:
            counts = np.log10(counts)
        xscale = (self.xbins[-1] - self.xbins[0]) / self.xbins.shape[0]
        yscale = (self.ybins[-1] - self.ybins[0]) / self.ybins.shape[0]

        self.imageItem.setImage(counts, autoLevels=self.auto_levels)
        self.transform = QtGui.QTransform(xscale, 0, 0, yscale, self.xbins[0], self.ybins[0])
        self.imageItem.setTransform(self.transform)


class ScatterWidget(PlotWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.num_terms = int(len(terms) / 2) if terms else 0

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))

            # buffered rows may contain None (e.g. a point whose paired series wasn't active
            # that event); convert to a plain float array so pyqtgraph gets NaN instead of an
            # object-dtype array mixing None with numbers, which it can't plot.
            x = np.asarray(data[x], dtype=float)
            y = np.asarray(data[y], dtype=float)

            if name not in self.plot:
                symbol, color = symbols_colors[i]
                idx = f"trace.{i}"
                legend_name = self.update_legend_layout(idx, name, symbol=symbol, color=color, style="None")
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                self.plot[name] = self.plot_view.plot(x=x, y=y, name=legend_name, pen=None, **attrs["point"])
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(x=x, y=y, **attrs["point"])


class WaveformWidget(PlotWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        i = len(self.plot)

        for term, name in self.terms.items():
            if name not in data:
                continue

            if not type(data[name]) is np.array:
                data[name] = np.array(data[name], dtype=float)

            if name not in self.plot:
                _, color = symbols_colors[i]
                idx = f"trace.{i}"
                i += 1
                legend_name = self.update_legend_layout(idx, name, symbol="None", line_color=color)
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                self.plot[name] = self.plot_view.plot(
                    y=data[name], name=legend_name, pen=attrs["pen"], **attrs["point"]
                )
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(y=data[name], **attrs["point"])


class MultiWaveformWidget(PlotWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)

    def data_updated(self, data):
        name = self.terms["In"]
        waveforms = data[name]
        for chan in range(waveforms.shape[0] if isinstance(data, np.ndarray) else len(waveforms)):
            cname = f"{name}:{chan}"
            if cname not in self.plot:
                _, color = symbols_colors[chan]
                idx = f"trace.{chan}"
                legend_name = self.update_legend_layout(idx, cname, symbol="None", line_color=color)
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[cname] = attrs
                self.plot[cname] = self.plot_view.plot(
                    y=waveforms[chan],
                    name=legend_name,
                    pen=attrs["pen"],
                    **attrs["point"],
                )
            else:
                attrs = self.trace_attrs[cname]
                self.plot[cname].setData(y=waveforms[chan], **attrs["point"])


class LineWidget(PlotWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.num_terms = int(len(terms) / 2) if terms else 0

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))

            if x not in data or y not in data:
                continue

            # buffered rows may contain None (e.g. a point whose paired series wasn't active
            # that event, as with TimePlot/LinePlot inputs marked optional) -- drop those before
            # sorting, since None can't be compared against a number, and a hole here would
            # otherwise break the line into disconnected segments.
            pairs = [(a, b) for a, b in zip(data[x], data[y]) if a is not None and b is not None]
            if not pairs:
                continue
            # sort the data using the x-axis, otherwise the drawn line is messed up
            x, y = zip(*sorted(pairs))

            if name not in self.plot:
                _, color = symbols_colors[i]
                idx = f"trace.{i}"
                i += 1
                legend_name = self.update_legend_layout(idx, name, symbol="None", line_color=color)
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                self.plot[name] = self.plot_view.plot(x=x, y=y, name=legend_name, pen=attrs["pen"], **attrs["point"])
            else:
                attrs = self.trace_attrs[name]
                self.plot[name].setData(x=x, y=y, **attrs["point"])


class TimeWidget(LineWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.graphics_layout.useOpenGL(False)
        ax = pg.DateAxisItem(orientation="bottom")
        self.plot_view.setAxisItems({"bottom": ax})


class CategoryWidget(PlotWidget):
    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(topics, terms, addr, parent=parent, **kwargs)
        self.y = {}  # { name : height }

    def data_updated(self, data):
        i = len(self.plot)

        for term, name in self.terms.items():
            if name not in data:
                continue

            arr = np.array(data[name], dtype=bool)
            data[name] = np.arange(0, len(arr))[arr]

            if name not in self.plot:
                self.y[name] = i
                symbol, color = symbols_colors[i]
                idx = f"trace.{i}"
                i += 1
                self.update_legend_layout(idx, name, symbol=symbol, style="None")
                attrs = self.legend_editors[idx].attrs
                self.trace_attrs[name] = attrs
                y = np.ones(len(data[name])) * self.y[name]
                self.plot[name] = self.plot_view.plot(x=data[name], y=y, pen=attrs["pen"], **attrs["point"])
            else:
                attrs = self.trace_attrs[name]
                y = np.ones(len(data[name])) * self.y[name]
                self.plot[name].setData(x=data[name], y=y, **attrs["point"])

        left_axis = self.plot_view.getAxis("left")
        left_axis.setTicks([list(enumerate(self.y.keys()))])
        self.plot_view.setYRange(-0.5, len(self.y) - 0.5)
