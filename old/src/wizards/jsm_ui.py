# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/wizards/jsm.ui'
#
# Created: Mon Apr 19 15:20:39 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_JabbimServiceManager(object):
    def setupUi(self, JabbimServiceManager):
        JabbimServiceManager.setObjectName("JabbimServiceManager")
        JabbimServiceManager.resize(428, 319)
        self.gridLayout = QtGui.QGridLayout(JabbimServiceManager)
        self.gridLayout.setObjectName("gridLayout")
        self.label = QtGui.QLabel(JabbimServiceManager)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 0, 1, 2)
        self.label_2 = QtGui.QLabel(JabbimServiceManager)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 2)
        self.treeWidget = QtGui.QTreeWidget(JabbimServiceManager)
        self.treeWidget.setRootIsDecorated(False)
        self.treeWidget.setAllColumnsShowFocus(True)
        self.treeWidget.setHeaderHidden(True)
        self.treeWidget.setObjectName("treeWidget")
        self.gridLayout.addWidget(self.treeWidget, 2, 0, 3, 1)
        self.textBrowser = QtGui.QTextBrowser(JabbimServiceManager)
        self.textBrowser.setObjectName("textBrowser")
        self.gridLayout.addWidget(self.textBrowser, 2, 1, 1, 1)
        self.jids = QtGui.QTreeWidget(JabbimServiceManager)
        self.jids.setRootIsDecorated(False)
        self.jids.setHeaderHidden(True)
        self.jids.setObjectName("jids")
        self.gridLayout.addWidget(self.jids, 3, 1, 1, 1)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem = QtGui.QSpacerItem(13, 23, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.add = QtGui.QPushButton(JabbimServiceManager)
        self.add.setObjectName("add")
        self.horizontalLayout.addWidget(self.add)
        self.reg = QtGui.QPushButton(JabbimServiceManager)
        self.reg.setObjectName("reg")
        self.horizontalLayout.addWidget(self.reg)
        self.configure = QtGui.QPushButton(JabbimServiceManager)
        self.configure.setObjectName("configure")
        self.horizontalLayout.addWidget(self.configure)
        self.gridLayout.addLayout(self.horizontalLayout, 4, 1, 1, 1)
        self.horizontalLayout_2 = QtGui.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.advanced = QtGui.QPushButton(JabbimServiceManager)
        self.advanced.setObjectName("advanced")
        self.horizontalLayout_2.addWidget(self.advanced)
        spacerItem1 = QtGui.QSpacerItem(349, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem1)
        self.pushButton = QtGui.QPushButton(JabbimServiceManager)
        self.pushButton.setObjectName("pushButton")
        self.horizontalLayout_2.addWidget(self.pushButton)
        self.gridLayout.addLayout(self.horizontalLayout_2, 5, 0, 1, 2)

        self.retranslateUi(JabbimServiceManager)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), JabbimServiceManager.reject)
        QtCore.QMetaObject.connectSlotsByName(JabbimServiceManager)

    def retranslateUi(self, JabbimServiceManager):
        JabbimServiceManager.setWindowTitle(QtGui.QApplication.translate("JabbimServiceManager", "Jabbim Service Manager", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("JabbimServiceManager", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'DejaVu Sans\'; font-size:9pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><h2>Jabbim Service Manager</h2></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("JabbimServiceManager", "Available Services:", None, QtGui.QApplication.UnicodeUTF8))
        self.treeWidget.headerItem().setText(0, QtGui.QApplication.translate("JabbimServiceManager", "Registered", None, QtGui.QApplication.UnicodeUTF8))
        self.treeWidget.headerItem().setText(1, QtGui.QApplication.translate("JabbimServiceManager", "Name", None, QtGui.QApplication.UnicodeUTF8))
        self.treeWidget.headerItem().setText(2, QtGui.QApplication.translate("JabbimServiceManager", "Sort", None, QtGui.QApplication.UnicodeUTF8))
        self.jids.headerItem().setText(0, QtGui.QApplication.translate("JabbimServiceManager", "1", None, QtGui.QApplication.UnicodeUTF8))
        self.add.setText(QtGui.QApplication.translate("JabbimServiceManager", "Add", None, QtGui.QApplication.UnicodeUTF8))
        self.reg.setText(QtGui.QApplication.translate("JabbimServiceManager", "Register", None, QtGui.QApplication.UnicodeUTF8))
        self.configure.setText(QtGui.QApplication.translate("JabbimServiceManager", "Configure", None, QtGui.QApplication.UnicodeUTF8))
        self.advanced.setText(QtGui.QApplication.translate("JabbimServiceManager", "Advanced", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("JabbimServiceManager", "Close", None, QtGui.QApplication.UnicodeUTF8))

