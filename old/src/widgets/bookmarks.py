from PyQt4 import QtCore, QtGui
import weakref
from widgets.chat import mucbrowser
from widgets.chat import joingroupchat
import preferences
from include.constants import RESOURCEPATH

class bookmarksClass:
	def __init__(self,bookmarks,main):
		self.bookmarks=bookmarks
		self.main=main
		#self.bookmarks.setItemDelegate(mucbrowser.delegate(0,self.bookmarks,22))
		self.bookmarks.setAlternatingRowColors(False)
		

		QtCore.QObject.connect(self.bookmarks, QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.bookmarksContextMenu)
		#QtCore.QObject.connect(self.bookmarks, QtCore.SIGNAL("currentItemChanged ( QTreeWidgetItem * , QTreeWidgetItem * )"),self.bookmarksCurrentChanged)
		#QtCore.QObject.connect(self.bookmarks, QtCore.SIGNAL("itemActivated ( QTreeWidgetItem *, int )"),self.bookmarksClicked)
		QtCore.QObject.connect(self.bookmarks, QtCore.SIGNAL("itemDoubleClicked ( QTreeWidgetItem * , int )"),self.bookmarksClicked)
		#QtCore.QObject.connect(self.bookmarks, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem *, int )"),self.bookmarksItemClicked)

		QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self.bookmarks,self.deleteCurrentBookmark)
		
		# set up bookmarks treeWidget
		self.bookmarks.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
		self.bookmarks.header().hide()
		self.bookmarks.hideColumn(1)
		
	#def on_discoItemsBookmarksReceived(self, par):
		#"""
		#Called when disco#items of bookmarked groupchat arrived.
		#"""
		#item = par[1]
		#mainWindow=self.main
		#if len(self.main.client.disco[unicode(par[0])][None]['items'])!=0:
			#users="<b>"+unicode(mainWindow.tr("Users:"))+"</b> "
			#for usr in self.main.client.disco[unicode(par[0])][None]['items'].itervalues():
				#users+=usr['name']+", "
		#else:
			#users=unicode(mainWindow.tr("There is no user"))
		#if item in self.bookmarks.selectedItems():
			#item.setData(0,32,QtCore.QVariant(users))
			#metrics=QtGui.QApplication.fontMetrics()
			#rect=metrics.boundingRect(0, 0,self.main.ui.bookmarks.columnWidth(0), self.main.height(), QtCore.Qt.TextWordWrap, "Users: "+unicode(item.data(0,32).toString()))
			#print 'aa',metrics.height(),rect.height()
			#item.setSizeHint(0,QtCore.QSize(100,metrics.height()*2+rect.height()))
			#self.main.ui.bookmarks.repaint()

	def bookmarksClicked(self,item,i):
		"""
		Joins MUC when user clicked on bookmark in Bookmarks tab.
		"""
		data=item.data(1,32)
		lst=data.toList()
		if len(lst)!=0:
			jid=unicode(lst[0].toString())
			nickname=unicode(lst[1].toString())
			password = unicode(lst[2].toString())
			if self.main.chat.addGroupChatTab(jid,nickname):
				self.main.client.joinGC(jid, nickname, password,self.main.config['sendRooms']=="True")
		elif item.text(1):
			j=self.main.getJid(unicode(item.text(1)))
			self.joingroupchatwizard=joingroupchat.joinGroupChatWindow(self.main,room=unicode(j.userhost()).split("@")[0],server=unicode(j.userhost()).split("@")[1],parent=self.main)
			self.joingroupchatwizard.show()

	def buildBookmarks(self,data=False):
		"""
		Adds bookmarks items to self.bookmarks (QTreeWidget)
		"""
		if data==False:
			self.bookmarks.clear()
			mainWindow=self.main
			parent=QtGui.QTreeWidgetItem(self.bookmarks)
			parent.setText(0,mainWindow.tr("Bookmarked Rooms"))
			parent.setIcon(0,QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/bookmarks.png"))
			#parent.setTextAlignment(0,QtCore.Qt.AlignCenter)
			parent.setBackground(0,QtGui.QBrush(self.bookmarks.palette().color(QtGui.QPalette.AlternateBase)))
			parent.setExpanded(True)
			for k,v in self.main.client.bookmarks['conference'].iteritems():
				item=QtGui.QTreeWidgetItem(parent)
				item.setText(0,unicode(v.name))
				item.setText(1,unicode(v.jid.full()))
				item.setData(1,32,QtCore.QVariant(QtCore.QStringList([unicode(v.jid.full()),unicode(v.nick),unicode(v.password)])))
				item.setIcon(0,QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/bookmarks.png"))
			if self.main.config['remoteMucList']=="True":
				self.main.client.callRemote('rpc@jabbim.cz/service', 'conf',('cs',)).addCallback(self.buildBookmarks)
		else:
			data=data[0][0]
			keys=data.keys()
			keys.reverse()
			for category in keys:
				rooms=data[category]
				parent=QtGui.QTreeWidgetItem(self.bookmarks)
				parent.setText(0,unicode(category))
				#parent.setTextAlignment(0,QtCore.Qt.AlignCenter)
				parent.setBackground(0,QtGui.QBrush(self.bookmarks.palette().color(QtGui.QPalette.AlternateBase)))
				parent.setExpanded(True)
				for room in rooms:
					item=QtGui.QTreeWidgetItem(parent)
					item.setText(0,unicode(room[1]))
					item.setText(1,unicode(room[0]))
					item.setIcon(0,QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/muc.png"))
					

	def deleteCurrentBookmark(self):
		"""
		Deletes currently selected bookmark.
		"""
		item=self.bookmarks.currentItem()
		if item:
			del self.main.client.bookmarks['conference'][unicode(item.text(0))]
			self.main.client.setBookmarks()
			self.buildBookmarks()

	def bookmarksContextMenu(self,pos):
		"""
		Makes bookmarks context menu. Called when user right-click on bookmark.
		"""
		mainWindow=self.main
		# make groupchat bookmarks menu
		item=self.bookmarks.itemFromIndex(self.bookmarks.indexAt(pos)) # get selected item
		jid=unicode(item.text(1)) # get item jid
		menu=QtGui.QMenu(self.bookmarks) # make menu
		if item.parent():
			# Join bookmarked groupchat
			data=item.data(1,32)
			lst=data.toList()
			if len(lst)!=0:
				action=menu.addAction(mainWindow.tr("Join"))
				action.setData(item.data(1,32))
				action.setObjectName("join")
				# separator
				menu.addSeparator()
				# Edit bookmark
				action=menu.addAction(mainWindow.tr("Edit bookmark"))
				action.setData(item.data(1,32))
				action.setObjectName("edit")
				# Delete bookmark
				action=menu.addAction(mainWindow.tr("Delete bookmark"))
				action.setData(item.data(1,32))
				action.setObjectName("delete")
			else:
				action=menu.addAction(mainWindow.tr("Join"))
				action.setData(QtCore.QVariant(jid))
				action.setObjectName("join")
				action=menu.addAction(mainWindow.tr("Bookmark"))
				action.setData(QtCore.QVariant(jid))
				action.setObjectName("bookmark")
		menu.connect(menu, QtCore.SIGNAL("triggered ( QAction * )"),self.bookmarksContextMenuTriggered)
		menu.popup(self.bookmarks.mapToGlobal(pos))

	def bookmarksContextMenuTriggered(self,action):
		"""
		Executes command according to action.objectName(). Called when user choose one of QAction from bookmarks menu.
		@type action: QAction
		@param action: QAction from bookmarks menu
		"""
		cmd=action.objectName()
		if cmd=="join":
			# join bookmarked groupchat
			data=action.data()
			lst=data.toList()
			if len(lst)!=0:
				jid=unicode(lst[0].toString())
				nickname=unicode(lst[1].toString())
				password = unicode(lst[2].toString())
				if self.main.chat.addGroupChatTab(jid,nickname):
					self.main.client.joinGC(jid, nickname, password,self.main.config['sendRooms']=="True")
			else:
				jid=unicode(data.toString())
				j=self.main.getJid(unicode(jid))
				self.joingroupchatwizard=joingroupchat.joinGroupChatWindow(self.main,room=unicode(j.userhost()).split("@")[0],server=unicode(j.userhost()).split("@")[1],parent=self.main)
				self.joingroupchatwizard.show()
		elif cmd=="edit":
			item=self.bookmarks.currentItem()
			data=action.data()
			lst=data.toList()
			jid=unicode(lst[0].toString()) # get jid
			if len(jid.split("@"))!=1:
				room=jid.split("@")[0]
				server=jid.split("@")[1]
			else:
				room=jid
			name=unicode(item.text(0))
			nickname=unicode(lst[1].toString()) # get nickname
			password=unicode(lst[2].toString()) # get password
			autojoin=self.main.client.bookmarks['conference'][jid].autojoin
			if password=="None" or not password:
				password=""
			edit=preferences.editBookmark(self.main,room,server,name,nickname,password,autojoin,self.main)
			edit.exec_()
		elif cmd=="delete":
			item=self.bookmarks.currentItem()
			del self.main.client.bookmarks['conference'][unicode(item.text(1))]
			self.main.client.setBookmarks()
			self.buildBookmarks()
		elif cmd=="bookmark":
			
			data=action.data()
			jid=unicode(data.toString()) # get jid
			if len(jid.split("@"))!=1:
				room=jid.split("@")[0]
				server=jid.split("@")[1]
			else:
				print "bad jid"
				return
			name=room
			nickname=unicode(self.main.client.jid.user) # get nickname
			password=unicode("") # get password
			autojoin=False
			edit=preferences.editBookmark(self.main,room,server,name,nickname,password,autojoin,self.main)
			edit.exec_()

	#def bookmarksItemClicked(self,item,i):
		#return
		#if item.isExpanded():
			#self.bookmarks.collapseItem(item)
		#else:
			#self.bookmarks.expandItem(item)

	#def bookmarksCurrentChanged(self,item,old):
		#if item and old and item.parent() and old.parent():
			#item.setSizeHint(0,old.sizeHint(0))

		#if old and old.parent():
			#old.setData(0,QtCore.Qt.SizeHintRole,QtCore.QVariant())

		#if item != None and item.parent():
			##self.bookmarks.setCurrentItem(item)
			#self.main.client.getDiscoItems(unicode(item.text(1)),callback=self.on_discoItemsBookmarksReceived,callback_par=(unicode(item.text(1)), item))
