# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/chat/leaveroom.ui'
#
# Created: Mon Apr 19 15:20:31 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_leaveroom(object):
    def setupUi(self, leaveroom):
        leaveroom.setObjectName("leaveroom")
        leaveroom.resize(308, 121)
        icon = QtGui.QIcon()
        icon.addFile(":/images/16x16/apps/jabbim.png")
        leaveroom.setWindowIcon(icon)
        self.gridlayout = QtGui.QGridLayout(leaveroom)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        spacerItem = QtGui.QSpacerItem(16, 27, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout.addItem(spacerItem, 2, 0, 1, 2)
        self.pushButton_2 = QtGui.QPushButton(leaveroom)
        self.pushButton_2.setObjectName("pushButton_2")
        self.gridlayout.addWidget(self.pushButton_2, 2, 3, 1, 1)
        self.pushButton = QtGui.QPushButton(leaveroom)
        self.pushButton.setObjectName("pushButton")
        self.gridlayout.addWidget(self.pushButton, 2, 2, 1, 1)
        self.label_2 = QtGui.QLabel(leaveroom)
        self.label_2.setMaximumSize(QtCore.QSize(48, 16200))
        self.label_2.setText("")
        self.label_2.setPixmap(QtGui.QPixmap(":/images/48x48/categories/conferences.png"))
        self.label_2.setObjectName("label_2")
        self.gridlayout.addWidget(self.label_2, 0, 0, 1, 1)
        self.leaveroom = QtGui.QLabel(leaveroom)
        self.leaveroom.setTextFormat(QtCore.Qt.RichText)
        self.leaveroom.setWordWrap(True)
        self.leaveroom.setObjectName("leaveroom")
        self.gridlayout.addWidget(self.leaveroom, 0, 1, 1, 3)
        self.checkBox = QtGui.QCheckBox(leaveroom)
        self.checkBox.setObjectName("checkBox")
        self.gridlayout.addWidget(self.checkBox, 1, 1, 1, 3)

        self.retranslateUi(leaveroom)
        QtCore.QObject.connect(self.pushButton_2, QtCore.SIGNAL("clicked()"), leaveroom.reject)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), leaveroom.accept)
        QtCore.QObject.connect(self.checkBox, QtCore.SIGNAL("toggled(bool)"), self.pushButton_2.setDisabled)
        QtCore.QMetaObject.connectSlotsByName(leaveroom)

    def retranslateUi(self, leaveroom):
        leaveroom.setWindowTitle(QtGui.QApplication.translate("leaveroom", "Leave room", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton_2.setText(QtGui.QApplication.translate("leaveroom", "No", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("leaveroom", "Yes", None, QtGui.QApplication.UnicodeUTF8))
        self.leaveroom.setText(QtGui.QApplication.translate("leaveroom", "You are trying to leave room jabbim@conf.netlab.cz\n"
"Do you realy want to leave this room?", None, QtGui.QApplication.UnicodeUTF8))
        self.checkBox.setText(QtGui.QApplication.translate("leaveroom", "Don\'t ask later", None, QtGui.QApplication.UnicodeUTF8))

