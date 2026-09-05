import os
from PyQt4 import QtCore, QtGui
from servicediscovery_ui import *
import dataforms
import legacyforms
from search import *
import commands
import addcontact
import weakref
from include.constants import RESOURCEPATH

class table(QtGui.QTreeWidget):
	def __init__(self,parent=None,service=None):
		QtGui.QTreeWidget.__init__(self,parent)
		self.setDragEnabled(True)
		self.setIconSize(QtCore.QSize(48,48))
		self.setObjectName("serviceDiscoveryTree")
		self.headerItem().setText(0,QtGui.QApplication.translate("serviceDiscovery", "name", None, QtGui.QApplication.UnicodeUTF8))
		self.headerItem().setText(1,QtGui.QApplication.translate("serviceDiscovery", "search", None, QtGui.QApplication.UnicodeUTF8))
		self.headerItem().setText(2,QtGui.QApplication.translate("serviceDiscovery", "register", None, QtGui.QApplication.UnicodeUTF8))
		self.headerItem().setText(3,QtGui.QApplication.translate("serviceDiscovery", "jid", None, QtGui.QApplication.UnicodeUTF8))
		self.headerItem().setText(4,QtGui.QApplication.translate("serviceDiscovery", "commands", None, QtGui.QApplication.UnicodeUTF8))
		self.headerItem().setText(5,QtGui.QApplication.translate("serviceDiscovery", "node", None, QtGui.QApplication.UnicodeUTF8))
		self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
		self.service=service

	def hasFeature(self,item,feature):
		for data in item.data(32,0).toList():
			if unicode(data.toString())==feature:
				return True
		return False


	def startDrag(self,actions):
		# start dragging selected contact
		item=self.currentItem()
		jid=unicode(item.text(3))
		if len(jid)!=0:
			self.drag=QtGui.QDrag(self)
			mimeData=QtCore.QMimeData()
			mimeData.setText(jid)
			self.drag.setMimeData(mimeData)
			self.action=self.drag.start(QtCore.Qt.CopyAction)

	def contextMenuEvent(self,event):
		print "context menu"
		item=self.itemFromIndex(self.indexAt(QtCore.QPoint(event.x(),event.y())))
		if item is None:
			return
		jid=unicode(item.text(3))
		if len(jid)==0:
			return
		menu=QtGui.QMenu(self)
		if self.service.main().getJid(jid):
			action=menu.addAction(self.tr("Add to roster"))
			action.setObjectName("add_to_roster")
			menu.addSeparator()
		if self.hasFeature(item,"jabber:iq:register"):
			action=menu.addAction(self.tr("Register / Unregister"))
			action.setObjectName("register")
		if self.hasFeature(item,"jabber:iq:search"):
			action=menu.addAction(self.tr("Search service for users"))
			action.setObjectName("search")
		if self.hasFeature(item,"http://jabber.org/protocol/commands"):
			action=menu.addAction(self.tr("Execute extra action"))
			action.setObjectName("command")
		menu.connect(menu, QtCore.SIGNAL("triggered ( QAction * )"),self.menuTriggered)
		menu.popup(QtCore.QPoint(event.globalX(),event.globalY()))


	def menuTriggered(self,action):
		cmd=action.objectName()
		jid=unicode(self.currentItem().text(3))
		name=unicode(self.currentItem().text(1))
		node=unicode(self.currentItem().text(5))
		if cmd=="add_to_roster":
			dialog=addcontact.addContactDialog(self.service.main(),self.service.main(),jid=jid,name=jid.split('@')[0])
			dialog.exec_()
		elif cmd=="register":
			d=self.service.main().client.getRegisterForm(unicode(jid))
			d.addCallback(self.service._onRegister)
		elif cmd=="search":
			d=self.service.main().client.getSearchForm(jid)
			d.addCallback(self.service._gotSearchForm)
		elif cmd=="command":
			if node:
				cmds = commands.Commands(self.service.main(), jid, getItems=False)
				cmds.execCommand(node, name, jid)
			else:
				cmds = commands.Commands(self.service.main(), jid)
			cmds.dialog.show()
			



