# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/events/ftuploadwidget.ui'
#
# Created: Mon Apr 19 15:20:37 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_FTUploadWidget(object):
    def setupUi(self, FTUploadWidget):
        FTUploadWidget.setObjectName("FTUploadWidget")
        FTUploadWidget.resize(181, 168)
        self.gridLayout = QtGui.QGridLayout(FTUploadWidget)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.filename = QtGui.QLabel(FTUploadWidget)
        self.filename.setObjectName("filename")
        self.horizontalLayout.addWidget(self.filename)
        self.toolButton = QtGui.QToolButton(FTUploadWidget)
        self.toolButton.setCheckable(True)
        self.toolButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.toolButton.setObjectName("toolButton")
        self.horizontalLayout.addWidget(self.toolButton)
        self.closeButton = QtGui.QPushButton(FTUploadWidget)
        self.closeButton.setMaximumSize(QtCore.QSize(20, 16777215))
        self.closeButton.setText("")
        self.closeButton.setObjectName("closeButton")
        self.horizontalLayout.addWidget(self.closeButton)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 2)
        self.jid = QtGui.QLabel(FTUploadWidget)
        self.jid.setObjectName("jid")
        self.gridLayout.addWidget(self.jid, 1, 0, 1, 2)
        self.more = QtGui.QLabel(FTUploadWidget)
        self.more.setTextFormat(QtCore.Qt.RichText)
        self.more.setObjectName("more")
        self.gridLayout.addWidget(self.more, 2, 0, 1, 2)
        self.transferInfo = QtGui.QLabel(FTUploadWidget)
        self.transferInfo.setWordWrap(True)
        self.transferInfo.setObjectName("transferInfo")
        self.gridLayout.addWidget(self.transferInfo, 3, 0, 1, 2)
        self.progressBar = QtGui.QProgressBar(FTUploadWidget)
        self.progressBar.setProperty("value", 0)
        self.progressBar.setObjectName("progressBar")
        self.gridLayout.addWidget(self.progressBar, 4, 0, 1, 2)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 5, 0, 1, 1)
        self.reject = QtGui.QPushButton(FTUploadWidget)
        self.reject.setObjectName("reject")
        self.gridLayout.addWidget(self.reject, 5, 1, 1, 1)

        self.retranslateUi(FTUploadWidget)
        QtCore.QObject.connect(self.toolButton, QtCore.SIGNAL("clicked(bool)"), self.more.setShown)
        QtCore.QMetaObject.connectSlotsByName(FTUploadWidget)

    def retranslateUi(self, FTUploadWidget):
        FTUploadWidget.setWindowTitle(QtGui.QApplication.translate("FTUploadWidget", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.filename.setText(QtGui.QApplication.translate("FTUploadWidget", "Smileys_test.zip", None, QtGui.QApplication.UnicodeUTF8))
        self.toolButton.setText(QtGui.QApplication.translate("FTUploadWidget", "More", None, QtGui.QApplication.UnicodeUTF8))
        self.jid.setText(QtGui.QApplication.translate("FTUploadWidget", "a@jabbim.cz", None, QtGui.QApplication.UnicodeUTF8))
        self.more.setText(QtGui.QApplication.translate("FTUploadWidget", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"</style></head><body style=\" font-family:\'MS Shell Dlg 2\'; font-size:8.25pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:8pt;\">File.txt</span></p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-size:8pt;\">test.zip</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-size:8pt;\">music.zip</p></body></html>", None, QtGui.QApplication.UnicodeUTF8))
        self.transferInfo.setText(QtGui.QApplication.translate("FTUploadWidget", "Zbyva: 30 s (255 kB/s)", None, QtGui.QApplication.UnicodeUTF8))
        self.reject.setText(QtGui.QApplication.translate("FTUploadWidget", "Close", None, QtGui.QApplication.UnicodeUTF8))

