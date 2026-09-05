# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/profiles.ui'
#
# Created: Mon Apr 19 15:20:33 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_profilesWindow(object):
    def setupUi(self, profilesWindow):
        profilesWindow.setObjectName("profilesWindow")
        profilesWindow.resize(322, 301)
        icon = QtGui.QIcon()
        icon.addFile(":/images/16x16/apps/jabbim.png")
        profilesWindow.setWindowIcon(icon)
        self.centralwidget = QtGui.QWidget(profilesWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.gridlayout = QtGui.QGridLayout(self.centralwidget)
        self.gridlayout.setObjectName("gridlayout")
        self.label = QtGui.QLabel(self.centralwidget)
        self.label.setObjectName("label")
        self.gridlayout.addWidget(self.label, 0, 0, 1, 2)
        self.line = QtGui.QFrame(self.centralwidget)
        self.line.setFrameShape(QtGui.QFrame.HLine)
        self.line.setFrameShadow(QtGui.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridlayout.addWidget(self.line, 1, 0, 1, 2)
        self.profilesList = QtGui.QListWidget(self.centralwidget)
        self.profilesList.setIconSize(QtCore.QSize(22, 22))
        self.profilesList.setObjectName("profilesList")
        self.gridlayout.addWidget(self.profilesList, 2, 0, 5, 1)
        self.newProfile = QtGui.QPushButton(self.centralwidget)
        self.newProfile.setObjectName("newProfile")
        self.gridlayout.addWidget(self.newProfile, 2, 1, 1, 1)
        self.changePassword = QtGui.QPushButton(self.centralwidget)
        self.changePassword.setObjectName("changePassword")
        self.gridlayout.addWidget(self.changePassword, 3, 1, 1, 1)
        self.removeProfile = QtGui.QPushButton(self.centralwidget)
        self.removeProfile.setObjectName("removeProfile")
        self.gridlayout.addWidget(self.removeProfile, 4, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 141, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridlayout.addItem(spacerItem, 5, 1, 1, 1)
        self.pushButton = QtGui.QPushButton(self.centralwidget)
        self.pushButton.setObjectName("pushButton")
        self.gridlayout.addWidget(self.pushButton, 6, 1, 1, 1)
        profilesWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(profilesWindow)
        QtCore.QObject.connect(self.pushButton, QtCore.SIGNAL("clicked()"), profilesWindow.close)
        QtCore.QMetaObject.connectSlotsByName(profilesWindow)

    def retranslateUi(self, profilesWindow):
        profilesWindow.setWindowTitle(QtGui.QApplication.translate("profilesWindow", "Profiles", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("profilesWindow", "<h2>Profiles</h2>", None, QtGui.QApplication.UnicodeUTF8))
        self.newProfile.setText(QtGui.QApplication.translate("profilesWindow", "New", None, QtGui.QApplication.UnicodeUTF8))
        self.changePassword.setText(QtGui.QApplication.translate("profilesWindow", "Change Password", None, QtGui.QApplication.UnicodeUTF8))
        self.removeProfile.setText(QtGui.QApplication.translate("profilesWindow", "Remove", None, QtGui.QApplication.UnicodeUTF8))
        self.pushButton.setText(QtGui.QApplication.translate("profilesWindow", "Close", None, QtGui.QApplication.UnicodeUTF8))

