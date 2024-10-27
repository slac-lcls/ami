from pyqtgraph import FileDialog
from qtpy import QtCore, QtWidgets


class SourceConfiguration(QtWidgets.QWidget):

    sigApply = QtCore.Signal(object)  # src_cfg dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure")
        self.formLayout = QtWidgets.QFormLayout(self)

        self.interval = QtWidgets.QDoubleSpinBox(self)
        self.interval.setValue(0.01)
        self.formLayout.addRow("Interval", self.interval)

        self.init_time = QtWidgets.QDoubleSpinBox(self)
        self.init_time.setValue(0.5)
        self.formLayout.addRow("Init Time", self.init_time)

        self.hb_period = QtWidgets.QSpinBox(self)
        self.hb_period.setValue(10)
        self.formLayout.addRow("Heartbeat Period", self.hb_period)

        self.source_type = QtWidgets.QComboBox(self)
        self.source_type.addItem("hdf5")
        self.source_type.addItem("psana")
        self.formLayout.addRow("Source Type", self.source_type)

        self.repeat = QtWidgets.QCheckBox(self)
        self.repeat.setChecked(True)
        self.formLayout.addRow("Repeat", self.repeat)

        self.files = []
        self.fileListView = QtWidgets.QListView(self)
        self.fileListView.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.fileListModel = QtCore.QStringListModel(self.files)
        self.fileListView.setModel(self.fileListModel)
        self.formLayout.addRow(self.fileListView)

        self.horizontalLayout = QtWidgets.QHBoxLayout()

        self.addBtn = QtWidgets.QPushButton("Add", parent=self)
        self.addBtn.clicked.connect(self.addFile)
        self.horizontalLayout.addWidget(self.addBtn)

        self.removeBtn = QtWidgets.QPushButton("Remove", parent=self)
        self.removeBtn.clicked.connect(self.removeFiles)
        self.horizontalLayout.addWidget(self.removeBtn)

        self.applyBtn = QtWidgets.QPushButton("Apply", parent=self)
        self.applyBtn.clicked.connect(self.applyClicked)
        self.horizontalLayout.addWidget(self.applyBtn)

        self.formLayout.addRow(self.horizontalLayout)

    def addFile(self):
        file_filters = self.source_type.currentText()
        if file_filters == "hdf5":
            file_filters = "*.h5 *.hdf5"
        elif file_filters == "psana":
            file_filters = "*.xtc2"

        self.fileDialog = FileDialog(None, "Load Data", None, file_filters)
        self.fileDialog.setFileMode(FileDialog.ExistingFiles)
        self.fileDialog.filesSelected.connect(self.fileDialogFilesSelected)
        self.fileDialog.show()

    def removeFiles(self):
        selectionModel = self.fileListView.selectionModel()
        for pth in selectionModel.selection().indexes():
            pth = pth.data()
            self.files.remove(pth)

        self.fileListModel.setStringList(self.files)

    def fileDialogFilesSelected(self, pths):
        self.files.extend(pths)
        self.fileListModel.setStringList(self.files)

    def saveState(self):
        cfg = {}
        cfg['type'] = self.source_type.currentText()
        cfg['interval'] = self.interval.value()
        cfg['init_time'] = self.init_time.value()
        cfg['hb_period'] = self.hb_period.value()
        cfg['files'] = self.files
        cfg['repeat'] = self.repeat.isChecked()

        return cfg

    def restoreState(self, state):
        self.source_type.setCurrentText(state['type'])
        self.interval.setValue(state['interval'])
        self.init_time.setValue(state['init_time'])
        self.hb_period.setValue(state['hb_period'])
        self.files = state['files']
        self.fileListModel.setStringList(self.files)
        self.repeat.setChecked(state['repeat'])

    def applyClicked(self):
        cfg = self.saveState()
        self.sigApply.emit(cfg)
