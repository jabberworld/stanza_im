# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/linkeditor.ui'
#
# Created: Mon Apr 19 15:20:32 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_linkEditor(object):
    def setupUi(self, linkEditor):
        linkEditor.setObjectName("linkEditor")
        linkEditor.resize(429, 115)
        icon = QtGui.QIcon()
        icon.addFile(":/images/16x16/apps/jabbim.png")
        linkEditor.setWindowIcon(icon)
        self.gridlayout = QtGui.QGridLayout(linkEditor)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.hboxlayout = QtGui.QHBoxLayout()
        self.hboxlayout.setMargin(0)
        self.hboxlayout.setSpacing(6)
        self.hboxlayout.setObjectName("hboxlayout")
        self.vboxlayout = QtGui.QVBoxLayout()
        self.vboxlayout.setMargin(0)
        self.vboxlayout.setSpacing(6)
        self.vboxlayout.setObjectName("vboxlayout")
        self.label = QtGui.QLabel(linkEditor)
        self.label.setObjectName("label")
        self.vboxlayout.addWidget(self.label)
        self.label_2 = QtGui.QLabel(linkEditor)
        self.label_2.setObjectName("label_2")
        self.vboxlayout.addWidget(self.label_2)
        self.hboxlayout.addLayout(self.vboxlayout)
        self.vboxlayout1 = QtGui.QVBoxLayout()
        self.vboxlayout1.setMargin(0)
        self.vboxlayout1.setSpacing(6)
        self.vboxlayout1.setObjectName("vboxlayout1")
        self.linkText = QtGui.QLineEdit(linkEditor)
        self.linkText.setObjectName("linkText")
        self.vboxlayout1.addWidget(self.linkText)
        self.url = QtGui.QLineEdit(linkEditor)
        self.url.setObjectName("url")
        self.vboxlayout1.addWidget(self.url)
        self.hboxlayout.addLayout(self.vboxlayout1)
        self.gridlayout.addLayout(self.hboxlayout, 0, 0, 1, 1)
        self.buttonBox = QtGui.QDialogButtonBox(linkEditor)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.NoButton|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.gridlayout.addWidget(self.buttonBox, 1, 0, 1, 1)

        self.retranslateUi(linkEditor)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("accepted()"), linkEditor.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), linkEditor.reject)
        QtCore.QMetaObject.connectSlotsByName(linkEditor)

    def retranslateUi(self, linkEditor):
        linkEditor.setWindowTitle(QtGui.QApplication.translate("linkEditor", "Edit link", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("linkEditor", "Link text:", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("linkEditor", "URL:", None, QtGui.QApplication.UnicodeUTF8))

