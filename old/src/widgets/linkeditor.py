import os
from PyQt4 import QtCore, QtGui
from linkeditor_ui import *

class linkEditorDialog(QtGui.QDialog):
	def __init__(self,widget,url=None,text=None,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.ui=Ui_linkEditor()
		self.ui.setupUi(self)
		self.widget=widget
		if url:
			self.ui.url.setText(url)
			self.ui.linkText.setFocus(QtCore.Qt.OtherFocusReason)
		if text:
			self.ui.linkText.setText(text)
			self.ui.url.setFocus(QtCore.Qt.OtherFocusReason)

	def accept(self):
		self.widget.ui.line.textCursor().insertHtml("<a href=\"%s\">%s</a>"%(unicode(self.ui.url.text()),unicode(self.ui.linkText.text())))
		print "inserting link ","<a href=\"%s\">%s</a>"%(unicode(self.ui.url.text()),unicode(self.ui.linkText.text()))
		self.done(1)
