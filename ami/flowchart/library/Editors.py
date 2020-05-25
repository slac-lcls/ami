import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtWidgets, QtCore
from ami.flowchart.library.WidgetGroup import generateUi


line_styles = {'None': QtCore.Qt.PenStyle.NoPen,
               'Solid': QtCore.Qt.PenStyle.SolidLine,
               'Dash': QtCore.Qt.PenStyle.DashLine,
               'Dot': QtCore.Qt.PenStyle.DotLine,
               'DashDot': QtCore.Qt.PenStyle.DashDotLine,
               'DashDotDot': QtCore.Qt.PenStyle.DashDotDotLine}


class TraceEditor(QtWidgets.QWidget):

    def __init__(self, node=None, parent=None, **kwargs):
        super().__init__(parent)

        if 'uiTemplate' in kwargs:
            self.uiTemplate = kwargs.pop('uiTemplate')
        else:
            self.uiTemplate = [
                # Point
                ('symbol', 'combo',
                 {'values': ['o', 't', 't1', 't2', 't3', 's', 'p', 'h', 'star', '+', 'd', 'None'],
                  'value': kwargs.get('symbol', 'o'), 'group': 'Point'}),
                ('Brush', 'color', {'value': kwargs.get('color', (255, 0, 0)), 'group': 'Point'}),
                ('Size', 'intSpin', {'min': 1, 'value': 14, 'group': 'Point'}),
                # Line
                ('color', 'color', {'group': 'Line'}),
                ('width', 'intSpin', {'min': 1, 'value': 1, 'group': 'Line'}),
                ('style', 'combo',
                 {'values': line_styles.keys(), 'value': kwargs.get('style', 'Solid'), 'group': 'Line'})]

        self.ui, self.stateGroup, self.ctrls, self.trace_attrs = generateUi(self.uiTemplate)

        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

        self.node = node

        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)

        self.layout.addWidget(self.ui, 0, 0, -1, 2)
        self.layout.setRowStretch(0, 1)
        self.layout.setColumnStretch(0, 1)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setFixedSize(200, 100)

        self.plot_view = self.plot_widget.addPlot()
        self.plot_view.setMenuEnabled(False)
        # self.plot_view.addLegend()

        ax = self.plot_view.getAxis('bottom')
        ay = self.plot_view.getAxis('left')
        self.plot_view.vb.removeItem(ax)
        self.plot_view.vb.removeItem(ay)
        self.plot_view.vb.setMouseEnabled(False, False)

        self.trace = None
        self.attrs = None
        self.update_plot()

        self.layout.addWidget(self.plot_widget, 0, 2, -1, -1)

    def update_plot(self):

        point = self.trace_attrs['Point']

        symbol = point['symbol']
        if symbol == 'None':
            symbol = None

        point = {'symbol': symbol,
                 'symbolSize': point['Size'],
                 'symbolBrush': tuple(point['Brush'])}

        line = self.trace_attrs['Line']
        line = {'color': line['color'],
                'width': line['width'],
                'style': line_styles[line['style']]}

        pen = pg.mkPen(**line)

        if self.trace is None:
            self.trace = self.plot_view.plot([0, 1, 2, 3], [0, 0, 0, 0], pen=pen, **point)
        else:
            self.trace.setData([0, 1, 2, 3], [0, 0, 0, 0], pen=pen, **point)

        self.attrs = {'pen': pen, 'point': point}

    def state_changed(self, *args, **kwargs):
        attr, group, val = args

        if group:
            self.trace_attrs[group][attr] = val
        else:
            self.trace_attrs[attr] = val

        self.update_plot()

        if self.node:
            self.node.sigStateChanged.emit(self.node)

    def saveState(self):
        return self.stateGroup.state()

    def restoreState(self, state):
        self.stateGroup.setState(state)
        self.update_plot()


class HistEditor(TraceEditor):

    def __init__(self, node=None, parent=None, **kwargs):
        kwargs['uiTemplate'] = [('brush', 'color', {'value': kwargs.get('color', (255, 0, 0))})]
        super().__init__(node=node, parent=parent, **kwargs)

    def update_plot(self):
        y = [0, 1, 2, 3, 4, 5, 4, 3, 2, 1]
        x = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        if self.trace is None:
            self.trace = self.plot_view.plot(x, y, stepMode=True, fillLevel=0, **self.trace_attrs)
        else:
            self.trace.setData(x=x, y=y, **self.trace_attrs)

        self.attrs = self.trace_attrs


