"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
from PyQt4 import QtCore, QtGui
from os.path import basename
from twisted.python import log
from os.path import basename
from widgets import vcardeditor
from widgets.chat import chatwidget
from twisted.internet import threads
import base64
import ftwidget
import weakref
from booleanwidget import booleanWidget
from ftwidget import FTDownloadWidget,FTUploadWidget
from adduserwidget import addUserWidget
from lineeditwidget import lineeditWidget
from include.constants import RESOURCEPATH

class abstractEvent:
	def __init__(self,parent):
		self.parent=weakref.proxy(parent)
		self.alive=True
		self.widgets=[]
		self.typ="dummy"
		self.category=None
		self.ID=None

	def setType(self,typ):
		self.typ=unicode(typ)

	def setCategory(self,category):
		self.category=unicode(category)
		if self.ID:
			self.parent.refreshTray()

	def addWidget(self,widget):
		self.widgets.append(weakref.ref(widget))

	def getWidgets(self):
		ret=[]
		for widget in self.widgets:
		    ret.append(widget())
		return ret

	def accept(self):
		if not self.alive:
			return False
		for widget in self.widgets:
			widget().eventAccepted()
		self.alive=False

		return True

	def reject(self):
		if not self.alive:
			return False
		for widget in self.widgets:
			widget().eventRejected()
		self.alive=False
		return True

class booleanEvent(abstractEvent):
	def __init__(self,parent):
		abstractEvent.__init__(self,parent)
		self.acceptHandler=None
		self.acceptDict=[]
		self.rejectHandler=None
		self.rejectDict=[]

	def setAcceptHandler(self,acceptHandler,acceptDict=[]):
		self.acceptHandler=acceptHandler
		self.acceptDict=acceptDict

	def setRejectHandler(self,rejectHandler,rejectDict=[]):
		self.rejectHandler=rejectHandler
		self.rejectDict=rejectDict

	def accept(self,data=[]):
		if abstractEvent.accept(self):
			if self.acceptHandler:
				self.acceptHandler(*self.acceptDict+data)
        	self.parent.main.reactor.callLater(0,self.parent.removeEvent,int(self.ID))

	def reject(self,data=[]):
		if abstractEvent.reject(self):
			if self.rejectHandler:
				self.rejectHandler(*self.rejectDict+data)
			self.parent.main.reactor.callLater(0,self.parent.removeEvent,int(self.ID))

class FTDownloadEvent(abstractEvent):
	def __init__(self,parent):
		abstractEvent.__init__(self,parent)
		self.SID=None
		self.currentFile=""
		self.jid=""
		self.fileSize=1
		self.fileTransfered=0

	def setFileTransfered(self,transfered):
		self.fileTransfered=transfered
		for widget in self.widgets:
			widget().setFileTransfered(transfered)

	def transferFinished(self):
		for widget in self.widgets:
			widget().transferFinished()

	def setFileSize(self,size):
		self.fileSize=size
		for widget in self.widgets:
			widget().setFileSize(size)

	def setCurrentFile(self,file):
		self.currentFile=file
		for widget in self.widgets:
			widget().setCurrentFile(file)

	def setJid(self,jid):
		self.jid=jid
		for widget in self.widgets:
			widget().setJid(jid)

	def accept(self):
		if abstractEvent.accept(self):
		 	self.parent.main.reactor.callLater(0,self.parent.removeEvent,int(self.ID))

	def reject(self):
		if self.parent.main.client.ft.has_key(self.SID):
			self.parent.main.client.ft[self.SID].finish()
		if abstractEvent.reject(self):
			self.parent.main.reactor.callLater(0,self.parent.removeEvent,int(self.ID))

