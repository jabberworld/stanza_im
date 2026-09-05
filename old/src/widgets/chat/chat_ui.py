# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/chat/chat.ui'
#
# Created: Mon Apr 19 15:20:30 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_chatWindow(object):
    def setupUi(self, chatWindow):
        chatWindow.setObjectName("chatWindow")
        chatWindow.resize(581, 562)
        icon = QtGui.QIcon()
        icon.addFile(":/images/16x16/apps/jabbim.png")
        chatWindow.setWindowIcon(icon)
        self.centralwidget = QtGui.QWidget(chatWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.gridlayout = QtGui.QGridLayout(self.centralwidget)
        self.gridlayout.setMargin(0)
        self.gridlayout.setSpacing(0)
        self.gridlayout.setObjectName("gridlayout")
        self.chatTab = QtGui.QTabWidget(self.centralwidget)
        self.chatTab.setObjectName("chatTab")
        self.tab = QtGui.QWidget()
        self.tab.setObjectName("tab")
        self.chatTab.addTab(self.tab, "")
        self.gridlayout.addWidget(self.chatTab, 0, 0, 1, 1)
        chatWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(chatWindow)
        self.chatTab.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(chatWindow)

    def retranslateUi(self, chatWindow):
        chatWindow.setWindowTitle(QtGui.QApplication.translate("chatWindow", "Chat", None, QtGui.QApplication.UnicodeUTF8))
        self.chatTab.setTabText(self.chatTab.indexOf(self.tab), QtGui.QApplication.translate("chatWindow", "Tab 1", None, QtGui.QApplication.UnicodeUTF8))

