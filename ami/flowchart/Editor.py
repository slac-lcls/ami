import os
import sys
import importlib
import logging
import pyqtgraph as pg
from pyqtgraph.debug import printExc
from pyqtgraph import dockarea, FileDialog
from pyqtgraph.Qt import QtGui, QtWidgets, QtCore
from ami.flowchart.NodeLibrary import isNodeClass


logger = logging.getLogger(__name__)


class LibraryEditor(QtWidgets.QWidget):

    sigApplyClicked = QtCore.Signal()
    sigReloadClicked = QtCore.Signal(object)

    def __init__(self, ctrlWidget, library):
        super().__init__()

        self.setWindowTitle("Manage Library")

        self.modules = {}  # {mod : [nodes]}
        self.paths = set()

        self.ctrl = ctrlWidget
        self.library = library

        self.layout = QtWidgets.QGridLayout(self)

        self.loadBtn = QtWidgets.QPushButton("Load Modules", parent=self)
        self.loadBtn.clicked.connect(self.loadFile)

        # self.reloadBtn = QtWidgets.QPushButton("Reload Selected Modules", parent=self)
        # self.reloadBtn.clicked.connect(self.reloadFile)

        self.tree = QtWidgets.QTreeWidget(parent=self)
        self.tree.setHeaderHidden(True)

        self.applyBtn = QtWidgets.QPushButton("Apply", parent=self)
        self.applyBtn.clicked.connect(self.applyClicked)

        self.layout.addWidget(self.loadBtn, 1, 1, 1, -1)
        # self.layout.addWidget(self.reloadBtn, 1, 2, 1, 1)
        self.layout.addWidget(self.tree, 2, 1, 1, -1)
        self.layout.addWidget(self.applyBtn, 3, 1, 1, -1)

    def loadFile(self):
        file_filters = "*.py"
        self.fileDialog = FileDialog(None, "Load Nodes", None, file_filters)
        self.fileDialog.setFileMode(FileDialog.ExistingFiles)
        self.fileDialog.filesSelected.connect(self.fileDialogFilesSelected)
        self.fileDialog.show()

    def fileDialogFilesSelected(self, pths):
        dirs = set(map(os.path.dirname, pths))

        for pth in dirs:
            if pth not in sys.path:
                sys.path.append(pth)

        self.paths.update(pths)

        for mod in pths:
            mod = os.path.basename(mod)
            mod = os.path.splitext(mod)[0]
            mod = importlib.import_module(mod)

            if mod in self.modules:
                continue

            nodes = [getattr(mod, name) for name in dir(mod) if isNodeClass(getattr(mod, name))]

            if not nodes:
                continue

            self.modules[mod] = nodes

            parent = QtWidgets.QTreeWidgetItem(self.tree, [mod.__name__])
            parent.mod = mod
            for node in nodes:
                child = QtWidgets.QTreeWidgetItem(parent, [node.__name__])
                child.mod = mod

            self.tree.expandAll()

    def reloadFile(self):
        mods = set()
        for item in self.tree.selectedItems():
            mods.add(item.mod)

        for mod in mods:
            pg.reload.reload(mod)

        self.sigReloadClicked.emit(mods)

    def applyClicked(self):
        loaded = False

        for mod, nodes in self.modules.items():
            for node in nodes:
                try:
                    self.library.addNodeType(node, [(mod.__name__, )])
                    loaded = True
                except Exception as e:
                    printExc(e)

        if not loaded:
            return

        self.ctrl.ui.clear_model(self.ctrl.ui.node_tree)
        self.ctrl.ui.create_model(self.ctrl.ui.node_tree, self.library.getLabelTree(rebuild=True))

        self.sigApplyClicked.emit()

    def saveState(self):
        return {'paths': list(self.paths)}

    def restoreState(self, state):
        self.fileDialogFilesSelected(state['paths'])


