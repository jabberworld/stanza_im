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
from extra_ui import *

from twisted.python import log
import base64
from widgets.events.ftwidget import FTDownloadWidget

class extraDialog(QtGui.QDialog):
	"""
	Jabbim Extra Dialog
	"""
	def __init__(self,typ,main,parent=None,download=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(True)
		self.ui=Ui_Extra()
		self.ui.setupUi(self)
		self.main=main
		self.ui.l=QtGui.QVBoxLayout(self.ui.prog)
		self.ui.stackedWidget.setCurrentIndex(0)
		if not download:
			if typ=="emoticons":
				self.ui.label.setText("<h3>"+self.tr("Emoticons")+"</h3>")
				self.main.client.callRemote('rpc@jabbim.cz/service', 'getList', ('emoticons/',)).addCallback(self._emoticonsListArrived)#.addErrback(self._emoticonsListError)
				self.directory='emoticons/'
			elif typ=="plugins":
				self.ui.label.setText("<h3>"+self.tr("Plugins")+"</h3>")
				self.main.client.callRemote('rpc@jabbim.cz/service', 'getList', ('plugins/',)).addCallback(self._emoticonsListArrived)#.addErrback(self._emoticonsListError)
				self.directory='plugins/'
			elif typ=="chatskins":
				self.ui.label.setText("<h3>"+self.tr("Chatskins")+"</h3>")
				self.main.client.callRemote('rpc@jabbim.cz/service', 'getList', ('chatskins/',)).addCallback(self._emoticonsListArrived)#.addErrback(self._emoticonsListError)
				self.directory='chatskins/'

		QtCore.QObject.connect(self.ui.listWidget,QtCore.SIGNAL("currentItemChanged( QListWidgetItem *, QListWidgetItem *)"),self.selectionChanged)
		self.ui.preview.hide()
		self.download=download
		if self.download:
			self.accept()

	def selectionChanged(self,item,old):
		if item:
			name=unicode(item.text())
			self.main.client.callRemote('rpc@jabbim.cz/service', 'getInfo', (self.directory+name,)).addCallback(self._emoticonArrived).addErrback(self._emoticonsListError)
	
	def _emoticonArrived(self,data):
		print data
		data=data[0][0]
		self.ui.textBrowser.setPlainText(data[1])
		pixmap=QtGui.QPixmap()
		image=base64.decodestring(str(data[2]))
		pixmap.loadFromData(image)
		self.ui.preview.show()
		self.ui.preview.setPixmap(pixmap)
		#print unicode(data)
	
	def _emoticonsListArrived(self,data):
		#(({'white': 'Tohle je kratky popis, vlastne nic duleziteho .. \n', 'black': 'Tohle je kratky popis, vlastne nic duleziteho .. \n'},), None)
		emoticons=data[0][0]
		for name,desc in emoticons.iteritems():
			item=QtGui.QListWidgetItem(unicode(name),self.ui.listWidget)
			item.setToolTip(unicode(desc))

	def _emoticonsListError(self,data):
		print data

	def showDownload(self,event):
		if not event():
			return
		#self.w=QtGui.QDialog(self.window)
		
		self.progress=FTDownloadWidget(event())
		self.progress.setParent(self.ui.prog)
		self.ui.l.addWidget(self.progress)
		#self.progress.eventAccepted=self.eventAccepted
		self.progress.eventRejected=self.reject
		self.ui.stackedWidget.setCurrentIndex(1)
		self.progress.show()
		event().addWidget(self.progress)
		self.main.client.dispatcher.unregisterHandler("FTDownloadEvent", self.showDownload)

	def _getFile(self,data):
		self.main.client.dispatcher.registerHandler("FTDownloadEvent", self.showDownload, "FTDownloadEvent")
		print "DATA:",unicode(data)
		sid=unicode(data[0][0])
		self.main.allowedSids[sid]=self.main.realHomeDir+'/'+unicode(self.downloading)
		print "GOT SID",sid
		print "KEYS ARE",self.main.client.ft.keys()
#		if self.main.client.ft.has_key(sid):
#			if self.main.client.ft[sid].method==None:
#				#self.main.events.addFTDownloadEvent(unicode(self.main.client.ft[sid].tojid),unicode(self.main.client.ft[sid].tojid),"",sid)
#				self.main.events.filetransferWidget[sid]=self.progress
#				self.main.events.filetransferWidget[sid].typ='extra'
#				self.main.events.filetransfer[sid]={'queueId':sid}
#				filename = self.main.realHomeDir+'/'+self.main.client.ft[sid].fileprops['name']
#				self.main.client.receiveFile(sid, self.main.client.ft[sid].answerId,  filename)
				#self.main.allowedSids.remove(sid)
		#else:
			#self.main.allowedSids.remove(sid)
		#self.done(1)

	def accept(self):
		if self.download:
##			b=QtGui.QPushButton()
##			self.progress=QtGui.QProgressDialog(self.tr('Downloading file:')+" "+self.download,"", 0, 100, self.main.preferencesWindow)
##			self.progress.setCancelButton(b)
##			b.hide()
			self.main.client.callRemote('rpc@jabbim.cz/service','getFile',(self.download+'.zip',)).addCallback(self._getFile)

		else:
			name=unicode(self.ui.listWidget.currentItem().text())
##			b=QtGui.QPushButton()
##			self.progress=QtGui.QProgressDialog(self.tr('Downloading pack:')+" "+name,"", 0, 100, self.main.preferencesWindow)
##			self.progress.setCancelButton(b)
##			b.hide()
			self.downloading=self.directory+name+'.zip'
			self.main.client.callRemote('rpc@jabbim.cz/service','getFile',(self.directory+name+'.zip',)).addCallback(self._getFile)
		#self.done(1)

	#def reject(self):
		#self.close()
