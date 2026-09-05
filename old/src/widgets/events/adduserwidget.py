import os
from PyQt4 import QtCore, QtGui
import weakref
from booleanwidget_ui import *
from widgets import vcardeditor

class addUserWidget(QtGui.QWidget):
	def __init__(self,event,parent=None):
		QtGui.QWidget.__init__(self,parent)
		self.event=weakref.proxy(event)
		self.ui=Ui_Form()
		self.ui.setupUi(self)
		self.metrics=QtGui.QFontMetrics(self.ui.text.font())
		self.ui.accept.setText(self.tr("Yes"))
		self.ui.reject.setText(self.tr("No"))
		QtCore.QObject.connect(self.ui.accept,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.ui.reject,QtCore.SIGNAL("clicked()"),self.reject)
		QtCore.QObject.connect(self.ui.text,QtCore.SIGNAL("linkActivated ( const QString & )"),self.showUserMenu)
		self.jid=""
		print "addUserWidget"

	def getSafeText(self,text,width):
		ret=""
		for word in text.split(' '):
			ret+=unicode(self.metrics.elidedText(word,QtCore.Qt.ElideMiddle, width))+" "
		return ret[:-1]

	def showUserMenu(self,link):
		print "usermenu"
		menu=QtGui.QMenu(self)
		menu.addAction(self.tr("Show VCard"),self.showVCard)
		menu.addAction(self.tr("Chat"),self.openChat)
		menu.popup(QtCore.QPoint(QtGui.QCursor.pos()))

	def showVCard(self,b=False):
		vcardeditor.vcardEditorDialog(self.event.parent.main, self.jid, self.event.parent.main, False).show()

	def openChat(self,b=False):
		self.event.parent.main.chat.addChatTab(self.jid,self.jid,self.event.parent.main.getIcon(self.jid,'online',size="16x16"))
		self.event.parent.main.chat.activate()

	def setData(self,jid,message=None):
		top_parent=self.parentWidget().parentWidget().parentWidget().parentWidget().parentWidget().parentWidget().width()
		self.setMinimumWidth(top_parent-10)
		if isinstance(jid,unicode):
			self.jid=unicode(jid)
			text=unicode(self.tr("Do you want to add user"))
			text+=" <a href=\"http://jid\">"+self.getSafeText(self.jid,self.width()-10)+"</a> "
			text+=unicode(self.tr("to you roster?"))
			if message:
				text+="<br/><i>"+self.getSafeText(unicode(message),self.width()-10)+"</i>"
		else:
			text=unicode(self.tr("Do you want to add this users?"))
			for j in jid:
				text+="<br/>"+self.getSafeText(unicode(j),self.width()-10)
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
