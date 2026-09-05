'''
Created on 16.4.2010

@author: sef
'''
from PyQt4 import QtGui, QtCore
import widgets
class aboutDialog(QtGui.QDialog):
	def __init__(self,parent):
		QtGui.QDialog.__init__(self,parent)
		self.setModal(False)
		self.ui = widgets.about_ui.Ui_about_window()
		self.ui.setupUi(self)
		self.ui.version.setTextFormat(QtCore.Qt.RichText)
		self.ui.version.setText(parent.version + "<br/>" +
			"PyQt: " + unicode(QtCore.PYQT_VERSION_STR) + "<br/>" +
			"Qt: "   + unicode(QtCore.QT_VERSION_STR))
		QtCore.QObject.connect(self.ui.mucLink, QtCore.SIGNAL("linkActivated(QString)"), parent.support)
