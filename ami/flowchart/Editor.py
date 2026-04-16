import importlib
import logging
import os
import sys

from pyqtgraph import FileDialog, dockarea
from pyqtgraph.debug import printExc
from qtpy import QtCore, QtGui, QtWidgets

from ami.flowchart.library.Editors import STYLE
from ami.flowchart.NodeLibrary import isNodeClass
from ami.flowchart.NodeStateWidget import NodeStateWidget

try:
    from qtconsole.inprocess import QtInProcessKernelManager  # noqa
    from qtconsole.rich_jupyter_widget import RichJupyterWidget  # noqa

    HAS_QTCONSOLE = True
except ImportError:
    HAS_QTCONSOLE = False


logger = logging.getLogger(__name__)


class UnifiedLibraryEditor(QtWidgets.QWidget):
    """Unified editor for managing both node library (.py) and subgraph library (.fc)"""

    sigApplyClicked = QtCore.Signal()
    sigReloadClicked = QtCore.Signal(object)

    def __init__(self, ctrlWidget, nodeLibrary, subgraphLibrary):
        super().__init__()

        self.setWindowTitle("Manage Libraries")

        # Node library data
        self.modules = {}  # {mod : [nodes]}
        self.node_loaded = {}
        self.node_paths = set()

        # Subgraph library data
        self.subgraphs = {}  # {name: template}
        self.subgraph_loaded = {}
        self.subgraph_paths = set()

        self.ctrl = ctrlWidget
        self.nodeLibrary = nodeLibrary
        self.subgraphLibrary = subgraphLibrary

        self.layout = QtWidgets.QGridLayout(self)

        # Buttons
        self.loadBtn = QtWidgets.QPushButton("Load Files", parent=self)
        self.loadBtn.clicked.connect(self.loadFile)

        self.loadDirBtn = QtWidgets.QPushButton("Load Directory", parent=self)
        self.loadDirBtn.clicked.connect(self.loadDirectory)

        # Trees
        self.nodeTree = QtWidgets.QTreeWidget(parent=self)
        self.nodeTree.setHeaderHidden(False)
        self.nodeTree.setHeaderLabel("Nodes (.py)")

        self.subgraphTree = QtWidgets.QTreeWidget(parent=self)
        self.subgraphTree.setHeaderHidden(False)
        self.subgraphTree.setHeaderLabel("Subgraphs (.fc)")

        self.applyBtn = QtWidgets.QPushButton("Apply", parent=self)
        self.applyBtn.clicked.connect(self.applyClicked)

        # Layout
        self.layout.addWidget(self.loadBtn, 0, 0, 1, 2)
        self.layout.addWidget(self.loadDirBtn, 1, 0, 1, 2)
        self.layout.addWidget(self.nodeTree, 2, 0, 1, 1)
        self.layout.addWidget(self.subgraphTree, 2, 1, 1, 1)
        self.layout.addWidget(self.applyBtn, 3, 0, 1, 2)

    def loadFile(self):
        file_filters = "Python and Flowchart files (*.py *.fc);;Python files (*.py);;Flowchart files (*.fc)"
        self.fileDialog = FileDialog(None, "Load Libraries", None, file_filters)
        self.fileDialog.setFileMode(FileDialog.ExistingFiles)
        self.fileDialog.filesSelected.connect(self.fileDialogFilesSelected)
        self.fileDialog.show()

    def loadDirectory(self):
        self.fileDialog = FileDialog(None, "Load Libraries", None, None)
        self.fileDialog.setFileMode(FileDialog.Directory)
        self.fileDialog.filesSelected.connect(self.fileDialogDirectorySelected)
        self.fileDialog.show()

    def fileDialogDirectorySelected(self, pths):
        py_files = []
        fc_files = []
        for pth in pths:
            for root, dirs, filenames in os.walk(pth):
                for filename in filenames:
                    full_path = os.path.join(root, filename)
                    if filename.endswith((".py", ".PY")) and not filename.startswith("_"):
                        py_files.append(full_path)
                    elif filename.endswith((".fc", ".FC")):
                        fc_files.append(full_path)

        # Process both types
        self.loadPythonFiles(py_files)
        self.loadFlowchartFiles(fc_files)

    def fileDialogFilesSelected(self, pths):
        # Separate by extension
        py_files = [p for p in pths if p.endswith((".py", ".PY"))]
        fc_files = [p for p in pths if p.endswith((".fc", ".FC"))]

        self.loadPythonFiles(py_files)
        self.loadFlowchartFiles(fc_files)

    def loadPythonFiles(self, pths):
        """Load .py files as node modules"""
        if not pths:
            return

        dirs = set(map(os.path.dirname, pths))

        for pth in dirs:
            if pth not in sys.path:
                sys.path.append(pth)

        self.node_paths.update(pths)

        for mod in pths:
            mod_name = os.path.basename(mod)
            mod_name = os.path.splitext(mod_name)[0]
            mod = importlib.import_module(mod_name)

            if mod in self.modules:
                continue

            nodes = [getattr(mod, name) for name in dir(mod) if isNodeClass(getattr(mod, name))]

            if not nodes:
                continue

            self.modules[mod] = nodes
            self.node_loaded[mod] = False

            parent = QtWidgets.QTreeWidgetItem(self.nodeTree, [mod.__name__])
            parent.mod = mod
            for node in nodes:
                child = QtWidgets.QTreeWidgetItem(parent, [node.__name__])
                child.mod = mod

            self.nodeTree.expandAll()

    def loadFlowchartFiles(self, pths):
        """Load .fc files as subgraph templates"""
        if not pths:
            return

        import json

        from ami.flowchart.SubgraphLibrary import SubgraphTemplate

        self.subgraph_paths.update(pths)

        # Group subgraphs by source file for hierarchical tree
        from collections import defaultdict

        by_file = defaultdict(list)

        for pth in pths:
            with open(pth, "r") as f:
                state = json.load(f)

            # Extract metadata
            metadata = state.get("subgraph_metadata", {})
            name = metadata.get("name", os.path.splitext(os.path.basename(pth))[0])
            description = metadata.get("description", "")

            if name in self.subgraphs:
                continue

            # Create template
            template = SubgraphTemplate(name, description, state, source_file=pth)

            self.subgraphs[name] = template
            self.subgraph_loaded[name] = False

            # Group by source file (without extension)
            filename = os.path.basename(pth)
            file_key = os.path.splitext(filename)[0]
            by_file[file_key].append((name, template, pth))

        # Build hierarchical tree
        for file_key in sorted(by_file.keys()):
            # Create parent item for the file
            file_item = QtWidgets.QTreeWidgetItem(self.subgraphTree, [file_key])
            file_item.setToolTip(0, f"Subgraphs from {file_key}.fc")

            # Add child items for each subgraph in this file
            for name, template, pth in sorted(by_file[file_key], key=lambda x: x[0]):
                item = QtWidgets.QTreeWidgetItem(file_item, [name])
                item.setToolTip(0, template.description or pth)
                item.template = template

        self.subgraphTree.expandAll()

    def applyClicked(self):
        node_loaded = False
        subgraph_loaded = False

        # Load node modules
        for mod, nodes in self.modules.items():
            if self.node_loaded[mod]:
                continue
            for node in nodes:
                try:
                    self.nodeLibrary.addNodeType(node, [(mod.__name__,)])
                    node_loaded = True
                except Exception as e:
                    printExc(e)
            self.node_loaded[mod] = True

        # Load subgraph templates
        for name, template in self.subgraphs.items():
            if self.subgraph_loaded[name]:
                continue
            try:
                self.subgraphLibrary.addSubgraph(name, template, paths=[template.source_file])
                subgraph_loaded = True
            except Exception:
                printExc(f"Error adding subgraph {name}: (continuing anyway)")
            self.subgraph_loaded[name] = True

        # Update UI trees
        if node_loaded:
            self.ctrl.ui.clear_model(self.ctrl.ui.node_tree)
            self.ctrl.ui.create_model(self.ctrl.ui.node_tree, self.nodeLibrary.getLabelTree(rebuild=True))

        if subgraph_loaded:
            self.ctrl.ui.clear_model(self.ctrl.ui.subgraph_tree)

            # Group subgraphs by source file (hierarchical)
            from collections import defaultdict

            by_file = defaultdict(dict)

            for name in self.subgraphLibrary.getNames():
                template = self.subgraphLibrary.getSubgraph(name)

                # Determine file key
                if template.source_file:
                    filename = os.path.basename(template.source_file)
                    file_key = os.path.splitext(filename)[0]
                else:
                    file_key = "Root"

                # Add to hierarchical structure
                by_file[file_key][name] = template.description or ""

            self.ctrl.ui.create_model(self.ctrl.ui.subgraph_tree, dict(by_file), typ="SubgraphTree")

        self.sigApplyClicked.emit()

    def saveState(self):
        return {"node_paths": list(self.node_paths), "subgraph_paths": list(self.subgraph_paths)}

    def restoreState(self, state):
        if "node_paths" in state:
            self.loadPythonFiles(state["node_paths"])
        if "subgraph_paths" in state:
            self.loadFlowchartFiles(state["subgraph_paths"])
        # Backward compatibility
        if "paths" in state and "node_paths" not in state:
            self.loadPythonFiles(state["paths"])


