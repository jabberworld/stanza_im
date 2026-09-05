import os
from PyQt4 import QtCore, QtGui
import weakref
from lineeditwidget_ui import *

class lineeditWidget(QtGui.QWidget):
	def __init__(self,event,parent=None):
		QtGui.QWidget.__init__(self,parent)
		self.event=weakref.proxy(event)
		self.ui=Ui_Form()
		self.ui.setupUi(self)
		self.metrics=QtGui.QFontMetrics(self.ui.text.font())
		QtCore.QObject.connect(self.ui.accept,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.ui.reject,QtCore.SIGNAL("clicked()"),self.reject)
		self.ui.text.setTextFormat(QtCore.Qt.RichText)
		self.ui.label.setTextFormat(QtCore.Qt.RichText)


	def getSafeText(self,text,width):
		ret=""
		for word in text.split(' '):
			ret+=unicode(self.metrics.elidedText(word,QtCore.Qt.ElideMiddle, width))+" "
		return ret[:-1]

	def setText(self,text):
		top_parent=self.parentWidget().parentWidget().parentWidget().parentWidget().parentWidget().parentWidget().width()
		self.setMinimumWidth(top_parent-10)
		self.ui.text.setText(self.getSafeText(text,self.width()-10))

	def setLabel(self,text):
		self.ui.label.setText(text)

	def setAcceptText(self,text):
		self.ui.accept.setText(text)

	def setRejectText(self,text):
		self.ui.reject.setText(text)

	def setLineEditText(self,text):
		self.ui.lineEdit.setText(text)

	def setEchoMode(self,mode=0):
		self.ui.lineEdit.setEchoMode(mode)

	def eventRejected(self):
		pass
	
	def eventAccepted(self):
		pass

	def accept(self):
		self.event.accept([unicode(self.ui.lineEdit.text())])

	def reject(self):
		self.event.reject()