class SearchProxyModel(QtCore.QSortFilterProxyModel):

    def setFilterRegExp(self, pattern):
        if isinstance(pattern, str):
            pattern = QtCore.QRegExp(
                pattern, QtCore.Qt.CaseInsensitive,
                QtCore.QRegExp.FixedString)
        super(SearchProxyModel, self).setFilterRegExp(pattern)

    def _accept_index(self, idx):
        if idx.isValid():
            text = idx.data(QtCore.Qt.DisplayRole)
            if self.filterRegExp().indexIn(text) >= 0:
                return True
            for row in range(idx.model().rowCount(idx)):
                if self._accept_index(idx.model().index(row, 0, idx)):
                    return True
        return False

    def filterAcceptsRow(self, sourceRow, sourceParent):
        idx = self.sourceModel().index(sourceRow, 0, sourceParent)
        return self._accept_index(idx)


def build_model():
    model = SearchProxyModel()
    model.setSourceModel(QtGui.QStandardItemModel())
    model.setDynamicSortFilter(True)
    model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
    return model


def build_tree(model=None, parent=None):
    tree = QtGui.QTreeView(parent=parent)
    tree.setSortingEnabled(True)
    tree.sortByColumn(0, QtCore.Qt.AscendingOrder)
    tree.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
    tree.setHeaderHidden(True)
    tree.setRootIsDecorated(True)
    tree.setUniformRowHeights(True)
    if model:
        tree.setModel(model)
    tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    tree.setDragEnabled(True)
    return tree


