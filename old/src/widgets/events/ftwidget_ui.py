# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/events/ftwidget.ui'
#
# Created: Mon Apr 19 15:20:38 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_FTWidget(object):
    def setupUi(self, FTWidget):
        FTWidget.setObjectName("FTWidget")
        FTWidget.resize(168, 114)
        self.gridLayout = QtGui.QGridLayout(FTWidget)
        self.gridLayout.setObjectName("gridLayout")
        self.filename = QtGui.QLabel(FTWidget)
        self.filename.setObjectName("filename")
        self.gridLayout.addWidget(self.filename, 0, 0, 1, 3)
        self.jid = QtGui.QLabel(FTWidget)
        self.jid.setObjectName("jid")
        self.gridLayout.addWidget(self.jid, 1, 0, 1, 4)
        self.closeButton = QtGui.QPushButton(FTWidget)
        self.closeButton.setMaximumSize(QtCore.QSize(20, 16777215))
        self.closeButton.setText("")
        self.closeButton.setObjectName("closeButton")
        self.gridLayout.addWidget(self.closeButton, 0, 3, 1, 1)
        self.transferInfo = QtGui.QLabel(FTWidget)
        self.transferInfo.setWordWrap(True)
        self.transferInfo.setObjectName("transferInfo")
        self.gridLayout.addWidget(self.transferInfo, 2, 0, 1, 4)
        self.progressBar = QtGui.QProgressBar(FTWidget)
        self.progressBar.setProperty("value", 0)
        self.progressBar.setObjectName("progressBar")
        self.gridLayout.addWidget(self.progressBar, 3, 0, 1, 4)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 4, 0, 1, 1)
        self.reject = QtGui.QPushButton(FTWidget)
        self.reject.setObjectName("reject")
        self.gridLayout.addWidget(self.reject, 4, 1, 1, 1)
        self.accept = QtGui.QPushButton(FTWidget)
        self.accept.setObjectName("accept")
        self.gridLayout.addWidget(self.accept, 4, 2, 1, 2)

        self.retranslateUi(FTWidget)
        QtCore.QMetaObject.connectSlotsByName(FTWidget)

    def retranslateUi(self, FTWidget):
        FTWidget.setWindowTitle(QtGui.QApplication.translate("FTWidget", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.filename.setText(QtGui.QApplication.translate("FTWidget", "Smileys_test.zip", None, QtGui.QApplication.UnicodeUTF8))
        self.jid.setText(QtGui.QApplication.translate("FTWidget", "a@jabbim.cz", None, QtGui.QApplication.UnicodeUTF8))
        self.transferInfo.setText(QtGui.QApplication.translate("FTWidget", "Zbyva: 30 s (255 kB/s)", None, QtGui.QApplication.UnicodeUTF8))
        self.reject.setText(QtGui.QApplication.translate("FTWidget", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.accept.setText(QtGui.QApplication.translate("FTWidget", "Open", None, QtGui.QApplication.UnicodeUTF8))

