'''
Created on 16.4.2010

@author: sef
'''
from PyQt4 import QtCore, QtGui
from widgets import tooltip
import traceback
import sys
from twisted.python import log
from include.constants import RESOURCEPATH

class AvatarLabel(QtGui.QLabel):
	def __init__(self,main,parent):
		QtGui.QLabel.__init__(self,parent)
		self.setObjectName("selfAvatar")
		self.main=main
		self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
		self.setMinimumWidth(64)
		self.setAlignment(QtCore.Qt.AlignCenter)
		self.tool = None

	def mouseDoubleClickEvent(self,event):
		self.main.identityEditor()
		event.accept()

	def contextMenuEvent(self,event):
		self.main.offlineMenu.move(event.globalX(),event.globalY())
		self.main.offlineMenu.popup(QtCore.QPoint(event.globalX(),event.globalY()))
		event.accept()

	def event(self, event):
		# tooltip request
		if int(event.type()) == 110:
			x = int(event.globalX())
			y = int(event.globalY())
			if not self.tool:
				jid = self.main.client.jid.userhost()
				self.tool = tooltip.ToolTip(self.main, jid, jid, QtCore.QPoint(x, y), False)
				self.tool.leaveEvent = self.tooltipLeaveEvent
			self.tool.show()
		return QtGui.QWidget.event(self,event)

	def tooltipLeaveEvent(self, event):
		self.tool.hide()
		self.tool.deleteLater()
		self.tool = None

	def leaveEvent(self,event):
		self.main.reactor.callLater(0.2, self._leaveEvent)

	def _leaveEvent(self):
		if self.tool and not self.tool.focus:
			self.tooltipLeaveEvent(None)

	def refreshToolTip(self):
		if self.main.client:
			text = self.main.getToolTip(self.main.client.jid.userhost())
#			self.setToolTip(text)
			# set tooltip also for tray icon
			# and utils.getWindowsVersion()!="vista"
			if sys.platform == 'win32':
				#contact = self.main.client.getContactByJid(jid)
				text=unicode(self.main.status.get(self.main.selfStatus, ''))
				self.main.tray.setToolTip(text)
			else:
				self.main.tray.setToolTip(text)

class avatarLoader(QtCore.QThread):
	def __init__(self,parent,path,avatarDef):
		QtCore.QThread.__init__(self,parent)
		self.path=path
		self.avatarDef=avatarDef

	def run(self):
		path=unicode(self.path)
		avatarDef=dict(self.avatarDef)
		hashe = []
		try:
			for hash in avatarDef.itervalues():
				if not hash in hashe and hash and hash!="None":
					hashe.append(unicode(str(hash)))
		except:
			message = unicode(traceback.format_exc(), 'utf-8')
			log.err( message)
		frame=QtGui.QImage(RESOURCEPATH+"images/32x32/frame.png")
		for hash in hashe:
			try:
				avatar=QtGui.QImage(path+'/'+hash)
				width=int(avatar.width())
				height=int(avatar.height())
				if avatar.isNull():
					log.err("avatar " + path+'/'+ hash + "cannot be loaded")
					continue
				avatar=avatar.scaled(25,25,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
				result=QtGui.QImage(32,32,QtGui.QImage.Format_ARGB32)
				result.fill(QtCore.Qt.transparent)
				# we have to implement this one:
				#if os.path.exists("themes/"+self.config['theme']+"/frame-32.png"):
					#frame=QtGui.QImage("themes/"+self.config['theme']+"/frame-32.png")
				#else:
				painter=QtGui.QPainter(result)
				painter.drawImage((32-avatar.width())/2,(32-avatar.height())/2,avatar)
				painter.drawImage(0,0,frame)
				painter.end()
				self.emit(QtCore.SIGNAL("imageLoaded(QString,QImage,int,int)"),QtCore.QString(hash),QtGui.QImage(result),int(width),int(height))
				del painter
				del result
			except:
				message = unicode(traceback.format_exc(), 'utf-8')
				log.err(message)

