# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/extra.ui'
#
# Created: Mon Apr 19 15:20:33 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Extra(object):
    def setupUi(self, Extra):
        Extra.setObjectName("Extra")
        Extra.resize(497, 300)
        icon = QtGui.QIcon()
        icon.addFile(":/images/16x16/apps/jabbim.png")
        Extra.setWindowIcon(icon)
        self.gridlayout = QtGui.QGridLayout(Extra)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.stackedWidget = QtGui.QStackedWidget(Extra)
        self.stackedWidget.setObjectName("stackedWidget")
        self.page = QtGui.QWidget()
        self.page.setObjectName("page")
        self.gridlayout1 = QtGui.QGridLayout(self.page)
        self.gridlayout1.setMargin(9)
        self.gridlayout1.setSpacing(6)
        self.gridlayout1.setObjectName("gridlayout1")
        self.listWidget = QtGui.QListWidget(self.page)
        self.listWidget.setMaximumSize(QtCore.QSize(165, 16777215))
        self.listWidget.setObjectName("listWidget")
        self.gridlayout1.addWidget(self.listWidget, 0, 0, 2, 1)
        self.preview = QtGui.QLabel(self.page)
        self.preview.setText("")
        self.preview.setObjectName("preview")
        self.gridlayout1.addWidget(self.preview, 1, 1, 1, 1)
        self.textBrowser = QtGui.QTextBrowser(self.page)
        self.textBrowser.setObjectName("textBrowser")
        self.gridlayout1.addWidget(self.textBrowser, 0, 1, 1, 1)
        self.stackedWidget.addWidget(self.page)
        self.page_2 = QtGui.QWidget()
        self.page_2.setObjectName("page_2")
        self.gridlayout2 = QtGui.QGridLayout(self.page_2)
        self.gridlayout2.setMargin(9)
        self.gridlayout2.setSpacing(6)
        self.gridlayout2.setObjectName("gridlayout2")
        spacerItem = QtGui.QSpacerItem(20, 171, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridlayout2.addItem(spacerItem, 1, 0, 1, 1)
        self.prog = QtGui.QWidget(self.page_2)
        self.prog.setObjectName("prog")
        self.gridlayout2.addWidget(self.prog, 0, 0, 1, 1)
        self.stackedWidget.addWidget(self.page_2)
        self.gridlayout.addWidget(self.stackedWidget, 1, 0, 1, 3)
        spacerItem1 = QtGui.QSpacerItem(241, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout.addItem(spacerItem1, 2, 0, 1, 1)
        self.pushButton_2 = QtGui.QPushButton(Extra)
        self.pushButton_2.setObjectName("pushButton_2")
        self.gridlayout.addWidget(self.pushButton_2, 2, 2, 1, 1)
        self.pushButton = QtGui.QPushButton(Extra)
        self.pushButton.setObjectName("pushButton")
        self.gridlayout.addWidget(self.pushButton, 2, 1, 1, 1)
        self.label = QtGui.QLabel(Extra)
        self.label.setObjectName("label")
        self.gridlayout.addWidget(self.label, 0, 0, 1, 1)

        self.retranslateUi(Extra)
        self.stackedWidget.setCurrentIndex(0)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), Extra.accept)
        QtCore.QObject.connect(self.pushButton_2, QtCore.SIGNAL("clicked()"), Extra.reject)
        QtCore.QMetaObject.connectSlotsByName(Extra)

    def retranslateUi(self, Extra):
        Extra.setWindowTitle(QtGui.QApplication.translate("Extra", "Jabbim Extra", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton_2.setText(QtGui.QApplication.translate("Extra", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("Extra", "Install", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("Extra", "<h2>Emoticons</h2>", None, QtGui.QApplication.UnicodeUTF8))

