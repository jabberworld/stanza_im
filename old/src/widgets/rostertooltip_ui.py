# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/rostertooltip.ui'
#
# Created: Mon Apr 19 15:20:35 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_RosterToolTip(object):
    def setupUi(self, RosterToolTip):
        RosterToolTip.setObjectName("RosterToolTip")
        RosterToolTip.resize(332, 156)
        self.gridlayout = QtGui.QGridLayout(RosterToolTip)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.vboxlayout = QtGui.QVBoxLayout()
        self.vboxlayout.setSpacing(6)
        self.vboxlayout.setMargin(0)
        self.vboxlayout.setObjectName("vboxlayout")
        self.hboxlayout = QtGui.QHBoxLayout()
        self.hboxlayout.setSpacing(6)
        self.hboxlayout.setMargin(0)
        self.hboxlayout.setObjectName("hboxlayout")
        self.nickname = QtGui.QLabel(RosterToolTip)
        self.nickname.setObjectName("nickname")
        self.hboxlayout.addWidget(self.nickname)
        self.metaWidget = QtGui.QWidget(RosterToolTip)
        self.metaWidget.setObjectName("metaWidget")
        self.hboxlayout.addWidget(self.metaWidget)
        self.vcard = QtGui.QLabel(RosterToolTip)
        self.vcard.setMaximumSize(QtCore.QSize(16, 16777215))
        self.vcard.setCursor(QtCore.Qt.PointingHandCursor)
        self.vcard.setObjectName("vcard")
        self.hboxlayout.addWidget(self.vcard)
        self.activity = QtGui.QLabel(RosterToolTip)
        self.activity.setMaximumSize(QtCore.QSize(18, 18))
        self.activity.setText("")
        self.activity.setObjectName("activity")
        self.hboxlayout.addWidget(self.activity)
        self.mood = QtGui.QLabel(RosterToolTip)
        self.mood.setMaximumSize(QtCore.QSize(18, 18))
        self.mood.setText("")
        self.mood.setObjectName("mood")
        self.hboxlayout.addWidget(self.mood)
        self.tune = QtGui.QLabel(RosterToolTip)
        self.tune.setMaximumSize(QtCore.QSize(18, 18))
        self.tune.setText("")
        self.tune.setObjectName("tune")
        self.hboxlayout.addWidget(self.tune)
        self.vboxlayout.addLayout(self.hboxlayout)
        self.jid = QtGui.QLabel(RosterToolTip)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.jid.sizePolicy().hasHeightForWidth())
        self.jid.setSizePolicy(sizePolicy)
        self.jid.setWordWrap(True)
        self.jid.setOpenExternalLinks(True)
        self.jid.setObjectName("jid")
        self.vboxlayout.addWidget(self.jid)
        self.subscription = QtGui.QLabel(RosterToolTip)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.subscription.sizePolicy().hasHeightForWidth())
        self.subscription.setSizePolicy(sizePolicy)
        self.subscription.setMouseTracking(True)
        self.subscription.setWordWrap(True)
        self.subscription.setObjectName("subscription")
        self.vboxlayout.addWidget(self.subscription)
        self.status = QtGui.QTextBrowser(RosterToolTip)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.status.sizePolicy().hasHeightForWidth())
        self.status.setSizePolicy(sizePolicy)
        self.status.setMaximumSize(QtCore.QSize(16777215, 50))
        self.status.setFrameShape(QtGui.QFrame.NoFrame)
        self.status.setFrameShadow(QtGui.QFrame.Plain)
        self.status.setLineWidth(0)
        self.status.setOpenExternalLinks(True)
        self.status.setObjectName("status")
        self.vboxlayout.addWidget(self.status)
        spacerItem = QtGui.QSpacerItem(256, 1, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.vboxlayout.addItem(spacerItem)
        self.gridlayout.addLayout(self.vboxlayout, 0, 1, 2, 1)
        self.label = QtGui.QLabel(RosterToolTip)
        self.label.setMaximumSize(QtCore.QSize(16777215, 64))
        self.label.setObjectName("label")
        self.gridlayout.addWidget(self.label, 0, 0, 1, 1)
        spacerItem1 = QtGui.QSpacerItem(20, 1, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridlayout.addItem(spacerItem1, 1, 0, 1, 1)

        self.retranslateUi(RosterToolTip)
        QtCore.QMetaObject.connectSlotsByName(RosterToolTip)

    def retranslateUi(self, RosterToolTip):
        RosterToolTip.setWindowTitle(QtGui.QApplication.translate("RosterToolTip", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.nickname.setText(QtGui.QApplication.translate("RosterToolTip", "<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'DejaVu Sans\'; font-size:12pt; font-weight:400; font-style:normal; text-decoration:none;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-weight:600;\">HanzZ</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.jid.setText(QtGui.QApplication.translate("RosterToolTip", "<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'DejaVu Sans\'; font-size:12pt; font-weight:400; font-style:normal; text-decoration:none;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-weight:600;\">JID:</span></p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.subscription.setText(QtGui.QApplication.translate("RosterToolTip", "Subscription:", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("RosterToolTip", "Avatar", None, QtGui.QApplication.UnicodeUTF8))

