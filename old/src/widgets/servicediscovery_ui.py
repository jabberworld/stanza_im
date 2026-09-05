# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'src/widgets/servicediscovery.ui'
#
# Created: Mon Apr 19 15:20:32 2010
#      by: PyQt4 UI code generator 4.7.2
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_serviceDiscovery(object):
    def setupUi(self, serviceDiscovery):
        serviceDiscovery.setObjectName("serviceDiscovery")
        serviceDiscovery.resize(551, 556)
        self.gridlayout = QtGui.QGridLayout(serviceDiscovery)
        self.gridlayout.setMargin(9)
        self.gridlayout.setSpacing(6)
        self.gridlayout.setObjectName("gridlayout")
        self.treeWidget = QtGui.QWidget(serviceDiscovery)
        self.treeWidget.setObjectName("treeWidget")
        self.gridlayout.addWidget(self.treeWidget, 1, 0, 1, 2)
        self.close = QtGui.QPushButton(serviceDiscovery)
        self.close.setObjectName("close")
        self.gridlayout.addWidget(self.close, 2, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(621, 27, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.gridlayout.addItem(spacerItem, 2, 0, 1, 1)
        self.hboxlayout = QtGui.QHBoxLayout()
        self.hboxlayout.setMargin(0)
        self.hboxlayout.setSpacing(6)
        self.hboxlayout.setObjectName("hboxlayout")
        self.label = QtGui.QLabel(serviceDiscovery)
        self.label.setObjectName("label")
        self.hboxlayout.addWidget(self.label)
        self.server = QtGui.QComboBox(serviceDiscovery)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Policy(7), QtGui.QSizePolicy.Policy(0))
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.server.sizePolicy().hasHeightForWidth())
        self.server.setSizePolicy(sizePolicy)
        self.server.setEditable(True)
        self.server.setObjectName("server")
        self.hboxlayout.addWidget(self.server)
        self.reload = QtGui.QPushButton(serviceDiscovery)
        self.reload.setObjectName("reload")
        self.hboxlayout.addWidget(self.reload)
        self.gridlayout.addLayout(self.hboxlayout, 0, 0, 1, 2)

        self.retranslateUi(serviceDiscovery)
        QtCore.QObject.connect(self.close, QtCore.SIGNAL("clicked()"), serviceDiscovery.reject)
        QtCore.QMetaObject.connectSlotsByName(serviceDiscovery)

    def retranslateUi(self, serviceDiscovery):
        serviceDiscovery.setWindowTitle(QtGui.QApplication.translate("serviceDiscovery", "Service Discovery", None, QtGui.QApplication.UnicodeUTF8))
        self.close.setText(QtGui.QApplication.translate("serviceDiscovery", "Close", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("serviceDiscovery", "Server:", None, QtGui.QApplication.UnicodeUTF8))
        self.reload.setText(QtGui.QApplication.translate("serviceDiscovery", "OK", None, QtGui.QApplication.UnicodeUTF8))