class Ui_Toolbar(object):
    def setupUi(self, parent=None, chart=None, configure=False):
        self.gridLayout = QtWidgets.QGridLayout(parent)

        self.toolBar = QtWidgets.QToolBar(parent)
        self.toolBar.setObjectName("toolBar")

        # new
        self.actionNew = QtWidgets.QAction(parent)
        self.actionNew.setIconText("New")
        self.actionNew.setObjectName("actionNew")

        # open
        self.actionOpen = QtWidgets.QAction(parent)
        self.actionOpen.setIconText("Open")
        self.actionOpen.setObjectName("actionOpen")

        # save
        self.actionSave = QtWidgets.QAction(parent)
        self.actionSave.setIconText("Save")
        self.actionSave.setObjectName("actionSave")

        # save
        self.actionSaveAs = QtWidgets.QAction(parent)
        self.actionSaveAs.setIconText("Save As")
        self.actionSaveAs.setObjectName("actionSaveAs")

        # apply
        self.actionApply = QtWidgets.QAction(parent)
        self.actionApply.setIconText("Apply")
        self.actionApply.setObjectName("actionApply")

        # configure
        if configure:
            self.actionConfigure = QtWidgets.QAction(parent)
            self.actionConfigure.setIconText("Configure")
            self.actionConfigure.setObjectName("actionConfigure")

        # profile
        # self.actionProfiler = QtWidgets.QAction(parent)
        # self.actionProfiler.setIconText("Profiler")
        # self.actionProfiler.setObjectName("actionProfiler")

        # reset
        self.actionReset = QtWidgets.QAction(parent)
        self.actionReset.setIconText("Reset")
        self.actionReset.setObjectName("actionReset")

        # console
        self.actionConsole = QtWidgets.QAction(parent)
        self.actionConsole.setIconText("Console")
        self.actionConsole.setObjectName("actionConsole")

        # Arrange
        self.actionArrange = QtWidgets.QAction(parent)
        self.actionArrange.setIconText("Arrange")
        self.actionArrange.setObjectName("actionArrange")

        # home
        self.actionHome = QtWidgets.QAction(parent)
        self.actionHome.setIconText("Home")
        self.actionHome.setObjectName("actionHome")

        self.navGroup = QtWidgets.QActionGroup(parent)

        # pan
        self.actionPan = QtWidgets.QAction(parent)
        self.actionPan.setIconText("Pan")
        self.actionPan.setObjectName("actionPan")
        self.actionPan.setCheckable(True)
        self.actionPan.setChecked(True)
        self.navGroup.addAction(self.actionPan)

        # select
        self.actionSelect = QtWidgets.QAction(parent)
        self.actionSelect.setIconText("Select")
        self.actionSelect.setObjectName("actionSelect")
        self.actionSelect.setCheckable(True)
        self.navGroup.addAction(self.actionSelect)

        # comment
        self.actionComment = QtWidgets.QAction(parent)
        self.actionComment.setIconText("Comment")
        self.actionComment.setObjectName("actionComment")
        self.actionComment.setCheckable(True)
        self.navGroup.addAction(self.actionComment)

        self.toolBar.addAction(self.actionNew)
        self.toolBar.addAction(self.actionOpen)
        self.toolBar.addAction(self.actionSave)
        self.toolBar.addAction(self.actionSaveAs)

        if configure:
            self.toolBar.addAction(self.actionConfigure)
        self.toolBar.addAction(self.actionApply)
        self.toolBar.addAction(self.actionReset)
        self.toolBar.addAction(self.actionConsole)
        # self.toolBar.addAction(self.actionProfiler)
        if configure:
            self.toolBar.insertSeparator(self.actionConfigure)
        else:
            self.toolBar.insertSeparator(self.actionApply)
        # self.toolBar.addAction(self.actionArrange)
        self.toolBar.addAction(self.actionHome)
        self.toolBar.addAction(self.actionPan)
        self.toolBar.addAction(self.actionSelect)
        self.toolBar.addAction(self.actionComment)
        # self.toolBar.insertSeparator(self.actionArrange)
        self.toolBar.insertSeparator(self.actionHome)

        widget = self.toolBar.widgetForAction(self.actionApply)
        widget.setObjectName("actionApply")

        self.source_model = build_model()
        self.source_search = QtGui.QLineEdit()
        self.source_search.setPlaceholderText('Search Sources...')
        self.source_tree = build_tree(self.source_model, parent)

        self.node_model = build_model()
        self.node_search = QtGui.QLineEdit()
        self.node_search.setPlaceholderText('Search Operations...')
        self.node_tree = build_tree(self.node_model, parent)

        self.gridLayout.addWidget(self.toolBar, 0, 0, 1, -1)

        self.node_dock = dockarea.Dock('nodes', size=(400, 1000))
        self.node_dock.hideTitleBar()
        self.node_dock.setOrientation('vertical')
        self.node_dock.addWidget(self.source_search, 1, 0, 1, 1)
        self.node_dock.addWidget(self.source_tree, 2, 0, 1, 1)
        self.node_dock.addWidget(self.node_search, 3, 0, 1, 1)
        self.node_dock.addWidget(self.node_tree, 4, 0, 1, 1)
        chart.addDock(self.node_dock, 'left')

        self.rateLbl = QtWidgets.QLabel("")
        self.rateLbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)

        self.libraryConfigure = QtWidgets.QPushButton("Manage Library")

        self.gridLayout.addWidget(chart, 1, 1, 1, -1)
        self.gridLayout.addWidget(self.libraryConfigure, 2, 1)
        self.gridLayout.addWidget(self.rateLbl, 2, 2, 1, -1)

        self.gridLayout.setRowStretch(1, 10)
        self.gridLayout.setColumnStretch(2, 10)

        self.node_search.textChanged.connect(self.node_search_text_changed)
        self.source_search.textChanged.connect(self.source_search_text_changed)

        self.pending = set()

    def populate_tree(self, children, parent):
        for child in sorted(children):
            if type(children[child]) is str:
                node = QtGui.QStandardItem(child)
                node.setToolTip(children[child])
                recurse = False
            else:
                recurse = True
                node = QtGui.QStandardItem(child)
            parent.appendRow(node)

            if recurse:
                self.populate_tree(children[child], node)

    def create_model(self, tree, data):
        model = tree.model().sourceModel()
        self.populate_tree(data, model.invisibleRootItem())
        tree.sortByColumn(0, QtCore.Qt.AscendingOrder)
        tree.expandAll()

    def clear_model(self, tree):
        model = tree.model().sourceModel()
        model.clear()

    def node_search_text_changed(self):
        self.search_text_changed(self.node_tree, self.node_model, self.node_search.text())

    def source_search_text_changed(self):
        self.search_text_changed(self.source_tree, self.source_model, self.source_search.text())

    def search_text_changed(self, tree, model, text):
        model.setFilterRegExp(text)
        tree.expandAll()

    def setPending(self, node):
        self.pending.add(node.name())
        self.toolBar.setStyleSheet("QToolButton#actionApply { background: lightgreen }")
        self.actionApply.setToolTip(f"Pending changes on: {self.pending}")

    def setPendingClear(self):
        self.pending = set()
        self.actionApply.setToolTip("")
        self.toolBar.setStyleSheet("QToolButton#actionApply { background: none }")
