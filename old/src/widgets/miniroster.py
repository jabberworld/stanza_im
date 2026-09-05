import os,weakref
from PyQt4 import QtCore, QtGui
from miniroster_ui import *
from twisted.internet import threads

class miniRosterDialog(QtGui.QDialog):
	def __init__(self,main,call,multiple=False,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.ui=Ui_miniRoster()
		self.ui.setupUi(self)
		self.main=weakref.ref(main)
		self.multiple=multiple
		self.call=call
		self.ui.users.header().hide()
		if not self.multiple:
			QtCore.QObject.connect(self.ui.users,QtCore.SIGNAL("itemDoubleClicked ( QTreeWidgetItem *, int )"),self.accept)
		QtCore.QObject.connect(self.ui.search,QtCore.SIGNAL(" textChanged ( const QString &)"),self.search)
		self.showUsers(self.main().ui.roster.users)
		
		self.searchIndex=list(self.main().ui.roster.users)

	def showUsers(self,allowedUsers):
		groups={}
		keys=[]
		for group in self.main().ui.roster.groups.keys():
			groups[group.replace(self.main().ui.roster.specialName,unicode(self.tr('Unknown')).lower())]=group
			keys.append(group.replace(self.main().ui.roster.specialName,unicode(self.tr('Unknown')).lower()))
		keys.sort()
		selected=False
		for g in sorted(keys):
			group=groups[unicode(g)]
			groupItem=self.main().ui.roster.groups[group]
			users=[]
			parent=QtGui.QTreeWidgetItem(self.ui.users)
			parent.setText(0,unicode(groupItem.name).replace(self.main().ui.roster.specialName,unicode(self.tr('Unknown'))))
			self.ui.users.setItemExpanded(parent,True)
			for user in self.main().ui.roster.users:
				if user.group==group and user in allowedUsers:
					users.append([user.name.lower(),user])
			users.sort()
			for user in users:
				item=user[1]
				child=QtGui.QTreeWidgetItem(parent)
				child.setText(0,item.name)
				child.jid=item.jid
				if not selected:
					self.ui.users.setCurrentItem(child)
					selected=True
				avatar=self.main().client.getAvatarImg(item.jid)
				if avatar:
					avatar=avatar[0]
				else:
					avatar=self.main().client.getAvatarImg(None)
					if avatar:
						avatar=avatar[0]
				avatar=avatar.scaled(22,22,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
				child.setIcon(0,QtGui.QIcon(avatar))

	def search(self,text):
		d=threads.deferToThread(self.compare,unicode(text),self.searchIndex)
		d.addCallback(self.compared)

	def compare(self,text,jids):
		ret=[]
		for user in jids:
			if unicode(user.name).lower().find(text)!=-1:
				ret.append(user)
		return ret
	def compared(self,rooms):
		self.ui.users.clear()
		self.showUsers(rooms)
		

	def accept(self,item=None,i=None):
		item=self.ui.users.currentItem()
		if item and item.parent()!=None:
			self.call(item.jid)
			QtGui.QDialog.accept(self)
