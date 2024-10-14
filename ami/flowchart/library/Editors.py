import os
import json
import numpy as np
import pyqtgraph as pg
from qtpy import QtGui, QtWidgets, QtCore
from ami.flowchart.library.WidgetGroup import generateUi


line_styles = {'None': QtCore.Qt.PenStyle.NoPen,
               'Solid': QtCore.Qt.PenStyle.SolidLine,
               'Dash': QtCore.Qt.PenStyle.DashLine,
               'Dot': QtCore.Qt.PenStyle.DotLine,
               'DashDot': QtCore.Qt.PenStyle.DashDotLine,
               'DashDotDot': QtCore.Qt.PenStyle.DashDotDotLine}


def load_style():
    style_path = os.path.expanduser("~/.config/ami/stylesheet.json")
    style = {}
    if os.path.exists(style_path):
        with open(style_path, 'r') as f:
            try:
                style = json.load(f)
            except json.decoder.JSONDecodeError as e:
                print(e)

    return style


class TraceEditor(QtWidgets.QWidget):

    def __init__(self, parent=None, widget=None, **kwargs):
        super().__init__(parent)

        if 'uiTemplate' in kwargs:
            self.uiTemplate = kwargs.pop('uiTemplate')
        else:
            self.uiTemplate = [
                # Point
                ('symbol', 'combo',
                 {'values': ['o', 't', 't1', 't2', 't3', 's', 'p', 'h', 'star', '+', 'd', 'None'],
                  'value': kwargs.get('symbol', 'o'), 'group': 'Point'}),
                ('Brush', 'color', {'value': kwargs.get('color', (0, 0, 255)), 'group': 'Point'}),
                ('Size', 'intSpin', {'min': 1, 'value': 14, 'group': 'Point'}),
                # Line
                ('color', 'color', {'group': 'Line', 'value': kwargs.get('line_color', (255, 255, 255))}),
                ('width', 'intSpin', {'min': 1, 'value': 1, 'group': 'Line'}),
                ('style', 'combo',
                 {'values': line_styles.keys(), 'value': kwargs.get('style', 'Solid'), 'group': 'Line'})]

        self.ui, self.stateGroup, self.ctrls, self.trace_attrs = generateUi(self.uiTemplate)

        if self.stateGroup:
            self.stateGroup.sigChanged.connect(self.state_changed)

        self.layout = QtWidgets.QGridLayout()
        self.setLayout(self.layout)

        self.layout.addWidget(self.ui, 0, 0, -1, 2)
        self.layout.setRowStretch(0, 1)
        self.layout.setColumnStretch(0, 1)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.useOpenGL(False)
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

        if 'restore' not in kwargs:
            style = load_style()
            name = widget.__class__.__name__
            if name in style:
                self.restoreState(style[name])

    def update_plot(self):
        point = self.trace_attrs['Point']

        symbol = point['symbol']
        if symbol == 'None':
            symbol = None

        point = {'symbol': symbol,
                 'symbolSize': point['Size'],
                 'symbolBrush': tuple(point['Brush'])}

        line = self.trace_attrs['Line']
        width = line['width']
        line = {'color': line['color'],
                'style': line_styles[line['style']]}

        # if pg.getConfigOption('useOpenGL'):
        line['width'] = width

        pen = pg.mkPen(**line)

        if 'Fill' in self.trace_attrs and self.trace_attrs['Fill']['Fill Annotation']:
            point['fillBrush'] = tuple(self.trace_attrs['Fill']['Brush'])
            point['fillLevel'] = 0

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

    def saveState(self):
        return self.stateGroup.state()

    def restoreState(self, state):
        self.stateGroup.setState(state)
        self.update_plot()


class HistEditor(TraceEditor):

    def __init__(self, parent=None, **kwargs):
        kwargs['uiTemplate'] = [('Brush', 'color', {'value': kwargs.get('color', (255, 0, 0))})]
        super().__init__(parent=parent, **kwargs)

    def update_plot(self):
        y = [0, 1, 2, 3, 4, 5, 4, 3, 2, 1]
        x = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        if self.trace is None:
            self.trace = self.plot_view.plot(x, y, stepMode=True, fillLevel=0, **self.trace_attrs)
        else:
            self.trace.setData(x=x, y=y, **self.trace_attrs)

        self.attrs = self.trace_attrs


