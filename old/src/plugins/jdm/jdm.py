# -*- coding: utf-8 -*-
import sys,os,time,urllib,re
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui
from urllib import quote, unquote
from twisted.python import log
from include import utils
import base64
from widgets import dataforms,legacyforms
from widgets.events.ftwidget import FTDownloadWidget
from twisted.internet import reactor
try:
	from hashlib import md5
except:
	log.msg('Please upgrade to python2.5')
	from md5 import new as md5

if sys.platform=="win32":
	import _winreg

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['jidPreview']={'type':'jid-list','label':self.main.tr("JIDs for preview list"), 'value':[]}
		self.config['iconMode']={'type':'boolean','label':self.main.tr("Show files as icons"),'value':'True'}
		self.config['jdmNavigIcon']={'type':'boolean','label':self.main.tr("Show JDM navigation icon"),'value':'True'}
class Plugin(plugins.PluginBase):
	def __init__(self,main, homedir, plugindir):
		print "Loading JDM Plugin"
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'jdm'
		self.installTranslator("locales/")
		self.description = self.tr('Jabbim disk manager')
		self.author = u"Josef 'Pepeq' Halíček & Martin 'Lolek' Tomašík"
		self.name = self.tr('JDM Plugin')
		self.version = '0.1149'
		self.category = ['utils']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.pwd=""
		self.configDialog=config(self)
		if main:
			self.loadConfig()
			self.window = self.loadWindow("%s/jdm_ui.py" % self.pluginDir,self.main)
			self.wizard = self.loadDialog("%s/jdw_ui.py" % self.pluginDir,self.main)
			self.downloadQueue=[]
			self.window.setWindowIcon(self.main.windowIcon())
##			self.window.ui.list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
##			self.window.ui.list.startDrag=self.startDrag
##			self.window.ui.list.setAcceptDrops(True)
##			self.window.ui.list.dropEvent = self.dropEvent
##			self.window.ui.list.dragMoveEvent = self.dragMoveEvent
##			self.window.ui.list.dragEnterEvent = self.dragEnterEvent
##			self.window.ui.line_jid.setText(self.main.client.jid.userhost())
			self.typ = "public"
			self.callTab=None
			self.thumbIndex=0
			self.esPath=""
			self.wizard.ui.download.setIcon(QtGui.QIcon("%s/icons/document-save.png" % self.pluginDir))
			self.wizard.ui.upload.setIcon(QtGui.QIcon("%s/icons/upload.png" % self.pluginDir))
			self.wizard.ui.remove.setIcon(QtGui.QIcon("%s/icons/edit-delete.png" % self.pluginDir))
			self.window.ui.buttonHome.setIcon(QtGui.QIcon("%s/icons/home.png" % self.pluginDir))
			self.window.ui.publicButton.setIcon(QtGui.QIcon("%s/icons/jdisk-public-24.png" % self.pluginDir))
			self.window.ui.privateButton.setIcon(QtGui.QIcon("%s/icons/jdisk-private-24.png" % self.pluginDir))
			self.window.ui.album.setIcon(QtGui.QIcon("%s/icons/jalbum-32.png" % self.pluginDir))
			self.window.ui.easyshare.setIcon(QtGui.QIcon("%s/icons/easy_share32.png" % self.pluginDir))
			self.wizard.ui.public.setIcon(QtGui.QIcon("%s/icons/jdisk-public-24.png" % self.pluginDir))
			self.wizard.ui.private.setIcon(QtGui.QIcon("%s/icons/jdisk-private-24.png" % self.pluginDir))
			self.wizard.ui.album.setIcon(QtGui.QIcon("%s/icons/jalbum-32.png" % self.pluginDir))
			self.wizard.ui.es.setIcon(QtGui.QIcon("%s/icons/easy_share32.png" % self.pluginDir))
			self.wizard.ui.configuration.setIcon(QtGui.QIcon("%s/icons/easy_share32.png" % self.pluginDir))
			self.wizard.ui.configuration.hide()
			self.wizard.ui.filename.setText('')
			self.wizard.ui.filesize.setText('')
			self.window.ui.showMiniRoster.setIcon(self.main.ui.mainTabWidget.tabIcon(0))
			self.group=QtGui.QButtonGroup(self.window)
			self.group.setExclusive(False)
			self.update=False

			self.wizard.ui.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
			
			QtCore.QObject.connect(self.group,QtCore.SIGNAL("buttonClicked ( QAbstractButton * )"),self.buttonClicked)
			QtCore.QObject.connect(self.wizard.ui.up,QtCore.SIGNAL("clicked()"),self.up)
##			QtCore.QObject.connect(self.window.ui.reload,QtCore.SIGNAL("clicked()"),self.call)
##			QtCore.QObject.connect(self.window.ui.esUp,QtCore.SIGNAL("clicked()"),self.esUp)
##			QtCore.QObject.connect(self.window.ui.esPath,QtCore.SIGNAL("returnPressed()"),self.esPathFinished)
			QtCore.QObject.connect(self.wizard.ui.tree, QtCore.SIGNAL("itemSelectionChanged ( )"),self.selectionChanged)
			QtCore.QObject.connect(self.wizard.ui.path, QtCore.SIGNAL("returnPressed ( )"),self.pathChanged)
