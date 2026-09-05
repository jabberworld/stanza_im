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
from groupchatadmin_ui import *
#import pyxl

from twisted.python import log
from widgets import dataforms
class groupchatAdminDialog(QtGui.QDialog):
	def __init__(self,main,jid,form,parent=None,subject="", admin = False):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.ui=Ui_groupchatAdmin()
		self.ui.setupUi(self)
		self.main=main
		self.jid=jid
		self.form=form
		self.subject=subject

		self.admin = admin

		if self.form:
			layout=QtGui.QGridLayout(self.ui.config)
			self.var,row=dataforms.makeDataForm(self.ui.config,layout,self.form)

			self.ui.subject.setPlainText(subject)
		else:
			self.ui.groupchatAdminTab.setTabEnabled(0,False)
			self.ui.groupchatAdminTab.setTabEnabled(1,False)
			self.ui.groupchatAdminTab.setCurrentIndex(2)
			self.ui.subject.setPlainText(subject)

		if admin == True:
			self.items={}
			nick = self.main.client.groupchats[self.jid].nick
			print self.jid+'/'+nick
			contact = self.main.client.getMucContactByJid(self.jid+'/'+nick)
			if contact != None:
				if contact.affiliation == 'owner':
					d=self.main.client.getMUCLists(self.jid, types = ['ban', 'member', 'admin', 'owner'])
					d.addCallback(self._gotLists)
				elif contact.affiliation == 'admin':
					d=self.main.client.getMUCLists(self.jid, types = ['ban', 'member'])
					d.addCallback(self._gotLists)		
				self.ui.groupchatAdminTab.setTabEnabled(1,True)	
			

	def _gotLists(self,data):
		jid=data[0]
		lists=data[1]
		#{'ban': (u'jabbim@conf.netlab.cz', 
		#{u'123098@jabber.intermax.com.ua': {u'affiliation': u'outcast', u'jid': u'123098@jabber.intermax.com.ua', 'reason': u''}
		#, u'jabber.intermax.com.ua': {u'affiliation': u'outcast', u'jid': u'jabber.intermax.com.ua', 'reason': u''}}), 'member': (u'jabbim@conf.netlab.cz', {u'zenek@jabbim.cz': {u'affiliation': u'member', u'jid': u'zenek@jabbim.cz', 'reason': u''}, u'lolek@njs.netlab.cz': {u'affiliation': u'member', u'jid': u'lolek@njs.netlab.cz', 'reason': u''}}), 'admin': (u'jabbim@conf.netlab.cz', {u'pyjim@jabber.cz': {u'affiliation': u'owner', u'jid': u'pyjim@jabber.cz', 'reason': u''}, u'hanzz@njs.netlab.cz': {u'affiliation': u'owner', u'jid': u'hanzz@njs.netlab.cz', 'reason': u''}, u'cornelius@njs.netlab.cz': {u'affiliation': u'owner', u'jid': u'cornelius@njs.netlab.cz', 'reason': u''}}), 'owner': (u'jabbim@conf.netlab.cz', {u'pyjim@jabber.cz': {u'affiliation': u'owner', u'jid': u'pyjim@jabber.cz', 'reason': u''}, u'hanzz@njs.netlab.cz': {u'affiliation': u'owner', u'jid': u'hanzz@njs.netlab.cz', 'reason': u''}, u'cornelius@njs.netlab.cz': {u'affiliation': u'owner', u'jid': u'cornelius@njs.netlab.cz', 'reason': u''}})}
		layout=QtGui.QGridLayout(self.ui.affiliation)
		self.tree=QtGui.QTreeWidget(self.ui.affiliation)
		QtCore.QObject.connect(self.tree, QtCore.SIGNAL("itemDoubleClicked ( QTreeWidgetItem *, int)"),self.itemDoubleClicked)
		QtCore.QObject.connect(self.tree, QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.contextMenu)
		
		self.tree.headerItem().setText(0,self.tr("JID"))
		self.tree.headerItem().setText(1,self.tr("Reason"))
		self.tree.setEditTriggers(self.tree.NoEditTriggers)
		#self.tree.setDragEnabled(True)
		#self.tree.setDragDropMode(QtGui.QAbstractItemView.InternalMove)
		self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)


		#self.tree.header().hide()
		layout.addWidget(self.tree,0,0,1,4)
		
		for key,value in lists.iteritems():
			parent=QtGui.QTreeWidgetItem(self.tree)
			parent.setText(0,unicode(key))
			parent.setExpanded(True)
			data=key
			if key=="ban":
				data="outcast"
			parent.setData(32,0,QtCore.QVariant(unicode(data)))
			for x,y in value[1].iteritems():
				item=QtGui.QTreeWidgetItem(parent)
				item.setText(0,unicode(y['jid']))
				item.setText(1,unicode(y['reason']))
				item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsEditable)
		self.tree.resizeColumnToContents(0)
		
		label=QtGui.QLabel(self.tr("Affiliation:"),self.ui.affiliation)
		layout.addWidget(label,1,0,1,1)
		self.affiliation=QtGui.QComboBox(self.ui.affiliation)
		self.affiliation.addItem(self.tr("Ban"),QtCore.QVariant(unicode("outcast")))
		self.affiliation.addItem(self.tr("Admin"),QtCore.QVariant(unicode("admin")))
		self.affiliation.addItem(self.tr("Owner"),QtCore.QVariant(unicode("owner")))
		self.affiliation.addItem(self.tr("Member"),QtCore.QVariant(unicode("member")))
		layout.addWidget(self.affiliation,1,1,1,1)
		
		label=QtGui.QLabel(self.tr("JID:"),self.ui.affiliation)
		layout.addWidget(label,1,2,1,1)
		self.jidLine=QtGui.QLineEdit(self.ui.affiliation)
		layout.addWidget(self.jidLine,1,3,1,1)
		
		label=QtGui.QLabel(self.tr("Reason:"),self.ui.affiliation)
		layout.addWidget(label,2,0,1,1)
		self.reasonLine=QtGui.QLineEdit(self.ui.affiliation)
		layout.addWidget(self.reasonLine,2,1,1,3)

		self.add=QtGui.QPushButton(self.tr("Add"),self.ui.affiliation)
		layout.addWidget(self.add,3,3,1,1)

		QtCore.QObject.connect(self.add, QtCore.SIGNAL("clicked()"),self.addAff)
		QtCore.QObject.connect(self.tree, QtCore.SIGNAL("itemChanged ( QTreeWidgetItem * , int )"),self.itemChanged)
		self.editItem=None

	def addAff(self):
		affiliation=unicode(self.affiliation.itemData(self.affiliation.currentIndex()).toString())
		jid=unicode(self.jidLine.text())
		reason=unicode(self.reasonLine.text())
		QtCore.QObject.disconnect(self.tree,QtCore.SIGNAL("itemChanged ( QTreeWidgetItem * , int )"),self.itemChanged)

		if len(jid)!=0:
			for i in range(self.tree.topLevelItemCount()):
				it=self.tree.topLevelItem(i)
				if unicode(it.data(32,0).toString())==affiliation:
					item=QtGui.QTreeWidgetItem(it)
					item.setText(0,jid)
					item.setText(1,reason)
					item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsEditable)
					self.items[unicode(item.text(0))+unicode(it.data(32,0).toString())]={"jid":unicode(item.text(0)),"reason":unicode(item.text(1)),"affiliation":unicode(it.data(32,0).toString())}
					break
		QtCore.QObject.connect(self.tree, QtCore.SIGNAL("itemChanged ( QTreeWidgetItem * , int )"),self.itemChanged)

	def itemChanged(self,item,i):
		parent=item.parent()
		if parent!=None and self.editItem!=None:
			print "settings"
			#self.items[unicode(self.editItem.text(0))+unicode(parent.data(32,0).toString())]={"jid":unicode(self.editItem.text(0)),"reason":unicode(self.editItem.text(1)),"affiliation":unicode(parent.data(32,0).toString())}
			self.items[unicode(self.editItem.text(0))+unicode(parent.data(32,0).toString())]={"jid":unicode(self.editItem.text(0)),"reason":"","affiliation":"none",'old':unicode(parent.data(32,0).toString())}
			self.items[unicode(item.text(0))+unicode(parent.data(32,0).toString())]={"jid":unicode(item.text(0)),"reason":unicode(item.text(1)),"affiliation":unicode(parent.data(32,0).toString())}
			self.editItem=None

	def contextMenu(self,pos):
		item=self.tree.itemFromIndex(self.tree.indexAt(pos)) # get selected item
		menu=QtGui.QMenu(self.tree) # make menu
		if item.parent()!=None:
			# Join bookmarked groupchat
			action=menu.addAction(self.tr("Delete item"))
			action.setData(item.data(0,32))
			action.setObjectName("delete")

		menu.connect(menu, QtCore.SIGNAL("triggered ( QAction * )"),self.contextMenuTriggered)
		# set menu position and show
		menu.popup(self.tree.mapToGlobal(pos))
	
	def contextMenuTriggered(self,action):
		cmd=action.objectName()
		if cmd=="delete":
			item=self.tree.currentItem()
			parent=item.parent()
			self.items[unicode(item.text(0))+unicode(parent.data(32,0).toString())]={"jid":unicode(item.text(0)),"reason":"","affiliation":"none",'old':unicode(parent.data(32,0).toString())}
			parent.takeChild(parent.indexOfChild(item))
	
	def itemDoubleClicked(self,item,i):
		#pass
		parent=item.parent()
		if parent==None:
			return
		self.editItem=item.clone()
		self.tree.editItem(item,i)
		#parent=item.parent()
		#if parent==None:
			#return
		#index=self.affiliation.findData(parent.data(32,0))
		#if index!=-1:
			#self.affiliation.setCurrentIndex(int(index))
			
	
	def accept(self):
		
		#{i:{"reason":reason,"jid":jid,"affiliation":affiliation},}
		if self.admin:
			for aff in ['outcast', 'member', 'admin', 'owner']:
				x=0
				items={}
				for item in self.items.itervalues():
					if item['affiliation']==aff:
						items[x]={"jid":item['jid'],"reason":item['reason'],"affiliation":item['affiliation']}
						x+=1
					if item.has_key('old'):
						if item['old']==aff:
							items[x]={"jid":item['jid'],"reason":item['reason'],"affiliation":item['affiliation']}
							x+=1
				if len(items)!=0:
					print items
					self.main.client.setMUCList(self.jid, items,"")
		if self.form:
			dataforms.sendDataForm(self.main,self.jid,self.form,self.var,"muc")
		if unicode(self.ui.subject.toPlainText())!=unicode(self.subject):
			self.main.client.sendMessage(self.jid, typ='groupchat', body=None, subject=unicode(self.ui.subject.toPlainText()))
		self.done(1)

#	def reject(self):
#		self.close()
