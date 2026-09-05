# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/vcardview.ui'
#
# Created: Mon Apr 19 15:20:32 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_vcardView(object):
    def setupUi(self, vcardView):
        vcardView.setObjectName("vcardView")
        vcardView.resize(337, 185)
        self.gridlayout = QtGui.QGridLayout(vcardView)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        spacerItem = QtGui.QSpacerItem(20, 191, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridlayout.addItem(spacerItem, 1, 2, 1, 1)
        self.avatar = QtGui.QLabel(vcardView)
        self.avatar.setObjectName("avatar")
        self.gridlayout.addWidget(self.avatar, 0, 2, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(291, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout.addItem(spacerItem1, 2, 0, 1, 1)
        self.pushButton = QtGui.QPushButton(vcardView)
        self.pushButton.setObjectName("pushButton")
        self.gridlayout.addWidget(self.pushButton, 2, 1, 1, 2)
        self.vcard = QtGui.QLabel(vcardView)
        self.vcard.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop)
        self.vcard.setOpenExternalLinks(True)
        self.vcard.setObjectName("vcard")
        self.gridlayout.addWidget(self.vcard, 0, 0, 2, 2)

        self.retranslateUi(vcardView)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), vcardView.reject)
        QtCore.QMetaObject.connectSlotsByName(vcardView)

    def retranslateUi(self, vcardView):
        vcardView.setWindowTitle(QtGui.QApplication.translate("vcardView", "VCard Viewer", None, QtGui.QApplication.UnicodeUTF8))
        self.avatar.setText(QtGui.QApplication.translate("vcardView", "Avatar", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("vcardView", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.vcard.setText(QtGui.QApplication.translate("vcardView", "Vcard", None, QtGui.QApplication.UnicodeUTF8))