##			QtCore.QObject.connect(self.window.ui.list,QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.fileMenu)
			QtCore.QObject.connect(self.wizard.ui.tree,QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.fileMenu)
			QtCore.QObject.connect(self.window.ui.buttonDownload,QtCore.SIGNAL("clicked()"),self.downloadCurrentFile)
			QtCore.QObject.connect(self.window.ui.buttonDelete,QtCore.SIGNAL("clicked()"),self.removeCurrentFile)
			QtCore.QObject.connect(self.window.ui.buttonUpload,QtCore.SIGNAL("clicked()"),self.sendFile)
			QtCore.QObject.connect(self.window.ui.buttonHome,QtCore.SIGNAL("clicked()"),self.home)
			QtCore.QObject.connect(self.window.ui.publicButton,QtCore.SIGNAL("clicked()"),self.public)
			QtCore.QObject.connect(self.window.ui.privateButton,QtCore.SIGNAL("clicked()"),self.private)
			QtCore.QObject.connect(self.window.ui.album,QtCore.SIGNAL("clicked()"),self.album)
			QtCore.QObject.connect(self.window.ui.easyshare,QtCore.SIGNAL("clicked()"),self.easyshare)
			QtCore.QObject.connect(self.wizard.ui.public,QtCore.SIGNAL("clicked()"),self.public)
			QtCore.QObject.connect(self.wizard.ui.private,QtCore.SIGNAL("clicked()"),self.private)
			QtCore.QObject.connect(self.wizard.ui.album,QtCore.SIGNAL("clicked()"),self.album)
			QtCore.QObject.connect(self.wizard.ui.es,QtCore.SIGNAL("clicked()"),self.easyshare)
			QtCore.QObject.connect(self.wizard.ui.back,QtCore.SIGNAL("clicked()"),self.wBack)
			QtCore.QObject.connect(self.wizard.ui.download,QtCore.SIGNAL("clicked()"),self.downloadCurrentFile)
			QtCore.QObject.connect(self.wizard.ui.remove,QtCore.SIGNAL("clicked()"),self.removeCurrentFile)
			QtCore.QObject.connect(self.wizard.ui.upload,QtCore.SIGNAL("clicked()"),self.sendFile)
			QtCore.QObject.connect(self.wizard.ui.configuration,QtCore.SIGNAL("clicked()"),self.esConfiguration)
			QtCore.QObject.connect(self.window.ui.showMiniRoster,QtCore.SIGNAL("clicked()"),self.showMiniRoster)
			QtCore.QObject.connect(self.window.ui.desktop,QtCore.SIGNAL("clicked()"),self.leftDesktop)
			QtCore.QObject.connect(self.window.ui.computer,QtCore.SIGNAL("clicked()"),self.leftComputer)
			QtCore.QObject.connect(self.window.ui.right,QtCore.SIGNAL("itemDoubleClicked ( QTreeWidgetItem *,int )"),self.doubleClicked)
			#QtCore.QObject.connect(self.wizard.ui.tree,QtCore.SIGNAL("itemActivated ( QListWidgetItem *)"),self.doubleClicked)
			QtCore.QObject.connect(self.wizard.ui.tree,QtCore.SIGNAL("itemDoubleClicked ( QListWidgetItem *)"),self.doubleClicked)
			self.wizard.ui.filename.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
			def myMouseDoubleClickEvent(event):
				self.renameFile()
			self.wizard.ui.filename.mouseDoubleClickEvent = myMouseDoubleClickEvent
			QtCore.QObject.connect(self.wizard.ui.filename,QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.filenameMenu)

			
			self.model=QtGui.QDirModel()
			self.model.supportedDropActions=self.supportedDropActions
			self.model.flags=self.flags
			self.model.setReadOnly(False)
			self.window.ui.left.setModel(self.model)
			self.window.ui.left.setDragEnabled(True)
			self.window.ui.left.setAcceptDrops(True)
			self.window.ui.left.startDrag=self.leftStartDrag
			self.window.ui.left.dropMimeData=self.leftDropMimeData
			self.window.ui.left.mimetypes=self.mimeTypes
			self.window.ui.left.setDropIndicatorShown(True)
			self.window.ui.left.setDragDropMode(QtGui.QAbstractItemView.DragDrop)
			self.window.ui.left.dragEnterEvent=self.dragEnterEvent
			self.window.ui.left.dragMoveEvent = self.dragMoveEvent
			self.window.ui.left.dropEvent = self.dropEvent
			
			self.wizard.ui.l=QtGui.QVBoxLayout(self.wizard.ui.prog)
			
			
			self.window.ui.right.dropMimeData=self.rightDropMimeData
			self.window.ui.right.startDrag=self.rightStartDrag
			self.window.ui.right.mimeTypes=self.mimeTypes
			self.window.ui.right.setDragEnabled(True)
			self.window.ui.right.setAcceptDrops(True)

			self.log = False
			self.registerHandler('on_message', self.on_message, priority=4)
			self.registerHandler('on_ftEnd', self.on_ftEnd, priority = 4)
			self.registerHandler('FTDownloadEvent', self.FTDownloadEvent)
			self.registerHandler('FTFileReceivedEvent', self.FTFileReceivedEvent)
			self.obsah=[]
			self.dnd={}
			if not os.path.exists(self.main.realHomeDir+"/jdmcache"):
				os.mkdir(self.main.realHomeDir+"/jdmcache")
			self.cache=self.main.realHomeDir+"/jdmcache"
			self.cacheList=self.getConfig(self.cache+"/list.cfg")
			self.filesToOpen=[]
			self.window.ui.progress=QtGui.QProgressBar(self.window.ui.statusbar)
			self.window.ui.statusbar.addWidget(self.window.ui.progress,1)
			self.window.ui.progress.hide()
			self.leftDesktop()
			self.stopDownload=False

			#desktop integration
			self.registerHandler('on_pluginsLoaded', self.registerRemote)
			self.array=[]
			if self.config['jdmNavigIcon']=="True":
				self.navigLayout = QtGui.QHBoxLayout()
				home = QtGui.QToolButton(self.wizard.ui.page)
				home.setIcon(QtGui.QIcon("%s/icons/home.png" % self.pluginDir))
				home.setToolTip(self.tr("Home"))
				self.navigLayout.addWidget(home)
				refresh = QtGui.QToolButton(self.wizard.ui.page)
				refresh.setIcon(QtGui.QIcon("%s/icons/view-refresh.png" % self.pluginDir))
				refresh.setToolTip(self.tr("Refresh"))
				self.navigLayout.addWidget(refresh)
				public = QtGui.QToolButton(self.wizard.ui.page)
				public.setIcon(QtGui.QIcon("%s/icons/jdisk-public-24.png" % self.pluginDir))
				public.setToolTip(self.tr("Public disk"))
				self.navigLayout.addWidget(public)
				private = QtGui.QToolButton(self.wizard.ui.page)
				private.setIcon(QtGui.QIcon("%s/icons/jdisk-private-24.png" % self.pluginDir))
				private.setToolTip(self.tr("Private disk"))
				self.navigLayout.addWidget(private)
				album = QtGui.QToolButton(self.wizard.ui.page)
				album.setIcon(QtGui.QIcon("%s/icons/jalbum-32.png" % self.pluginDir))
				album.setToolTip(self.tr("Album"))
				self.navigLayout.addWidget(album)
				
				
				QtCore.QObject.connect(home,QtCore.SIGNAL("clicked()"),self.home)
				QtCore.QObject.connect(refresh,QtCore.SIGNAL("clicked()"),self.refresh)
				QtCore.QObject.connect(public,QtCore.SIGNAL("clicked()"),self.public)
				QtCore.QObject.connect(private,QtCore.SIGNAL("clicked()"),self.private)
				QtCore.QObject.connect(album,QtCore.SIGNAL("clicked()"),self.album)
				self.wizard.ui.rightLayout.insertLayout(0,self.navigLayout)
				self.key={}
				self.movesubmenu={}
		else:
			self.loadConfig(homedir)
	
	def up(self):
		path = unicode(self.wizard.ui.path.text())
		if path.endswith("/"):
			path=path[:-1]
		path = path.split("/")
		if len(path)==0:
			self.showSlot()
		else:
			p = "/".join(path[:-1])+"/"
			if p.endswith("easyshare/"):
				self.wizard.ui.path.setText(p.replace("/easyshare/",""))
			elif p.endswith("easyshare"):
				self.wizard.ui.path.setText(p.replace("/easyshare",""))
			else:
				self.wizard.ui.path.setText(p)
			self.pathChanged()
		
	def pathChanged(self):
		self.wizard.ui.filename.setText("")
		path = unicode(self.wizard.ui.path.text())
		if path.endswith("/"):
			path=path[:-1]
		path = path.split("/")
		if len(path)>=2:
			if len(path)>2:
				self.showSlot(path[0],path[1],"/".join(path[2:])+"/")
			else:
				self.showSlot(path[0],path[1])
		elif len(path)==1:
			self.showSlot(path[0])
		elif len(path)==0:
			self.showSlot()
			
	def clientCreated(self):
		self.jid = self.main.client.jid.userhost()
		self.pwd = ""
		plugins.PluginBase.clientCreated(self)

	def registerRemote(self):
		remote = self.main.getPlugin('remote')
		if remote != False and remote != None:
			remote.registerPluginFunc('jdm_public', self.remotePublic)
			utils.regWindowsMenu('Send to JDM Public', 'jdm_public')
			remote.registerPluginFunc('jdm_private', self.remotePrivate)
			utils.regWindowsMenu('Send to JDM Private', 'jdm_private')

	def unregisterRemote(self):
		remote = self.main.getPlugin('remote')
		if remote != False and remote != None:
			remote.unregisterPluginFunc('jdm_public')
			utils.unregWindowsMenu('Send to JDM Public')
			remote.unregisterPluginFunc('jdm_private')
			utils.unregWindowsMenu('Send to JDM Private')
        	
	def remotePublic(self, arg):
		self.main.showFiletransferDialog([arg], 'public@disk.jabbim.cz')
	def remotePrivate(self, arg):
		self.main.showFiletransferDialog([arg], 'private@disk.jabbim.cz')

	def on_remove(self):
		self.unregisterRemote()
		
	def esConfiguration(self):
		self.showPluginConfigDialog("easyshare",self.wizard)
		#self.easyshare()

	def wBack(self):
		self.wizard.ui.back.hide()
		#if self.wizard.ui.stackedWidget.currentIndex()==2:
			#self.wizard.progress.reject()
		#self.wizard.ui.stackedWidget.setCurrentIndex(0)

	def FTFileReceivedEvent(self,event):
		print "JDM FTFileReceivedEvent"
		if not event(): #or (self.window.isHidden() and self.wizard.isHidden()):
			return
		sid,id = event().acceptDict
		print "sid,id",sid,id
		print "self.main.ft",self.main.ft
		odesilatel=unicode(self.main.client.ft[sid].tojid.full())
		#event().accept()
		print "FT JID",unicode(self.main.ft[sid].tojid.full()),unicode(self.main.ft[sid].fromjid.full())
		if odesilatel.userhost()!="public@disk.jabbim.cz" and odesilatel.userhost()!="private@disk.jabbim.cz" and odesilatel.userhost()!="album@disk.jabbim.cz":
			return
		
		self.main.events.addFTDownloadEvent(odesilatel,filename,"",sid,self.ft[sid].fileprops['size'])
		self.main.client.receiveFile(sid, id,  filename)

	def FTDownloadEvent(self,event):
		if not event() or (self.window.isHidden() and self.wizard.isHidden()):
			return
		#self.w=QtGui.QDialog(self.window)
		try:
			self.wizard.progress.ui
			self.wizard.progress.reject()
		except:
			pass
		self.wizard.progress=FTDownloadWidget(event())
		self.wizard.progress.setJid(unicode(self.main.client.ft[event().SID].fromjid.userhost()))
		self.wizard.progress.setParent(self.wizard.ui.prog)
		self.wizard.ui.l.addWidget(self.wizard.progress)
		#self.wizard.progress.eventAccepted=self.eventAccepted
		self.wizard.progress.eventRejected=self.eventRejected
		self.wizard.progress.transferFinished=self.tFinished
		self.wizard.ui.stackedWidget.setCurrentIndex(2)
		self.wizard.progress.show()
		event().addWidget(self.wizard.progress)

	def tFinished(self):
		self.wizard.progress.ui.progressBar.hide()
		self.wizard.progress.ui.accept.show()
		self.wizard.progress.ui.transferInfo.setText(self.tr("Finished"))
		self.wizard.progress.ui.reject.hide()
		
	def eventRejected(self):
		self.wizard.progress.hide()
		self.wizard.ui.l.removeWidget(self.wizard.progress)
		self.wizard.progress.setParent(None)
		self.wizard.progress.deleteLater()
		del self.wizard.progress
		

	def dragEnterEvent(self, event):
		log.msg("left drag enter")
		if event.mimeData().hasText() or event.mimeData().ormat("text/uri-list"):
			event.acceptProposedAction()
		else:
			event.ignore()

	def flags(self,index):
		defaultFlags = QtGui.QDirModel.flags(self.model,index)
		return QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled | defaultFlags

	def supportedDropActions(self):
		return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

	def mimeTypes(self):
		# set mimetypes, which we accept
		return QtCore.QStringList(["text/plain","text/uri-list"])

	def leftDropMimeData(self,parent,index,data,action):
		path=unicode(self.model.fileInfo(index).absoluteFilePath())
		log.msg("left drop" + path)
		return True

	def rightDropMimeData(self,parent,index,data,action):
		new=[]
		if (data.hasUrls()):
			urlList=data.urls()
			if len(urlList)>0:
				for url in urlList:
					f=unicode(url.toLocalFile())
					if len(f)!=0:
						new.append(f)
		else:
			new=[unicode(data.text())]
		file=new
		if self.typ=="public":
			self.main.showFiletransferDialog(file, 'public@disk.jabbim.cz')
		elif self.typ=="private":
			self.main.showFiletransferDialog(file, 'private@disk.jabbim.cz')
		elif self.typ=="album":
			self.main.showFiletransferDialog(file, 'album@disk.jabbim.cz')
		return True

	def rightStartDrag(self,actions):
		# start dragging selected contact
		path=unicode(self.window.ui.right.currentItem().text())
		print "right drag",path
		self.window.ui.right.drag=QtGui.QDrag(self.window.ui.right)
		mimeData=QtCore.QMimeData()
		mimeData.setText(path)
		self.window.ui.right.drag.setMimeData(mimeData)
		self.window.ui.right.action=self.window.ui.right.drag.start(QtCore.Qt.CopyAction)

	def leftStartDrag(self,actions):
		# start dragging selected contact
		path=unicode(self.model.fileInfo(self.window.ui.left.currentIndex()).absoluteFilePath())
		print "left drag",path
		if os.path.isdir(path):
			#TODO easyshare
			return
		else:
			self.window.ui.left.drag=QtGui.QDrag(self.window.ui.left)
			mimeData=QtCore.QMimeData()
			mimeData.setText(path)
			self.window.ui.left.drag.setMimeData(mimeData)
			self.window.ui.left.action=self.window.ui.left.drag.start(QtCore.Qt.CopyAction)

	def leftDesktop(self):