class ChannelEditor(QtWidgets.QWidget):

    sigStateChanged = QtCore.Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.uiTemplate = [("num hits", "intSpin", {"value": 1, "min": 1}),
                           ("uniform parameters", "check"),
                           ("DLD", "check"),
                           ("cfd_wfbinbeg", "intSpin", {"value": 0, "min": 0}),
                           ("cfd_wfbinend", "intSpin", {"value": 1, "min": 1})]

        self.ui, self.stateGroup, self.ctrls, self.values = generateUi(self.uiTemplate)
        self.stateGroup.sigChanged.connect(self.state_changed)

        self.layout = QtWidgets.QFormLayout()
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

        params = ['all parameters', 'channel', 'delay', 'fraction', 'offset', 'polarity',
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

        channel_group = [('channel', 'text', {'values': f'Channel {channel}', 'group': name}),
                         ('delay', 'doubleSpin', {'group': name}),
                         ('fraction', 'doubleSpin', {'group': name}),
                         ('offset', 'doubleSpin', {'group': name}),
                         ('polarity', 'combo', {'values': ["Negative", "Positive"], 'group': name}),
                         ('sample_interval', 'doubleSpin', {'group': name}),
                         ('threshold', 'doubleSpin', {'group': name}),
                         ('timerange_low', 'doubleSpin', {'group': name}),
                         ('timerange_high', 'doubleSpin', {'group': name}),
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

        from_state = from_stateGroup.state()[from_channel]
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

        self.sigStateChanged.emit(attr, group, val)

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
                _, stateGroup, _, _ = self.add_channel(name=channel)
            else:
                _, stateGroup, _, _ = self.channel_groups[channel]

            self.values[channel] = state[channel]
            stateGroup.setState({channel: state[channel]})


class AnnotationEditor(TraceEditor):

    sigRemoved = QtCore.Signal(object)

    def __init__(self, parent=None, name="", **kwargs):
        uiTemplate = [
            ('name', 'text'),
            # from
            ('X', 'doubleSpin', {'value': 0, 'group': kwargs.get('from_', 'From')}),
            ('Y', 'doubleSpin', {'value': 0, 'group': kwargs.get('from_', 'From')}),
            # to
            ('X', 'doubleSpin', {'value': 0, 'group': kwargs.get('to', 'To')}),
            ('Y', 'doubleSpin', {'value': 0, 'group': kwargs.get('to', 'To')}),
            # Point
            ('symbol', 'combo',
             {'values': ['o', 't', 't1', 't2', 't3', 's', 'p', 'h', 'star', '+', 'd', 'None'],
              'value': kwargs.get('symbol', 'o'), 'group': 'Point'}),
            ('Brush', 'color', {'value': kwargs.get('color', (0, 0, 255)), 'group': 'Point'}),
            ('Size', 'intSpin', {'min': 1, 'value': 14, 'group': 'Point'}),
            # Line
            ('color', 'color', {'group': 'Line'}),
            ('width', 'intSpin', {'min': 1, 'value': 1, 'group': 'Line'}),
            ('style', 'combo',
             {'values': line_styles.keys(), 'value': kwargs.get('style', 'Solid'), 'group': 'Line'})
        ]

        if kwargs.get('fill', False):
            uiTemplate.extend([
                ('Fill Annotation', 'check', {'group': 'Fill', 'checked': True}),
                ('Brush', 'color', {'value': (255, 0, 0, 100), 'group': 'Fill'})
            ])

        super().__init__(parent=parent, uiTemplate=uiTemplate)
        self.name = name
        self.remove_btn = QtWidgets.QPushButton("Remove", self)
        self.remove_btn.clicked.connect(self.remove)
        self.ui.layout().addWidget(self.remove_btn)

    def trace_data(self):
        pass

    def update_plot(self):
        super().update_plot()
        pen = self.attrs['pen']
        point = self.attrs['point']
        x, y = self.trace_data()

        self.trace.setData(x, y, pen=pen, **point)

    def remove(self):
        self.sigRemoved.emit(self.name)


class LineEditor(AnnotationEditor):

    def __init__(self, parent=None, name="", **kwargs):
        super().__init__(parent, name, from_='From', to='To')

    def trace_data(self):
        x = [self.trace_attrs['From']['X'], self.trace_attrs['To']['X']]
        y = [self.trace_attrs['From']['Y'], self.trace_attrs['To']['Y']]
        return x, y


class RectEditor(AnnotationEditor):

    def __init__(self, parent=None, name="", **kwargs):
        super().__init__(parent, name, from_='Top Left', to='Bottom Right', symbol='None', fill=True)

    def trace_data(self):
        tl = (self.trace_attrs['Top Left']['X'], self.trace_attrs['Top Left']['Y'])
        br = (self.trace_attrs['Bottom Right']['X'], self.trace_attrs['Bottom Right']['Y'])

        x = [tl[0], br[0], br[0], tl[0], tl[0]]
        y = [tl[1], tl[1], br[1], br[1], tl[1]]
        return x, y


class CircleEditor(AnnotationEditor):

    def __init__(self, parent=None, name="", **kwargs):
        super().__init__(parent, name, from_='Center', to='Radius', symbol='None', fill=True)

    def trace_data(self):
        x = [self.trace_attrs['Center']['X'], self.trace_attrs['Radius']['X']]
        y = [self.trace_attrs['Center']['Y'], self.trace_attrs['Radius']['Y']]

        center = QtCore.QPointF(x[0], y[0])
        radius = QtGui.QVector2D(x[1], y[1]).distanceToPoint(QtGui.QVector2D(center))

        t = np.linspace(0, 2*np.pi, 100)
        x = center.x() + radius * np.sin(t)
        y = center.y() + radius * np.cos(t)
        return x, y


def pixmapFromBase64(base64):
    pixmap = QtGui.QPixmap()
    pixmap.loadFromData(QtCore.QByteArray.fromBase64(base64))
    # icon = QtGui.QIcon(pixmap)
    # return icon
    return pixmap


camera = b'iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAACXBIWXMAAA9hAAAPYQGoP6dpAAAAJXRFWHRkYXRlOmNyZWF0ZQAyMDEzLTEyLTI2VDIwOjA3OjM5KzAwOjAwzdqr/wAAACV0RVh0ZGF0ZTptb2RpZnkAMjAxMy0xMi0yNlQyMDowNzozOSswMDowMLyHE0MAAANwSURBVFiFxZdPS6pbFMZ/mfqmealBlEFNzrBBVEevgQg1ug6CE3SgCJo0KPwCUR8gaN5nkP6gXScHmoWBERcKHAhNFCP648GwQ6Um2rqDV1+8ve978V5IH9iT/ey1n8Xea629Vxd6uIHvwO/AIFAExGBdN9DTIv8LuAAiwEOddwDDzQZWYBt4q2/4GeOtrvEb8KXuhCb+4xOFP46TuhMattso3hjbDXH3Jx/7v12H24IacHbaDzvw3YIa7Z3CVwtqqnUKfVbUPG0Jm5ubzM/PA/D29kY+n2dgYABFUbQ1sViMnZ2dVrd0WjEuIiiKQiAQwOVyaXMzMzP4fD5KpRL39/d4vV4cDsc/7J6enkilUpTLZXp6eqhUKsTjccrlspFMGSDKhwi1Wq1ydnYmRigWi5JOpyWfz0symZRkMimvr686vlgsanMXFxdis9mMMiFq6IDX6zUVPz09lcXFRVEURVuvKIosLy/L1dWVTrwBn8/XugOBQMBQPBqNSn9/vwBit9vF4/GIx+MRu90ugPT19Uk8Hjd03u/3/38HisWiXF5eytDQkACytLQkuVxO46+vr2Vubk4Acbvd8vj4qLP3er2GDlhQXy1TNAIuGo2Sy+UIBoOEw2EGBwc1vlqtsr+/TzAY5OHhgd3dXZ293W5e647NTqA5oKampgSQRCJhGnCJREIAmZyc1PGBQMDoBI4smNSBhufDw8M4HA6y2SwAExMThnwzl81mDXkDOC0Y1IH393edcW9vLwCFQsF080KhoK1tQRygbDGarVQqOuPp6WkAwuGw6eYHBwcAjI+PtyIOUAODLPD7/bo0Ojk5EUCcTqdhqp2fn4vL5RJAjo+PdbxJDPy3OrCysqLVgFAoJJFIRCKRiIRCIa0WrK+vf04dSKfT8vz8LFtbW2K1WnWbdXd3y8bGhlSrVUPnzepAFxADvjVfzMjICJlMBpvNZhhwmUyGvb09UqkUtVqN0dFRVldXGRsb011yqVTi5uaG2dlZ7u7uPtJHXah14I+PzMLCAmtra7y8vOie3AbMnuRm/vb2lsPDQ2KxmI4H/gQ4Mjiado1jC2rT0Cn8tKB2LJ3CX9Dhb3nDk442JqC2SSdtFP+B2g4CaoP4pe5Eu5pTTbyrLn4PlOpzjfb8K9AHOFF/rzX06GqR/4kacM3tOQB/A606Lk9DGknwAAAAAElFTkSuQmCC'  # noqa: E501
