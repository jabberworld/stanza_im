# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/filetransfer.ui'
#
# Created: Mon Apr 19 15:20:36 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_fileTransfer(object):
    def setupUi(self, fileTransfer):
        fileTransfer.setObjectName("fileTransfer")
        fileTransfer.resize(470, 310)
        icon = QtGui.QIcon()
        icon.addFile(":/images/16x16/apps/jabbim.png")
        fileTransfer.setWindowIcon(icon)
        self.gridlayout = QtGui.QGridLayout(fileTransfer)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        spacerItem = QtGui.QSpacerItem(231, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout.addItem(spacerItem, 1, 0, 1, 1)
        self.treeWidget = QtGui.QTreeWidget(fileTransfer)
        self.treeWidget.setEditTriggers(QtGui.QAbstractItemView.AnyKeyPressed|QtGui.QAbstractItemView.DoubleClicked|QtGui.QAbstractItemView.EditKeyPressed|QtGui.QAbstractItemView.NoEditTriggers)
        self.treeWidget.setRootIsDecorated(False)
        self.treeWidget.setAllColumnsShowFocus(True)
        self.treeWidget.setObjectName("treeWidget")
        self.gridlayout.addWidget(self.treeWidget, 0, 0, 1, 2)
        self.hboxlayout = QtGui.QHBoxLayout()
        self.hboxlayout.setMargin(0)
        self.hboxlayout.setSpacing(6)
        self.hboxlayout.setObjectName("hboxlayout")
        self.pushButton_2 = QtGui.QPushButton(fileTransfer)
        self.pushButton_2.setObjectName("pushButton_2")
        self.hboxlayout.addWidget(self.pushButton_2)
        self.pushButton = QtGui.QPushButton(fileTransfer)
        self.pushButton.setObjectName("pushButton")
        self.hboxlayout.addWidget(self.pushButton)
        self.gridlayout.addLayout(self.hboxlayout, 1, 1, 1, 1)

        self.retranslateUi(fileTransfer)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), fileTransfer.accept)
        QtCore.QObject.connect(self.pushButton_2, QtCore.SIGNAL("clicked()"), fileTransfer.reject)
        QtCore.QMetaObject.connectSlotsByName(fileTransfer)

    def retranslateUi(self, fileTransfer):
        fileTransfer.setWindowTitle(QtGui.QApplication.translate("fileTransfer", "File Transfer", None, QtGui.QApplication.UnicodeUTF8))
        self.treeWidget.setToolTip(QtGui.QApplication.translate("fileTransfer", "Here you see files prepared to transfer", None, QtGui.QApplication.UnicodeUTF8))
        self.treeWidget.headerItem().setText(0, QtGui.QApplication.translate("fileTransfer", "Name", None, QtGui.QApplication.UnicodeUTF8))
        self.treeWidget.headerItem().setText(1, QtGui.QApplication.translate("fileTransfer", "Description", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton_2.setText(QtGui.QApplication.translate("fileTransfer", "Cancel", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("fileTransfer", "Send", None, QtGui.QApplication.UnicodeUTF8))

