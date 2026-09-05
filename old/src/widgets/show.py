from PyQt4 import QtGui, QtCore
from twisted.python import log
 
class showLabel(QtGui.QLabel):
        def __init__(self, parent, defaulttext = ""):
                QtGui.QLabel.__init__(self, None)
		self.defaulttext = unicode(defaulttext)
		self.setText(self.defaulttext)
                self.parent = parent
        def mouseReleaseEvent(self,event):
		text = unicode(self.text())
		text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
		if text == self.defaulttext: # Asi neni nechytrejsi
			text = u"" 
		self.parent.lineEdit.setText(text)
		self.parent.lineEdit.show()
                self.hide()
		self.parent.lineEdit.setFocus(QtCore.Qt.MouseFocusReason)
		
class showLineEdit(QtGui.QLineEdit):
	def __init__(self, label, parent):
                QtGui.QLineEdit.__init__(self, parent)
		self.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
		self.label = label
		self.parent = parent

	def keyPressEvent(self, event):
		key = event.key()
		if key == QtCore.Qt.Key_Escape:
			QtCore.QObject.disconnect(self, QtCore.SIGNAL("lostFocus()"), self.parent.lineEditToLabel)
			self.label.show()
			self.hide()
			QtCore.QObject.connect(self, QtCore.SIGNAL("lostFocus()"), self.parent.lineEditToLabel)
		else:
			QtGui.QLineEdit.keyPressEvent(self, event)

class showWidget(QtGui.QWidget):
	def __init__(self, main, layout, labeltext = ""):
		QtGui.QWidget.__init__(self, None)
		self.main = main
		self.label = showLabel(self, labeltext)
		layout.addWidget(self.label)
		self.lineEdit = showLineEdit(self.label, self)
		self.lineEdit.hide()
		QtCore.QObject.connect(self.lineEdit,QtCore.SIGNAL("lostFocus()"),self.lineEditToLabel)
		QtCore.QObject.connect(self.lineEdit,QtCore.SIGNAL("returnPressed()"),self.lineEditToLabel)
                layout.addWidget(self.lineEdit)
#		self.resize(300,50)
		
	def lineEditToLabel(self):
		text = unicode(self.lineEdit.text())
		text4label = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
		self.label.setText(text4label)
		if text == u"":
			self.label.setText(self.label.defaulttext)
		self.label.show()
		self.lineEdit.hide()
		self.main.client.sendPresence(
			status = text,
			show = self.main.client.roster['users'][self.main.client.jid.userhost()].resources[self.main.client.jid.resource].show
		)

	def setText(self, text):
		self.label.setText(text)
		self.lineEdit.setText(text)

