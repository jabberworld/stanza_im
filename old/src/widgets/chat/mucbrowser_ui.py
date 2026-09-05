# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/chat/mucbrowser.ui'
#
# Created: Mon Apr 19 15:20:30 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_MUCBrowser(object):
    def setupUi(self, MUCBrowser):
        MUCBrowser.setObjectName("MUCBrowser")
        MUCBrowser.resize(640, 389)
        self.gridlayout = QtGui.QGridLayout(MUCBrowser)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.hboxlayout = QtGui.QHBoxLayout()
        self.hboxlayout.setMargin(0)
        self.hboxlayout.setSpacing(6)
        self.hboxlayout.setObjectName("hboxlayout")
        self.label = QtGui.QLabel(MUCBrowser)
        self.label.setObjectName("label")
        self.hboxlayout.addWidget(self.label)
        self.filter = QtGui.QLineEdit(MUCBrowser)
        self.filter.setMaximumSize(QtCore.QSize(125, 16777215))
        self.filter.setObjectName("filter")
        self.hboxlayout.addWidget(self.filter)
        self.line = QtGui.QFrame(MUCBrowser)
        self.line.setFrameShape(QtGui.QFrame.VLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName("line")
        self.hboxlayout.addWidget(self.line)
        self.buttonBox = QtGui.QDialogButtonBox(MUCBrowser)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.NoButton|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.hboxlayout.addWidget(self.buttonBox)
        self.gridlayout.addLayout(self.hboxlayout, 1, 0, 1, 1)
        self.groupchats = QtGui.QTreeWidget(MUCBrowser)
        self.groupchats.setAllColumnsShowFocus(True)
        self.groupchats.setObjectName("groupchats")
        self.gridlayout.addWidget(self.groupchats, 0, 0, 1, 1)

        self.retranslateUi(MUCBrowser)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("accepted()"), MUCBrowser.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), MUCBrowser.reject)
        QtCore.QMetaObject.connectSlotsByName(MUCBrowser)

    def retranslateUi(self, MUCBrowser):
        MUCBrowser.setWindowTitle(QtGui.QApplication.translate("MUCBrowser", "MUC Browser", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("MUCBrowser", "Find:", None, QtGui.QApplication.UnicodeUTF8))
        self.groupchats.headerItem().setText(1, QtGui.QApplication.translate("MUCBrowser", "JID", None, QtGui.QApplication.UnicodeUTF8))
        self.groupchats.headerItem().setText(2, QtGui.QApplication.translate("MUCBrowser", "Room name", None, QtGui.QApplication.UnicodeUTF8))
        self.groupchats.headerItem().setText(3, QtGui.QApplication.translate("MUCBrowser", "#", None, QtGui.QApplication.UnicodeUTF8))