class FTUploadEvent(abstractEvent):
	def __init__(self,parent):
		abstractEvent.__init__(self,parent)
		self.queue={}
		self.SID=None

	def setQueue(self,queue):
		self.queue=queue
		for widget in self.widgets:
			widget().setQueue(queue)

	def setCurrentFile(self,file):
		for widget in self.widgets:
			widget().setCurrentFile(file)

	def setJid(self,jid):
		for widget in self.widgets:
			widget().setJid(jid)

	def setFileSize(self,size):
		for widget in self.widgets:
			widget().setFileSize(size)

	def setFileTransfered(self,transfered):
		for widget in self.widgets:
			widget().setFileTransfered(transfered)

	def transferFinished(self):
		for widget in self.widgets:
			widget().transferFinished()

	def accept(self):
		if abstractEvent.accept(self):
		 	self.parent.main.reactor.callLater(0,self.parent.removeEvent,int(self.ID))

	def reject(self):
		if self.parent.main.client.ft.has_key(self.SID):
			self.parent.main.client.ft[self.SID].finish()
		if abstractEvent.reject(self):
			self.parent.main.reactor.callLater(0,self.parent.removeEvent,int(self.ID))

class fileClass:
	def __init__(self,name,path,description):
		self.name=name
		self.path=path
		self.description=description
		self.sid=None

class events:
	def __init__(self,main):
		self.main=main
		self.filetransferQueue={}
		self.filetransferWidget={}
		self.filetransfer={}
		#self.events=[]
		self.events={}
		self.trayIcon=None
		self.jabbimIcon=None
		self.timer=QtCore.QTimer()
		QtCore.QObject.connect(self.timer, QtCore.SIGNAL("timeout ()"),self.timeout)
		#QtCore.QObject.connect(self.main.ui.eventsListWidget, QtCore.SIGNAL("itemDoubleClicked ( QListWidgetItem * )"),self.itemClicked)
		#self.main.ui.eventsListWidget.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
		self.ID=0
		self.blankIcon=QtGui.QPixmap(16,16)
		self.blankIcon.fill(QtCore.Qt.transparent)

		self.messagesLayout=QtGui.QVBoxLayout(self.main.ui.messages)
		self.messagesLayout.setContentsMargins(2,2,2,2)
		self.filetransfersLayout=QtGui.QVBoxLayout(self.main.ui.fileTransfers)
		self.filetransfersLayout.setContentsMargins(2,2,2,2)
		self.authorizationsLayout=QtGui.QVBoxLayout(self.main.ui.authorizations)
		self.authorizationsLayout.setContentsMargins(2,2,2,2)
		self.otherLayout=QtGui.QVBoxLayout(self.main.ui.other)
		self.otherLayout.setContentsMargins(2,2,2,2)


		self.main.ui.authorizations.hide()
		self.main.ui.fileTransfers.hide()
		self.main.ui.messages.hide()
		self.main.ui.other.hide()

		colors=QtGui.QTreeWidget()
		self.main.ui.scrollAreaWidgetContents.palette().setColor(QtGui.QPalette.Window,QtGui.QColor(colors.palette().color(QtGui.QPalette.Base)))
		colors.deleteLater()
		del colors
		self.ftEvents={}

	def timeout(self):
		if self.jabbimIcon:
			self.main.tray.setIcon(self.trayIcon)
			self.main.ui.mainTabWidget.setTabIcon(self.main.ui.mainTabWidget.indexOf(self.main.ui.eventsTab),self.trayIcon)
		else:
			self.main.tray.setIcon(self.main.getCurrentTrayIcon())
			self.main.ui.mainTabWidget.setTabIcon(self.main.ui.mainTabWidget.indexOf(self.main.ui.eventsTab),QtGui.QIcon(self.blankIcon))
		self.jabbimIcon=not self.jabbimIcon

	def trayClicked(self):
		if len(self.events)!=0:
			for event in self.events.values():
				if event.category!="messages":
					return False
			self.events[self.events.keys()[0]].accept()
		return False

	def refreshTray(self):
		types=[]
		mainWindow=self.main
		if len(self.events)==0:
			if self.main.selfStatus!="":
				data=self.main.selfStatus
				mainWindow.tray.setToolTip(unicode(mainWindow.tr('Your status:'))+" "+unicode(self.main.status[data]))
			else:
				mainWindow.tray.setToolTip('')
		categories=[]
		for event in self.events.values():
			if not event.category in categories:
				if event.typ=="fileDownload":
					categories.append("_")
				else:
					categories.append(event.category)
		if len(categories)==0 or (len(categories)==1 and categories==["filetransfers"]):
			self.timer.stop()
			if self.jabbimIcon!=None:
				mainWindow.tray.setIcon(self.main.getCurrentTrayIcon())
				self.main.ui.mainTabWidget.setTabIcon(self.main.ui.mainTabWidget.indexOf(self.main.ui.eventsTab),QtGui.QIcon("images/16x16/categories/event.png"))
				if self.main.ui.mainTabWidget.currentIndex()==self.main.ui.mainTabWidget.indexOf(self.main.ui.eventsTab):
					self.main.ui.mainTabWidget.setCurrentIndex(0)
				self.jabbimIcon=None
		elif categories==["messages"]:
			self.trayIcon=QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/message.png")
			self.timer.start(1000)
		else:
			self.trayIcon=QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/event.png")
			self.timer.start(1000)