# Alias for backward compatibility
LibraryEditor = UnifiedLibraryEditor


class SearchProxyModel(QtCore.QSortFilterProxyModel):

    def setFilterRegularExpression(self, pattern):
        if isinstance(pattern, str):
            pattern = QtCore.QRegularExpression(pattern, QtCore.QRegularExpression.PatternOption.CaseInsensitiveOption)
        super(SearchProxyModel, self).setFilterRegularExpression(pattern)

    def _accept_index(self, idx):
        if idx.isValid():
            text = idx.data(QtCore.Qt.DisplayRole)
            if self.filterRegularExpression().match(text).hasMatch():
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
    tree = QtWidgets.QTreeView(parent=parent)
    tree.setSortingEnabled(True)
    tree.sortByColumn(0, QtCore.Qt.AscendingOrder)
    tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
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
        self.gridLayout.setSpacing(0)

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

        # save as
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

        # reset
        self.actionReset = QtWidgets.QAction(parent)
        self.actionReset.setIconText("Reset")
        self.actionReset.setObjectName("actionReset")

        if HAS_QTCONSOLE:
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

        # inspector
        self.actionInspector = QtWidgets.QAction(parent)
        self.actionInspector.setIconText("Inspector")
        self.actionInspector.setObjectName("actionInspector")
        self.actionInspector.setCheckable(True)
        self.actionInspector.setChecked(False)  # Hidden by default

        self.toolBar.addAction(self.actionNew)
        self.toolBar.addAction(self.actionOpen)
        self.toolBar.addAction(self.actionSave)
        self.toolBar.addAction(self.actionSaveAs)

        if configure:
            self.toolBar.addAction(self.actionConfigure)
        self.toolBar.addAction(self.actionApply)
        self.toolBar.addAction(self.actionReset)
        if HAS_QTCONSOLE:
            self.toolBar.addAction(self.actionConsole)

        if configure:
            self.toolBar.insertSeparator(self.actionConfigure)
        else:
            self.toolBar.insertSeparator(self.actionApply)
        # self.toolBar.addAction(self.actionArrange)
        self.toolBar.addAction(self.actionHome)
        self.toolBar.addAction(self.actionPan)
        self.toolBar.addAction(self.actionSelect)
        self.toolBar.addAction(self.actionComment)
        self.toolBar.addAction(self.actionInspector)
        # self.toolBar.insertSeparator(self.actionArrange)
        self.toolBar.insertSeparator(self.actionHome)

        widget = self.toolBar.widgetForAction(self.actionApply)
        widget.setObjectName("actionApply")

        self.source_model = build_model()
        self.source_search = QtWidgets.QLineEdit()
        self.source_search.setPlaceholderText("Search Sources...")
        self.source_tree = build_tree(self.source_model, parent)

        self.node_model = build_model()
        self.node_search = QtWidgets.QLineEdit()
        self.node_search.setPlaceholderText("Search Operations...")
        self.node_tree = build_tree(self.node_model, parent)

        self.subgraph_model = build_model()
        self.subgraph_search = QtWidgets.QLineEdit()
        self.subgraph_search.setPlaceholderText("Search Subgraphs...")
        self.subgraph_tree = build_tree(self.subgraph_model, parent)

        self.gridLayout.addWidget(self.toolBar, 0, 0, 1, -1)

        self.node_dock = dockarea.Dock("nodes", size=(400, 1000))
        self.node_dock.hideTitleBar()
        self.node_dock.setOrientation("vertical")
        self.node_dock.addWidget(self.source_search, 1, 0, 1, 1)
        self.node_dock.addWidget(self.source_tree, 2, 0, 1, 1)
        self.node_dock.addWidget(self.node_search, 3, 0, 1, 1)
        self.node_dock.addWidget(self.node_tree, 4, 0, 1, 1)
        self.node_dock.addWidget(self.subgraph_search, 5, 0, 1, 1)
        self.node_dock.addWidget(self.subgraph_tree, 6, 0, 1, 1)
        chart.addDock(self.node_dock, "left")

        # Create state inspector dock on the right
        self.state_dock = dockarea.Dock("Node State", size=(400, 1000))
        self.state_widget = NodeStateWidget()
        self.state_dock.addWidget(self.state_widget)
        chart.addDock(self.state_dock, "right")
        self.state_dock.setVisible(False)  # Hidden by default

        # Connect inspector action to dock visibility
        self.actionInspector.toggled.connect(self.state_dock.setVisible)

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
        self.subgraph_search.textChanged.connect(self.subgraph_search_text_changed)

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

    def create_model(self, tree, data, typ="OperationTree"):
        model = tree.model().sourceModel()
        self.populate_tree(data, model.invisibleRootItem())
        tree.sortByColumn(0, QtCore.Qt.AscendingOrder)
        tree.expandAll()
        if typ in STYLE and not STYLE[typ].get("expand", True):
            tree.collapseAll()

    def clear_model(self, tree):
        model = tree.model().sourceModel()
        model.clear()

    def node_search_text_changed(self):
        self.search_text_changed(self.node_tree, self.node_model, self.node_search.text())

    def source_search_text_changed(self):
        self.search_text_changed(self.source_tree, self.source_model, self.source_search.text())

    def subgraph_search_text_changed(self):
        self.search_text_changed(self.subgraph_tree, self.subgraph_model, self.subgraph_search.text())

    def search_text_changed(self, tree, model, text):
        model.setFilterRegularExpression(text)
        tree.expandAll()

    def setPending(self, node):
        self.pending.add(node.name())
        self.toolBar.setStyleSheet("QToolButton#actionApply { background: lightgreen }")
        self.actionApply.setToolTip(f"Pending changes on: {self.pending}")

    def setPendingClear(self):
        self.pending = set()
        self.actionApply.setToolTip("")
        self.toolBar.setStyleSheet("QToolButton#actionApply { background: none }")
