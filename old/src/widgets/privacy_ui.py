# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/privacy.ui'
#
# Created: Mon Apr 19 15:20:38 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_PrivacyListEditor(object):
    def setupUi(self, PrivacyListEditor):
        PrivacyListEditor.setObjectName("PrivacyListEditor")
        PrivacyListEditor.resize(400, 300)
        self.gridlayout = QtGui.QGridLayout(PrivacyListEditor)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.privacyList = QtGui.QTreeWidget(PrivacyListEditor)
        self.privacyList.setObjectName("privacyList")
        self.gridlayout.addWidget(self.privacyList, 1, 0, 1, 3)
        spacerItem = QtGui.QSpacerItem(201, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout.addItem(spacerItem, 2, 0, 1, 1)
        self.pushButton_2 = QtGui.QPushButton(PrivacyListEditor)
        self.pushButton_2.setObjectName("pushButton_2")
        self.gridlayout.addWidget(self.pushButton_2, 2, 1, 1, 1)
        self.pushButton = QtGui.QPushButton(PrivacyListEditor)
        self.pushButton.setObjectName("pushButton")
        self.gridlayout.addWidget(self.pushButton, 2, 2, 1, 1)
        self.addContact_headerLabel = QtGui.QLabel(PrivacyListEditor)
        self.addContact_headerLabel.setObjectName("addContact_headerLabel")
        self.gridlayout.addWidget(self.addContact_headerLabel, 0, 0, 1, 3)

        self.retranslateUi(PrivacyListEditor)
        QtCore.QObject.connect(self.pushButton_2, QtCore.SIGNAL("clicked()"), PrivacyListEditor.reject)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), PrivacyListEditor.accept)
        QtCore.QMetaObject.connectSlotsByName(PrivacyListEditor)

    def retranslateUi(self, PrivacyListEditor):
        PrivacyListEditor.setWindowTitle(QtGui.QApplication.translate("PrivacyListEditor", "Privacy List Editor", None, QtGui.QApplication.UnicodeUTF8))
        self.privacyList.headerItem().setText(0, QtGui.QApplication.translate("PrivacyListEditor", "Jabber ID", None, QtGui.QApplication.UnicodeUTF8))
        self.privacyList.headerItem().setText(1, QtGui.QApplication.translate("PrivacyListEditor", "Configuration", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton_2.setText(QtGui.QApplication.translate("PrivacyListEditor", "Cancel", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("PrivacyListEditor", "Save", None, QtGui.QApplication.UnicodeUTF8))
        self.addContact_headerLabel.setText(QtGui.QApplication.translate("PrivacyListEditor", "<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'DejaVu Sans\'; font-size:9pt; font-weight:400; font-style:normal; text-decoration:none;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:12pt; font-weight:600;\">Privacy list editor</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))

