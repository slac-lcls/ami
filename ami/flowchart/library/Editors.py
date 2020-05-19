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
