# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/addcontact.ui'
#
# Created: Mon Apr 19 15:20:35 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_addContact(object):
    def setupUi(self, addContact):
        addContact.setObjectName("addContact")
        addContact.resize(335, 303)
        self.gridlayout = QtGui.QGridLayout(addContact)
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
        self.add_jidLabel = QtGui.QLabel(addContact)
        self.add_jidLabel.setObjectName("add_jidLabel")
        self.vboxlayout.addWidget(self.add_jidLabel)
        self.add_nicknameLabel = QtGui.QLabel(addContact)
        self.add_nicknameLabel.setObjectName("add_nicknameLabel")
        self.vboxlayout.addWidget(self.add_nicknameLabel)
        self.add_groupLabel = QtGui.QLabel(addContact)
        self.add_groupLabel.setObjectName("add_groupLabel")
        self.vboxlayout.addWidget(self.add_groupLabel)
        self.hboxlayout.addLayout(self.vboxlayout)
        self.vboxlayout1 = QtGui.QVBoxLayout()
        self.vboxlayout1.setSpacing(6)
        self.vboxlayout1.setMargin(0)
        self.vboxlayout1.setObjectName("vboxlayout1")
        self.add_jid = QtGui.QLineEdit(addContact)
        self.add_jid.setObjectName("add_jid")
        self.vboxlayout1.addWidget(self.add_jid)
        self.add_nickname = QtGui.QLineEdit(addContact)
        self.add_nickname.setObjectName("add_nickname")
        self.vboxlayout1.addWidget(self.add_nickname)
        self.add_group = QtGui.QComboBox(addContact)
        self.add_group.setEditable(True)
        self.add_group.setObjectName("add_group")
        self.vboxlayout1.addWidget(self.add_group)
        self.hboxlayout.addLayout(self.vboxlayout1)
        self.gridlayout.addLayout(self.hboxlayout, 1, 0, 1, 1)
        self.gridlayout1 = QtGui.QGridLayout()
        self.gridlayout1.setMargin(0)
        self.gridlayout1.setSpacing(6)
        self.gridlayout1.setObjectName("gridlayout1")
        self.add_messageLabel = QtGui.QLabel(addContact)
        self.add_messageLabel.setObjectName("add_messageLabel")
        self.gridlayout1.addWidget(self.add_messageLabel, 0, 0, 1, 1)
        self.add_message = QtGui.QTextEdit(addContact)
        self.add_message.setObjectName("add_message")
        self.gridlayout1.addWidget(self.add_message, 1, 0, 1, 2)
        spacerItem = QtGui.QSpacerItem(191, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout1.addItem(spacerItem, 0, 1, 1, 1)
        self.gridlayout.addLayout(self.gridlayout1, 2, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(314, 13, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridlayout.addItem(spacerItem1, 3, 0, 1, 1)
        self.gridLayout_3 = QtGui.QGridLayout()
        self.gridLayout_3.setSpacing(6)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.buttonBox = QtGui.QDialogButtonBox(addContact)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)
        self.buttonBox.setObjectName("buttonBox")
        self.gridLayout_3.addWidget(self.buttonBox, 0, 1, 1, 1)
        self.search = QtGui.QPushButton(addContact)
        self.search.setObjectName("search")
        self.gridLayout_3.addWidget(self.search, 0, 0, 1, 1)
        self.gridlayout.addLayout(self.gridLayout_3, 4, 0, 1, 1)
        self.addContact_headerLabel = QtGui.QLabel(addContact)
        self.addContact_headerLabel.setObjectName("addContact_headerLabel")
        self.gridlayout.addWidget(self.addContact_headerLabel, 0, 0, 1, 1)

        self.retranslateUi(addContact)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("accepted()"), addContact.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), addContact.reject)
        QtCore.QMetaObject.connectSlotsByName(addContact)
        addContact.setTabOrder(self.add_jid, self.add_nickname)
        addContact.setTabOrder(self.add_nickname, self.add_group)
        addContact.setTabOrder(self.add_group, self.add_message)

    def retranslateUi(self, addContact):
        addContact.setWindowTitle(QtGui.QApplication.translate("addContact", "Add Contact", None, QtGui.QApplication.UnicodeUTF8))
        self.add_jidLabel.setText(QtGui.QApplication.translate("addContact", "Jabber ID:", None, QtGui.QApplication.UnicodeUTF8))
        self.add_nicknameLabel.setText(QtGui.QApplication.translate("addContact", "Nickname:", None, QtGui.QApplication.UnicodeUTF8))
        self.add_groupLabel.setText(QtGui.QApplication.translate("addContact", "Group:", None, QtGui.QApplication.UnicodeUTF8))
        self.add_jid.setToolTip(QtGui.QApplication.translate("addContact", "If you don\'t know contact\'s JID, you can\'t add <br>contact directly (use search function)", None, QtGui.QApplication.UnicodeUTF8))
        self.add_nickname.setToolTip(QtGui.QApplication.translate("addContact", "What do you want to see in your roster :)", None, QtGui.QApplication.UnicodeUTF8))
        self.add_group.setToolTip(QtGui.QApplication.translate("addContact", "Choose existing group or enter name for the new group", None, QtGui.QApplication.UnicodeUTF8))
        self.add_messageLabel.setText(QtGui.QApplication.translate("addContact", "Message:", None, QtGui.QApplication.UnicodeUTF8))
        self.add_message.setToolTip(QtGui.QApplication.translate("addContact", "Enter a short message that you want to send to the added contact.", None, QtGui.QApplication.UnicodeUTF8))
        self.add_message.setHtml(QtGui.QApplication.translate("addContact", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'Sans Serif\'; font-size:9pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">Hi! I am adding you to my roster using the jabber client Jabbim! Please authorize me to see you when you are available. Thanks!</p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.search.setText(QtGui.QApplication.translate("addContact", "Search", None, QtGui.QApplication.UnicodeUTF8))
        self.addContact_headerLabel.setText(QtGui.QApplication.translate("addContact", "<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'DejaVu Sans\'; font-size:9pt; font-weight:400; font-style:normal; text-decoration:none;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:12pt; font-weight:600;\">Add contact</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))

