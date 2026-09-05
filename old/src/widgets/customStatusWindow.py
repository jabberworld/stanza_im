'''
Created on 16.4.2010

@author: sef
'''
from PyQt4 import QtGui, QtCore
import widgets.status_ui
class customStatusWindow(QtGui.QDialog):
	def __init__(self,jid,show=None,parent=None, main=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.ui = widgets.status_ui.Ui_status()
		self.ui.setupUi(self)
		self.timer=QtCore.QTimer()
		self.main = main
		self.main.app.connect(self.timer, QtCore.SIGNAL("timeout ()"),self.timeout)
		self.main.app.connect(self.ui.status, QtCore.SIGNAL("cursorPositionChanged ()"),self.timerStop)
		self.main.app.connect(self.ui.status, QtCore.SIGNAL("textChanged ()"),self.timerStop)
		self.ui.statusBox.hide()
		self.ui.save.hide()
		self.timer.start(1000)
		self.i=4
		self.jid=jid
		self.show=show
		self.timeout()

	def timerStop(self):
		self.timer.stop()
		self.ui.time.setText("")

	def timeout(self):
		if self.i!=0:
			self.ui.time.setText(self.tr("Window will be closed in ")+unicode(self.i)+self.tr(" seconds."))
			self.i-=1
		else:
			self.accept()
			self.timer.stop()
	def accept(self):
		if type(self.jid) != list:
			self.main.client.sendPresence(to=self.jid,show = unicode(self.show), status = unicode(self.ui.status.toPlainText ()))
		else:
			show = unicode(self.show)
			status = unicode(self.ui.status.toPlainText())
			for jid in self.jid:
				self.main.client.sendPresence(to=jid, show = show, status = status)
		self.done(1)