class serviceDiscoveryDialog(QtGui.QDialog):
	def __init__(self,main,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		if isinstance(main,weakref.ref):
			self.main=main
		else:
			self.main=weakref.ref(main)

		self.setModal(False)
		self.ui=Ui_serviceDiscovery()
		self.ui.setupUi(self)
		
		self.ui.reload.setEnabled(False)
		if not self.main().client.jid.host in self.main().config['discoHistory']:
			self.main().config['discoHistory'].append(self.main().client.jid.host)
		for server in self.main().config['discoHistory']:
			self.ui.server.addItem(server)
		
		layout=QtGui.QHBoxLayout(self.ui.treeWidget)
		layout.setMargin(0)
		self.ui.tree=table(self.ui.treeWidget,self)
		layout.addWidget(self.ui.tree)
		
		#for category in self.getCategories():
		self.ui.tree.header().hide()
		self.ui.tree.hideColumn(3)
		QtCore.QObject.connect(self.ui.tree, QtCore.SIGNAL("itemExpanded ( QTreeWidgetItem * )"),self.expanded)
		QtCore.QObject.connect(self.ui.tree, QtCore.SIGNAL("itemCollapsed ( QTreeWidgetItem * )"),self.collapsed)
		QtCore.QObject.connect(self.ui.tree, QtCore.SIGNAL("itemDoubleClicked ( QTreeWidgetItem * , int )"),self.itemClicked)
		QtCore.QObject.connect(self.ui.tree, QtCore.SIGNAL("currentItemChanged ( QTreeWidgetItem * , QTreeWidgetItem *  )"),self.itemSelected)
		#QtCore.QObject.connect(self.ui.register, QtCore.SIGNAL("clicked()"),self.register)
		#QtCore.QObject.connect(self.ui.search, QtCore.SIGNAL("clicked()"),self.search)
		self.group=QtGui.QButtonGroup(self)
		QtCore.QObject.connect(self.group,QtCore.SIGNAL("buttonClicked ( QAbstractButton * )"),self.buttonClicked)

		QtCore.QObject.connect(self.ui.reload,QtCore.SIGNAL("clicked()"),self.discoReload)
#		self.ui.server.setText(self.main().client.jid.host)
		self.server = self.main().client.jid.host
		self.ui.server.setFocus(QtCore.Qt.MouseFocusReason)

#d=self.main().client.getRegisterForm(jid)
		#self.load()
		
		self.main().client.getDiscoItems(self.main().client.jid.host, callback = self.load).addErrback(self._discoErr)

		#for key in self.main().client.disco.keys():
			#if self.main().client.disco[key][None].has_key("identities"):
				#item=QtGui.QTreeWidgetItem(self.ui.tree)
				#for identity,values in self.main().client.disco[key][None]["identities"].iteritems():
					#if 
				
			#elif self.main().client.disco[key][None].has_key("err"):
				#print key,"error"
	def _discoErr(self, err):
		print 'disco error ', err
		self.ui.reload.setEnabled(True)
		
	def discoReload(self):
		self.ui.reload.setEnabled(False)
		self.server = unicode(self.ui.server.currentText())
		if not self.server in self.main().config['discoHistory']:
			self.main().config['discoHistory'].append(self.server)
#			self.ui.server.addItem(self.server)
#			self.ui.server.setCurrentIndex(len(self.main().config['discoHistory']))

		self.ui.tree.clear()
		self.main().client.getDiscoItems(self.server, callback = self.load).addErrback(self._discoErr)

	def buttonClicked(self,b):
		if b.typ=="register":
			d=self.main().client.getRegisterForm(unicode(b.jid))
			d.addCallback(self._onRegister)
		elif b.typ=="search":
			d=self.main().client.getSearchForm(b.jid)
			d.addCallback(self._gotSearchForm)
		elif b.typ=="cmds":
			if b.node:
				cmds = commands.Commands(self.main, b.jid, getItems=False)
				cmds.execCommand(b.node, b.name, b.jid)
			else:
				cmds = commands.Commands(self.main, b.jid)
			#cmds = commands.Commands(self.main, b.jid)
			cmds.dialog.show()



	def register(self):
		jid=unicode(self.ui.tree.currentItem().text(3))
		d=self.main().client.getRegisterForm(jid)
		d.addCallback(self._onRegister)

	def search(self):
		jid=unicode(self.ui.tree.currentItem().text(3))
		d=self.main().client.getSearchForm(jid)
		d.addCallback(self._gotSearchForm)

	def _gotSearchForm(self,data):
		if not data:
			return
		jid,legacy,form=data
		if form!=None:
			self.dialog=searchDialog(self.main,jid,form,self)
			self.dialog.show()

	def _onRegister(self,data):
		if not data:
			return
		jid,legacy,form=data
		if form!=None:
			self.dialog=dataforms.dataFormsDialog(self.main(),form,jid,"register",self)
			self.dialog.show()
		else:
			self.dialog=legacyforms.legacyFormsDialog(self.main,legacy,jid,"disco",self)
			self.dialog.show()

	def expanded(self,item):
		self.ui.tree.resizeColumnToContents(0)
		#self.ui.tree.resizeColumnToContents(1)
		#self.ui.tree.resizeColumnToContents(2)

	def collapsed(self,item):
		self.ui.tree.resizeColumnToContents(0)
		#self.ui.tree.resizeColumnToContents(1)
		#self.ui.tree.resizeColumnToContents(2)

	def itemClicked(self,item,i):
		jid=unicode(item.text(3))
		if len(jid)==0:
			return
		if self.main().client.hasIdentity(jid, 'conference'):
			#self.done(1)
			self.main().mucBrowser()
			self.main().joingroupchatwizard.ui.serverName.addItem(jid)
			self.main().joingroupchatwizard.ui.serverName.setCurrentIndex(self.main().joingroupchatwizard.ui.serverName.count()-1)
			return
		
		#self.main().client.getDiscoItems(jid, callback = self._discoItemsReceived, callback_par = (item,True))

	def itemSelected(self,item,old):
		if item is None:
			return
		jid=unicode(item.text(3))
		node=unicode(item.text(5))
		if len(node)==0:
			node = None
			
		if len(jid)==0:
			return
		if self.main().client.hasIdentity(jid, 'conference', 'text'):
			return
		self.main().client.getDiscoItems(jid, node = node, callback = self._discoItemsReceived, callback_par = (item,False,node))

	def _discoinfo(self,item,node_key=None):
		(item,node_key) = item
		key = unicode(item.text(3))
		#print key,self.main().client.disco.keys()
		if self.main().client.disco[key][(key,node_key)].has_key("features"):
			if "jabber:iq:register" in list(self.main().client.disco[key][(key,node_key)]['features']):
				register=QtGui.QPushButton(self.ui.tree)
				#register.setMaximumWidth(40)
				#register.setMinimumWidth(24)
				register.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/register.png"))
				register.setIconSize(QtCore.QSize(32,32))
				#register.setEnabled(False)
				register.setFlat(True)
				register.jid=item.text(3)
				register.typ="register"
				register.setToolTip(self.tr("Register service"))
				self.group.addButton(register)
				self.ui.tree.setItemWidget(item,2,register)
			if "jabber:iq:search" in list(self.main().client.disco[key][(key,node_key)]['features']):
				search=QtGui.QPushButton(self.ui.tree)
				#search.setMaximumWidth(16)
				#search.setMinimumWidth(24)
				search.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/search.png"))
				search.setIconSize(QtCore.QSize(32,32))
				#search.setEnabled(False)
				search.setFlat(True)
				search.jid=item.text(3)
				search.typ="search"
				search.setToolTip(self.tr("Search service for users"))
				self.group.addButton(search)
				self.ui.tree.setItemWidget(item,1,search)
			if "http://jabber.org/protocol/commands" in list(self.main().client.disco[key][(key,node_key)]['features']):
				cmds=QtGui.QPushButton(self.ui.tree)
				cmds.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/exec.png"))
				cmds.setIconSize(QtCore.QSize(32,32))
				cmds.setFlat(True)
				cmds.jid=item.text(3)
				cmds.node=node_key
				cmds.name=unicode(item.text(1))
				cmds.typ="cmds"
				cmds.setToolTip(self.tr("Execute extra action"))
				self.group.addButton(cmds)
				self.ui.tree.setItemWidget(item,4,cmds)
			item.setData(32,0,QtCore.QVariant(list(self.main().client.disco[key][(key,node_key)]['features'])))
		else:
			item.setData(32,0,QtCore.QVariant(list([])))

	def _discoItemsReceived(self,data,node_key=None):
		item=data[0]
		expand=data[1]
		node_key=data[2]
		jid=unicode(item.text(3))
		for i in range(item.childCount()):
			item.takeChild(0)
		print self.main().client.disco[jid]
		for (key,node),values in self.main().client.disco[jid][(jid,node_key)]['items'].iteritems():
			#print values
			it=QtGui.QTreeWidgetItem(item)
			it.setText(3,self.main().getJid(values['jid']).full())
			if values.has_key("name"):
				it.setText(0,values["name"])
			else:
				it.setText(0,key)
			if values.has_key("node"):
				it.setText(5,values["node"])
			it.setIcon(0,item.icon(0))
			it.setToolTip(0,values['jid'])
			self.main().client.getDiscoInfo(values['jid'],node=node,callback=self._discoinfo, callback_par = (it,node))
		self.ui.tree.sortItems(0,QtCore.Qt.AscendingOrder)
		item.setExpanded(expand)
		
		self.ui.tree.resizeColumnToContents(0)

	def load(self,data=None,node_key=None):
		self.ui.reload.setEnabled(True)
		categories={}
		self.services=QtGui.QTreeWidgetItem(self.ui.tree)
		self.services.setText(0,self.tr("Services"))
		self.services.setIcon(0,QtGui.QIcon(RESOURCEPATH+"images/48x48/apps/jabbim.png"))
		self.transports=QtGui.QTreeWidgetItem(self.ui.tree)
		self.transports.setText(0,self.tr("Transports"))
		self.transports.setIcon(0,QtGui.QIcon(RESOURCEPATH+"images/48x48/apps/jabbim.png"))
		self.conferences=QtGui.QTreeWidgetItem(self.ui.tree)
		self.conferences.setText(0,self.tr("Conferences"))
		self.conferences.setIcon(0,QtGui.QIcon(RESOURCEPATH+"images/48x48/categories/conferences.png"))
		#print self.main().client.disco.keys()
		#key=self.main().client.jid.host
		key = self.server
		if key in self.main().client.disco.keys():
			if self.main().client.disco[key][(key,node_key)].has_key("identities"):
				if self.main().client.disco[key][(key,node_key)].has_key("items"):
					for item,values in self.main().client.disco[key][(key,node_key)]['items'].iteritems():
						print "disco items for "+values['jid']
						(key,node) = item
						self.main().client.getDiscoInfo(values['jid'], node=node, callback = self.root,callback_par=(values['jid']))

				
			elif self.main().client.disco[key][(key,node_key)].has_key("err"):
				print key,"error"
			print self.main().client.disco.get(key)
		print categories.keys()
		return categories

	def root(self,data=None,node_key=None):
		key=data
		print "get disco items "+data
		if key in self.main().client.disco.keys():
			if self.main().client.disco[key][(key,node_key)].has_key("identities"):
				for identity,values in self.main().client.disco[key][(key,node_key)]["identities"].iteritems():
					parentitem=None
					if values.has_key('category'):
						#if not values['category'] in categories.keys():
							#item=QtGui.QTreeWidgetItem(self.ui.tree)
							#item.setText(0,values['category']) # todo => lepsi nazvy
							#item.setIcon(0,QtGui.QIcon("images/48x48/apps/jabbim.png"))
							#categories[values['category']]=item
						if values.has_key('name'):
							#[u'conference', u'service', u'headline', u'component', u'server', u'services', u'proxy', u'directory', u'gateway', u'store', u'pubsub']
							if values['category'] in ['service','headline','services','store','directory','component']:
								parentitem=QtGui.QTreeWidgetItem(self.services)
							elif values['category'] in ['conference']:
								parentitem=QtGui.QTreeWidgetItem(self.conferences)
							elif values['category'] in ['gateway']:
								parentitem=QtGui.QTreeWidgetItem(self.transports)
							if parentitem:
								parentitem.setText(0,values['name'])
								if values.has_key("type"):
									typ=values['type']
									if typ=="pep" or typ=="im":
										typ="jabber"
									elif typ=="file":
										typ="disk"
									parentitem.setIcon(0,self.main().getIcon(size="22x22",usertype=typ))
									parentitem.setText(3,key)
									parentitem.setToolTip(0,key)
					if self.main().client.disco[key][(key,node_key)].has_key("features") and parentitem:
						parentitem.setData(32,0,QtCore.QVariant(list(self.main().client.disco[key][(key,node_key)]['features'])))
	
						if "jabber:iq:register" in list(self.main().client.disco[key][(key,node_key)]['features']):
							register=QtGui.QPushButton(self.ui.tree)
							#register.setMaximumWidth(40)
							#register.setMinimumWidth(24)
							register.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/register.png"))
							register.setIconSize(QtCore.QSize(32,32))
							#register.setEnabled(False)
							register.setFlat(True)
							register.jid=parentitem.text(3)
							register.typ="register"
							register.setToolTip(self.tr("Register service"))
							self.group.addButton(register)
							self.ui.tree.setItemWidget(parentitem,2,register)
						if "jabber:iq:search" in list(self.main().client.disco[key][(key,node_key)]['features']):
							search=QtGui.QPushButton(self.ui.tree)
							#search.setMaximumWidth(16)
							#search.setMinimumWidth(24)
							search.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/search.png"))
							search.setIconSize(QtCore.QSize(32,32))
							#search.setEnabled(False)
							search.setFlat(True)
							search.jid=parentitem.text(3)
							search.typ="search"
							search.setToolTip(self.tr("Search service for users"))
							self.group.addButton(search)
							self.ui.tree.setItemWidget(parentitem,1,search)
						if "http://jabber.org/protocol/commands" in list(self.main().client.disco[key][(key,node_key)]['features']):
							cmds=QtGui.QPushButton(self.ui.tree)
							cmds.setMaximumWidth(34)
							cmds.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/exec.png"))
							cmds.setIconSize(QtCore.QSize(32,32))
							cmds.setFlat(True)
							cmds.jid=parentitem.text(3)
							cmds.node=node_key
							cmds.name=unicode(parentitem.text(1))
							cmds.typ="cmds"
							cmds.setToolTip(self.tr("Execute extra action"))
							self.group.addButton(cmds)
							self.ui.tree.setItemWidget(parentitem,4,cmds)
		self.ui.tree.sortItems(0,QtCore.Qt.AscendingOrder)
		self.ui.tree.resizeColumnToContents(0)
		self.ui.tree.setColumnWidth (1,34)
		self.ui.tree.setColumnWidth (2,34)
		self.ui.tree.setColumnWidth (4,34)
	def accept(self):
		self.done(1)