#		if not 'message' in types and not 'newMessage' in types:
	#		self.main.chat.flashStatus=False
		#self.main.ui.roster.refreshEvents()

	def getEvents(self,name,typ):
		ret=[]
		for key,event in self.events.iteritems():
			if event.typ==name and event.category==typ:
				ret.append(event)
		return ret

	def addEvent(self,event=None):
		if not event:
			self.events[self.ID]=abstractEvent(self)
		else:
			self.events[self.ID]=event
		self.events[self.ID].ID=self.ID
		self.ID+=1
		if self.events[self.ID-1].category:
			self.refreshTray()
		return self.events[self.ID-1]

	def removeEvent(self,ID):
		if not self.events.has_key(ID):
			return
		widget=self.events[ID].widgets[0]()
		category=self.events[ID].category
		if category=="messages":
			self.messagesLayout.removeWidget(widget)
			widget.setParent(None)
			widget.deleteLater()
			del widget
			if self.messagesLayout.count()==0:
				self.main.ui.messages.hide()
		elif category=="filetransfers":
			self.filetransfersLayout.removeWidget(widget)
			widget.setParent(None)
			widget.deleteLater()
			del widget
			if self.filetransfersLayout.count()==0:
				self.main.ui.fileTransfers.hide()
		elif category=="authorizations":
			self.authorizationsLayout.removeWidget(widget)
			widget.setParent(None)
			widget.deleteLater()
			del widget
			if self.authorizationsLayout.count()==0:
				self.main.ui.authorizations.hide()
		elif category=="other":
			self.otherLayout.removeWidget(widget)
			widget.setParent(None)
			widget.deleteLater()
			del widget
			if self.otherLayout.count()==0:
				self.main.ui.other.hide()
		if hasattr(self.events[ID],"SID"):
			if self.ftEvents.has_key(self.events[ID].SID):
				del self.ftEvents[self.events[ID].SID]
		del self.events[ID].widgets
		del self.events[ID]
		self.refreshTray()

	def removeAll(self):
		for i in range(len(self.events.keys())):
			self.removeEvent(self.events.keys()[0])

	def addWidget(self,widget,group="messages"):
		if group=="messages":
			widget.setParent(self.main.ui.messages)
			self.messagesLayout.addWidget(widget)
			self.main.ui.messages.show()
			return widget
		elif group=='filetransfers':
			widget.setParent(self.main.ui.fileTransfers)
			self.filetransfersLayout.addWidget(widget)
			self.main.ui.fileTransfers.show()
			return widget
		elif group=="authorizations":
			widget.setParent(self.main.ui.authorizations)
			self.authorizationsLayout.addWidget(widget)
			self.main.ui.authorizations.show()
			return widget
		elif group=="other":
			widget.setParent(self.main.ui.other)
			self.otherLayout.addWidget(widget)
			self.main.ui.other.show()
			return widget

	def addLineEditEvent(self,typ="invitation",category="other"):
		event=booleanEvent(self)
		event.setType(typ)
		event.setCategory(category)
		widget=lineeditWidget(event)
		widget=self.addWidget(widget,category)
		event.addWidget(widget)
		return self.addEvent(event)


	def addBooleanEvent(self,typ="message",category="messages"):
		event=booleanEvent(self)
		event.setType(typ)
		event.setCategory(category)
		widget=booleanWidget(event)
		widget=self.addWidget(widget,category)
		event.addWidget(widget)
		return self.addEvent(event)
		#return event


	def addAddUserEvent(self,jid,status):
		"""
		Adds 'Add User' Event.
		@type jid: unicode
		@param jid: Jabber ID of sender
		@type status: unicode
		@param status: senders status message
		"""
		events = self.main.events.getEvents("subscribe","authorizations")
		if len(events)==0:
			event=booleanEvent(self)
			event.setType("addUser")
			event.setCategory("authorizations")
			widget=addUserWidget(event)
			widget=self.addWidget(widget,"authorizations")
			widget.jids=[jid]
			event.addWidget(widget)
			widget.setData(jid,status)
		else:
			widget.jids.append(jid)
			event=events[0]
			widget.setData(widget.jids,status)
		
		
		event.setAcceptHandler(self.main.client._onSubscribe,[list(widget.jids),'online',False])
		event.setRejectHandler(self.main.client._onSubscribeReject,[list(widget.jids),'online',False])
		return self.addEvent(event)

	def addSubscribeEvent(self,jid,status):
		#	def sendPresence(self, to = None, show = None, status = None, priority = None, typ = None, caps = True):
		mainWindow=self.main
		self.addBooleanEvent(self.main.client.sendPresence,[jid,None,status,None,'subscribed'],self.main.client.sendPresence,[jid,None,status,None,'unsubscribed'],header=unicode(mainWindow.tr('Subscribe request')),text=unicode(mainWindow.tr('From:'))+" "+unicode(jid),name=jid,typ="subscribe")

	def isImage(self,file):
		if unicode(file).lower().endswith('.jpg'):
			return 'image/jpeg'
		if unicode(file).lower().endswith('.png'):
			return 'image/png'
		if unicode(file).lower().endswith('.gif'):
			return 'image/gif'
		if unicode(file).lower().endswith('.jpeg'):
			return 'image/jpeg'
		if unicode(file).lower().endswith('.bmp'):
			return 'image/bmp'
		if unicode(file).lower().endswith('.tiff'):
			return 'image/tiff'
		return False

	def makeFTPreview(self,file):
		img=QtGui.QImage(file)
		image=img.scaled(128,128,QtCore.Qt.KeepAspectRatio)#,QtCore.Qt.SmoothTransformation)
		return image

	def addFTUploadEvent(self,jid,files,descriptions,forceTree=False):
		print "addFTUploadEvent"
		if jid.find("/") == -1:
			res = self.main.client.roster['users'][jid].getHighestResource()
			jid+="/"+res
		if isinstance(files,dict):
			if not forceTree:
				j=self.main.getJid(jid)
				feature=False
				print jid
				if self.main.client.roster['users'].has_key(j.userhost()):
					print '1'
					if self.main.client.roster['users'][j.userhost()].resources.has_key(j.resource):
						print '2'
						feature=self.main.client.roster['users'][j.userhost()].resources[j.resource].hasFeature('http://dev.jabbim.cz/jabbim/treeft')
			else:
				feature=True
			if feature:
				d=self.main.client.sendFiles(jid, files) #files = {name:abs. path, ..}
				d.addCallback(self._addFTUploadEvent,jid,files,descriptions)
			else:
				print "starting ft upload"
				self._addFTUploadEvent(None,jid,files,descriptions,None)
		else:
			typ=self.isImage(files[0])
			j=self.main.getJid(jid)
			feature=False
			if self.main.client.roster['users'].has_key(j.userhost()):
				if self.main.client.roster['users'][j.userhost()].resources.has_key(j.resource):
					feature=self.main.client.roster['users'][j.userhost()].resources[j.resource].hasFeature('http://kopete.kde.org/protocol/file-preview')
			print 'feature',feature
			if typ!=False and feature:
				print 'generating file preview'
				d=threads.deferToThread(self.makeFTPreview,files[0])
				d.addCallback(self._addFTUploadEvent,jid,files,descriptions,'image/png')
			else:
				print "starting ft upload"
				self._addFTUploadEvent(None,jid,files,descriptions,None)

	def _addFTUploadEvent(self,data,jid,files,descriptions,previewType=None):
		#print jid,previewType,preview
		print "_addFTUploadEvent"
		filesQueue={}
		preview=None
		if data:
			print "got data",data,type(data)
			if isinstance(data,QtGui.QImage):
				bytes=QtCore.QByteArray()
				buf=QtCore.QBuffer(bytes)
				buf.open(QtCore.QIODevice.WriteOnly)
				data.save(buf, "PNG")
				preview=base64.encodestring(str(bytes))
			else:
				files=data[1]
				text=""
				for name,value in files.iteritems():
					filesQueue[name]=fileClass(name,value[0],descriptions[name])
					filesQueue[name].sid=value[1]
		if isinstance(files,list):
			f={}
			for file in files:
				f[file]=[file]
			files=f
		if len(filesQueue)==0:
			for name,value in files.iteritems():
				filesQueue[name]=fileClass(name,value[0],descriptions[name])

		if jid.find("/") == -1:
			res = self.main.client.roster['users'][jid].getHighestResource()
		else:
			jid, res = jid.split("/", 1)



		event=FTUploadEvent(self)
		event.setType("ftUpload")
		event.setCategory("filetransfers")
		
		event.jid=jid+"/"+res
		widget=FTUploadWidget(event)
		widget=self.addWidget(widget,"filetransfers")
		event.addWidget(widget)

		k=filesQueue.keys()[0]
		file=filesQueue[k]
		event.setCurrentFile(file.name)
		event.setJid(jid)
		event.setQueue(filesQueue)
		del event.queue[file.name]
		

		if res==None:
			if file.sid:
				sid=file.sid
				self.main.client.sendFile(jid+'/'+res, file.name, file.path,descriptions[file.name],preview=preview,previewType='image/png',sid=sid)
			else:
				sid=self.main.client.sendFile(jid, file.name, basename(file.path),descriptions[file.name],preview=preview,previewType='image/png')
			tab,index=self.main.chat.findTab(jid,typ=['chat'])
		else:
			if file.sid:
				sid=file.sid
				self.main.client.sendFile(jid+'/'+res, file.name, file.path,descriptions[file.name],preview=preview,previewType='image/png',sid=sid)
			else:
				sid=self.main.client.sendFile(jid+'/'+res,basename(file.name), file.path,descriptions[file.name],preview=preview,previewType='image/png')
			tab,index=self.main.chat.findTab(jid+'/'+res,typ=['chat'])
		event.SID=sid
		event.setFileSize(int(self.main.client.ft[sid].size))
		self.ftEvents[sid]=event
		self.addEvent(event)
		mainWindow=self.main
		mainWindow.tray.showMessage(unicode(mainWindow.tr("Sending file "))+basename(file.name)+mainWindow.tr(" to ")+unicode(jid), mainWindow.tr("You can see progress of sending in Events tab in main window."), QtGui.QSystemTrayIcon.Information, 4000)

		if tab:
			tab.chat.textEditWrite(self.main.webkitThemeFactory.genChatStatus(unicode(mainWindow.tr("Sending file"))+" "+basename(file.name),self.main.now()))
			tab.chat.lastMessageFrom=""


	def addFTDownloadEvent(self,jid,file,description,sid,size):
		# descriptions['soubor']='popis'
		file=unicode(file)
		#text="<b>"+basename(unicode(file))+'</b>'

		if jid.find("/") == -1:
			showJid = jid
			showRes = self.main.client.roster['users'][jid].getHighestResource()
		else:
			showJid, showRes = jid.split("/", 1)

		event=FTDownloadEvent(self)
		event.setType("ftDownload")
		event.setCategory("filetransfers")
		widget=FTDownloadWidget(event)
		widget=self.addWidget(widget,"filetransfers")
		event.addWidget(widget)
		event.setCurrentFile(file)
		print "SHOWJID",showJid, jid
		event.setJid(showJid)
		event.setFileSize(int(size))
		event.SID=sid
		# get event height (based on font size)
		tab,index=self.main.chat.findTab(unicode(jid),typ=['chat'])
		mainWindow=self.main
		if tab:
			tab.chat.textEditWrite(self.main.webkitThemeFactory.genChatStatus(unicode(mainWindow.tr("Receiving file"))+" "+unicode(basename(file)),self.main.now()))
			tab.chat.lastMessageFrom=""

		self.ftEvents[sid]=event
		self.addEvent(event)
  		self.main.client.dispatcher.publishEvent('FTDownloadEvent', weakref.ref(event))

	def nextFTUploadEvent(self,sid):
		event=self.ftEvents[sid]
		jid=event.jid
		
		if event.queue[event.queue.keys()[0]].sid:
			self._nextFTUploadEvent(None,sid,None)
		else:
			file=event.queue[event.queue.keys()[0]].name
			typ=self.isImage(file)
			j=self.main.getJid(jid)
			feature=False
			if self.main.client.roster.has_key(j.userhost()):
				if self.main.client.roster[j.userhost()].resources.has_key(j.resource):
					feature=self.main.client.roster[j.userhost()].resources[j.resource].hasFeature('http://kopete.kde.org/protocol/file-preview')
			if typ!=False and feature:
				print 'generating file preview'
				d=threads.deferToThread(self.makeFTPreview,files[0])
				d.addCallback(self._nextFTUploadEvent,sid,'image/png')
			else:
				self._nextFTUploadEvent(None,sid,None)

	def _nextFTUploadEvent(self,preview,sid,previewType=False):
		event=self.ftEvents[sid]
		jid=event.jid
		file=event.queue[event.queue.keys()[0]]
		description=event.queue[file.name].description
		del event.queue[file.name]


		if preview:
			bytes=QtCore.QByteArray()
			buf=QtCore.QBuffer(bytes)
			buf.open(QtCore.QIODevice.WriteOnly)
			preview.save(buf, "PNG")
			preview=base64.encodestring(str(bytes))

		widget=event.getWidgets()[0]
		#widget.setText(text)
		event.setCurrentFile(file.name)
		event.setQueue(event.queue)
		mainWindow=self.main
		if file.sid:
			sid2=file.sid
			self.main.client.sendFile(jid, file.name, file.path, description,preview=preview,previewType=previewType,sid=sid2)
		else:
			sid2=self.main.client.sendFile(jid, basename(file.name), file.path, description,preview=preview,previewType=previewType)
		event.setFileSize(int(self.main.client.ft[sid2].size))
		event.SID=sid2
		self.ftEvents[sid2]=event
		del self.ftEvents[sid]
		#mainWindow.tray.showMessage(mainWindow.tr("Sending file ")+basename(file)+mainWindow.tr(" to ")+unicode(jid), mainWindow.tr("You can see progress of sending in Events tab in main window."), QtGui.QSystemTrayIcon.Information, 4000)


		tab,index=self.main.chat.findTab(jid,typ=['chat'])
		if tab:
			tab.chat.textEditWrite(self.main.webkitThemeFactory.genChatStatus(unicode(mainWindow.tr("Sending file"))+" "+unicode(basename(file.name)),self.main.now()))
			tab.chat.lastMessageFrom=""
