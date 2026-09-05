# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/statuseditor.ui'
#
# Created: Mon Apr 19 15:20:35 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_statusEditor(object):
    def setupUi(self, statusEditor):
        statusEditor.setObjectName("statusEditor")
        statusEditor.resize(291, 300)
        icon = QtGui.QIcon()
        icon.addFile(":/images/16x16/apps/jabbim.png")
        statusEditor.setWindowIcon(icon)
        self.gridlayout = QtGui.QGridLayout(statusEditor)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.editStatus = QtGui.QPushButton(statusEditor)
        self.editStatus.setObjectName("editStatus")
        self.gridlayout.addWidget(self.editStatus, 2, 1, 1, 1)
        self.statusList = QtGui.QListWidget(statusEditor)
        self.statusList.setIconSize(QtCore.QSize(22, 22))
        self.statusList.setObjectName("statusList")
        self.gridlayout.addWidget(self.statusList, 2, 0, 4, 1)
        self.removeStatus = QtGui.QPushButton(statusEditor)
        self.removeStatus.setObjectName("removeStatus")
        self.gridlayout.addWidget(self.removeStatus, 3, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(35, 111, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridlayout.addItem(spacerItem, 4, 1, 1, 1)
        self.line = QtGui.QFrame(statusEditor)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridlayout.addWidget(self.line, 1, 0, 1, 2)
        self.pushButton = QtGui.QPushButton(statusEditor)
        self.pushButton.setObjectName("pushButton")
        self.gridlayout.addWidget(self.pushButton, 5, 1, 1, 1)
        self.label = QtGui.QLabel(statusEditor)
        self.label.setObjectName("label")
        self.gridlayout.addWidget(self.label, 0, 0, 1, 2)

        self.retranslateUi(statusEditor)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), statusEditor.reject)
        QtCore.QMetaObject.connectSlotsByName(statusEditor)

    def retranslateUi(self, statusEditor):
        statusEditor.setWindowTitle(QtGui.QApplication.translate("statusEditor", "Status message Editor", None, QtGui.QApplication.UnicodeUTF8))
        self.editStatus.setText(QtGui.QApplication.translate("statusEditor", "Edit", None, QtGui.QApplication.UnicodeUTF8))
        self.removeStatus.setText(QtGui.QApplication.translate("statusEditor", "Remove", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("statusEditor", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("statusEditor", "<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'DejaVu Sans\'; font-size:9pt; font-weight:400; font-style:normal; text-decoration:none;\">\n"
"<p style=\" margin-top:16px; margin-bottom:12px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-size:x-large; font-weight:600;\"><span style=\" font-size:x-large;\">Status messages editor</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))

