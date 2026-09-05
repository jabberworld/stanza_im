# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/events/booleanwidget.ui'
#
# Created: Mon Apr 19 15:20:38 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(231, 62)
        self.gridLayout = QtGui.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.text = QtGui.QLabel(Form)
        self.text.setWordWrap(True)
        self.text.setObjectName("text")
        self.gridLayout.addWidget(self.text, 0, 0, 1, 3)
        spacerItem = QtGui.QSpacerItem(48, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 1, 0, 1, 1)
        self.reject = QtGui.QPushButton(Form)
        self.reject.setObjectName("reject")
        self.gridLayout.addWidget(self.reject, 1, 1, 1, 1)
        self.accept = QtGui.QPushButton(Form)
        self.accept.setObjectName("accept")
        self.gridLayout.addWidget(self.accept, 1, 2, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtGui.QApplication.translate("Form", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.text.setText(QtGui.QApplication.translate("Form", "New message from: hanzz@njs.netlab.cz", None, QtGui.QApplication.UnicodeUTF8))
        self.reject.setText(QtGui.QApplication.translate("Form", "Ingore", None, QtGui.QApplication.UnicodeUTF8))
        self.accept.setText(QtGui.QApplication.translate("Form", "Read", None, QtGui.QApplication.UnicodeUTF8))