##		HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders\Desktop
		folder=None
		if sys.platform=="win32":
			hkcu = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
			folders=_winreg.OpenKey(hkcu, r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders')
			try:
				(folder, typ) = _winreg.QueryValueEx(folders, "Desktop")
			except WindowsError:
				folder=None
		if folder:
			self.window.ui.left.setRootIndex(self.model.index(unicode(folder)))

	def leftComputer(self):
		self.window.ui.left.setRootIndex(self.model.index("/"))

	def esPathFinished(self):
		self.esPath=unicode(self.window.ui.esPath.text())
		if not self.esPath.endswith("/") and self.esPath!="":
			self.espath+="/"
		if self.esPath=="":
			self.easyshare()
		else:
			contact = self.main.client.getContactByJid(self.jid)
			jid=self.jid+"/"+contact.getHighestResource()
			#self.window.ui.esPath.setText(self.esPath)
			self.main.client.callRemote(jid, 'listShare',(unicode(self.esPath),)).addCallback(self.updateView)

	def esUp(self):
		d=self.esPath.split("/")
		if len(d)>2:
			self.esPath='/'.join(d[:-2])+"/"
			contact = self.main.client.getContactByJid(self.jid)
			jid=self.jid+"/"+contact.getHighestResource()
			self.window.ui.esPath.setText(self.esPath)
			self.main.client.callRemote(jid, 'listShare',(unicode(self.esPath),)).addCallback(self.updateView)
		elif len(self.esPath)!=0:
			self.easyshare()
	
	def easyshare(self):
		contact = self.main.client.getContactByJid(self.jid)
		if contact:
			jid=self.jid+"/"+contact.getHighestResource()
			self.main.client.callRemote(jid, 'getShares',()).addCallback(self.esGotShares)
			self.typ='easyshare'
			self.esPath=""
			#self.window.ui.esPath.setText(self.esPath)
##			self.window.ui.esWidget.show()
	
	def esGotShares(self,data):
		data=data[0][0]
		
		#self.window.ui.esPath.setText(self.esPath)
		#self.window.ui.list.clear()
		#self.window.ui.right.clear()
		#self.wizard.ui.tree.clear()
		icon=QtGui.QIcon(self.pluginDir+"/icons/folder.png")
		for d in data:
			#item=QtGui.QTreeWidgetItem(self.window.ui.right)
			item=QtGui.QListWidgetItem(self.wizard.ui.tree)
			item.setData(32,QtCore.QVariant(QtCore.QStringList([u"-1"])))
			item.setText(unicode(d))
			item.setIcon(icon)
			item.path=unicode(d)+"/"
		self.wizard.ui.stackedWidget.setCurrentIndex(1)
		self.wizard.ui.back.show()
		self.wizard.ui.remove.hide()
		self.wizard.ui.upload.hide()
		if self.jid==self.main.client.jid.userhost():
			self.wizard.ui.configuration.show()
		else:
			self.wizard.ui.configuration.hide()

	def buildContactMenu(self,menu,contact):
		"""
		Adds QAction to the menu above contact 
		"""
		self.action=menu.addAction(self.tr("Jabber Disk"))
		self.action.setData(QtCore.QVariant(unicode(contact.jid)))
		self.action.setObjectName("jdm_show_jdisk")
		self.action.setIcon(QtGui.QIcon("%s/icons/jdisk-public-24.png" % self.pluginDir))
		QtCore.QObject.connect(self.action,QtCore.SIGNAL("triggered ( bool )"),self.contactMenuToggled)

	def contactMenuToggled(self,b):
		"""
		User choose our QAction from contactMenu (menu above contact)
		"""
		jid=unicode(self.action.data().toString())
		self.showSlot(jid)
		self.action.deleteLater()

	def showMiniRoster(self):
		self.main.ui.roster.showMiniRoster(self.miniRosterAccepted)
	
	def miniRosterAccepted(self,jid):
		self.call(jid,'public')
		

	def setIconMode(self,bool):
		if bool:
			if self.typ=="album":
				self.window.ui.list.setGridSize(QtCore.QSize(160,160))
			else:
				self.window.ui.list.setGridSize(QtCore.QSize(128,96))
			self.window.ui.list.setViewMode(QtGui.QListView.IconMode)
			self.config["iconMode"]='True'
		else:
			self.window.ui.list.setGridSize(QtCore.QSize())
			self.window.ui.list.setViewMode(QtGui.QListView.ListMode)
			self.config["iconMode"]='False'
		self.config.write()

	def public(self, path="/"):
##		self.window.ui.esWidget.hide()
		self.wizard.ui.tree.clear()
		#self.call(typ='public')
		self.showSlot(jid = self.main.client.jid.userhost(), typ='public', path=path)
		self.wizard.ui.path.setText(self.jid+"/"+self.typ+path)

	def private(self, path="/"):
##		self.window.ui.esWidget.hide()
		self.wizard.ui.tree.clear()
		#self.call(typ='private')
		self.showSlot(jid = self.main.client.jid.userhost(), typ='private', path=path)
		self.wizard.ui.path.setText(self.jid+"/"+self.typ+path)

	def album(self, path="/"):
##		self.window.ui.esWidget.hide()
		self.wizard.ui.tree.clear()
		#self.call(typ='album')
		self.showSlot(jid = self.main.client.jid.userhost(), typ='album', path=path)
		self.wizard.ui.path.setText(self.jid+"/"+self.typ+path)

	def home(self):
		self.wizard.ui.tree.clear()
		self.showSlot(jid = self.main.client.jid.userhost())
		#self.call(self.main.client.jid.userhost())
	
	def refresh(self):
		self.wizard.ui.tree.clear()
		self.pathChanged()
		#path=self.pwd
		#if self.pwd=="/":
			#path=None
		#self.showSlot(jid = self.jid, typ=self.typ, path=path)

	def buttonClicked(self,button):
		if button.typ=="album":
			self.showSlot(unicode(button.jid), typ="album")
	#		if button.isChecked():
	#			tab,i=self.main.chat.findTab(unicode(button.jid))
#				if tab:
#					tab.chat.ui.webkit.page().mainFrame().evaluateJavaScript('var group = document.createElement(\'div\'); group.innerHTML="<div id=\\"light\\" style=\\"position: fixed;top: 10%;right:10%;left: 10%;width: 80%;height: 70%;padding: 16px;background-color: white;z-index:1002;border: 1px solid black;overflow: auto;\\"></div>";document.body.appendChild(group);')
#					self.callTab=tab
#					self.call(unicode(button.jid),"album")
#			else:
#				tab,i=self.main.chat.findTab(unicode(button.jid))
#				if tab:
#					tab.chat.ui.webkit.page().mainFrame().evaluateJavaScript("removeById(\'light\');")
		else:
			self.showSlot(unicode(button.jid), typ="public")
#			if button.isChecked():
#				tab,i=self.main.chat.findTab(unicode(button.jid))
#				if tab:
#					tab.chat.ui.webkit.page().mainFrame().evaluateJavaScript('var group = document.createElement(\'div\'); group.innerHTML="<div id=\\"light\\" style=\\"position: fixed;top: 10%;right:10%;left: 10%;width: 80%;height: 70%;padding: 16px;background-color: white;z-index:1002;border: 1px solid black;overflow: auto;\\"></div>";document.body.appendChild(group);')
#					self.callTab=tab
#					self.call(unicode(button.jid),"public")
#			else:
#				tab,i=self.main.chat.findTab(unicode(button.jid))
#				if tab:
#					tab.chat.ui.webkit.page().mainFrame().evaluateJavaScript("removeById(\'light\');")
			

	def chatMenuItemTriggered(self,action):
		cmd=unicode(action.objectName())
		if cmd=="show_my_disk":
			tab,i=self.main.chat.findTab(unicode(action.parent().parent().jid))
			print tab,i
			if tab:
				tab.chat.ui.webkit.page().mainFrame().evaluateJavaScript('var group = document.createElement(\'div\'); group.innerHTML="<div id=\\"light\\" style=\\"position: fixed;top: 10%;right:10%;left: 10%;width: 80%;height: 70%;padding: 16px;background-color: white;z-index:1002;border: 1px solid black;overflow: auto;\\"><a href = \\"javascript:void(0)\\" onclick = \\"removeById(\'light\');\\">Close</a></div>";document.body.appendChild(group);')
				self.callTab=tab
				self.call(unicode(action.parent().parent().jid),"album")
			#anchor="http://disk.jabbim.cz/%s/"%(unicode(self.main.client.jid.userhost()))
			#QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))
		elif cmd=="show_users_disk":
			anchor="http://disk.jabbim.cz/%s/"%(unicode(action.parent().parent().jid))
			QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))
		elif cmd=="show_my_disk_jdm":
			self.showSlot(self.main.client.jid.userhost())
		elif cmd=="show_my_album_jdm":
			self.showSlot(self.main.client.jid.userhost(),typ='album')
		elif cmd=="show_users_disk_jdm":
			self.showSlot(unicode(action.parent().parent().jid))
		elif cmd=="show_users_album_jdm":
			self.showSlot(unicode(action.parent().parent().jid),typ="album")
		elif cmd=="show_my_album":
			anchor="http://album.jabbim.cz/%s/"%(unicode(self.main.client.jid.userhost()))
			QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))
		elif cmd=="show_users_album":
			anchor="http://album.jabbim.cz/%s/"%(unicode(action.parent().parent().jid))
			QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))

	def buildChatWidget(self,jid,layout,widget):
		jid=self.main.getJid(jid)
		# create Archive button
		button=QtGui.QPushButton()
		button.setCheckable(False)
		button.setIconSize(QtCore.QSize(16,16))
		button.setIcon(QtGui.QIcon("%s/icons/jalbum-32.png" % self.pluginDir))
		button.jid=unicode(jid.userhost())
		button.typ="album"
		button.setToolTip("Show Photos")
		#button.setText(self.tr("Show Photos"))
		# add button to buttonGroup
		self.group.addButton(button)
		layout.addWidget(button)

		button=QtGui.QPushButton()
		button.setCheckable(False)
		button.setIconSize(QtCore.QSize(16,16))
		button.setIcon(QtGui.QIcon("%s/icons/jdisk-public.png" % self.pluginDir))
		button.jid=unicode(jid.userhost())
		button.typ="public"
		button.setToolTip("Show Jdisk")
		#button.setText(self.tr("Show Jdisk"))
		# add button to buttonGroup
		self.group.addButton(button)
		layout.addWidget(button)

		w=QtGui.QWidget()
		l=QtGui.QHBoxLayout(w)
		w.label1=QtGui.QLabel(w)
		l.addWidget(w.label1)
		w.label2=QtGui.QLabel(w)
		l.addWidget(w.label2)
		w.label3=QtGui.QLabel(w)
		l.addWidget(w.label3)

		widget.addCoolWidget(w)


	def statsThumbArrived(self,thumb,data,w,widget):
		cacheFile="%s/%s.jpg" % (self.cache,self.main.getJid(widget.jid).userhost()+data[0][0])
		print "cacheFile",cacheFile,(self.cache,self.main.getJid(widget.jid).userhost()+data[0][0])
		if thumb:
			print "saving",data[0]
			image=base64.decodestring(str(thumb[0]))
			pixmap=QtGui.QPixmap()
			pixmap.loadFromData(image)
			#self.thumbs[data[0]].setIcon(QtGui.QIcon(pixmap))
			self.checkAndCreateDirectory(cacheFile)
			f=open(cacheFile,"wb")
			f.write(image)
			f.close()
			self.cacheList[cacheFile] = md5(image).hexdigest()
			self.cacheList.write()
		else:
			pixmap=QtGui.QPixmap(cacheFile)

		pixmap=pixmap.scaled(64,64,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
		if not w.label1.pixmap():
			w.label1.setPixmap(pixmap)
		elif not w.label2.pixmap():
			w.label2.setPixmap(pixmap)
		elif not w.label3.pixmap():
			w.label3.setPixmap(pixmap)
			return
		else:
			return

		del data[0]
		if len(data)!=0:
			if not self.stopDownload:
				cacheFile="%s/%s.jpg" % (self.cache,self.main.getJid(widget.jid).userhost()+data[0][0])
				if os.path.isfile(cacheFile):
					self.main.client.reactor.callLater(0,self.statsThumbArrived,None,data,w,widget)
				else:
					self.main.client.callRemote('rpc@jabbim.cz/service', 'getThumb', (self.main.getJid(widget.jid).userhost(),data[0][0])).addCallback(self.statsThumbArrived,data,w,widget)



	def sendFile(self):
		if self.typ=="public":
			self.main.client.sendMessage("public@disk.jabbim.cz", u"cd "+self.pwd)
			self.main.sendFiles('public@disk.jabbim.cz')
			self.array.append(('public@disk.jabbim.cz',self.pwd,'cd'))
		elif self.typ=="private":
			self.main.client.sendMessage("private@disk.jabbim.cz", u"cd "+self.pwd)
			self.main.sendFiles('private@disk.jabbim.cz')
			self.array.append(('private@disk.jabbim.cz',self.pwd,'cd'))
		elif self.typ=="album":
			self.main.client.sendMessage("album@disk.jabbim.cz", u"cd "+self.pwd)
			self.main.sendFiles('album@disk.jabbim.cz')
			self.array.append(('album@disk.jabbim.cz',self.pwd,'cd'))

##	def startDrag(self,actions):
##		# start dragging selected contact
##		item=self.window.ui.list.currentItem()
##
##		self.drag=QtGui.QDrag(self.window.ui.list)
##		mimeData=QtCore.QMimeData()
##		mimeData.setText("http://disk.jabbim.cz/"+self.main.client.jid.userhost()+"/"+item.text())
##		mimeData.setUrls([QtCore.QUrl("http://disk.jabbim.cz/"+self.main.client.jid.userhost()+"/"+item.text())])
##		self.dnd=item
##		self.drag.setMimeData(mimeData)
##		self.action=self.drag.start(QtCore.Qt.CopyAction)
##
	def dropEvent(self, event):
		print "left drop event"
		if event.mimeData().hasText():
			f=unicode(event.mimeData().text())
			index=self.window.ui.left.indexAt(event.pos())
			path=unicode(self.model.fileInfo(index).absoluteFilePath())
			if not os.path.isdir(path):
				path=os.path.dirname(path)
			print "left drop",path
			if self.typ=="public":
				self.main.allowedJids["public@disk.jabbim.cz/"+unicode(f)]=path
				self.main.client.sendMessage("public@disk.jabbim.cz", u"get //"+self.jid+"\%public"+unicode(self.pwd+f).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				#self.filesToOpen.append(self.cache+"/"+unicode(item.text()))
			elif self.typ=="private":
				self.main.allowedJids["private@disk.jabbim.cz/"+unicode(f)]=path
				self.main.client.sendMessage("private@disk.jabbim.cz", u"get //"+self.jid+"\%private"+unicode(self.pwd+f).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				#self.filesToOpen.append(self.cache+"/"+unicode(item.text()))
			elif self.typ=="album":
				self.main.allowedJids["album@disk.jabbim.cz/"+unicode(f)]=path
				self.main.client.sendMessage("album@disk.jabbim.cz", u"get //"+self.jid+"\%album"+unicode(self.pwd+f).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				#self.filesToOpen.append(self.cache+"/"+unicode(item.text()))
			elif self.typ=="easyshare":
				contact = self.main.client.getContactByJid(self.jid)
				if contact:
					jid=self.jid+"/"+contact.getHighestResource()
					data=[]
					items=self.window.ui.right.selectedItems()
					for item in items:
						data.append(self.getPath(item))
					self.main.client.callRemote(jid, 'getFiles',(data,))


			event.acceptProposedAction()
##
	def dragMoveEvent(self, event):
		index=self.window.ui.left.indexAt(event.pos())
		if index:
			self.window.ui.left.setCurrentIndex(index)
		event.acceptProposedAction()
##	def dragEnterEvent(self, event):
##		if event.mimeData().hasText() or event.mimeData().hasFormat("text/uri-list"):
##			event.acceptProposedAction()
##		elif event.mimeData().hasText():
##			if self.main.getJid(unicode(event.mimeData().text())):
##				event.acceptProposedAction()
##			else:
##				event.ignore()
##		else:
##			event.ignore()
			
			
	def createNewFolder(self,lastEnterName=""):
		name,b=QtGui.QInputDialog.getText(self.main,self.tr("New folder"),self.tr("Enter new folder name:"), QtGui.QLineEdit.Normal, lastEnterName)
		name=unicode(name)
		# if user set new name
		i=[]
		for item in self.wizard.ui.tree.findItems("*", QtCore.Qt.MatchWrap | QtCore.Qt.MatchWildcard):
			i.append(item.text())
		if b==True and len(name)!=0 and not re.search("[/]", name) and name not in i:
			jmeno=unicode(self.pwd+name).replace("'","\\'").replace('"','\\"').replace(' ','\ ')
			if self.typ=="public":
				self.main.client.sendMessage("public@disk.jabbim.cz", u"mkdir "+jmeno+"")
				self.array.append(('public@disk.jabbim.cz',self.pwd,'mkdir'))
				self.public(self.pwd)
			elif self.typ=="private":
				self.main.client.sendMessage("private@disk.jabbim.cz", u"mkdir "+jmeno+"")
				self.array.append(('private@disk.jabbim.cz',self.pwd,'mkdir'))
				self.private(self.pwd)
			elif self.typ=="album":
				self.main.client.sendMessage("album@disk.jabbim.cz", u"mkdir "+jmeno+"")
				self.array.append(('album@disk.jabbim.cz',self.pwd,'mkdir'))
				self.album(self.pwd)
		elif b==True:
			message = QtGui.QMessageBox(self.main)
			message.setText(self.tr("Wrong folder name"))
			if name in i:
				message.setDetailedText(self.tr("Already exist file/folder with this name in same folder"))
			else:
				message.setDetailedText(self.tr("Is not alowed file name with char /"))
			message.setWindowTitle(self.tr("Warning"))
			message.setIcon(QtGui.QMessageBox.Warning)
			message.exec_()
			#if message==QtGui.QMessageBox.Ok:
			self.createNewFolder(name)

		
	def addUserToPreview(self,jid=None, lastEnterJid=""):
		if jid==None:
			name,b=QtGui.QInputDialog.getText(self.main,self.tr("Enter Jabber ID"),self.tr("Enter Jabber ID (user@server):"), QtGui.QLineEdit.Normal, lastEnterJid)
			name=unicode(name)
			if b==True and len(name)!=0:
				if self.main.getJid(name)==None:
					msg = self.tr("Wrong Jabber ID")
					detmsg = self.tr("You are entered wrong jabber ID")
					message = QtGui.QMessageBox(self.main)
					message.setText(msg)
					message.setDetailedText(detmsg)
					message.setWindowTitle(self.tr("Warning"))
					message.setIcon(QtGui.QMessageBox.Warning)
					message.exec_()
					#if message==QtGui.QMessageBox.Ok:
					self.addUserToPreview(None,name)
					return
				jid=name
		if not jid in self.config['jidPreview'] and jid!=self.main.client.jid.userhost():
			self.config['jidPreview'].append(jid)
			self.showSlot()

			
	def removeCurrentUsers(self):
		items=self.wizard.ui.tree.selectedItems()
		for item in items:
			data=item.data(32).toList()
			print "remove",data
			jid=unicode(data[1].toString())
			if jid in self.config['jidPreview']:
				self.config['jidPreview'].remove(jid)
		self.showSlot()
	
	def downloadFilesInDirectory(self):
		#self.downloadQueue.append(unicode(self.pwd+item.text()))
		items=self.wizard.ui.tree.selectedItems()
		for item in items:
			data=item.data(32).toList()
			size=unicode(data[0].toString())
			if size=="-1":
				self.downloadAllDirectory(self.jid,self.typ,self.pwd+item.text()+"/")
			else:
				self.downloadQueue.append((self.jid,self.typ,unicode(self.pwd+item.text())))
		if len(self.downloadQueue)>0:
			(jid,typ,pwd)=self.downloadQueue.pop()
			if typ=="public":
				self.main.client.sendMessage("public@disk.jabbim.cz", u"get //"+jid+"\%public"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
			elif typ=="private":
				self.main.client.sendMessage("private@disk.jabbim.cz", u"get //"+jid+"\%private"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
			elif typ=="album":
				self.main.client.sendMessage("album@disk.jabbim.cz", u"get //"+jid+"\%album"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))

	def downloadAllDirectory(self,jid,typ,pwd):
		print "GET TREE",jid,typ,unicode(pwd)
		self.key[unicode(pwd)]=('download',jid,typ,1,[])
		print "snd_msg",typ+"@disk.jabbim.cz", u"ls //"+jid+"%"+typ+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ ')
		self.main.client.sendMessage(typ+"@disk.jabbim.cz", u"ls //"+jid+"%"+typ+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
		print "(typ+\"@disk.jabbim.cz\",unicode(pwd),unicode(pwd))",(typ+"@disk.jabbim.cz",unicode(pwd),unicode(pwd))
		self.array.append((typ+"@disk.jabbim.cz",unicode(pwd),unicode(pwd)))
		
	def _downloadAllDirectory(self,key):
		(akce,jid,typ,isall,tree)=self.key[key]
		c=0
		for x in range(len(tree)):
			if tree[x][1]==-1:
				c=c+1
				continue
			self.downloadQueue.append((jid,typ,unicode(tree[x][0])))
		if len(self.downloadQueue)>0:
			(jid,typ,pwd)=self.downloadQueue.pop()
			self.main.client.sendMessage(typ+"@disk.jabbim.cz", u"get '//"+jid+"%"+typ+unicode(pwd).replace("'","\\'").replace('"','\\"')+"'")
			#self.array.append((typ+'@disk.jabbim.cz',self.pwd,'rm'))
		if c>0:
			message = QtGui.QMessageBox(self.main)
			message.setText(self.tr("No files in subfolder/s for download","",c))
			message.setWindowTitle(self.tr("Information"))
			message.setIcon(QtGui.QMessageBox.Information)
			message.exec_()
		del self.key[key]
	
	def removeDirectory(self):
		items=self.wizard.ui.tree.selectedItems()
		if len(items)==0:
			return
		else:
			if self.typ=="private":
				jid="private@disk.jabbim.cz"
			elif self.typ=="public":
				jid="public@disk.jabbim.cz"
			elif self.typ=="album":
				jid="album@disk.jabbim.cz"
			else:
				return
			for item in items:
				nde = unicode(self.pwd) + unicode(item.text())+"/"
				print "GET TREE",unicode(nde)
				self.key[nde]=('remove',self.jid,self.typ,1,[])
				self.main.client.sendMessage(jid, u"ls //"+self.jid+"%"+self.typ+nde.replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				print "(jid,nde,nde)",(jid,nde,nde)
				self.array.append((jid,nde,nde))
	
	def removeAll(self,key):
		(akce,jid,typ,isall,tree)=self.key[key]
		detmsg=key+"\n"
		for x in tree:
			detmsg=detmsg+x[0]+"\n"
		message = QtGui.QMessageBox(self.main)
		message.setText(self.tr("You want delete %n files and folders. Are you sure?", "", len(tree)))
		message.setDetailedText(detmsg)
		message.setWindowTitle(self.tr("Remove"))
		message.setStandardButtons(QtGui.QMessageBox.Yes | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel);
		message.setDefaultButton(QtGui.QMessageBox.Cancel);
		message.setIcon(QtGui.QMessageBox.Question)
		vysl = message.exec_()
		if vysl==QtGui.QMessageBox.Yes:
			for x in range(len(tree)-1,-1,-1):
				self.main.client.sendMessage(typ+"@disk.jabbim.cz", u"rm '"+unicode(tree[x][0]).replace("'","\\'").replace('"','\\"')+"'")
				self.array.append((typ+'@disk.jabbim.cz',self.pwd,'rm'))
				print "(typ+'@disk.jabbim.cz',self.pwd,'rm')",(typ+'@disk.jabbim.cz',self.pwd,'rm')
			print "mazuuuuuuuuuuuuuuuuuuuuuuuuu"
		del self.key[key]
		
	def dirTreeMenu(self,action=None):
		print "HOVER", action
		print "GET TREE"#,unicode(nde)
		data=action.data().toList()
		typ = unicode(data[0].toString())
		pwd = unicode(data[1].toString())
		if self.movesubmenu.has_key(typ+pwd) or self.key.has_key(typ+pwd): #menu exist or getting now
			if self.movesubmenu.has_key(typ+pwd):
				print "self.movesubmenu.has_key(typ+pwd)"
			else:
				self.key.has_key(typ+pwd)
			return
		self.key[typ+pwd]=('move',action,typ,0,[])
		self.main.client.sendMessage(typ+"@disk.jabbim.cz", u"ls //"+self.jid+"%"+typ+pwd.replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
		self.array.append((typ+"@disk.jabbim.cz",pwd,typ+pwd))
		
	def _dirTreeMenu(self,key):
		(akce,orig_action,typ,isall,tree)=self.key[key]
		self.movesubmenu[typ+key] = QtGui.QMenu()
		
		action=self.movesubmenu[typ+key].addAction(self.tr("paste here"))
		action.setData(QtCore.QVariant(QtCore.QStringList([typ,key])))
		action.setObjectName("move")
		
		self.movesubmenu[typ+key].addSeparator()
		for x in tree:
			if x[1]!=-1:
				continue
			name=x[0].split('/')[-2:-1][0]
			action=self.movesubmenu[typ+key].addAction(name)
			action.setData(QtCore.QVariant(QtCore.QStringList([typ,x[0]])))
			action.setObjectName("move")
		orig_action.setMenu(self.movesubmenu[typ+key])

		del self.key[key]
		
	def moveItems(self, action):
		data=action.data().toList()
		typ = unicode(data[0].toString())
		pwd = unicode(data[1].toString())
		items=self.wizard.ui.tree.selectedItems()
		for item in items:
			self.main.client.sendMessage(self.typ+"@disk.jabbim.cz", u"mv '//"+self.jid+"%"+self.typ+self.pwd+unicode(item.text()).replace("'","\\'").replace('"','\\"')+"' "+"'//"+self.jid+"%"+unicode(pwd+item.text()).replace("'","\\'").replace('"','\\"')+"'")
			self.array.append((self.typ+'@disk.jabbim.cz',self.pwd,'mv'))
		self.pathChanged()
	
	def sendFileFromServer(self, jid=None, lastEnterName=""):
		items=self.wizard.ui.tree.selectedItems()
		if jid==None:
			name,b=QtGui.QInputDialog.getText(self.main,self.tr("Enter full jid"),self.tr("Enter full JID (user@server/resource):"), QtGui.QLineEdit.Normal, lastEnterName)
			name=unicode(name)
			if b==True and len(name)!=0:
				if self.main.getJid(name)==None:
					self._sendFileFromServerEr(None,name,err='jid')
					return
				elif self.main.getJid(name).resource==None:
					self._sendFileFromServerEr(None,name,err='resource')
					return
				jid=name
		
		if len(items)>=1:
			for item in items:
				data=unicode(item.data(32).toString())
				self.main.client.sendMessage(self.typ+"@disk.jabbim.cz", u"send "+jid.replace("'","\\'").replace('"','\\"').replace(' ','\\ ')+" "+unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
	
	def _sendFileFromServerEr(self, jid, name, err):
		if err=='jid':
			msg = self.tr("Wrong Jabber ID")
			detmsg = self.tr("You are entered wrong jabber ID")
		elif err=='resource':
			msg = self.tr("Wrong full Jabber ID")
			detmsg = self.tr("You need enter full (with resource) Jabber ID user@server/resource")
		message = QtGui.QMessageBox(self.main)
		message.setText(msg)
		message.setDetailedText(detmsg)
		message.setWindowTitle(self.tr("Warning"))
		message.setIcon(QtGui.QMessageBox.Warning)
		message.exec_()
		#if message==QtGui.QMessageBox.Ok:
		self.sendFileFromServer(None, name)
		
	def countFolderFiles(self,items):
		count_file=[]
		count_folder=[]
		for item in items:
			data=item.data(32).toList()
			size=unicode(data[0].toString())
			if size=="-1":
				count_folder.append(item)
			else:
				count_file.append(item)
		return (count_file, count_folder)
	
	def fileMenu(self,pos):
		items=self.wizard.ui.tree.selectedItems()
		self.menu=QtGui.QMenu()
		#action=self.menu.addAction(self.tr("Show files as icons"))
		#action.setCheckable(True)
		#if self.config['iconMode']=="True":
			#action.setChecked(True)
		#else:
			#action.setChecked(False)
		#QtCore.QObject.connect(action,QtCore.SIGNAL("triggered ( bool)"),self.setIconMode)
		
		if len(items)!=0:
			if len(items)==1:
				for item in items: #jen jednou :)
					data=item.data(32).toList()
					size=unicode(data[0].toString())
					try:
						desc=unicode(data[1].toString())
					except:
						desc=""
					if self.jid and ( self.typ=="public" or self.typ=="private" or self.typ=="album" ):
						if size!="-1": # 1 item, 1 file
							self.menu.addAction(self.tr("Download file"),self.downloadCurrentFile)
							if self.jid==self.main.client.jid.userhost():
								self.menu.addAction(self.tr("Rename"),self.renameFile)
								self.menu.addAction(self.tr("Remove file"),self.removeCurrentFile)
							if self.typ!="private":
								self.menu.addAction(self.tr("Copy link to clipboard"),self.copyToClipboard)
							if (self.typ=="public" or self.typ=="private" or self.typ=="album") and self.jid==self.main.client.jid.userhost():
								submenu = self.menu.addMenu(self.tr("Send file from server to"))
								submenu.addAction(self.tr("manually enter JID"),self.sendFileFromServer)
								subsubmenu = submenu.addMenu(self.tr("from roster"))
								fun_dict={}
								for jid in self.main.client.roster['users'].keys():
									#self.roster['users'][jid.userhost()].resources[self.roster['users'][jid.userhost()].getHighestResource()]
									if jid==self.main.client.jid.userhost():
										continue
									if len(self.main.client.roster['users'][jid].resources.keys())==1:
										def tmpfun(jid=jid):
											self.sendFileFromServer(jid+"/"+self.main.client.roster['users'][jid].resources.keys()[0])
										fun_dict[jid]=tmpfun
										del tmpfun
										subsubmenu.addAction(jid,fun_dict[jid])
									elif len(self.main.client.roster['users'][jid].resources.keys())>1:
										cont_res = subsubmenu.addMenu(jid)
										for res in self.main.client.roster['users'][jid].resources.keys():
											def tmpfun(jid=jid,res=res):
												self.sendFileFromServer(jid+"/"+res)
											fun_dict[jid+'/'+res]=tmpfun
											del tmpfun
											cont_res.addAction(jid+'/'+res,fun_dict[jid+'/'+res])
											
									else:
										continue
								submenu = self.menu.addMenu(self.tr("Move file to"))
								action=submenu.addAction(self.tr("Current location"))
								action.setData(QtCore.QVariant(QtCore.QStringList([self.typ,self.pwd])))
								action.setObjectName("move")
								action=submenu.addAction(self.tr("Public disk"))
								action.setData(QtCore.QVariant(QtCore.QStringList(['public','/'])))
								action.setObjectName("move")
								action=submenu.addAction(self.tr("Private disk"))
								action.setData(QtCore.QVariant(QtCore.QStringList(['private','/'])))
								action.setObjectName("move")
								action=submenu.addAction(self.tr("Album"))
								action.setData(QtCore.QVariant(QtCore.QStringList(['album','/'])))
								action.setObjectName("move")
								submenu.connect(submenu, QtCore.SIGNAL("hovered ( QAction * )"),self.dirTreeMenu)
								submenu.connect(submenu, QtCore.SIGNAL("triggered ( QAction * )"),self.moveItems)
						else: # 1 item, 1 dir
							#self.menu.addAction(self.tr("Download all files inside this folder"),self.downloadFilesInDirectory)
							self.menu.addAction(self.tr("Download all files and subfolders inside this folder"),self.downloadFilesInDirectory)
							if self.jid==self.main.client.jid.userhost():
								self.menu.addAction(self.tr("Rename"),self.renameFile)
								self.menu.addAction(self.tr("Remove folder and all files and subfolders inside this folder"),self.removeDirectory)
							if self.typ!="private":
								self.menu.addAction(self.tr("Copy link to clipboard"),self.copyToClipboard)
							if self.jid==self.main.client.jid.userhost():
								submenu = self.menu.addMenu(self.tr("Move folder to"))
								action=submenu.addAction(self.tr("Current location"))
								action.setData(QtCore.QVariant(QtCore.QStringList([self.typ,self.pwd])))
								action.setObjectName("move")
								action=submenu.addAction(self.tr("Public disk"))
								action.setData(QtCore.QVariant(QtCore.QStringList(['public','/'])))
								action.setObjectName("move")
								action=submenu.addAction(self.tr("Private disk"))
								action.setData(QtCore.QVariant(QtCore.QStringList(['private','/'])))
								action.setObjectName("move")
								action=submenu.addAction(self.tr("Album"))
								action.setData(QtCore.QVariant(QtCore.QStringList(['album','/'])))
								action.setObjectName("move")
								submenu.connect(submenu, QtCore.SIGNAL("hovered ( QAction * )"),self.dirTreeMenu)
								submenu.connect(submenu, QtCore.SIGNAL("triggered ( QAction * )"),self.moveItems)
					elif self.jid and self.typ=="easyshare" and size!="-3":
						if size=="-1":
							self.menu.addAction(self.tr("Download all files and subfolders inside this folder"),self.downloadCurrentFile)
						else:
							self.menu.addAction(self.tr("Download file"),self.downloadCurrentFile)
					elif size=="-2":
						if desc==self.main.client.jid.userhost():
							a=self.menu.addAction(self.tr("You can not remove own Jabber ID"))
							a.setEnabled(False)
						else:
							a=self.menu.addAction(self.tr("Remove user from this list"),self.removeCurrentUsers)
							a.setData(QtCore.QVariant(desc))
			else: #more items selected
				if self.jid and ( self.typ=="public" or self.typ=="private" or self.typ=="album" ):
					(count_file,count_folder) = self.countFolderFiles(items)
					if len(count_folder)==0:
						self.menu.addAction(self.tr("Download selected files"),self.downloadCurrentFile)
						if self.jid==self.main.client.jid.userhost():
							self.menu.addAction(self.tr("Remove selected files"),self.removeCurrentFile)
							if self.typ=="public" or self.typ=="private" or self.typ=="album":
									submenu = self.menu.addMenu(self.tr("Send file from server to"))
									submenu.addAction(self.tr("manually enter JID"),self.sendFileFromServer)
									subsubmenu = submenu.addMenu(self.tr("from roster"))
									fun_dict={}
									for jid in self.main.client.roster['users'].keys():
										#self.roster['users'][jid.userhost()].resources[self.roster['users'][jid.userhost()].getHighestResource()]
										if jid==self.main.client.jid.userhost():
											continue
										if len(self.main.client.roster['users'][jid].resources.keys())==1:
											def tmpfun(jid=jid):
												self.sendFileFromServer(jid+"/"+self.main.client.roster['users'][jid].resources.keys()[0])
											fun_dict[jid]=tmpfun
											del tmpfun
											subsubmenu.addAction(jid,fun_dict[jid])
										elif len(self.main.client.roster['users'][jid].resources.keys())>1:
											cont_res = subsubmenu.addMenu(jid)
											for res in self.main.client.roster['users'][jid].resources.keys():
												def tmpfun(jid=jid,res=res):
													self.sendFileFromServer(jid+"/"+res)
												fun_dict[jid+'/'+res]=tmpfun
												del tmpfun
												cont_res.addAction(jid+'/'+res,fun_dict[jid+'/'+res])
												
										else:
											continue
									submenu = self.menu.addMenu(self.tr("Move files to"))
									action=submenu.addAction(self.tr("Current location"))
									action.setData(QtCore.QVariant(QtCore.QStringList([self.typ,self.pwd])))
									action.setObjectName("move")
									action=submenu.addAction(self.tr("Public disk"))
									action.setData(QtCore.QVariant(QtCore.QStringList(['public','/'])))
									action.setObjectName("move")
									action=submenu.addAction(self.tr("Private disk"))
									action.setData(QtCore.QVariant(QtCore.QStringList(['private','/'])))
									action.setObjectName("move")
									action=submenu.addAction(self.tr("Album"))
									action.setData(QtCore.QVariant(QtCore.QStringList(['album','/'])))
									action.setObjectName("move")
									submenu.connect(submenu, QtCore.SIGNAL("hovered ( QAction * )"),self.dirTreeMenu)
									submenu.connect(submenu, QtCore.SIGNAL("triggered ( QAction * )"),self.moveItems)
					elif len(count_file)==0:
						#self.menu.addAction(self.tr("Download all files inside selected folders"),self.downloadFilesInDirectory)
						self.menu.addAction(self.tr("Download all files and subfolders inside selected folders"),self.downloadFilesInDirectory)
						if self.jid==self.main.client.jid.userhost():
							self.menu.addAction(self.tr("Remove folders and all files and subfolders inside selected folders"),self.removeDirectory)
							submenu = self.menu.addMenu(self.tr("Move folders to"))
							action=submenu.addAction(self.tr("Current location"))
							action.setData(QtCore.QVariant(QtCore.QStringList([self.typ,self.pwd])))
							action.setObjectName("move")
							action=submenu.addAction(self.tr("Public disk"))
							action.setData(QtCore.QVariant(QtCore.QStringList(['public','/'])))
							action.setObjectName("move")
							action=submenu.addAction(self.tr("Private disk"))
							action.setData(QtCore.QVariant(QtCore.QStringList(['private','/'])))
							action.setObjectName("move")
							action=submenu.addAction(self.tr("Album"))
							action.setData(QtCore.QVariant(QtCore.QStringList(['album','/'])))
							action.setObjectName("move")
							submenu.connect(submenu, QtCore.SIGNAL("hovered ( QAction * )"),self.dirTreeMenu)
							submenu.connect(submenu, QtCore.SIGNAL("triggered ( QAction * )"),self.moveItems)
					else:
						self.menu.addAction(self.tr("Download selected files and all files inside selected folders"),self.downloadFilesInDirectory)
						if self.jid==self.main.client.jid.userhost() and ( self.typ=="public" or self.typ=="private" or self.typ=="album" ):
							submenu = self.menu.addMenu(self.tr("Move folders and files to"))
							action=submenu.addAction(self.tr("Current location"))
							action.setData(QtCore.QVariant(QtCore.QStringList([self.typ,self.pwd])))
							action.setObjectName("move")
							action=submenu.addAction(self.tr("Public disk"))
							action.setData(QtCore.QVariant(QtCore.QStringList(['public','/'])))
							action.setObjectName("move")
							action=submenu.addAction(self.tr("Private disk"))
							action.setData(QtCore.QVariant(QtCore.QStringList(['private','/'])))
							action.setObjectName("move")
							action=submenu.addAction(self.tr("Album"))
							action.setData(QtCore.QVariant(QtCore.QStringList(['album','/'])))
							action.setObjectName("move")
							submenu.connect(submenu, QtCore.SIGNAL("hovered ( QAction * )"),self.dirTreeMenu)
							submenu.connect(submenu, QtCore.SIGNAL("triggered ( QAction * )"),self.moveItems)
					self.menu.addAction(self.tr("Copy links to clipboard"),self.copyToClipboard)
				elif self.jid and self.typ=="easyshare":
					self.menu.addAction(self.tr("Download files"),self.downloadCurrentFile)
		else:
			if self.jid and ( self.typ=="public" or self.typ=="private" or self.typ=="album" ):
				self.menu.addAction(self.tr("Create new folder"),self.createNewFolder)
				self.menu.addAction(self.tr("Upload new file here"),self.sendFile)
				self.menu.popup(self.wizard.ui.tree.mapToGlobal(pos))
			elif not self.jid:
				submenu = self.menu.addMenu(self.tr("Add new user"))
				submenu.addAction(self.tr("manually enter JID"),self.addUserToPreview)
				subsubmenu = submenu.addMenu(self.tr("from roster"))
				#i=[]
				#for item in self.wizard.ui.tree.findItems("*", QtCore.Qt.MatchWrap | QtCore.Qt.MatchWildcard):
					#data=item.data(32).toList()
					#i.append(unicode(data[1].toString()))
				#print "polozky:",i
				
				
				function_dict={}
				for jid in self.main.client.roster['users'].keys():
					if jid==self.main.client.jid.userhost():
						continue
					def tempfunc(jid=jid):
						self.addUserToPreview(jid)
					function_dict[jid] = tempfunc
					del tempfunc
					act=subsubmenu.addAction(jid,function_dict[jid])
					#act.setCheckable(True)
					#act.setChecked(False)
					#if jid in i:
						#act.setChecked(True)
					#act.setData(QtCore.QVariant(jid))
		pos.setY(pos.y() + 5);
		self.menu.popup(self.wizard.ui.tree.mapToGlobal(pos))
				
		
	def renameFile(self,entered=None):
		items=self.wizard.ui.tree.selectedItems()
		if len(items)!=1 or not self.jid or not self.typ or self.typ=="easyshare" or self.jid!=self.main.client.jid.userhost():
			return
		for item in items:
			data=item.data(32).toList()
			size=unicode(data[0].toString())
			if size== "-2" or size=="-3":
				return
		item = items[0]
		value=unicode(item.text())
		if entered:
			value=entered
		name,b=QtGui.QInputDialog.getText(self.main,self.tr("Rename"),self.tr("Enter new name:"), QtGui.QLineEdit.Normal, value)
		name=unicode(name)
		# if user set new name
		i=[]
		for n_item in self.wizard.ui.tree.findItems("*", QtCore.Qt.MatchWrap | QtCore.Qt.MatchWildcard):
			i.append(unicode(n_item.text()))
		if b==True and len(name)!=0 and not re.search("[/]", name) and name not in i:
			jmeno=unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"')
			jmeno2=unicode(self.pwd+unicode(name)).replace("'","\\'").replace('"','\\"')
			if self.typ=="public":
				self.main.client.sendMessage("public@disk.jabbim.cz", u"mv '"+jmeno+"' '"+jmeno2+"'")
				self.array.append(('public@disk.jabbim.cz',self.pwd,'mv'))
				self.public(self.pwd)
			elif self.typ=="private":
				self.main.client.sendMessage("private@disk.jabbim.cz", u"mv '"+jmeno+"' '"+jmeno2+"'")
				self.array.append(('private@disk.jabbim.cz',self.pwd,'mv'))
				self.private(self.pwd)
			elif self.typ=="album":
				self.main.client.sendMessage("album@disk.jabbim.cz", u"mv '"+jmeno+"' '"+jmeno2+"'")
				self.array.append(('album@disk.jabbim.cz',self.pwd,'mv'))
				self.album(self.pwd)
		elif b==True:
			message = QtGui.QMessageBox(self.main)
			message.setText(self.tr("Wrong file/folder name"))
			if name in i:
				message.setDetailedText(self.tr("Already exist file/folder with this name in same folder"))
			else:
				message.setDetailedText(self.tr("Is not alowed file name with char /"))
			message.setWindowTitle(self.tr("Warning"))
			message.setIcon(QtGui.QMessageBox.Warning)
			message.exec_()
			self.renameFile(entered=name)
			#QtGui.QErrorMessage(self.main,)

	def copyToClipboard(self):
		items=self.wizard.ui.tree.selectedItems()
		text=""
		if len(items)==0:
			if self.typ=="public":
				text+="http://disk.jabbim.cz/"+self.jid+urllib.quote(self.pwd)+"\n"
			elif self.typ=="album":
				text+="http://album.jabbim.cz/"+self.jid+urllib.quote(self.pwd)+"\n"
			QtGui.QApplication.clipboard().setText(text[:-1])
			return
		for item in items:
			if self.typ=="public":
				text+="http://disk.jabbim.cz/"+self.jid+urllib.quote(self.pwd)+urllib.quote(unicode(item.text()))+"\n"
			elif self.typ=="album":
				text+="http://album.jabbim.cz/"+self.jid+urllib.quote(self.pwd)+urllib.quote(unicode(item.text()))+"\n"
			QtGui.QApplication.clipboard().setText(text[:-1])

	def filenameMenu(self,pos):
		if not self.jid:
			return
		items=self.wizard.ui.tree.selectedItems()
		self.menu=QtGui.QMenu()
		for item in items:
			data=item.data(32).toList()
			size=int(data[0].toString())
			if size == -2 or size == -3:
				return
		if len(items)==1:
			self.menu.addAction(self.tr("Copy filename to clipboard"),self.copyFileName)
			if self.typ!="easyshare":
				self.menu.addAction(self.tr("Copy link to clipboard"),self.copyToClipboard)
		elif len(items)>1:
			self.menu.addAction(self.tr("Copy filenames to clipboard"),self.copyFileName)
			if self.typ!="easyshare":
				self.menu.addAction(self.tr("Copy links to clipboard"),self.copyToClipboard)
		else:
			return
		pos.setY(pos.y()+5)
		self.menu.popup(self.wizard.ui.filename.mapToGlobal(pos))

	def descriptionMenu(self,pos):
		if not self.jid:
			return
		items=self.wizard.ui.tree.selectedItems()
		self.menu=QtGui.QMenu()
		for item in items:
			data=item.data(32).toList()
			try:
				desc=unicode(data[1].toString())
			except:
				decs=""
			if size == -2 or size == -3:
				return
		if len(items)==1:
			if self.typ!="easyshare":
				self.menu.addAction(self.tr("Copy description to clipboard"),self.copyDescription)
		else:
			return
		pos.setY(pos.y()+5)
		self.menu.popup(self.wizard.ui.filename.mapToGlobal(pos))
		
	def copyFileName(self):
		items=self.wizard.ui.tree.selectedItems()
		text=""
		for item in items:
			text+=item.text()+"\n"
		QtGui.QApplication.clipboard().setText(text[:-1])
	
	def copyDescription(self):
		QtGui.QApplication.clipboard().setText(self.wizard.ui.description.text())

	def downloadCurrentFile(self):
		#items=self.window.ui.list.selectedItems()
		items=self.wizard.ui.tree.selectedItems()
		if len(items)==0:
			return
		if self.typ=="easyshare":
			contact = self.main.client.getContactByJid(self.jid)
			if contact:
				jid=self.jid+"/"+contact.getHighestResource()
				data=[]
				items=self.wizard.ui.tree.selectedItems()
				for item in items:
					data.append(self.getPath(item))
				self.main.client.callRemote(jid, 'getFiles',(data,))
		else:
			for item in items:
				self.downloadQueue.append((self.jid,self.typ,unicode(self.pwd+item.text())))
			(jid,typ,pwd)=self.downloadQueue.pop()
			if typ=="public":
				self.main.client.sendMessage("public@disk.jabbim.cz", u"get //"+jid+"\%public"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
			elif self.typ=="private":
				self.main.client.sendMessage("private@disk.jabbim.cz", u"get //"+self.jid+"\%private"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
			elif self.typ=="album":
				self.main.client.sendMessage("album@disk.jabbim.cz", u"get //"+self.jid+"\%album"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))

	def removeCurrentFile(self):
		items=self.wizard.ui.tree.selectedItems()
		if len(items)==0:
			return
		for item in items:
			if self.typ=="public":
				self.main.client.sendMessage("public@disk.jabbim.cz", u"rm '"+unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"')+"'")
				self.array.append(('public@disk.jabbim.cz',self.pwd,'rm'))
			elif self.typ=="private":
				self.main.client.sendMessage("private@disk.jabbim.cz", u"rm '"+unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"')+"'")
				self.array.append(('private@disk.jabbim.cz',self.pwd,'rm'))
			elif self.typ=="album":
				self.main.client.sendMessage("album@disk.jabbim.cz", u"rm '"+unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"')+"'")
				self.array.append(('album@disk.jabbim.cz',self.pwd,'rm'))
		for i in range(len(items)):
			#self.wizard.ui.tree.takeTopLevelItem(self.wizard.ui.tree.indexOfTopLevelItem(items[0]))
			self.wizard.ui.tree.takeItem(self.wizard.ui.tree.row(items[0]))
			del items[0]

	def toNormalSize(self,size):
		if size<0:
			return ""
		original=int(size)
		new=int(size/1000) # kB
		if new==0:
			return str(round(original,2.0))+" B" # B
		size=new
		new=int(size/1000) # MB
		if new==0:
			return str(round(original/1000.0,2))+" kB" # kB
		return str(round(original/1000000.0,2))+" MB" # MB
		
	def toByte(self,size):
		velikosti=['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB']
		try:
			v=float(size[0])
		except:
			return "0"
		if size[1] in velikosti:
			for x in range(0,velikosti.index(size[1])):
				v=v*1024
			return str(int(v))
		else:
			return "0"

	def updateView(self, data=None, parent=None, msg=None):
		#if not self.update and not parent:
			#self.window.ui.right.clear()
		if msg:
			data=[]
			if len(self.array)==0:
				return
			else:
				frm, typ, body, subject, xhtml, chatstate, delay, error = msg.legacyUnpack()
				if self.main.getJid(frm).userhost()==self.array[0][0]:
					(fromjid, pwd, cmd) = self.array.pop(0)
					if cmd=='rm' or cmd=='cd' or cmd=='mv' or cmd=='mkdir':
						return
					if cmd=='ls':
						self.pwd=pwd
						self.wizard.ui.filename.setText(self.main.tr("Empty folder"))
				else:
					return
				if re.search("<dir> ([^/]+)/ - .*", body): # do budoucna
					telo=re.findall("(<dir> ([^/]+)/ - (.*))|([0-9]+ - (.+) \[([0-9.]+[PETGMK]{0,1}i{0,1}[B]{1})\] - (.*))", body)
					if len(telo)!=0:
						for radek in telo:
							if radek[1]=='':
								data.append((radek[4],"100",radek[6]))
							else:
								data.append((radek[1],"-1",radek[2]))
					elif cmd=='ls':
						return
				else:
					telo=re.findall("(<dir> ([^/]+)/)|([0-9]+ - (.+) \[([0-9.]+[PETGMK]{0,1}i{0,1}[B]{1})\] - (.*))", body)
					if len(telo)!=0:
						for radek in telo:
							if radek[1]=='':
								s=self.toByte(re.findall("([0-9.]+)([^0-9]+)",radek[4])[0])
								data.append((radek[3],s,radek[5]))
							else:
								data.append((radek[1],"-1"))
					elif cmd=='ls':
						return
				if cmd!='ls':
					(akce,jid,typ,isall,tree)=self.key[cmd]
					isall=isall-1
					for i in range(len(data)):
						item=list(data[i])
						name=unicode(item[0])
						size=int(item[1])
						if size==-1:
							name=pwd+name+"/"
							if isall>=0:
								isall=isall+1
								self.main.client.sendMessage(typ+"@disk.jabbim.cz", u"ls //"+jid+"%"+typ+unicode(name).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
								self.array.append((typ+"@disk.jabbim.cz",name,cmd))
						else:
							name=pwd+name
						data[i]=(name,size)
					tree.extend(data)
					self.key[cmd]=(akce,jid,typ,isall,tree)
					if isall<=0:
						if akce=='remove':#self.funkce(cmd)
							self.removeAll(cmd)
						elif akce=='download':
							self._downloadAllDirectory(cmd)
						elif akce=='move':
							self._dirTreeMenu(cmd)
					return
		else:
			self.wizard.ui.tree.clear()
			data=data[0][0]
		#if parent:
			#self.window.ui.right.expandItem(parent)
			#self.wizard.ui.tree.expandItem(parent)
			#pass
##		self.window.ui.esPath.setText(self.esPath)
		if len(data)>0:
			self.wizard.ui.filename.setText("")
		self.thumbs={}
		html=""
		for file in data:
			if self.update:
				#items=self.window.ui.right.findItems(file[0],QtCore.Qt.MatchExactly)
				items=self.wizard.ui.tree.findItems(file[0],QtCore.Qt.MatchExactly)
				if len(items)!=0:
					continue
			name=file[0]
			size=int(file[1])
			if len(file)>=3:
				desc=file[2]
			else:
				desc=""
			#if parent:
				#item=QtGui.QListWidgetItem(parent)
				#pass
			#else:
				#item=QtGui.QTreeWidgetItem(self.window.ui.right)
			item=QtGui.QListWidgetItem(self.wizard.ui.tree)
			item.setText(unicode(name))
			#item.setText(1,unicode(self.toNormalSize(size)))
			item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode(size),desc])))
			if int(size)==-1:
				item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/folder.png"))
				if parent:
					item.path=unicode(parent.path)+name+"/"
			else:
				if parent:
					item.path=unicode(parent.path)+name
				ext=name.split('.')[-1]
				if ext in ["exe","run","sh","bin"]: 
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/application-x-executable.png"))
					ic=self.pluginDir+"/application-x-executable.png"
				elif ext in ["svg","jpg","png","gif","tif","tiff","bmp","ico","xcf"]: 
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/image-x-generic.png"))
					ic=self.pluginDir+"/image-x-generic.png"
				elif ext in ["wav","mp3","ogg","mp4","flac"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/audio-x-generic.png"))
					ic=self.pluginDir+"/audio-x-generic.png"
				elif ext in ["rar","zip","gz","bz","tgz","deb","rpm","tar","pkg","7z","ace"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/package-x-generic.png"))
					ic=self.pluginDir+"/package-x-generic.png"
				elif ext in ["htm","html","xml"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/text-html.png"))
					ic=self.pluginDir+"/text-html.png"
				elif ext in ["txt","c","py","log"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/text-x-generic.png"))
					ic=self.pluginDir+"/text-x-generic.png"
				elif ext in ["mov","avi","mpg","swf","dv"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/text-x-generic.png"))
					ic=self.pluginDir+"/text-x-generic.png"
				elif ext in ["odt","doc","pdf","docx"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/x-office-document.png"))
					ic=self.pluginDir+"/x-office-document.png"
				elif ext in ["ods","xls","cvs"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/x-office-spreadsheet.png"))
					ic=self.pluginDir+"/x-office-spreadsheet.png"
				elif ext in ["pts","ppt","odp"]:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/x-office-presentation.png"))
					ic=self.pluginDir+"/x-office-presentation.png"
				else:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/text-x-generic-template.png"));  #preventivne pokud se netrefime
					ic=self.pluginDir+"/icons/text-x-generic-template.png"
				#html+='<div style=\\"float: left;width: 129px;height:150px;padding: 10px;text-align:center;\\"><a href=\\"http://disk.jabbim.cz/'+self.jid+self.pwd+urllib.quote(unicode(name))+'\\"><img src=\\"file:///'+ic.replace("//","/")+'\\"/><p>'+unicode(name)+'</p></a></div>'
				html+='<div style=\\"float: left;width: 129px;height:150px;padding: 10px;text-align:center;\\"><img src=\\"file:///'+ic.replace("//","/")+'\\"/><p>'+unicode(name)+'</p></div>'
			#self.window.ui.right.addItem(item)
			if self.typ=="album" and size!=-1:
				self.thumbs[unicode(self.pwd+name)]=item
		if self.callTab and self.typ=="public":
			self.callTab.chat.ui.webkit.page().mainFrame().evaluateJavaScript('var group = document.createElement(\'div\'); group.innerHTML="'+html+'";document.getElementById("light").appendChild(group);')
		#self.wizard.ui.tree.resizeColumnToContents(0)
		data=self.thumbs.keys()
		print "THUMBS!!!",self.thumbs
		if self.typ=="album" and len(data)!=0:
			if len(data)!=0:
				self.stopDownload=False
				self.window.ui.progress.setValue(0)
				self.window.ui.progress.setMaximum(len(data))
				self.window.ui.progress.show()
				self.main.client.callRemote('rpc@jabbim.cz/service', 'getThumb', (self.jid,data[0])).addCallback(self.thumbArrived,data)
		if self.update==True:
			self.update=False
	
	def checkAndCreateDirectory(self,directory):
		path = directory.split("/")
		path="/".join(path[:-1])+"/"
		try:
			os.makedirs(path)
		except:
			print "JDM cache path exist:",path
	
	def thumbArrived(self,thumb,data,check=True):
		cacheFile="%s/%s.jpg" % (self.cache,self.jid+data[0])
		if thumb:
			print "saving",data[0],check
			image=base64.decodestring(str(thumb[0]))
			pixmap=QtGui.QPixmap()
			pixmap.loadFromData(image)
			self.thumbs[data[0]].setIcon(QtGui.QIcon(pixmap))
			self.checkAndCreateDirectory(cacheFile)
			f=open(cacheFile,"wb")
			f.write(image)
			f.close()
			self.cacheList[cacheFile] = md5(image).hexdigest()
			self.cacheList.write()
		else:
			self.thumbs[data[0]].setIcon(QtGui.QIcon(cacheFile))
		if self.callTab:
			#if self.thumbIndex<10:
			self.callTab.chat.ui.webkit.page().mainFrame().evaluateJavaScript('var group = document.createElement(\'div\'); group.setAttribute("id","image'+str(self.thumbIndex)+'"); group.innerHTML="<div style=\\"float: left;width: 129px;height:150px;padding: 10px;text-align:center;\\"><a href=\\"http://album.jabbim.cz/'+self.jid+'/'+unicode(urllib.quote(self.thumbs[data[0]].text()))+'\\"><img src=\\"file://'+cacheFile+'\\"/><p>'+unicode(self.thumbs[data[0]].text())+'</p></a></div>";document.getElementById("light").appendChild(group);')
			#else:
				#self.callTab.chat.ui.webkit.page().mainFrame().evaluateJavaScript('var group = document.createElement(\'div\'); group.setAttribute("id","image'+str(self.thumbIndex)+'"); group.innerHTML="<div style=\\"float: left;width: 129px;padding: 10px;text-align:center;display:none;\\"><img src=\\"file://'+cacheFile+'\\"/></div>";document.getElementById("light").appendChild(group);')
			self.thumbIndex+=1
		self.window.ui.progress.setValue(self.window.ui.progress.value()+1)
		del data[0]
		if len(data)==0:
			self.thumbs={}
			self.window.ui.progress.hide()

			#if check:
				#data=self.thumbs.keys()
				#self.main.client.callRemote('rpc@jabbim.cz/service', 'getHash', (self.jid,data[0])).addCallback(self.hashArrived,data)
		else:
			if not self.stopDownload:
				cacheFile="%s/%s.jpg" % (self.cache,self.jid+data[0])
				if os.path.isfile(cacheFile):
					self.main.client.reactor.callLater(0,self.thumbArrived,None,data)
				else:
					self.main.client.callRemote('rpc@jabbim.cz/service', 'getThumb', (self.jid,data[0])).addCallback(self.thumbArrived,data)
			else:
				self.stopDownload=False
				self.thumbs={}
				self.window.ui.progress.hide()

	def hashArrived(self,hs,data):
		hs=hs[0][0]
		cacheFile="%s/%s.jpg" % (self.cache,self.jid+data[0])
		download=True
		if self.cacheList.has_key(cacheFile):
			print data[0],hs,self.cacheList[cacheFile]
			if self.cacheList[cacheFile]==hs:
				download=False
		if download:
			self.main.client.callRemote('rpc@jabbim.cz/service', 'getThumb', (self.jid,data[0])).addCallback(self.thumbArrived,[data[0]],False)
		del data[0]
		if len(data)!=0:
			cacheFile="%s/%s.jpg" % (self.cache,self.jid+data[0])
			self.main.client.callRemote('rpc@jabbim.cz/service', 'getHash', (self.jid,data[0])).addCallback(self.hashArrived,data)
		

	def buildMainWindowMenu(self):
		if self.main.isConnected():
			menu=self.mainWindowMenu()
			menu.addAction("Jabbim disk manager",self.showSlot)
	
	def call(self,jid=None,typ=None, path=None):
		self.thumbIndex=0
		self.stopDownload=True
		self.wizard.ui.stackedWidget.setCurrentIndex(1)
		self.wizard.ui.back.show()
##		self.window.ui.label_size.setText("")
##		self.window.ui.label_name.setText("")
		if typ:
			self.typ=typ
		if jid:
			self.jid=jid
			self.window.ui.line_jid.setText(self.jid)
		if path==None:
			path="/"
		elif path[0]!="/":
			path="/"+path
			
		#else:
			#self.jid=unicode(self.window.ui.line_jid.text())
			#self.jid=unicode(self.main.client.jid.userhost())
		path2=path.replace("'","\\'").replace('"','\\"').replace(' ','\\ ')
		if self.typ=="public":
			#self.main.client.callRemote('rpc@jabbim.cz/service', 'listPublic', (self.jid,)).addCallback(self.updateView)
			self.main.client.sendMessage("public@disk.jabbim.cz", u"ls //"+self.jid+"\%public"+path2)
			self.array.append(('public@disk.jabbim.cz',path,'ls'))
			self.wizard.ui.remove.show()
			self.wizard.ui.upload.show()
			self.wizard.ui.configuration.hide()
##			self.window.ui.list.setIconSize(QtCore.QSize(32,32))
##			self.window.ui.list.setGridSize(QtCore.QSize(128,96))
##			self.window.ui.esWidget.hide()
		elif self.typ=="private":
			#self.main.client.callRemote('rpc@jabbim.cz/service', 'listPrivate', (self.jid,)).addCallback(self.updateView)
			self.main.client.sendMessage("private@disk.jabbim.cz", u"ls //"+self.jid+"\%private"+path2)
			self.array.append(('private@disk.jabbim.cz',path,'ls'))
			self.wizard.ui.remove.show()
			self.wizard.ui.upload.show()
			self.wizard.ui.configuration.hide()
##			self.window.ui.list.setIconSize(QtCore.QSize(32,32))
##			self.window.ui.list.setGridSize(QtCore.QSize(128,96))
##			self.window.ui.esWidget.hide()
		elif self.typ=="album":
			#self.main.client.callRemote('rpc@jabbim.cz/service', 'listAlbum', (self.jid,)).addCallback(self.updateView)
			self.main.client.sendMessage("album@disk.jabbim.cz", u"ls //"+self.jid+"\%album"+path2)
			self.array.append(('album@disk.jabbim.cz',path,'ls'))
			self.wizard.ui.remove.show()
			self.wizard.ui.upload.show()
			self.wizard.ui.configuration.hide()
##			#if self.config['iconMode']=="True":
##			self.window.ui.list.setIconSize(QtCore.QSize(128,128))
##			self.window.ui.list.setGridSize(QtCore.QSize(160,160))
##			self.window.ui.esWidget.hide()
		else:
			self.wizard.ui.remove.hide()
			self.wizard.ui.upload.hide()
			self.wizard.ui.configuration.show()

		if self.jid != self.main.client.jid.userhost():
			self.window.ui.buttonDelete.setEnabled(False)
			self.window.ui.buttonUpload.setEnabled(False)
			self.window.ui.privateButton.setEnabled(False)
			self.wizard.ui.remove.setEnabled(False)
			self.wizard.ui.upload.setEnabled(False)
			self.wizard.ui.private.setEnabled(False)
		else:
			self.window.ui.buttonDelete.setEnabled(True)
			self.window.ui.buttonUpload.setEnabled(True)
			self.window.ui.privateButton.setEnabled(True)
			self.wizard.ui.remove.setEnabled(True)
			self.wizard.ui.upload.setEnabled(True)
			self.wizard.ui.private.setEnabled(True)
	

	def buildMainWindowToolBar(self):
		self.toolBarButton = self.mainWindowToolBarAction(QtGui.QIcon("%s/icons/jdisk-public-24.png" % self.pluginDir),"",self.showSlot)

	def showSlot(self,jid=None,typ=None,path = None):
		self.wizard.show()
		self.wizard.ui.stackedWidget.setCurrentIndex(1)
##		if self.main.client.isVip:
##			self.window.ui.vipInfo.hide()
##		else:
##			self.window.ui.vipInfo.show()
		self.wizard.ui.tree.clear()
		if (not self.main.client.roster['users'].has_key("public@disk.jabbim.cz") or not self.main.client.roster['users'].has_key("private@disk.jabbim.cz")) or not self.main.client.roster['users'].has_key("album@disk.jabbim.cz"):
			d=self.main.client.getRegisterForm("disk.jabbim.cz")
			d.addCallback(self._onRegister)
		if jid:
			self.jid=jid
			self.window.ui.line_jid.setText(self.jid)
			self.wizard.setWindowTitle(unicode(self.jid))
		else:
			self.jid = None
			self.wizard.setWindowTitle('Jabbim disk manager')
			#self.jid=unicode(self.window.ui.line_jid.text())
			#self.jid=unicode(self.main.client.jid.userhost())
		path2=path
		if path==None:
			path2=""
		
		self.wizard.ui.private.setEnabled(self.jid==self.main.client.jid.userhost())
		if typ:
			self.wizard.ui.path.setText(jid + "/" + typ + "/"+path2)
			if typ != "public" and typ != "private" and typ != "album":
				if path:
					contact = self.main.client.getContactByJid(self.jid)
					if contact:
						jid=self.jid+"/"+contact.getHighestResource()
						self.wizard.ui.path.setText(self.jid + "/" + self.typ + "/" + path)
						item = QtGui.QListWidgetItem()
						item.path = path
						self.main.client.callRemote(jid, 'listShare',(path,)).addCallback(self.updateView,item)
				else:
					self.easyshare()
			else:
				self.call(jid,typ,path)
			self.window.ui.buttonDownload.setEnabled(False)
			self.wizard.ui.back.show()
		elif jid:
			self.wizard.ui.path.setText(jid + "/")
			self.wizard.ui.tree.clear()
			item=QtGui.QListWidgetItem(self.wizard.ui.tree)
			item.setText(self.tr("Public disk"))
			item.setIcon(QtGui.QIcon("%s/icons/jdisk-public-24.png" % self.pluginDir))
			item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode('-3'),"public"])))
			
			if self.jid==self.main.client.jid.userhost():
				item=QtGui.QListWidgetItem(self.wizard.ui.tree)
				item.setIcon(QtGui.QIcon("%s/icons/jdisk-private-24.png" % self.pluginDir))
				item.setText(self.tr("Private disk"))
				item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode('-3'),"private"])))
			
			item=QtGui.QListWidgetItem(self.wizard.ui.tree)
			item.setIcon(QtGui.QIcon("%s/icons/jalbum-32.png" % self.pluginDir))
			item.setText(self.tr("Album"))
			item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode('-3'),"album"])))
			
			self.easyshare()
			
			#item=QtGui.QListWidgetItem(self.wizard.ui.tree)
			#item.setIcon(QtGui.QIcon("%s/easy_share32.png" % self.pluginDir))
			#item.setText(self.tr("Shared folders"))
			#item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode('-3'),"easyshare"])))
		else:
			self.wizard.ui.back.hide()
			self.wizard.ui.path.setText("")
			
			self.wizard.ui.tree.clear()
			item=QtGui.QListWidgetItem(self.wizard.ui.tree)
			item.setText(unicode(self.tr("Me")))
			#pixmap=self.main.getAvatar(jid,frame=False,size="128x128",status=None)
			pixmap=self.main.selfAvatar
			if pixmap==None:
				item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/folder.png"))
			else:
				item.setIcon(QtGui.QIcon(pixmap))
			#item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/folder.png"))
			item.setToolTip(self.main.client.jid.userhost())
			#item.setText(1,unicode(self.toNormalSize(size)))
			item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode('-2'),unicode(self.main.client.jid.userhost())])))
			
			for jid in self.config['jidPreview']:
				item=QtGui.QListWidgetItem(self.wizard.ui.tree)
				if self.main.client.roster['users'].has_key(jid) and len(self.main.client.roster['users'][jid].name)!=0:
						item.setText(unicode(self.main.client.roster['users'][jid].name))
				else:
					item.setText(unicode(jid))
				item.setToolTip(jid)
				pixmap=self.main.getAvatar(jid,frame=False,size="128x128",status=None)
				if pixmap==None:
					item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/folder.png"))
				else:
					item.setIcon(QtGui.QIcon(pixmap))
				item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode('-2'),unicode(jid)])))
			
			for jid in self.main.client.roster['users'].keys():
				if self.main.client.hasFeature(jid,"http://dev.jabbim.cz/jabbim/easyshare") and unicode(self.main.client.jid.userhost()) != jid and jid not in self.config['jidPreview']:
					item=QtGui.QListWidgetItem(self.wizard.ui.tree)
					if len(self.main.client.roster['users'][jid].name)!=0:
						item.setText(unicode(self.main.client.roster['users'][jid].name))
					else:
						item.setText(jid)
					item.setToolTip(jid)
					#item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/folder.png"))
					pixmap=self.main.getAvatar(jid,frame=False,size="128x128",status=None)
					if pixmap==None:
						item.setIcon(QtGui.QIcon(self.pluginDir+"/icons/folder.png"))
					else:
						item.setIcon(QtGui.QIcon(pixmap))
					#item.setText(1,unicode(self.toNormalSize(size)))
					item.setData(32,QtCore.QVariant(QtCore.QStringList([unicode('-2'),unicode(jid)])))
			

	def _onRegister(self,data):
		if not data:
			return
		jid,legacy,form=data
		if form!=None:
			self.dialog=dataforms.dataFormsDialog(self.main,form,jid,"register",self)
			self.dialog.show()
		else:
			self.dialog=legacyforms.legacyFormsDialog(self.main,legacy,jid,"disco",self.window)
			self.dialog.show()
	
	def on_message(self,msg):
		self.msg = msg
		#frm, typ, body, subject, xhtml, chatstate, delay, error = msg.legacyUnpack()
		frm=msg.frm
		
		#if self.typ=="public":
			#text="public@disk.jabbim.cz"
		#elif self.typ=="private":
			#text="private@disk.jabbim.cz"
		#elif self.typ=="album":
			#text="album@disk.jabbim.cz"
		#else:
			#return True
		
		if unicode(frm).find("public@disk.jabbim.cz")!=-1 or unicode(frm).find("private@disk.jabbim.cz")!=-1 or unicode(frm).find("album@disk.jabbim.cz")!=-1 :
			self.updateView(parent=None,msg=msg)
			#return False
			if not self.window.isHidden() or not self.wizard.isHidden():
				return False
		return True

	def on_ftEnd(self, sid, error = None): #pokud je error None je vse v poradku, jinak strucny popis chyby.
		if not self.window.isHidden() or not self.wizard.isHidden():
			if self.typ=="public":
				text="public@disk.jabbim.cz"
			elif self.typ=="private":
				text="private@disk.jabbim.cz"
			elif self.typ=="album":
				text="album@disk.jabbim.cz"
			else:
				return
			filename=unicode(self.main.client.ft[sid].filepath)
			if error == None and self.main.client.ft[sid].tojid.full().find(text)!=-1 and not filename in self.filesToOpen:
				self.update=True
				self.call(typ=self.typ)
			if filename in self.filesToOpen:
				self.filesToOpen.remove(filename)
				if self.main.allowedJids.has_key(text+"/"+self.main.client.ft[sid].fileprops['name']):
					del self.main.allowedJids[text+"/"+self.main.client.ft[sid].fileprops['name']]
				if error==None:
					if sys.platform == 'win32':
						filename=filename.replace("/","\\")
						print "open win32",[filename]
						os.startfile(filename)
					else:
						print "open linux",[filename]
						os.system(u"xdg-open \"%s\"" % filename.encode('utf8'))
					if self.main.events.ftEvents.has_key(sid):
						self.main.events.ftEvents[sid].reject()
						self.wizard.ui.back.hide()
						self.wizard.ui.stackedWidget.setCurrentIndex(1)
			try:
				(jid,typ,pwd)=self.downloadQueue.pop()
			except:
				pwd=None
			if pwd:
				if typ=="public":
					self.main.client.sendMessage("public@disk.jabbim.cz", u"get //"+jid+"\%public"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				elif typ=="private":
					self.main.client.sendMessage("private@disk.jabbim.cz", u"get //"+jid+"\%private"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				elif typ=="album":
					self.main.client.sendMessage("album@disk.jabbim.cz", u"get //"+jid+"\%album"+unicode(pwd).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))

	def selectionChanged(self):
		items=self.wizard.ui.tree.selectedItems()
		self.wizard.ui.filename.setToolTip("")
		if len(items)!=0:
			self.wizard.ui.image.show()
			if len(items)==1:
				item=items[0]
				self.wizard.ui.filename.setToolTip(item.text())
				data=item.data(32).toList()
				size=int(data[0].toString())
				try:
					desc=unicode(data[1].toString())
				except:
					desc=""
				if size == -1:
					self.wizard.ui.filename.setText(self.tr("Folder"))
					self.wizard.ui.remove.setEnabled(False)
					self.wizard.ui.download.setEnabled(False)
					self.wizard.ui.description.setText(desc)
					self.wizard.ui.filesize.setText("")
				elif size == -2:
					self.wizard.ui.filename.setText(self.tr("User"))
					self.wizard.ui.remove.setEnabled(False)
					self.wizard.ui.download.setEnabled(False)
					self.wizard.ui.description.setText(self.tr("This folder contains all files shared by user."))
					self.wizard.ui.filesize.setText("")
				elif size == -3:
					self.wizard.ui.filename.setText(item.text())
					self.wizard.ui.remove.setEnabled(False)
					self.wizard.ui.download.setEnabled(False)
					self.wizard.ui.filesize.setText("")
					typ = unicode(data[1].toString())
					if typ == "album":
						self.wizard.ui.description.setText(self.tr("This folder contains photos shared through Jabbim Album Service."))
					elif typ == "public":
						self.wizard.ui.description.setText(self.tr("This folder contains files shared through Jabbim Disk Service."))
					elif typ == "private":
						self.wizard.ui.description.setText(self.tr("This folder contains files shared you private files."))
					elif typ == "easyshare":
						self.wizard.ui.description.setText(self.tr("This folder contains shared folders and files."))
				else:
					self.wizard.ui.filesize.setText(self.toNormalSize(size))
					self.wizard.ui.remove.setEnabled(self.jid==self.main.client.jid.userhost())
					self.wizard.ui.download.setEnabled(True)
					self.wizard.ui.description.setText(desc)
				self.wizard.ui.filename.setText(item.text())
				self.wizard.ui.image.setPixmap(item.icon().pixmap(128,128))
			else:
				(count_file,count_folder) = self.countFolderFiles(items)
				if len(count_folder)>0:
					self.wizard.ui.remove.setEnabled(False)
					self.wizard.ui.download.setEnabled(False)
				elif len(count_file)>0:
					self.wizard.ui.remove.setEnabled(True)
					self.wizard.ui.download.setEnabled(True)
				self.wizard.ui.image.setText("")
				self.wizard.ui.description.setText("")
				self.wizard.ui.filename.setText(unicode( self.tr("%n file(s)",None,"",len(items)) ))
				size=0
				for it in items:
					data=it.data(32).toList()
					if int(data[0].toString())!=-1:
						size+=int(data[0].toString())
				self.wizard.ui.filesize.setText(self.toNormalSize(size))
		else:
			self.wizard.ui.remove.setEnabled(False)
			self.wizard.ui.download.setEnabled(False)
			self.wizard.ui.filename.setText("")
			self.wizard.ui.filesize.setText("")
			self.wizard.ui.description.setText("")
			self.wizard.ui.image.hide()

	def getPath(self,item):
		#path=""
		#parents=[item]
		#parent=item.parent()
		#while parent:
			#parents.append(parent)
			#parent=parent.parent()
		#parents.reverse()
		#for parent in parents:
			#path+=unicode(parent.text(0))+"/"
		return unicode(item.path)
		#return path[:-1]

	def doubleClicked(self,item,col=None):
		data=item.data(32).toList()
		size=int(data[0].toString())
		if size == -1 and self.typ!="easyshare":
			#size = unicode(data[0].toString()
			pwd = unicode(self.pwd)+unicode(item.text())+"/"
			pwd2 = pwd.replace("'","\\'").replace('"','\\"').replace(' ','\\ ')
			self.main.client.sendMessage(self.typ + "@disk.jabbim.cz", u"ls //"+self.jid+"%"+self.typ+pwd2)
			self.array.append((self.typ+'@disk.jabbim.cz',pwd,'ls'))
			self.wizard.ui.tree.clear()
			self.wizard.ui.path.setText(self.jid+"/"+self.typ+pwd)
			#self.showSlot(self.jid)
		elif size == -2:
			self.jid = unicode(data[1].toString())
			self.showSlot(self.jid)
		elif size == -3:
			self.showSlot(self.jid,unicode(data[1].toString()))
		else:
			if self.typ=="public":
				self.main.allowedJids["public@disk.jabbim.cz/"+unicode(item.text())]=self.cache
				self.main.client.sendMessage("public@disk.jabbim.cz", u"get //"+self.jid+"\%public"+unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				self.filesToOpen.append(self.cache+"/"+unicode(item.text()))
			elif self.typ=="private":
				self.main.allowedJids["private@disk.jabbim.cz/"+unicode(item.text())]=self.cache
				self.main.client.sendMessage("private@disk.jabbim.cz", u"get //"+self.jid+"\%private"+unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				self.filesToOpen.append(self.cache+"/"+unicode(item.text()))
			elif self.typ=="album":
				self.main.allowedJids["album@disk.jabbim.cz/"+unicode(item.text())]=self.cache
				self.main.client.sendMessage("album@disk.jabbim.cz", u"get //"+self.jid+"\%album"+unicode(self.pwd+unicode(item.text())).replace("'","\\'").replace('"','\\"').replace(' ','\\ '))
				self.filesToOpen.append(self.cache+"/"+unicode(item.text()))
			elif self.typ=="easyshare":
				contact = self.main.client.getContactByJid(self.jid)
				if contact:
					jid=self.jid+"/"+contact.getHighestResource()
					self.wizard.ui.path.setText(self.jid + "/" + self.typ + "/" + self.getPath(item))
					self.main.client.callRemote(jid, 'listShare',(self.getPath(item),)).addCallback(self.updateView,item)



