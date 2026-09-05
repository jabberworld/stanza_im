import os
from PyQt4 import QtCore, QtGui
import weakref
from booleanwidget_ui import *

class booleanWidget(QtGui.QWidget):
	def __init__(self,event,parent=None):
		QtGui.QWidget.__init__(self,parent)
		self.event=weakref.proxy(event)
		self.ui=Ui_Form()
		self.ui.setupUi(self)
		QtCore.QObject.connect(self.ui.accept,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.ui.reject,QtCore.SIGNAL("clicked()"),self.reject)

	def setText(self,text):
		self.ui.text.setText(text)

	def setAcceptText(self,text):
		self.ui.accept.setText(text)

	def setRejectText(self,text):
		self.ui.reject.setText(text)

	def eventRejected(self):
		pass
	
	def eventAccepted(self):
		pass

	def accept(self):
		self.event.accept()

	def reject(self):
		self.event.reject()