class ChannelEditor(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.uiTemplate = [("num hits", "intSpin", {"value": 1, "min": 1}),
                           ("uniform parameters", "check"),
                           ("dld", "check")]

        self.ui, self.stateGroup, self.ctrls, self.values = generateUi(self.uiTemplate)
        self.stateGroup.sigChanged.connect(self.state_changed)

        self.layout = QtGui.QFormLayout()
        self.setLayout(self.layout)

        self.layout.addRow(self.ui)

        addBtn = QtWidgets.QPushButton("Add", parent=self)
        addBtn.clicked.connect(self.add_channel)

        removeBtn = QtWidgets.QPushButton("Remove", parent=self)
        removeBtn.clicked.connect(self.remove_channel)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(addBtn)
        hbox.addWidget(removeBtn)
        self.layout.addRow(hbox)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(QtWidgets.QLabel("Copy", parent=self))

        params = ['all parameters', 'name', 'delay', 'fraction', 'offset', 'polarity',
                  'sample_interval', 'threshold', 'timerange_high', 'timerange_low', 'walk']

        self.copy_param = QtWidgets.QComboBox()
        for p in params:
            self.copy_param.addItem(p)

        hbox.addWidget(self.copy_param)
        hbox.addWidget(QtWidgets.QLabel("from", parent=self))

        self.from_channel = QtWidgets.QComboBox(parent=self)
        hbox.addWidget(self.from_channel)

        hbox.addWidget(QtWidgets.QLabel("to", parent=self))
        self.to_channel = QtWidgets.QComboBox(parent=self)
        hbox.addWidget(self.to_channel)

        copyBtn = QtWidgets.QPushButton("Copy", parent=self)
        copyBtn.clicked.connect(self.copy_channel)
        hbox.addWidget(copyBtn)

        self.layout.addRow(hbox)

        self.channel_groups = {}
        self.add_channel()

    def add_channel(self, name=None):
        channel = len(self.channel_groups)

        if not name:
            name = f"Channel {channel}"

        channel_group = [('name', 'text', {'values': f'Channel {channel}', 'group': name}),
                         ('delay', 'doubleSpin', {'group': name}),
                         ('fraction', 'doubleSpin', {'group': name}),
                         ('offset', 'doubleSpin', {'group': name}),
                         ('polarity', 'combo', {'values': ["Negative"], 'group': name}),
                         ('sample_interval', 'doubleSpin', {'group': name}),
                         ('threshold', 'doubleSpin', {'group': name}),
                         ('timerange_high', 'doubleSpin', {'group': name}),
                         ('timerange_low', 'doubleSpin', {'group': name}),
                         ('walk', 'doubleSpin', {'group': name})]

        self.channel_groups[name] = generateUi(channel_group)
        ui, stateGroup, ctrls, attrs = self.channel_groups[name]
        self.values[name] = attrs[name]

        self.layout.addWidget(ui)
        stateGroup.sigChanged.connect(self.state_changed)

        self.from_channel.addItem(name)
        self.to_channel.addItem(name)

        return ui, stateGroup, ctrls, attrs

    def remove_channel(self):
        channel = len(self.channel_groups)-1
        if channel == 0:
            return

        self.from_channel.removeItem(channel)
        self.to_channel.removeItem(channel)

        channel = f"Channel {channel}"
        ui, stateGroup, ctrls, attrs = self.channel_groups[channel]

        self.layout.removeWidget(ui)
        ctrls[channel]['groupbox'].deleteLater()
        del self.channel_groups[channel]

    def copy_channel(self):
        from_channel = self.from_channel.currentText()
        to_channel = self.to_channel.currentText()

        param = self.copy_param.currentText()

        _, from_stateGroup, _, _ = self.channel_groups[from_channel]
        _, to_stateGroup, _, _ = self.channel_groups[to_channel]

        from_state = from_stateGroup.state()
        if param == "all parameters":
            to_stateGroup.setState({to_channel: from_state})
        else:
            to_state = to_stateGroup.state()
            to_state[param] = from_state[param]
            to_stateGroup.setState(to_state)

    def state_changed(self, *args, **kwargs):
        attr, group, val = args

        if group:
            self.values[group][attr] = val
        else:
            self.values[attr] = val

    def saveState(self):
        state = self.stateGroup.state()

        state['channels'] = len(self.channel_groups)

        for name, group in self.channel_groups.items():
            _, stateGroup, _, _ = group
            state[name] = stateGroup.state()[name]

        return state

    def restoreState(self, state):
        self.stateGroup.setState(state)

        channels = state['channels']

        for channel in range(0, channels):
            channel = f"Channel {channel}"
            if channel not in self.channel_groups:
                _, stateGroup, _, vals = self.add_channel(name=channel)
            else:
                _, stateGroup, _, vals = self.channel_groups[channel]

            self.values[channel] = vals[channel]
            stateGroup.setState({channel: state[channel]})
