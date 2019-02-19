from PyQt5 import QtGui, QtWidgets


class Ui_Toolbar(object):
    def setupUi(self, parent=None):
        self.toolBar = QtWidgets.QToolBar(parent)
        self.toolBar.setObjectName("toolBar")

        # new
        self.actionNew = QtWidgets.QAction(parent)
        icon = QtGui.QIcon.fromTheme("document-new")
        self.actionNew.setIcon(icon)
        self.actionNew.setIconText("New")
        self.actionNew.setObjectName("actionNew")

        # open
        self.actionOpen = QtWidgets.QAction(parent)
        icon = QtGui.QIcon.fromTheme("document-open")
        self.actionOpen.setIcon(icon)
        self.actionOpen.setIconText("Open")
        self.actionOpen.setObjectName("actionOpen")

        # save
        self.actionSave = QtWidgets.QAction(parent)
        icon = QtGui.QIcon.fromTheme("document-save")
        self.actionSave.setIcon(icon)
        self.actionSave.setIconText("Save")
        self.actionSave.setObjectName("actionSave")

        # apply
        self.actionApply = QtWidgets.QAction(parent)
        icon = QtGui.QIcon.fromTheme("document-new")
        self.actionApply.setIcon(icon)
        self.actionApply.setIconText("Apply")
        self.actionApply.setObjectName("actionApply")

        self.toolBar.addAction(self.actionNew)
        self.toolBar.addAction(self.actionOpen)
        self.toolBar.addAction(self.actionSave)
        self.toolBar.addAction(self.actionApply)
