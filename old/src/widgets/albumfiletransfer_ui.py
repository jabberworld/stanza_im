# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/albumfiletransfer.ui'
#
# Created: Mon Apr 19 15:20:29 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_albumFiletransferDialog(object):
    def setupUi(self, albumFiletransferDialog):
        albumFiletransferDialog.setObjectName("albumFiletransferDialog")
        albumFiletransferDialog.resize(476, 451)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/images/16x16/apps/jabbim.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        albumFiletransferDialog.setWindowIcon(icon)
        self.gridlayout = QtGui.QGridLayout(albumFiletransferDialog)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.hboxlayout = QtGui.QHBoxLayout()
        self.hboxlayout.setSpacing(6)
        self.hboxlayout.setMargin(0)
        self.hboxlayout.setObjectName("hboxlayout")
        self.vboxlayout = QtGui.QVBoxLayout()
        self.vboxlayout.setSpacing(6)
        self.vboxlayout.setMargin(0)
        self.vboxlayout.setObjectName("vboxlayout")
        self.label = QtGui.QLabel(albumFiletransferDialog)
        self.label.setObjectName("label")
        self.vboxlayout.addWidget(self.label)
        self.files = QtGui.QListWidget(albumFiletransferDialog)
        self.files.setMaximumSize(QtCore.QSize(160, 16777215))
        self.files.setObjectName("files")
        self.vboxlayout.addWidget(self.files)
        self.addFiles = QtGui.QPushButton(albumFiletransferDialog)
        self.addFiles.setObjectName("addFiles")
        self.vboxlayout.addWidget(self.addFiles)
        self.hboxlayout.addLayout(self.vboxlayout)
        self.vboxlayout1 = QtGui.QVBoxLayout()
        self.vboxlayout1.setSpacing(6)
        self.vboxlayout1.setMargin(0)
        self.vboxlayout1.setObjectName("vboxlayout1")
        self.photo = QtGui.QLabel(albumFiletransferDialog)
        self.photo.setFrameShape(QtGui.QFrame.StyledPanel)
        self.photo.setObjectName("photo")
        self.vboxlayout1.addWidget(self.photo)
        self.label_2 = QtGui.QLabel(albumFiletransferDialog)
        self.label_2.setObjectName("label_2")
        self.vboxlayout1.addWidget(self.label_2)
        self.description = QtGui.QTextEdit(albumFiletransferDialog)
        self.description.setObjectName("description")
        self.vboxlayout1.addWidget(self.description)
        self.hboxlayout.addLayout(self.vboxlayout1)
        self.gridlayout.addLayout(self.hboxlayout, 0, 0, 1, 2)
        self.hboxlayout1 = QtGui.QHBoxLayout()
        self.hboxlayout1.setSpacing(6)
        self.hboxlayout1.setMargin(0)
        self.hboxlayout1.setObjectName("hboxlayout1")
        self.pushButton_2 = QtGui.QPushButton(albumFiletransferDialog)
        self.pushButton_2.setObjectName("pushButton_2")
        self.hboxlayout1.addWidget(self.pushButton_2)
        self.pushButton = QtGui.QPushButton(albumFiletransferDialog)
        self.pushButton.setObjectName("pushButton")
        self.hboxlayout1.addWidget(self.pushButton)
        self.gridlayout.addLayout(self.hboxlayout1, 1, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(211, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout.addItem(spacerItem, 1, 0, 1, 1)

        self.retranslateUi(albumFiletransferDialog)
        QtCore.QObject.connect(self.pushButton_2, QtCore.SIGNAL("clicked()"), albumFiletransferDialog.reject)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), albumFiletransferDialog.accept)
        QtCore.QMetaObject.connectSlotsByName(albumFiletransferDialog)

    def retranslateUi(self, albumFiletransferDialog):
        albumFiletransferDialog.setWindowTitle(QtGui.QApplication.translate("albumFiletransferDialog", "Filetransfer", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("albumFiletransferDialog", "File list:", None, QtGui.QApplication.UnicodeUTF8))
        self.addFiles.setText(QtGui.QApplication.translate("albumFiletransferDialog", "Add more files", None, QtGui.QApplication.UnicodeUTF8))
        self.photo.setText(QtGui.QApplication.translate("albumFiletransferDialog", "photo", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("albumFiletransferDialog", "File Description:", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton_2.setText(QtGui.QApplication.translate("albumFiletransferDialog", "Cancel", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("albumFiletransferDialog", "Send", None, QtGui.QApplication.UnicodeUTF8))

