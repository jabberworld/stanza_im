# -*- coding: utf-8 -*-
"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See theF
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
import sys,os

from PyQt4 import QtCore, QtGui
from os.path import basename
from twisted.python import log
import dataforms,legacyforms
from pyxl import jid as jidT
import time
import filetransfer
import albumfiletransfer
import addcontact
import vcardeditor
import commands
import defaultrosterstyle
import compactrosterstyle
import miniroster
from locale import strcoll
import operator
import weakref
import tooltip
from include.constants import RESOURCEPATH

class emptyRosterWidget(QtGui.QWidget):
	def __init__(self,main,parent=None):
		QtGui.QWidget.__init__(self,parent)
		layout=QtGui.QVBoxLayout(self)
		self.label=QtGui.QLabel(self)
		self.label.setWordWrap(True)
		self.main=weakref.ref(main)
		#self.label.setMinimumHeight(200)
		layout.addWidget(self.label)

		self.add=QtGui.QPushButton(self.tr("Add contact"),self)
		layout.addWidget(self.add)

		if unicode(QtCore.QLocale.system().name())[:2] in ['cs','sk']:
			self.icq=QtGui.QPushButton(self.tr("Show all my ICQ friends"),self)
			layout.addWidget(self.icq)
			QtCore.QObject.connect(self.icq,QtCore.SIGNAL("clicked()"),self.registerICQ)

		#layout.addStretch()

		QtCore.QObject.connect(self.add,QtCore.SIGNAL("clicked()"),main.addContactMainWindow)

	def registerICQ(self):
		d=self.main().client.getRegisterForm("icq.jabber.cz")
		d.addCallback(self._onRegister)

	def _onRegister(self,data):
		if not data:
			return
		jid,legacy,form=data
		if form!=None:
			self.dialog=dataforms.dataFormsDialog(self.main(),form,jid,"register",self)
			self.dialog.show()
		else:
			self.dialog=legacyforms.legacyFormsDialog(self.main(),legacy,jid,"disco",self)
			self.dialog.show()

	def emptyRoster(self):
		print "empty roster..."
		text="<b>"+unicode(self.tr("Welcome to Jabbim!"))+"</b><br/>"
		text+=unicode(self.tr("Your contact list is empty. You can add or find your friends by clicking on button below or by Add contact from menu Actions."))
		self.label.setText(text)
		self.label.show()
		self.add.show()

	def noOnline(self):
		text=self.tr("You haven't any online contact in your contact list. To see offline contacts, you have to click Show Offline button, which is above this message.")
		self.label.setText(text)
		self.label.show()
		self.add.hide()

	def noSearch(self):
		text=self.tr("No search results for your keywords")
		self.label.setText(text)
		self.label.show()
		self.add.hide()

class groupItem:
	def __init__(self,name,icon,main):
		self.name=name
		self.icon=icon
		self.expanded=False
		self.typ='group'
		self.main=main
		self.online=0
		self.all=0
		self.escapedName=name.replace("<","&lt;").replace(">","&gt;")
		self.height=0

	def setExpanded(self,bool):
		self.expanded=bool
		if not self.expanded:
			self.icon=QtGui.QIcon(RESOURCEPATH+"images/"+self.main.iconSize+"/icons/group-closed.png")
		else:
			self.icon=QtGui.QIcon(RESOURCEPATH+"images/"+self.main.iconSize+"/icons/group-open.png")

class userItem:
	"""
	Class for users roster items
	"""
	def __init__(self,name,group,jid,main,icon=None):
		self.name=name #: contact name
		self.icon=icon #: contact icon
		self.typ='user' #: typ of item, constant for user items
		self.group=group #: group of contact
		self.status=9
		self.statusMessage=None #: statusMessage
		self.main=main #: rosterWidget
		self.avatar=None
		self.hidden=False
		self.last=False
		#self.test=None
		self.metajid="" #: contains parent jid of this item, if this contact is member of metacontacts
		self.expanded=False
		self.blink=None # if True, icon blinks
		self.jid = jid
		self.privacy = {"block":False, "allow":False, "hide":False}
		self.hiddenBySearch=False
		self.transport=False
		self.escapedName=name.replace("<","&lt;").replace(">","&gt;")
		self.frameAvatar=None
		self.selectedFrameAvatar=None
		self.mood=None
		self.tune=False
		self.song=""
		self.height=0

	def clone(self):
		"""
		Makes new instance of userItem which is copy of current userItem
		"""
		item=userItem(unicode(self.name),unicode(self.group),self.jid,self.main,self.icon)
		item.statusMessage=self.statusMessage
		item.avatar=self.avatar
		item.hidden=self.hidden
		item.jid=unicode(self.jid)
		item.metajid=unicode(self.metajid)
		item.status=int(self.status)
		item.frameAvatar=self.frameAvatar
		item.privacy['block']=self.privacy['block']
		item.privacy['allow']=self.privacy['allow']
		item.privacy['hide']=self.privacy['hide']
		item.selectedFrameAvatar=self.selectedFrameAvatar
		item.mood=self.mood
		item.tune=self.tune
		item.height=self.height
		return item

	def setIcon(self,icon):
		"""
		Sets userItem icon
		@type icon: QtGui.QIcon
		"""
		self.icon=icon
		self.main.repaint()

	def setAvatar(self,icon):
		"""
		Sets userItem's avatar. Frame is painted automaticaly by this function.
		@type icon: QtGui.QIcon
		"""
		self.avatar=icon
		self.frameAvatar=QtGui.QIcon(self.main.main.getAvatar(self.avatar.pixmap(30,30),size="32x32",frame=True))
		self.selectedFrameAvatar=QtGui.QIcon(self.main.main.getAvatar(self.avatar.pixmap(60,58),size="64x64",frame=True))

	def setHidden(self,hidden):
		"""
		Hide or show userItem
		@type hidden: boolean
		"""
		self.hidden=hidden
		self.main.repaint()

class special:
	"""
	special item for contact which aren't in any group
	"""
	def __init__(self):
		self.typ="group"
		self.main="special"
		#self.name=".#$%^&*()_.@#$%^&*(((((((((("
		self.name="zzzzzzzzzzzzzzzzzzzzzz%%%$@#@^&"
		self.expanded=True

class rosterWidget(QtGui.QWidget):
	"""
	RosterLiveWidget class.
	"""
	def __init__(self,parent=None,main=None):
		QtGui.QWidget.__init__(self,parent)
		self.main=main
		self.groups={}
		self.specialName="zzzzzzzzzzzzzzzzzzzzzz%%%$@#@^&"
		#self.specialName=".#$%^&*()_.@#$%^&*(((((((((("
		self.groups[self.specialName]=special()
		self.users=[]
		self.iconSize="32x32"
		self.setObjectName("mainRosterWidget")
		self.setMinimumWidth(150)
		self.setMinimumHeight(150)
		self.setAcceptDrops(True)
		self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
		self.setMouseTracking(True)
		self.setFocusPolicy(QtCore.Qt.ClickFocus)

		self.selected=None
		self.selectedHeight=0
		self.showOffline=False
		self.newitem=None
		self.item=None
		self.sortedGroups=[]
		self.sorted={}
		#self.statusLabel=activeWidget(self)
		#self.buttonWidget=None
		#self.bigAvatar=False
		self.data={}
		self.metaItems={}
		self.events=[]
		self.bl=True
		#self.changePos=False
		self.searchMode=False
		self.favouriteMode=False
		#self.reshow=False
		self.userHeight=32
		self.groupHeight=32
		self.theme=True
		self.timestamp=0
		self.scrollUp = None
		self.compact=False

		self.timer=QtCore.QTimer(self) # timer for drag and drop
		QtCore.QObject.connect(self.timer, QtCore.SIGNAL("timeout ()"),self.popup)
		self.timerBlink=QtCore.QTimer(self) # timer for blinking
		QtCore.QObject.connect(self.timerBlink, QtCore.SIGNAL("timeout ()"),self.blink)

		self.colors=QtGui.QTreeWidget(self.main)
		self.colors.hide()
		self.colors.setObjectName("rosterView")
		self.tool=None

		self.reskin()
		self.blinkJids=[]
		self.main.ui.rosterSearch.hide()
		self.main.ui.rosterSearchLabel.hide()
		self.main.ui.rosterSearchClose.hide()

		self.emptyRosterWidget=emptyRosterWidget(self.main,self.main.ui.rosterWidget)
		self.main.ui.rosterWidget.layout().insertWidget(0,self.emptyRosterWidget)

		#self.setRosterStyle(defaultrosterstyle.rosterStyle)

		#self.groups[self.specialName].height=self.rosterStyle.heightForItem(self.groups[self.specialName])
		self.lastMove=[0,0,None]

		#QtCore.QObject.connect(self.main.scroll.verticalScrollBar(),QtCore.SIGNAL("valueChanged ( int )"),self.sliderChanged)


	def sliderChanged(self,i):
		pass
	#{ Public functions

	def showMiniRoster(self,call):
		d=miniroster.miniRosterDialog(self.main,call,False,self.main)
		d.exec_()

	def setRosterStyle(self,styleClass,config):
		self.rosterStyle=styleClass(self,config)
		for user in self.users:
			user.height=self.rosterStyle.heightForItem(user)
		for item in self.groups.iteritems():
			item[1].height=self.rosterStyle.heightForItem(item[1])
		self.repaint()



	def addGroup(self,name):
		"""
		Adds new group to the roster.
		@type name: unicode
		@param name: groups name
		@rtype: groupItem
		@return: created groupItem
		@see: L{AddUser}, L{getGroupUsers}, L{getAllGroupUsers}, L{getGroupSortedUsers}
		"""
		item=groupItem(name,QtGui.QIcon(RESOURCEPATH+"images/"+self.iconSize+"/icons/group-closed.png"),self)
		item.height=self.rosterStyle.heightForItem(item)
		self.groups[name]=item
		self.repaint()
		return item

	def addUser(self,jid,name,group):
		"""
		Adds new user to the roster.
		@type jid: unicode
		@param jid: users Jabber ID
		@type name: unicode
		@param name: users name
		@type group: unicode
		@param group: group name or None for user without group
		@see: L{addGroup}, L{getGroupUsers}, L{getAllGroupUsers}, L{getGroupSortedUsers}
		"""
		if len(name)==0:
			name=jid
		if not group:
			group=self.specialName
		item=userItem(name,group,jid,self)
		item.icon=self.main.getIcon(jid,size="32x32",status=self.main.icons["9"])
		item.height=self.rosterStyle.heightForItem(item)
		item.hidden=True
		#item.setAvatar(QtGui.QIcon("images/48x48/apps/jabbim.png"))
		self.users.append(item)
		return item

	def getGroupUsers(self,group):
		"""
		Returns user items according to show online. If L{showOffline} is False, only non-offline users are returned
		@type group: unicode
		@param group: name of group
		@rtype: list
		@return: list of userItems
		@see: L{addGroup}, L{addUser}, L{getAllGroupUsers}, L{getGroupSortedUsers}
		"""
		ret=[]
		for user in self.users:
			#if self.showOffline==True:
			if user.group==group:
				ret.append(user)
			#else:
				#if user.group==group and not user.hidden:
					#ret.append(user)
		return ret

	def getAllGroupUsers(self,group):
		"""
		Returns all user items from group.
		@type group: unicode
		@param group: name of group
		@rtype: list
		@return: list of userItems
		@see: L{addGroup}, L{addUser}, L{getGroupUsers}, L{getGroupSortedUsers}
		"""
		ret=[]
		for user in self.users:
			if user.group==group:
				ret.append(user)
		return ret

	def getGroupSortedUsers(self,group):
		"""
		Returns users from group. If L{showOffline} is False, only non-offline users are returned.
		If C{self.main.config['showTransports']} is True, transports are returned too.
		@type group: unicode
		@param group: group name
		@rtype: list
		@return: sorted list of userItem
		@see: L{addGroup}, L{addUser}, L{getGroupUsers}, L{getAllGroupUsers}
		"""
		ret=[]
		transport=self.main.config['showTransports']
		for key in self.sorted[group]:
			user=key[1]
			if transport=='True' and user.transport==True and user.jid in self.main.client.roster['users'].keys():
				ret.append(user)
			elif not user.transport:
				if self.showOffline==True and not user.hiddenBySearch:
					if user.group==group and user.jid in self.main.client.roster['users'].keys():
						ret.append(user)
				else:
					if user.group==group and not user.hidden and not user.hiddenBySearch and user.jid in self.main.client.roster['users'].keys():
						ret.append(user)

		return ret

	def getIconByJID(self,jid,size="16x16"):
		"""
		Returns QtGui.QIcon according to users show. If user is not in roster, offline icon will be returned.
		@type jid: unicode
		@param jid: contacts Jabber ID
		@rtype: QtGui.QIcon
		@return: show iconf for this user
		@see: L{getNameByJid}, U{QtGui.QIcon<http://www.riverbankcomputing.com/Docs/PyQt4/html/qicon.html>}
		"""
		jid=self.main.getJid(jid)
		if self.main.client.roster['users'].has_key(jid.userhost()):
			contact=self.main.client.roster['users'][jid.userhost()]
			if jid.resource in contact.resources:
				show=contact.resources[jid.resource].show
			else:
				if len(contact.status)==2:
					show=contact.status[0]
					status=contact.status[1]
				else:
					if len(contact.status)==1:
						show=contact.status[0]
					else:
						show="offline"
					status=None
			print show
			return self.main.getIcon(unicode(jid.userhost()),status=str(show),size=size)
		return self.main.getIcon(unicode(jid.userhost()),status='offline',size=size)

	def getNameByJID(self,jid):
		"""
		Returns name for jid. If jid is not in roster, returns the same JID instead of name.
		@type jid: unicode
		@param jid: contacts Jabber ID
		@rtype: unicode
		@return: users name
		@see: L{getIconByJID}
		"""
		jid=self.main.getJid(jid)
		if self.main.client.roster['users'].has_key(jid.userhost()):
			if len(self.main.client.roster['users'][jid.userhost()].name)!=0:
				return self.main.client.roster['users'][jid.userhost()].name
		return jid.full()

	def itemAt(self,x1,y1,count=None):
		"""
		Returns items with first item position x1,y1.
		@type x1: int
		@param x1: x position of item
		@type x2: int
		@param x2: y position of item
		@type count: int
		@param count: count of returned items. First item has position [x1,y1].
		@rtype: list
		@return: [list of userItem - groupItem - specialItem, X of last item, Y of last item]
		@see: L{itemCoordinates}
		"""
		x=0
		y=0
		got=0
		gotx=0
		goty=0
		ret=[]
		if self.searchMode==False:
			if self.favouriteMode==False:
				# go through all groups
				for key in self.sortedGroups:
					item=self.groups[key] # groupItem
					items=self.getGroupSortedUsers(item.name) # list of userItems
					# group is not empty
					if len(items)!=0:
						# we want to save this groupItem
						if got!=0 and not item in ret:
							ret.append(item)
							got+=1
						if y1>=y and y1<=y+item.height and got==0:
							if not item in ret:
								ret.append(item)
								got+=1
								goty=y#+self.rosterStyle.spaceBetweenGroups
							if not count:
								return item
						# we got items which we want
						#if got==count:
						if count and y-y1>count:
							return ret,0,goty
						# groupItem has some items and it's expanded
						y+=item.height
						if item.expanded and len(items)!=0:
							_items=[] # temp variable
							# handle expanded metacontacts
							for useritem in items:
								if useritem.expanded:
									if self.metaItems.has_key(useritem.metajid):
										for contact in self.metaItems[useritem.metajid]:
											if contact.jid!=useritem.jid:
												_items.append([items.index(useritem),contact])
							_items.reverse()
							for useritem in _items:
								items.insert(useritem[0]+1,useritem[1])
							# go through all userItems
							#y+=items[0].height
							for index in range(len(items)):
								useritem=items[index]
								if got!=0 and not useritem in ret:
									ret.append(useritem)
									got+=1
								if y1>=y and y1<=y+useritem.height and got==0:
									if not useritem in ret:
										ret.append(useritem)
										got+=1
										goty=y
									if not count:
										return useritem

								#if got==count:
								if count and y-y1>count:
									return ret,0,goty
								y+=useritem.height
							#y-=useritem.height
			else:
				users = sorted(self.main.userRating.users.values(), key=operator.attrgetter('rating'), reverse=True)
				jids = [u.jid for u in users if u.rating!=0.0]
				jids=list(self.main.config['favUsers'])+jids
				items={}
				u=[]
				transport=self.main.config['showTransports']
				for v in self.metaItems.itervalues():
					for user in v:
						u.append(user)
				h=0
				for jid in jids:
					if h>self.height():
						break
					for user in self.users+u:
						if user.jid==jid:
							if transport=='True' and user.transport==True and user.jid in self.main.client.roster['users'].keys():
								items[user.jid]=user
								h+=user.height
							elif not user.transport:
								if self.showOffline==True and not user.hiddenBySearch:
									items[user.jid]=user
									h+=user.height
								else:
									if not user.hidden and not user.hiddenBySearch and user.jid in self.main.client.roster['users'].keys():
										items[user.jid]=user
										h+=user.height
							break
				for jid in jids:
					if items.has_key(jid):
						item=items[jid]
						if item.hiddenBySearch==False:
							useritem=item
							if got!=0 and not useritem in ret:
								ret.append(useritem)
								got+=1

							if y1>=y and y1<=y+item.height:
								if count and not useritem in ret:
									ret.append(useritem)
									got+=1
									goty=y
								if not count:
									return useritem
							if got==count:
								return ret,0,goty
							y+=item.height
		else:
			users=[]
			# append all userItems to one list
			for item in self.users:
				if not self.metaItems.has_key(item.jid):
					users.append([item.name.lower(),item])
			for v in self.metaItems.itervalues():
				for user in v:
					users.append([user.name.lower(),user])
			# sort them
			users.sort()
			for item in users:
				item=item[1]
				if item.hiddenBySearch==False:
					useritem=item
					if got!=0 and not useritem in ret:
						ret.append(useritem)
						got+=1

					if y1>=y and y1<=y+item.height:
						if count and not useritem in ret:
							ret.append(useritem)
							got+=1
							goty=y
						if not count:
							return useritem
					if got==count:
						return ret,0,goty
					y+=item.height

		if got!=0:
			return ret,0,goty

		if count:
			return [],None,None

	def itemCoordinates(self,i):
		"""
		Returns left-top corners coordinates of userItem. If userItem is not founded, returns [None,None]
		@type i: userItem
		@param i: userItem
		@rtype: list
		@return: [X,Y]
		@see: L{itemAt}
		"""
		x=0
		y=0
		if self.searchMode==False:
			if self.favouriteMode==False:
				for key in self.sortedGroups:
					item=self.groups[key]
					items=self.getGroupSortedUsers(item.name)
					if len(items)!=0:
						if item==i:
							return x,y
						if item.expanded and len(items)!=0:
							previous=None
							_items=[]
							for useritem in items:
								if useritem.expanded:
									if self.metaItems.has_key(useritem.metajid):
										for contact in self.metaItems[useritem.metajid]:
											if contact.jid!=useritem.jid:
												_items+=[contact]
							items+=_items
							y+=items[0].height
							for useritem in items:
								if useritem==i:
									return x,y
								y+=useritem.height
							y-=useritem.height
								#if useritem==self.item:
									#y+=self.selectedHeight-28

							#if useritem==self.item:
								#y-=32
						y+=item.height
			else:
				users = sorted(self.main.userRating.users.values(), key=operator.attrgetter('rating'), reverse=True)
				jids = [u.jid for u in users if u.rating!=0.0]
				jids=list(self.main.config['favUsers'])+jids
				items={}
				u=[]
				transport=self.main.config['showTransports']
				for v in self.metaItems.itervalues():
					for user in v:
						u.append(user)
				h=0
				for jid in jids:
					if h>self.height():
						break
					for user in self.users+u:
						if user.jid==jid:
							if transport=='True' and user.transport==True and user.jid in self.main.client.roster['users'].keys():
								items[user.jid]=user
								if user==i:
									return 0,h
								h+=user.height
							elif not user.transport:
								if self.showOffline==True and not user.hiddenBySearch:
									items[user.jid]=user
									if user==i:
										return 0,h
									h+=user.height
								else:
									if not user.hidden and not user.hiddenBySearch and user.jid in self.main.client.roster['users'].keys():
										items[user.jid]=user
										if user==i:
											return 0,h
										h+=user.height
							break
				#for jid in jids:
					#if items.has_key(jid):
						#item=items[jid]
						#if item.hiddenBySearch==False:
							#useritem=item
							#if got!=0 and not useritem in ret:
								#ret.append(useritem)
								#got+=1

							#if y1>=y and y1<=y+item.height:
								#if count and not useritem in ret:
									#ret.append(useritem)
									#got+=1
									#goty=y
								#if not count:
									#return useritem
							#if got==count:
								#return ret,0,goty
							#y+=item.height
		else:

			users=[]
			for item in self.users:
				if not self.metaItems.has_key(item.jid):
					users.append([item.name.lower(),item])
			for v in self.metaItems.itervalues():
				for user in v:
					users.append([user.name.lower(),user])
			users.sort()
			for item in users:
				item=item[1]
				if item.hiddenBySearch==False:
					useritem=item
					if useritem==i:
						return x,y
					#if useritem==self.item:
						#y+=self.selectedHeight-28
					y+=useritem.height

		return None,None


	def getHostItems(self,host):
		"""
		Returns all userItem with selected host.
		@type host: unicode
		@param host: host without @ (for example jabbim.cz, nsj.netlab.cz etc.)
		@rtype: list
		@return: list of userItem
		"""
		ret=[]
		for user in self.users:
			j=self.main.getJid(user.jid)
			if j:
				if j.host==host:
					ret.append(user)
		for mainjid,users in self.metaItems.iteritems():
			for user in users:
				j=self.main.getJid(user.jid)
				if j:
					if j.host==host:
						ret.append(user)
		return ret

	def getUserItems(self,jid):
		"""
		Returns all userItems for JID.
		@type jid: unicode
		@param jid: Jabber ID without resource (test@njs.netlab.cz)
		@rtype: list
		@return: list of userItems
		"""
		ret=[]
		for user in self.users:
			if user.jid==jid:
				ret.append(user)
		return ret

	def getMetaItems(self,jid):
		"""
		Returns all metaItems for JID.
		@type jid: unicode
		@param jid: metaItem Jabber ID
		@rtype: list
		@return: list of userItem
		"""
		ret=[]
		for mainjid,users in self.metaItems.iteritems():
			for user in users:
				if user.jid==jid:
					ret.append([user,mainjid])
		return ret

	#}

	#{ Private functions

	def getMetaParents(self,jid):
		ret=[]
		for user in self.users:
			if user.metajid==jid:
				ret.append(user)
		return ret

	def disconnect(self):
		"""
		Resets roster. Called by mainWindow on disconnect
		"""
		self.groups={}
		#self.specialName=".#$%^&*()_.@#$%^&*(((((((((("
		self.specialName="zzzzzzzzzzzzzzzzzzzzzz%%%$@#@^&"
		self.groups[self.specialName]=special()
		self.groups[self.specialName].height=self.rosterStyle.heightForItem(self.groups[self.specialName])

	def refreshEvents(self):
		"""
		Blinks with userItem icon if there is some event for userItem with event's JID.
		"""
		events=[]
		for event in self.main.events.events:
			if event['type']=="message":
				JID=jidT.JID(event['name']).userhost()
				if not JID in self.blinkJids:
					self.blinkJids.append(JID)
				events.append(JID)
				for item in self.getUserItems(JID):
					if not item in self.events:
						item.blink=QtGui.QIcon(event['iconName'].replace("xxxxx","32x32"))
						self.events.append(item)
		for jid in self.blinkJids:
			if not jid in events:
				for item in self.getUserItems(jid):
					if item in self.events:
						self.events.remove(item)
		self.timerBlink.start(1000)

	def blink(self):
		return
		self.bl=not self.bl
		if len(self.main.events.events)>0:
			#log.msg("blink")
			self.repaint()
		else:
			self.timerBlink.stop()
			self.bl=True
			self.repaint()

	def reskin(self,style=None):
		"""
		Reload roster skin
		"""


		if self.theme==True:
			self.colors.setObjectName("rosterView")
		else:
			self.colors.setObjectName("rosterView2")

		self.palet=self.colors.palette()

		self.palette().setColor(QtGui.QPalette.Window,self.palet.color(QtGui.QPalette.Base))
		self.repaint()

	def sortGroup(self,group):
		temp=[]
		for user in self.getGroupUsers(group):
			temp.append([unicode(user.status)+user.name,user])
		temp.sort(cmp=lambda a,b: strcoll(a[0],b[0]))
		self.sorted[group]=temp

		all=0
		online=0
		for user in self.users:
			if user.group==group:
				all+=1
				if unicode(user.status)!="9":
					online+=1
					#if not somebodyOnline:
						#somebodyOnline=True
		self.groups[group].online=online
		self.groups[group].all=all

		self.setSize()

	def sortItems(self,column=None,typ=None):
		"""
		Sort groups and users in groups and count online/offline users
		"""
		self.sortedGroups=self.groups.keys()
		self.sortedGroups.sort(cmp=strcoll)
		somebodyOnline=False
		if self.specialName in self.sortedGroups:
			self.sortedGroups.remove(self.specialName)
			self.sortedGroups.append(self.specialName)
		for group in self.sortedGroups:
			temp=[]
			for user in self.getGroupUsers(group):
				temp.append([unicode(user.status)+user.name,user])
			temp.sort(cmp=lambda a,b: strcoll(a[0],b[0]))
			self.sorted[group]=temp

			all=0
			online=0
			for user in self.users:
				if user.group==group:
					all+=1
					if unicode(user.status)!="9":
						online+=1
						if not somebodyOnline:
							somebodyOnline=True
			self.groups[group].online=online
			self.groups[group].all=all
		if not somebodyOnline and not self.searchMode:
			#doc=QtGui.QTextDocument()
			#option=doc.defaultTextOption()
			#option.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
			#doc.setDefaultTextOption(option)
			#doc.setHtml(self.tr("You haven't any contacts in your contact list. You can add them with Add contact from menu Actions."))
			if len(self.users)==0:
				if self.emptyRosterWidget.isHidden():
					#self.emptyRosterWidget.setGeometry(0,0,self.width(),self.height())
					self.emptyRosterWidget.emptyRoster()
					self.emptyRosterWidget.show()
			else:
				if self.emptyRosterWidget.isHidden():
					#self.emptyRosterWidget.setGeometry(0,0,self.width(),self.height())
					self.emptyRosterWidget.noOnline()
					self.emptyRosterWidget.show()
		else:
			if not self.emptyRosterWidget.isHidden():
				self.emptyRosterWidget.hide()
				#painter.drawText(QtCore.QRectF(10,10,self.width()-20,100),QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap,self.tr("You haven't any online contact in your contact list. To see offline contacts, you have to click Show Offline button, which is above this message."))
#		else:
#			if not somebodyOnline and self.searchMode:
				#painter.drawText(QtCore.QRectF(10,10,self.width()-20,100),QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap,self.tr("No search results for your keywords"))
				#if self.emptyRosterWidget.isHidden():
					#self.emptyRosterWidget.setGeometry(0,0,self.width(),self.height())
					#self.emptyRosterWidget.noSearch()
					#self.emptyRosterWidget.show()
#			else:
				#if not self.emptyRosterWidget.isHidden():
					#self.emptyRosterWidget.hide()
			#doc.drawContents(painter,)
		self.setSize()

	def event(self,event):
		# tooltip request:
		if int(event.type())==110:
			x = int(event.x())
			y = int(event.y())
			item = self.itemAt(x, y) # get item in coordinates
			#self.setToolTip("")
			if item and isinstance(item, userItem):
				#if item!=None and item.typ=="user": # tooltips are only for contacts (not for groups)
					#text = self.main.getToolTip(item.jid, item.escapedName)
					#self.setToolTip(text)
				if not self.tool:
					#self._mouseLeaveEvent(None)
					g = self.mapToGlobal(QtCore.QPoint(x, y))
					self.tool = tooltip.ToolTip(self.main, item.jid, unicode(item.escapedName), g, False)
					self.tool.leaveEvent = self.tooltipLeaveEvent
					# XXX leaveEvent -> nastavit None
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

	def mouseMoveEvent(self,event):
		"""
		starts drag and drop if mouse button is pressed
		"""
		item=self.itemAt(int(event.x()),int(event.y()))
		if self.lastMove[0]==0 and event.buttons()!=QtCore.Qt.NoButton:
			self.lastMove=[event.x(),event.y(),item]
		elif self.lastMove[0]!=0 and event.buttons()==QtCore.Qt.NoButton:
			self.lastMove=[0,0,None]

		if item and (abs(event.x()-self.lastMove[0])>10 or abs(event.y()-self.lastMove[1])>10):
			item=[self.lastMove[2]]
			if event.buttons()!=QtCore.Qt.NoButton:
				if item[0].typ=='user' and len(self.data)==0:
					mimeData = QtCore.QMimeData()
					mimeData.setText(item[0].jid) # mimedata is users jid
					self.data[mimeData]=item[0] # we have to find the item if user drop it
					self.drag = QtGui.QDrag(self)
					self.drag.setMimeData(mimeData)

					f=QtGui.QApplication.font()
					f.setPixelSize(11)
					f.setBold(True)

					metrics=QtGui.QFontMetrics(f)
					width=int(metrics.width(item[0].name))

					avatar=self.main.getAvatar(item[0].jid,size="64x64")
					if not avatar:
						avatar=QtGui.QPixmap(RESOURCEPATH+"images/32x32/apps/jabbim.png")

					result=QtGui.QPixmap(avatar.width()+width+6,avatar.height()+4)
					result.fill(QtGui.QColor(0,0,0))
					painter=QtGui.QPainter(result)
					painter.fillRect(1,1,result.width()-2,result.height()-2,QtGui.QBrush(self.palet.color(QtGui.QPalette.Base)))
					painter.drawPixmap(2,2,avatar)
					painter.setFont(f)
					painter.drawText(QtCore.QRectF(avatar.width()+3,0,width,avatar.height()),QtCore.Qt.AlignCenter,item[0].name)
					painter.end()

					self.drag.setPixmap(result)
					QtCore.QObject.connect(self.drag,QtCore.SIGNAL("targetChanged ( QWidget * )"),self.dtc)
					dropAction = self.drag.start(QtCore.Qt.CopyAction | QtCore.Qt.MoveAction)
			elif len(self.data)!=0:
				self.data={}
				self.lastMove=[0,0,None]

		return QtGui.QWidget.mouseMoveEvent(self,event)

	def dtc(self,widget):
		if widget!=self and self.selected:
			self.selected=None
			self.repaint()


	#def dndmessage(self,text):
		#if self.main.client.roster['users'].has_key(text):
			#return "presunout kontakt/vytvorit metakontakt"

	def popup(self):
		"""
		called by timer if user wants to use autoscroll when DNDs the item
		"""
		if self.scrollUp==None:
			self.timer.stop()
		if not self.scrollUp:
			if self.main.scroll.verticalScrollBar().value()+10>self.main.scroll.verticalScrollBar().maximum():
				self.main.scroll.verticalScrollBar().setValue(self.main.scroll.verticalScrollBar().maximum())
				self.timer.stop()
			else:
				self.main.scroll.verticalScrollBar().setValue(self.main.scroll.verticalScrollBar().value()+10)
		else:
			if self.main.scroll.verticalScrollBar().value()-10<0:
				self.main.scroll.verticalScrollBar().setValue(0)
				self.timer.stop()
			else:
				self.main.scroll.verticalScrollBar().setValue(self.main.scroll.verticalScrollBar().value()-10)

	def resizeEvent(self,event):
		"""
		resizes activeWidget if roster is resized
		"""
		#if self.statusLabel:
			#self.statusLabel.resize(self.width()-46,self.selectedHeight-32)
		#if not self.emptyRosterWidget.isHidden():
			#self.emptyRosterWidget.setGeometry(0,0,self.width(),self.height())
		self.refreshSizes()
		if hasattr(self.rosterStyle,"resizeEvent"):
			self.rosterStyle.resizeEvent()
		return QtGui.QWidget.resizeEvent(self,event)

	def refreshSizes(self):
		for user in self.users:
			user.height=self.rosterStyle.heightForItem(user)
		for item in self.groups.iteritems():
			item[1].height=self.rosterStyle.heightForItem(item[1])


	def paintGroupItem(self,painter,item,x,y):
		"""
		paints group item in normal roster
		"""
		self.rosterStyle.paintGroupItem(painter,item,x,y)

	def paintUserItem(self,painter,useritem,x,y,last):
		"""
		paints user item in normal roster
		"""
		self.rosterStyle.paintUserItem(painter,useritem,x,y,last)

	def paintEvent(self,event):
		QtGui.QWidget.paintEvent(self,event)
		painter=QtGui.QPainter(self)
		painter.setClipping(True)
		#painter.setRenderHint(painter.Antialiasing)
		painter.setClipRegion(event.region())
		for rect in event.region().rects():
			items,x,y=self.itemAt(1,rect.y(),rect.height())
			for i in range(len(items)):
				item=items[i]
				last=False
				if i+1!=len(items):
					if items[i+1].typ=="group":
						last=True
				else:
					last=True
				if item.typ=="group":
					#y+=self.rosterStyle.spaceBetweenGroups
					self.paintGroupItem(painter,item,0,y)
				else:
					self.paintUserItem(painter,item,0,y,last)
				y+=item.height
		#if self.reshow:
			#self.statusLabel.hide()

	def setSize(self):
		"""
		Set height of rosterLiveWidget
		"""
		x=0
		y=0
		if self.searchMode==False:
			if self.favouriteMode==False:
				for key in self.sortedGroups:
					item=self.groups[key]
					items=self.getGroupSortedUsers(item.name)
					if (len(items)!=0 and not self.showOffline) or self.showOffline:
						if item.expanded and len(items)!=0:
							for useritem in items:
								y+=useritem.height
						y+=item.height#+self.rosterStyle.spaceBetweenGroups
			else:
				y=self.parent().height()-20
				#users = sorted(self.main.userRating.users.values(), key=operator.attrgetter('rating'), reverse=True)
				#if len(users)>10:
					#users=users[:10]
				#jids = [u.jid for u in users ]
				#items={}
				#u=[]
				#for v in self.metaItems.itervalues():
					#for user in v:
						#u.append(user)
				#for user in self.users+u:
					#if user.jid in jids:
						#items[user.jid]=user
				#for jid in jids:
					#if items.has_key(jid):
						#if y+items[jid].height<self.parent().height()-20:
							#y+=items[jid].height
						#else:
							#break
		else:
			for item in self.users:
				if item.hiddenBySearch==False:
					useritem=item
					y+=useritem.height
		#if self.main.config['bigOnClick']=='True':
			#size=y+self.selectedHeight-28
		#else:
		size=y
		#if size<self.parent().height()-20:
			#if self.parent().height()-20>0:
				#self.setMinimumHeight(self.parent().height()-20)
		#else:
		#if y+self.selectedHeight-28>0 and self.selectedHeight!=0 and not self.statusLabel.isHidden():
			#self.setMinimumHeight(size)
		#else:
		self.setMinimumHeight(size)
		#self.setMinimumHeight(1500)


	#def sel(self):
		#self.item=self.selected
		#self.reshow=True
		#self.repaint()
		#self.setSize()

	#def sel2(self):
		#self.item = None
		#self.selected = None
		#self.statusLabel.hide()
		#self.reshow=True
		#self.repaint()
		#self.setSize()

	def repaintItem(self,item):
		x,y=self.itemCoordinates(self.item)
		if x!=None:
			self.repaint(0,y-10,self.width(),item.height+20)

	def selectItem(self,item):
		"""
		Select item
		@type item: userItem
		"""
		if self.item!=item and item!=None and item.main!='special':
			#self.selected=item
			if self.item:
				y=self.itemCoordinates(self.item)[1]
				height=self.item.height
			else:
				y=-1
			self.item=item
			self.repaintItem(self.item)
			if y>0:
				self.repaint(0,y-10,self.width(),height+20)
			#self.reshow=True
			self.setSize()
			#self.main.client.reactor.callLater(0.2,self.sel)

		elif self.item == item and self.item != None and item.main!='special':
			y=self.itemCoordinates(self.item)[1]
			height=self.item.height
			self.item = None
			#self.selected = None
			#self.statusLabel.hide()
			#self.reshow=True

			self.repaint(0,y-10,self.width(),height+20)
			self.setSize()
		#if item!=None:
			#if item.typ=='group' and item.main!='special':
				#self.statusLabel.hide()

	def mousePressEvent(self,event):
		x=event.x()
		y=event.y()
		item=self.itemAt(x,y)
		if item==None:
			return QtGui.QWidget.mouseReleaseEvent(self,event)
		if x<0:
			# sets item properties according to metaItem, which is represented by button
			if self.metaItems.has_key(item.metajid):
				#index=0
				#for i in self.metaItems[item.metajid]:
					#if i.jid==item.jid:
						#index=self.metaItems[item.metajid].index(i)-1
						#break
				#meta=self.metaItems[item.metajid][index]
				#item.name=meta.name
				#item.escapedName=meta.escapedName
				#item.frameAvatar=meta.frameAvatar
				#item.selectedFrameAvatar=meta.selectedFrameAvatar
				#item.icon=meta.icon
				#item.avatar=meta.avatar
				#item.status=meta.status
				#item.statusMessage=meta.statusMessage
				#item.jid=meta.jid
				item.expanded=not item.expanded
				self.repaint()
				return
		else:
			t=QtGui.QApplication.doubleClickInterval()/1000.0
			timestamp=float(time.time())
			if timestamp-self.timestamp<=t and self.main.config['bigOnClick']=="True" and self.item==item:
				self.mouseDoubleClickEvent(event)
			else:
				if event.button() == QtCore.Qt.LeftButton:
					self.oldItem=self.item
					if item.typ=='group':
						self.selectItem(item)
					else:
						self.selectItem(item)

					if item.typ=='group' and item.main!='special':
						if item.expanded:
							item.icon=QtGui.QIcon(RESOURCEPATH+"images/"+self.iconSize+"/icons/group-closed.png")
							item.expanded=False
						else:
							item.icon=QtGui.QIcon(RESOURCEPATH+"images/"+self.iconSize+"/icons/group-open.png")
							item.expanded=True
						self.setSize()
						#self.statusLabel.hide()
						x,y=self.itemCoordinates(item)
						self.repaint(0,y-10,self.width(),self.height()-y+10)
			self.timestamp=float(timestamp)
		QtGui.QWidget.mousePressEvent(self,event)

	def openChat(self,j):
		jid = jidT.JID(j)
		jid_r = jid.userhost()
		item=self.getUserItems(j)
		if len(item)==0:
			item=self.getMetaItems(j)
			item=item[0][0]
		else:
			item=item[0]
		if jid.resource:
			res=jid.resource
		else:
			res = self.main.client.roster['users'][jid_r].getHighestResource()
		if res==None:
			self.main.chat.addChatTab(item.jid,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
		else:
			self.main.chat.addChatTab(item.jid+"/"+res,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
		self.main.chat.activate()

	def mouseDoubleClickEvent(self,event):
		x=event.x()
		y=event.y()
		item=self.itemAt(x,y)
		#if self.item!=item:
			#if self.main.config['bigOnClick']=="False":
				#if x>0:
					#return self.mouseReleaseEvent(event)
				#return
			#else:
				#item=self.oldItem

		if item==None:
			return QtGui.QWidget.mouseReleaseEvent(self,event)
		if item.typ=='group' and item.main!='special':
			if item.expanded:
				item.icon=QtGui.QIcon(RESOURCEPATH+"images/"+self.iconSize+"/icons/group-closed.png")
				item.expanded=False
			else:
				item.icon=QtGui.QIcon(RESOURCEPATH+"images/"+self.iconSize+"/icons/group-open.png")
				item.expanded=True
			self.setSize()
			x,y=self.itemCoordinates(item)
			self.repaint(0,y-10,self.width(),self.height()-y+10)
		else:
			self.main.chat.addChatTab(item.jid,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
			self.main.chat.activate()

	def keyPressEvent(self,event):
		key=event.key()
		if key==QtCore.Qt.Key_Down:
			if self.item:
				x,y=self.itemCoordinates(self.item)
				#if self.item.typ=="group" or self.item.typ=="special":
				item=self.itemAt(x,y+self.item.height+16)
				#else:
					#if not self.compact:
						#item=self.itemAt(x,y+self.selectedHeight+33)
					#else:
						#item=self.itemAt(x,y+self.selectedHeight+1)
					#print item.typ
				if item.main=="special":
					x,y=self.itemCoordinates(item)
					item=self.itemAt(x,y+item.height+5)

				self.selectItem(item)
			#self.timer.start(40)
			event.accept()
		elif key==QtCore.Qt.Key_Up:
			if self.item:
				x,y=self.itemCoordinates(self.item)

				item=self.itemAt(x,y-3)
				if item.main=="special":
					x,y=self.itemCoordinates(item)
					item=self.itemAt(x,y-3)
				self.selectItem(item)
			#self.timer.start(40)
			event.accept()
		elif (key==QtCore.Qt.Key_Return or key==QtCore.Qt.Key_Enter) and self.item != None:
			jid = jidT.JID(self.item.jid)
			jid_r = jid.userhost()
			item=self.item
			if jid.resource:
				res=jid.resource
			else:
				res = self.main.client.roster['users'][jid_r].getHighestResource()
			if res==None:
				self.main.chat.addChatTab(item.jid,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
			else:
				self.main.chat.addChatTab(item.jid+"/"+res,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))

			#self.main.chat.addChatTab(item.jid,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))

			self.item = None
			#self.selected = None
			if self.searchMode==True:
				self.searchMode=False
				for user in self.users:
					user.hiddenBySearch=False
				self.main.ui.rosterSearch.setText("")
				self.main.ui.rosterSearch.hide()
				self.main.ui.rosterSearchLabel.hide()
				self.main.ui.rosterSearchClose.hide()

			#self.statusLabel.hide()
			#self.reshow=True
			self.setSize()
			self.repaint()
			self.main.chat.activate()
		elif key==QtCore.Qt.Key_Escape:
			self.item = None
			#self.selected = None
			if self.searchMode==True:
				self.searchMode=False
				for user in self.users:
					user.hiddenBySearch=False
				self.main.ui.rosterSearch.setText("")
				self.main.ui.rosterSearch.hide()
				self.main.ui.rosterSearchLabel.hide()
				self.main.ui.rosterSearchClose.hide()

			#self.statusLabel.hide()
			#self.reshow=True
			self.setSize()
			self.repaint()

		elif key==QtCore.Qt.Key_Delete: #tohle by mozna chtelo nejake potvrzeni 'Opravdu to chcete udelat?'
			self.main.client.delContact(self.item.jid)
		elif key==QtCore.Qt.Key_F2:
			jid=self.item.jid
			try:
				name=unicode(self.main.client.roster['users'][jid].name)
			except:
				name = ''
##			print "roster_new_group_action",jid,name
			# get new group name with QDialog
			name,b=QtGui.QInputDialog.getText(self,self.tr("Rename"),self.tr("Enter new name:"), QtGui.QLineEdit.Normal, name)
			name=unicode(name)
			# if user set new name of group
			if b==True and len(name)!=0:
				# add new group
				contact=self.main.client.roster['users'][jid]
				self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription, self.main.client.roster['users'][jid].groups)
			pass
		elif key==QtCore.Qt.Key_F and event.modifiers() & QtCore.Qt.ControlModifier:
			self.search('', True) #show searching in roster with empty fieldl
		elif key==QtCore.Qt.Key_O and event.modifiers() & QtCore.Qt.ControlModifier:
			check=not self.main.offline
			#self.main.ui.showOffline.setChecked(check)
			self.main.hideOffline(check)
		elif key==QtCore.Qt.Key_E and event.modifiers() & QtCore.Qt.ControlModifier:
			self.main.client.evil = not self.main.client.evil
			print self.main.client.evil
		else:
			#self.main.ui.rosterSearch.setFocus(QtCore.Qt.MouseFocusReason)
			self.main.ui.rosterSearch.event(event)
		event.ignore()


	def dragEnterEvent(self, event):
		#log.msg('DRAG ENTER')
		if event.mimeData().hasText() or event.mimeData().hasFormat("text/uri-list"):
			event.acceptProposedAction()
		else:
			event.ignore()

	def dragLeaveEvent(self, event):
		self.selected=None
		self.repaint()
		event.accept()

	def dragMoveEvent(self, event):
		#log.msg('DRAG MOVE')
		pos=event.pos()
		#print pos.x(),pos.y()
		item=self.itemAt(pos.x(),pos.y())
		self.scrollUp=None
		if pos.y()-self.main.scroll.verticalScrollBar().value()>self.main.scroll.height()-16:
			self.timer.start(50)
			self.scrollUp=False
		if pos.y()-self.main.scroll.verticalScrollBar().value()<32:
			self.scrollUp=True
			self.timer.start(50)

		#if not pos.y()>self.main.scroll.height()-16 and not pos.y()-self.main.scroll.verticalScrollBar().value():
			#self.timer.stop()

		if item:
			event.acceptProposedAction()
			if self.selected!=item:
				self.selected=item
				self.repaint()
		else:
			if self.selected:
				self.selected=None
				self.repaint()
			event.ignore()

	def dropEvent(self, event):
		self.scrollUp=None
		if self.selected:
			self.selected=None
			self.repaint()
		print "drop"
		if (event.mimeData().hasUrls()):
			urlList=event.mimeData().urls()
			if len(urlList)>0:
				new=[]
				for url in urlList:
					f=unicode(url.toLocalFile())
					if len(f)!=0:
						new.append(f)
				file=new
				print file
				position = event.pos()
				item=self.itemAt(position.x(),position.y())
				if item.typ=="user":
					self.main.showFiletransferDialog(file,item.jid)
					#if item.jid=="album@disk.jabbim.cz":
						#self.dialog=albumfiletransfer.albumFiletransferDialog(self.main,file,item.jid)
					#else:
						#self.dialog=filetransfer.filetransferDialog(self.main,file,item.jid)
					#self.dialog.show()
			event.acceptProposedAction()
		elif event.mimeData().hasText():
			jid = unicode(event.mimeData().text())
			position = event.pos()
			item=self.itemAt(position.x(),position.y())
			print "has text"
			if not self.data.has_key(event.mimeData()):
				print "has not data"
				gr=""
				if item.typ=="group":
					gr=item.name
					ijid = False
				elif item.typ=="user":
					gr=item.group
					ijid = item.jid
				try:
					jidT.JID(jid)
					validJid=True
				except:
					validJid=False
				if validJid:
					contact = self.main.client.getContactByJid(jid)
					if contact == None or ijid == False:
						dialog=addcontact.addContactDialog(self.main,self,jid=jid,group=gr,name=jid.split('@')[0])
						dialog.exec_()
					elif contact != None and ijid != False:
						self.main.client.sendContact(self.main.client.getHighestJid(ijid), contact) #roster item exchange
				#else:

				event.ignore()
				return

			oldItem=self.data[event.mimeData()]
			if item==oldItem:
				event.ignore()
				del self.data[event.mimeData()]
				return

			#print jid,item.name
			#for piece in pieces:
				#newLabel = DragLabel(piece, self)
				#newLabel.move(position)
				#newLabel.show()

				#position += QtCore.QPoint(newLabel.width(), 0)

			#if event.source() in self.children():
				#event.setDropAction(QtCore.Qt.MoveAction)
				#event.accept()
			#else:
			event.acceptProposedAction()

			# normal user > group
			if oldItem.typ=="user" and item.typ=="group":
				#items=QtCore.QStringList()
				#items.append(self.tr("Move"))
				#items.append(self.tr("Copy"))
				#q,b=QtGui.QInputDialog.getItem(self,self.tr("Action"),self.tr("Select action."), items,0,False)
				#q=unicode(q)

				contactMenu=QtGui.QMenu(self)
				if item.name!=self.specialName:
					action=contactMenu.addAction(self.tr("Move to group"))
					action.jid=jid
					action.oldItem=oldItem
					action.item=item
					action.setObjectName("move_to_group_ng")

					action=contactMenu.addAction(self.tr("Copy to group"))
					action.jid=jid
					action.item=item
					action.setObjectName("copy_to_group_ng")

				# signal
				contactMenu.connect(contactMenu, QtCore.SIGNAL("triggered ( QAction * )"),self.dropMenuTriggered)
				contactMenu.popup(self.mapToGlobal(position))

				#if b==True and len(q)!=0:
					#index=int(items.indexOf(QtCore.QRegExp(q)))
					#if index==0:
						#name=unicode(self.main.client.roster['users'][jid].name)
						#contact=self.main.client.roster['users'][jid]
						#g=contact.groups
						#if len(g)!=0:
							#g.remove(unicode(self.groups[oldItem.group].name))
						#else:
							#for yy in self.getUserItems(contact.jid):
								#self.users.remove(yy)
						#self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription,g+[unicode(item.name)])
					#else:
						#self.changeGroup(jid,"+",unicode(item.name))

			# metacontact > normal user
			elif oldItem.typ=="user" and oldItem.metajid!="" and item.typ=="user":
				del self.data[event.mimeData()]
				event.ignore()
				return
				items=QtCore.QStringList()
				items.append(self.tr("Move to group"))
				q,b=QtGui.QInputDialog.getItem(self.main,self.tr("Contact action"),self.tr("Select action."), items,0,False)
				q=unicode(q)
				if b==True and len(q)!=0:
					index=int(items.indexOf(QtCore.QRegExp(q)))

					if index==0:
						for it in self.metaItems[oldItem.metajid]:
							if it.jid==oldItem.jid:
								self.setHighest(oldItem.metajid)
								self.metaItems[oldItem.metajid].remove(it)
								del self.main.client.roster_meta[oldItem.jid]
								break
						print self.metaItems[oldItem.metajid]
						if len(self.metaItems[oldItem.metajid])==1:
							highest=self.metaItems[oldItem.metajid][0]
							#oldItem.name=highest.name+"LOL"
							#oldItem.icon=highest.icon
							#oldItem.avatar=highest.avatar
							#oldItem.status=highest.status
							#oldItem.statusMessage=highest.statusMessage
							#oldItem.jid=highest.jid
							#if str(oldItem.status)!="9":
								#oldItem.hidden=False
							#else:
								#oldItem.hidden=True
							#oldItem.metajid=""
							#oldItem.tag=""
							self.setHighest(oldItem.metajid)
							del self.main.client.roster_meta[self.metaItems[oldItem.metajid][0].jid]
							del self.metaItems[oldItem.metajid]
							name=unicode(self.main.client.roster['users'][highest.jid].name)
							contact=self.main.client.roster['users'][highest.jid]
							gr=unicode(oldItem.group)
							for it in self.getUserItems(oldItem.metajid):
								self.users.remove(it)
							for it in self.getUserItems(contact.jid):
								it.metajid=""
							self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription,[gr])

						self.main.client.setMetacontacts()
						self.main.client.makeTempMeta()
						name=unicode(self.main.client.roster['users'][jid].name)
						contact=self.main.client.roster['users'][jid]
						for it in self.getUserItems(contact.jid):
							it.metajid=""
						self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription,[unicode(item.group)])
						#self.statusLabel.hide()
						self.sortItems()
						self.repaint()


			# normal user > normal/meta user
			elif oldItem.typ=="user" and item.typ=="user":
				#items=QtCore.QStringList()
				#items.append(self.tr("Move to group"))
				#items.append(self.tr("Make metacontact"))
				#items.append(self.tr("Copy to group"))
				#q,b=QtGui.QInputDialog.getItem(self,self.tr("Contact action"),self.tr("Select action."), items,0,False)
				#q=unicode(q)
				# build contact menu
				contactMenu=QtGui.QMenu(self)
				if self.specialName!=item.group:
					action=contactMenu.addAction(self.tr("Move to group"))
					action.jid=jid
					action.oldItem=oldItem
					action.item=item
					action.setObjectName("move_to_group_nn")

				action=contactMenu.addAction(self.tr("Make metacontact"))
				action.item=item
				action.oldItem=oldItem
				action.setObjectName("make_metacontact_nn")
				if self.main.client.hasFeature(item.jid, 'http://jabber.org/protocol/rosterx'):
					action=contactMenu.addAction(self.tr("Send contact"))
					action.jid=oldItem.jid
					action.item=item
					action.setObjectName("send_contact")

				if self.specialName!=item.group:
					action=contactMenu.addAction(self.tr("Copy to group"))
					action.jid=jid
					action.item=item
					action.setObjectName("copy_to_group_nn")
				# signal
				contactMenu.connect(contactMenu, QtCore.SIGNAL("triggered ( QAction * )"),self.dropMenuTriggered)
				contactMenu.popup(self.mapToGlobal(position))

				#if b==True and len(q)!=0:
					#index=int(items.indexOf(QtCore.QRegExp(q)))

					#if index==0:
						#name=unicode(self.main.client.roster['users'][jid].name)
						#contact=self.main.client.roster['users'][jid]
						#g=contact.groups
						#if len(g)!=0:
							#g.remove(unicode(self.groups[oldItem.group].name))
						#else:
							#for yy in self.getUserItems(contact.jid):
								#self.users.remove(yy)
						#self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription,g+[unicode(item.group)])
					#elif index==1:
						#if not self.metaItems.has_key(item.metajid):
							#item.metajid=item.jid
							#item.tag=item.jid
							#self.metaItems[item.metajid]=[]
							#self.main.client.roster_meta[item.jid]={'tag':item.tag,'order':10}
							#it=item.clone()
							#it.tag=item.tag

							#self.metaItems[item.metajid].append(it)
						#it=oldItem.clone()
						#it.tag=item.tag

						#self.metaItems[item.metajid].append(it)
						#for i in self.getUserItems(oldItem.jid):
							#self.users.remove(i)
						#self.setHighest(item.metajid)
						#self.main.client.roster_meta[oldItem.jid]={'tag':item.tag,'order':1}
						#self.main.client.setMetacontacts()

						#self.sortItems()
						#if self.item!=item:
							#self.selectItem(item)
						#self.reshow=True
						#self.repaint()

					#elif index==2:
						#self.changeGroup(jid,"+",unicode(item.group))
			event.acceptProposedAction()
			del self.data[event.mimeData()]
		else:
			event.ignore()

	def dropMenuTriggered(self,action):
		cmd=action.objectName()
		if cmd=="move_to_group_nn":
			jid=action.jid
			oldItem=action.oldItem
			item=action.item

			name=unicode(self.main.client.roster['users'][jid].name)
			contact=self.main.client.roster['users'][jid]
			g=contact.groups
			if len(g)!=0:
				g.remove(unicode(self.groups[oldItem.group].name))
			else:
				g=[]
				for yy in self.getUserItems(contact.jid):
					self.users.remove(yy)
			self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription,g+[unicode(item.group)])
		elif cmd=="make_metacontact_nn":
			item=action.item
			oldItem=action.oldItem
			if not self.metaItems.has_key(item.metajid):
				item.metajid=item.jid
				item.tag=item.jid
				self.metaItems[item.metajid]=[]
				self.main.client.roster_meta[item.jid]={'tag':item.tag,'order':10}
				it=item.clone()
				it.tag=item.tag

				self.metaItems[item.metajid].append(it)
			it=oldItem.clone()
			it.tag=item.tag

			self.metaItems[item.metajid].append(it)
			for i in self.getUserItems(oldItem.jid):
				self.users.remove(i)
			self.setHighest(item.metajid)
			self.main.client.roster_meta[oldItem.jid]={'tag':item.tag,'order':1}
			self.main.client.setMetacontacts()
			self.main.client.makeTempMeta()

			self.sortItems()
			if self.item!=item:
				self.selectItem(item)
			#self.reshow=True
			self.repaint()

		elif cmd == 'send_contact':
			jid = unicode(action.jid)
			self.main.client.sendContact(self.main.client.getHighestJid(action.item.jid), self.main.client.getContactByJid(jid))

		elif cmd=="copy_to_group_nn":
			item=action.item
			jid=action.jid
			self.changeGroup(jid,"+",unicode(item.group))

		elif cmd=="move_to_group_ng":
			jid=action.jid
			oldItem=action.oldItem
			item=action.item
			name=unicode(self.main.client.roster['users'][jid].name)
			contact=self.main.client.roster['users'][jid]
			g=contact.groups
			if len(g)!=0:
				g.remove(unicode(self.groups[oldItem.group].name))
			else:
				for yy in self.getUserItems(contact.jid):
					self.users.remove(yy)
			self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription,g+[unicode(item.name)])
		elif cmd=="copy_to_group_ng":
			item=action.item
			jid=action.jid
			self.changeGroup(jid,"+",unicode(item.name))

	def makeHiddenItem(self):
		pass

	def mimeTypes(self):
		# set mimetypes, which we accept
		return QtCore.QStringList("text/plain")

	def getGroupItem(self,name):
		return None



	def search(self,text="", forceEmpty = False):
		text=unicode(text).lower()
		first=None
		if len(text)!=0 or forceEmpty:
			self.main.ui.rosterSearch.show()
			self.main.ui.rosterSearchLabel.show()
			self.main.ui.rosterSearchClose.show()
			self.searchMode=True
			for user in self.users:
				if user.name.lower().find(text)!=-1:
					user.hiddenBySearch=False
				else:
					user.hiddenBySearch=True
			for v in self.metaItems.itervalues():
				for user in v:
					if user.name.lower().find(text)!=-1:
						user.hiddenBySearch=False
					else:
						user.hiddenBySearch=True

		else:
			self.main.ui.rosterSearch.hide()
			self.main.ui.rosterSearch.setText("")
			self.main.ui.rosterSearchLabel.hide()
			self.main.ui.rosterSearchClose.hide()
			self.searchMode=False
			#self.statusLabel.hide()
			for user in self.users:
				user.hiddenBySearch=False
			for v in self.metaItems.itervalues():
				for user in v:
					user.hiddenBySearch=False

		first=self.itemAt(1,1)
		if self.item!=first:
			self.selectItem(first)
		self.setSize()
		self.repaint()

	def hidden(self,bool):
		pass


	def refreshStats(self):
		pass

	def isSameStatus(self,jid,show):
		if not self.main.client.roster['users'].has_key(jid):
			print "compare: jid is not in roster"
			return True
		res = self.main.client.roster['users'][jid].getHighestResource()
		if res!=None:
			print "compare: no resource"
			res=self.main.client.roster['users'][jid].resources[res]
			show=res.show
			status=res.status
		else:
			status=self.main.client.roster['users'][jid].status
			if len(status)<=1:
				status=""
			else:
				status=status[1]
			if status!=None:
				status=status.replace("\n"," ").replace("<","&lt;").replace(">","&gt;")
			else:
				status=""

		users = self.getUserItems(jid)
		if len(users)==0:
			users=self.getMetaItems(jid)
			if len(users)!=0:
				users=users[0]
			else:
				print "compare: no user item"
				return True
		user=users[0]
		if user.statusMessage==status and user.status==self.main.shows[unicode(show)] and user.height==self.rosterStyle.heightForItem(user):
			return True
		return False

	def setStatus(self,jid,show,i=None,status=None,first=False):
		if not self.main.client.roster['users'].has_key(jid):
			return
		res = self.main.client.roster['users'][jid].getHighestResource()
		if res!=None:
			res=self.main.client.roster['users'][jid].resources[res]
			show=res.show
			status=res.status

		rect=QtCore.QRect()
		for user in self.getUserItems(jid):
			user.icon=self.main.getIcon(jid,size="32x32",status=self.main.icons[self.main.shows[unicode(show)]])
			x,y=self.itemCoordinates(user)
			if self.main.shows[unicode(show)]!="9":
				user.hidden=False
			elif len(self.main.client.roster['users'][jid].resources)==0:
				user.hidden=True
				#if self.item==user:
					#self.statusLabel.hide()
			user.statusMessage=status
			user.status=self.main.shows[unicode(show)]
			user.height=self.rosterStyle.heightForItem(user)
			# user was visible
			self.sortGroup(user.group)
			x1,y1=self.itemCoordinates(user)
			if y!=None:
				# user is visible
				if y1!=None:
					if y1>y:
						self.repaint(0,y-10,self.width(),y1-y+user.height+20)
					else:
						self.repaint(0,y1-10,self.width(),y-y1+user.height+20)
				else:
					self.repaint(0,y-10,self.width(),self.height()-y+10)
			else:
				if y1!=None:
					self.repaint(0,y1-10,self.width(),self.height()-y1+10)

			#self.repaintItem(user)

		for couple in self.getMetaItems(jid):
			user=couple[0]
			mainjid=couple[1]
			user.icon=self.main.getIcon(jid,size="32x32",status=self.main.icons[self.main.shows[unicode(show)]])
			if self.main.shows[unicode(show)]!="9":
				user.hidden=False
			else:
				user.hidden=True
			user.statusMessage=status
			user.status=self.main.shows[unicode(show)]
			user.height=self.rosterStyle.heightForItem(user)
			highest=None
			allOffline=True
			for item in self.metaItems[mainjid]:
				if str(item.status)!="9":
					allOffline=False
				if highest:
					husertype=""
					usertype=""
					if self.main.hosts.has_key(jidT.JID(highest.jid).host):
						husertype=self.main.hosts[jidT.JID(highest.jid).host]
					if self.main.hosts.has_key(jidT.JID(item.jid).host):
						usertype=self.main.hosts[jidT.JID(item.jid).host]
					#if (int(item.status)<int(highest.status) and husertype!="jabber" and highest.status=="9") or (husertype!="jabber" and highest.status=="9"):
					#print item.jid,highest.jid,item.status,highest.status,usertype=="jabber" and item.status!="9",highest.status=="9" and item.status!="9"
					if (usertype=="jabber" and str(item.status)!="9") or (str(highest.status)=="9" and str(item.status!="9")):
						highest=item
				else:
					highest=item
			item=self.getMetaParents(mainjid)
			if allOffline:
				try:
					item[0].hidden=True
				except:
					print 'BUG!!! ',  item[0]

			if highest:
				if len(item)!=0:
					item=item[0]
					if item.jid!=highest.jid:
						item.name=highest.name
						item.escapedName=highest.escapedName
						item.frameAvatar=highest.frameAvatar
						item.selectedFrameAvatar=highest.selectedFrameAvatar
						item.icon=highest.icon
						item.avatar=highest.avatar
						item.status=highest.status
						item.statusMessage=highest.statusMessage
						item.jid=highest.jid
						if str(item.status)!="9":
							item.hidden=False
						else:
							item.hidden=True
						item.height=self.rosterStyle.heightForItem(item)
						#self.repaintItem(item)
		if not first:
			#self.statusLabel.hide()
			#self.changePos=True
			self.sortItems()
			#self.repaint()
		#for user in self.getUserItems(jid):
			#log.msg("hidden:"+unicode(user.hidden))

	def setHighest(self,mainjid):
		highest=None
		print "-------"
		for item in self.metaItems[mainjid]:
			if highest:
				husertype=""
				usertype=""
				if self.main.hosts.has_key(jidT.JID(highest.jid).host):
					husertype=self.main.hosts[jidT.JID(highest.jid).host]
				if self.main.hosts.has_key(jidT.JID(item.jid).host):
					usertype=self.main.hosts[jidT.JID(item.jid).host]
				#if (int(item.status)<int(highest.status) and husertype!="jabber" and highest.status=="9") or (husertype!="jabber" and highest.status=="9"):
				#print item.jid,highest.jid,item.status,highest.status,usertype=="jabber" and item.status!="9",highest.status=="9" and item.status!="9"
				if ((usertype=="jabber" and str(item.status)!="9") or (str(highest.status)=="9" and str(item.status!="9"))) and item.jid!=mainjid:
					highest=item
			else:
				if item.jid!=mainjid:
					highest=item
		print "-------"
		if highest:
			item=self.getUserItems(mainjid)
			if len(item)!=0:
				item=item[0]
				if item.jid!=highest.jid:
					item.name=highest.name
					item.icon=highest.icon
					item.avatar=highest.avatar
					item.status=highest.status
					item.statusMessage=highest.statusMessage
					item.jid=highest.jid
					if str(item.status)!="9":
						item.hidden=False
					else:
						item.hidden=True

	def cloneContact(self,parent,item):
		pass

	def buildJidMenu(self,jid):
		# build contact menu
		contactMenu=QtGui.QMenu(self)
		jid=self.main.getJid(jid)


		action=contactMenu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/add-user.png"),self.tr("Add to roster"))
		action.setData(QtCore.QVariant(jid.userhost()))
		action.setObjectName("add_contact")

		if self.main.client.groupchats != {}:	# Mozna zobrazit i kdyz v mucu nejsme aby to bylo vic videt :)
			submenu = contactMenu.addMenu(QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/muc.png"),self.tr("Invite to conference"))
			for gc in self.main.client.groupchats.keys():
				action = submenu.addAction(gc)
				action.setData(QtCore.QVariant(QtCore.QStringList([jid.full(), gc])))
				action.setObjectName("invite_gc")



		# custom status
		submenu=contactMenu.addMenu(self.tr("Custom status"))


		for status in ["online", "chat", "away", "xa", "dnd", "offline"]:
			action=submenu.addAction(self.main.getIcon(status=status,size="32x32"),self.main.status[status])
			action.setObjectName("custom_status")
			action.setData(QtCore.QVariant(QtCore.QStringList([unicode(status), unicode(jid.userhost())])))

		# separator
		contactMenu.addSeparator()

		action=contactMenu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/v-card.png"),self.tr("vCard"))
		action.setData(QtCore.QVariant(jid.userhost()))
		action.setObjectName("vcard")
		# filetransfer
		#resource=jid.resource
		#if len(resource)!=0:
			#if self.main.client.roster['users'][jid].resources[resource[0]].hasFeature('http://jabber.org/protocol/si/profile/file-transfer'):
				#action=contactMenu.addAction(self.tr("Send file"))
				#action.setData(QtCore.QVariant(jid))
				#action.setObjectName("send_file")
				#action.setIcon(QtGui.QIcon("images/32x32/actions/upload.png"))

		#for key,value in self.main.plugins.iteritems():
			#if value['module']:
				#self.main.runPluginCommand(value['module'].buildContactMenu,[contactMenu,contact])
		# separator
		contactMenu.addSeparator()

		## break up metacontact
		#if self.main.client.roster_meta.has_key(jid):
			#action=contactMenu.addAction(self.tr("Break up metacontact"))
			#action.setData(QtCore.QVariant(jid))
			#action.setObjectName("break_up_meta")
		## rename
		#action=contactMenu.addAction(self.tr("Rename"))
		#action.setData(QtCore.QVariant(jid))
		#action.setObjectName("rename")
		## delete from group
		#if group!=None and len(self.main.client.roster['users'][jid].groups)>1:
			#action=contactMenu.addAction(self.tr("Delete from group"))
			#action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"-"+group])))
			#action.setObjectName("check_group")
		## delete from roster
		#action=contactMenu.addAction(self.tr("Delete from roster"))
		#action.setData(QtCore.QVariant(jid))
		#action.setObjectName("delete_action")

		#value = contact.subscription
		#if value in ["ask"]:
			#action = contactMenu.addAction(self.tr("Authorize"))
			#action.setData(QtCore.QVariant(jid))
			#action.setObjectName("a_authorize")
		#if value in ["from", "both",'ask']:
			#action = contactMenu.addAction(self.tr("Remove authorization"))
			#action.setData(QtCore.QVariant(jid))
			#action.setObjectName("a_unauthorize")
		#if value in ["none", "from"]:
			#action = contactMenu.addAction(self.tr("Request authorization"))
			#action.setData(QtCore.QVariant(jid))
			#action.setObjectName("a_ask")

		## separator
		#contactMenu.addSeparator()
		## groups . submenu
		#group=contactMenu.addMenu (self.tr("Groups"))
		## groups . new group
		#action=group.addAction(self.tr("New Group"))
		#action.setData(QtCore.QVariant(jid))
		#action.setObjectName("new_group")
		## groups . separator
		#group.addSeparator()
		## groups . groups list
		##g=self.getGroups(str(jid))
		#for k,v in self.groups.iteritems():
			#if k!="Unknown" and k!=self.specialName:
				#action=group.addAction(unicode(k))
				#action.setObjectName("check_group")
				#action.setCheckable(True)
			##if len(self.main.client.roster['users'][jid].groups)==0:
				##if k=="Unknown":
					##action.setChecked(True)
					##action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"-"+unicode(k)])))
				##else:
					##action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"+"+unicode(k)])))
			##else:
				#if k in self.main.client.roster['users'][jid].groups:
					#action.setChecked(True)
					#action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"-"+unicode(k)])))
					#if len(self.main.client.roster['users'][jid].groups)<=1:
						#action.setEnabled(False)
				#else:
					#action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"+"+unicode(k)])))

		if self.main.client.privacy:
			if self.main.client.privacy.active:
				submenu = contactMenu.addMenu(self.tr("Privacy"))
				if not self.main.client.privacy.active.isBlockedJID(jid.userhost()):
					action = submenu.addAction(self.tr("Block contact"))
					action.setData(QtCore.QVariant(jid.userhost()))
					action.setObjectName("privacy_block")
				else:
					action = submenu.addAction(self.tr("Unblock contact"))
					action.setData(QtCore.QVariant(jid.userhost()))
					action.setObjectName("privacy_unblock")

				# Sekci nemazat
				#if not self.main.client.privacy.active.isAllowedJID(jid):
				#	action = submenu.addAction(self.tr("Allow contact to see my status when I am invisible"))
				#	action.setData(QtCore.QVariant(jid))
				#	action.setObjectName("privacy_allow")
				#else:
				#	action = submenu.addAction(self.tr("Disallow contact to see my status when I am invisible"))
				#	action.setData(QtCore.QVariant(jid))
				#	action.setObjectName("privacy_disallow")

				if not self.main.client.privacy.active.isHiddenJID(jid.userhost()):
					action = submenu.addAction(self.tr("Always hide my status to contact"))
					action.setData(QtCore.QVariant(jid.userhost()))
					action.setObjectName("privacy_hide")
				else:
					action = submenu.addAction(self.tr("Don't hide my status to contact"))
					action.setData(QtCore.QVariant(jid.userhost()))
					action.setObjectName("privacy_unhide")
		#if len(contact.resources)!=0:
			#if oneres:
				#if self.main.client.roster['users'][jid].resources[resource[0]].hasFeature('http://jabber.org/protocol/commands'):
					#action=contactMenu.addAction(QtGui.QIcon("images/16x16/actions/exec.png"),self.tr("Extra actions"))
					#action.setData(QtCore.QVariant("%s/%s" % (jid, contact.resources.keys()[0])))
					#action.setObjectName("ad_hoc")
			#else:
				#submenu=contactMenu.addMenu(QtGui.QIcon("images/16x16/actions/exec.png"),self.tr("Extra actions"))
				#for res in contact.resources.keys():
					#if res != None:
						#if self.main.client.roster['users'][jid].resources[res].hasFeature('http://jabber.org/protocol/commands'):
							#action=submenu.addAction(res)
							#action.setData(QtCore.QVariant("%s/%s" %(jid,res)))
							#action.setObjectName("ad_hoc")

				submenu.connect(submenu, QtCore.SIGNAL("hovered ( QAction * )"),self.contactMenuHovered)

		# signal
		contactMenu.connect(contactMenu, QtCore.SIGNAL("triggered ( QAction * )"),self.contactMenuTriggered)
		contactMenu.connect(contactMenu, QtCore.SIGNAL("hovered ( QAction * )"),self.contactMenuHovered)
		return contactMenu

	def buildContactMenu(self,jid,group):
		# build contact menu
		contactMenu=QtGui.QMenu(self)
		contact = self.main.client.roster['users'][jid]
		oneres = len(contact.resources.keys()) < 2
		myJid = jid == self.main.client.jid.userhost()

		# chat
		if oneres:
			action=contactMenu.addAction(self.tr("Chat"))
			if action != None:
				action.setData(QtCore.QVariant(unicode(jid)))
				action.setObjectName("chat")
		else:
			submenu = contactMenu.addMenu(self.tr("Chat"))
			for res in contact.resources.keys():
				if res != None:
					action=submenu.addAction(unicode(res))
					action.setData(QtCore.QVariant("%s/%s" % (jid, res)))
					action.setObjectName("chat")
		if self.main.client.groupchats != {} and not myJid:	# Mozna zobrazit i kdyz v mucu nejsme aby to bylo vic videt :)
			submenu = contactMenu.addMenu(QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/muc.png"),self.tr("Invite to conference"))
			if oneres:
				for gc in self.main.client.groupchats.keys():
					action = submenu.addAction(gc)
					action.setData(QtCore.QVariant(QtCore.QStringList([jid, gc])))
					action.setObjectName("invite_gc")
			else:
				for gc in self.main.client.groupchats.keys():
					submenu2 = submenu.addMenu(gc)
					for res in contact.resources.keys():
						if res != None:
							action = submenu2.addAction(res)
							action.setData(QtCore.QVariant(QtCore.QStringList(["%s/%s" % (jid, res), gc])))
							action.setObjectName("invite_gc")
		# one2one -> muc
		lst = []
		for i in range(self.main.chat.ui.chatTab.count()):
			w=self.main.chat.ui.chatTab.widget(i)
			if w.typ=='chat' and w.jid != contact.jid:
				lst.append(w.jid)
		if len(lst)>0 and not myJid:
			submenu = contactMenu.addMenu(self.tr("Invite to chat"))
			if oneres:
				for name in lst:
					action = submenu.addAction(self.getNameByJID(name))
					action.setObjectName("invite_chat")
					action.setData(QtCore.QVariant(QtCore.QStringList([unicode(name), jid])))
			else:
				for name in lst:
					submenu2 = submenu.addMenu(self.getNameByJID(name))
					for res in contact.resources.keys():
						if res != None:
							action = submenu2.addAction(res)
							action.setObjectName("invite_chat")
							action.setData(QtCore.QVariant(QtCore.QStringList([unicode(name),"%s/%s" % (jid, res) ]))) # kam pozyvame, koho

		# custom status
		if not myJid:
			submenu=contactMenu.addMenu(self.tr("Custom status"))

			for status in ["online", "chat", "away", "xa", "dnd", "offline"]:
				action=submenu.addAction(self.main.getIcon(status=status,size="32x32"),self.main.status[status])
				action.setObjectName("custom_status")
				action.setData(QtCore.QVariant(QtCore.QStringList([unicode(status), unicode(jid)])))

		# separator
		contactMenu.addSeparator()
		# vcard
		#if oneres:
			#action=contactMenu.addAction(QtGui.QIcon("images/16x16/categories/v-card.png"),self.tr("vCard"))
			#resource=contact.resources.keys()
			#if len(resource)!=0:
				#action.setData(QtCore.QVariant("%s/%s" % (jid, resource[0])))
			#else:
				#action.setData(QtCore.QVariant("%s" % (jid)))
			#action.setObjectName("vcard")
		#else:		# Potrebujeme resource pro Software Version, vCard je na nem nezavisla
			#submenu=contactMenu.addMenu(QtGui.QIcon("images/16x16/categories/v-card.png"),self.tr("vCard"))
			#for res in contact.resources.keys():
				#if res != None:
					#action=submenu.addAction(res)
					#action.setData(QtCore.QVariant("%s/%s" %(jid,res)))
					#action.setObjectName("vcard")
		action=contactMenu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/v-card.png"),self.tr("vCard"))
		action.setData(QtCore.QVariant(jid))
		action.setObjectName("vcard")
		# filetransfer
		if oneres and not myJid:
			resource=contact.resources.keys()
			if len(resource)!=0:
				print contact.resources.keys()
				print self.main.client.roster['users'][jid].resources[resource[0]].features
				if contact.resources[resource[0]].hasFeature('http://jabber.org/protocol/si/profile/file-transfer'):
					action=contactMenu.addAction(self.tr("Send file"))
					action.setData(QtCore.QVariant(jid))
					action.setObjectName("send_file")
					action.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/upload.png"))
		else:
			submenu = None
			for resource in contact.resources.keys():
				if resource != None:
					if len(resource)!=0 and (jid+'/'+resource) != self.main.client.jid.full():
						if contact.resources[resource].hasFeature('http://jabber.org/protocol/si/profile/file-transfer'):
							if submenu == None:
								submenu = contactMenu.addMenu(self.tr("Send file"))
							action = submenu.addAction(resource)
							action.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/upload.png"))
							action.setData(QtCore.QVariant("%s/%s" % (jid, resource)))
							action.setObjectName("send_file")
		self.main.pluginManager.buildContactMenu(contactMenu, contact)
			
		# separator
		contactMenu.addSeparator()

		# break up metacontact
		if self.main.client.roster_meta.has_key(jid):
			action=contactMenu.addAction(self.tr("Break up metacontact"))
			action.setData(QtCore.QVariant(jid))
			action.setObjectName("break_up_meta")
		# rename
		if not myJid:
			action=contactMenu.addAction(self.tr("Rename"))
			action.setData(QtCore.QVariant(jid))
			action.setObjectName("rename")
		# delete from group
		if group!=None and len(self.main.client.roster['users'][jid].groups)>1 and not myJid:
			action=contactMenu.addAction(self.tr("Delete from group"))
			action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"-"+group])))
			action.setObjectName("check_group")
		# delete from roster
		if not myJid:
			action=contactMenu.addAction(self.tr("Delete from roster"))
			action.setData(QtCore.QVariant(jid))
			action.setObjectName("delete_action")
#		if not myJid:  #removed menuentry for fav
#			action = contactMenu.addAction(self.tr("Favourite contact"))
#			action.setData(QtCore.QVariant(jid))
#			action.setObjectName("fav")
#			action.setCheckable(True)
#			action.setChecked(unicode(jid) in self.main.config['favUsers'])

		if not myJid:
			value = contact.subscription
			if value in ["ask"]:
				action = contactMenu.addAction(self.tr("Authorize"))
				action.setData(QtCore.QVariant(jid))
				action.setObjectName("a_authorize")
			if value in ["from", "both",'ask']:
				action = contactMenu.addAction(self.tr("Remove authorization"))
				action.setData(QtCore.QVariant(jid))
				action.setObjectName("a_unauthorize")
			if value in ["none", "from"]:
				action = contactMenu.addAction(self.tr("Request authorization"))
				action.setData(QtCore.QVariant(jid))
				action.setObjectName("a_ask")

		if not myJid:
			# separator
			contactMenu.addSeparator()
			# groups . submenu
			group=contactMenu.addMenu (self.tr("Groups"))
			# groups . new group
			action=group.addAction(self.tr("New Group"))
			action.setData(QtCore.QVariant(jid))
			action.setObjectName("new_group")
			# groups . separator
			group.addSeparator()
			# groups . groups list
			#g=self.getGroups(str(jid))
			for k,v in self.groups.iteritems():
				if k!="Unknown" and k!=self.specialName and len(k)!=0:
					action=group.addAction(unicode(k))
					action.setObjectName("check_group")
					action.setCheckable(True)
				#if len(self.main.client.roster['users'][jid].groups)==0:
					#if k=="Unknown":
						#action.setChecked(True)
						#action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"-"+unicode(k)])))
					#else:
						#action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"+"+unicode(k)])))
				#else:
					if k in self.main.client.roster['users'][jid].groups:
						action.setChecked(True)
						action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"-"+unicode(k)])))
						if len(self.main.client.roster['users'][jid].groups)<=1:
							action.setEnabled(False)
					else:
						action.setData(QtCore.QVariant(QtCore.QStringList([unicode(jid),u"+"+unicode(k)])))

		if self.main.client.privacy and not myJid:
			if self.main.client.privacy.active:
				submenu = contactMenu.addMenu(self.tr("Privacy"))
				if not self.main.client.privacy.active.isBlockedJID(jid):
					action = submenu.addAction(self.tr("Block contact"))
					action.setData(QtCore.QVariant(jid))
					action.setObjectName("privacy_block")
				else:
					action = submenu.addAction(self.tr("Unblock contact"))
					action.setData(QtCore.QVariant(jid))
					action.setObjectName("privacy_unblock")

				# Sekci nemazat
				#if not self.main.client.privacy.active.isAllowedJID(jid):
				#	action = submenu.addAction(self.tr("Allow contact to see my status when I am invisible"))
				#	action.setData(QtCore.QVariant(jid))
				#	action.setObjectName("privacy_allow")
				#else:
				#	action = submenu.addAction(self.tr("Disallow contact to see my status when I am invisible"))
				#	action.setData(QtCore.QVariant(jid))
				#	action.setObjectName("privacy_disallow")

				if not self.main.client.privacy.active.isHiddenJID(jid):
					action = submenu.addAction(self.tr("Always hide my status to contact"))
					action.setData(QtCore.QVariant(jid))
					action.setObjectName("privacy_hide")
				else:
					action = submenu.addAction(self.tr("Don't hide my status to contact"))
					action.setData(QtCore.QVariant(jid))
					action.setObjectName("privacy_unhide")
		if len(contact.resources)!=0 and not myJid:
			if oneres:
				if self.main.client.roster['users'][jid].resources[resource[0]].hasFeature('http://jabber.org/protocol/commands'):
					action=contactMenu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/exec.png"),self.tr("Extra actions"))
					action.setData(QtCore.QVariant("%s/%s" % (jid, contact.resources.keys()[0])))
					action.setObjectName("ad_hoc")
				elif resource[0]==None: #adhoc for services
					action=contactMenu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/exec.png"),self.tr("Extra actions"))
					action.setData(QtCore.QVariant("%s" % (jid)))
					action.setObjectName("ad_hoc")
			else:
				submenu=contactMenu.addMenu(QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/exec.png"),self.tr("Extra actions"))
				for res in contact.resources.keys():
					if res != None:
						if self.main.client.roster['users'][jid].resources[res].hasFeature('http://jabber.org/protocol/commands'):
							action=submenu.addAction(res)
							action.setData(QtCore.QVariant("%s/%s" %(jid,res)))
							action.setObjectName("ad_hoc")

				submenu.connect(submenu, QtCore.SIGNAL("hovered ( QAction * )"),self.contactMenuHovered)

		# signal
		contactMenu.connect(contactMenu, QtCore.SIGNAL("triggered ( QAction * )"),self.contactMenuTriggered)
		contactMenu.connect(contactMenu, QtCore.SIGNAL("hovered ( QAction * )"),self.contactMenuHovered)
		return contactMenu

	def buildGroupMenu(self,name):
		# build contact menu
		contactMenu=QtGui.QMenu(self)
		action=contactMenu.addAction(self.tr("Rename"))
		action.setData(QtCore.QVariant(name))
		action.setObjectName("rename")

		action=contactMenu.addAction(self.tr("Rename by vCard"))
		action.setData(QtCore.QVariant(name))
		action.setObjectName("rename_by_vcard")

		contactMenu.addSeparator()

		action=contactMenu.addAction(self.tr("Remove group"))
		action.setData(QtCore.QVariant(name))
		action.setObjectName("remove_group")

		submenu=contactMenu.addMenu(self.tr("Custom status"))

		for status in ["online", "chat", "away", "xa", "dnd", "offline"]:
			action=submenu.addAction(self.main.getIcon(status=status,size="32x32"),self.main.status[status])
			action.setObjectName("custom_status")
			action.setData(QtCore.QVariant(QtCore.QStringList([unicode(status), unicode(name)])))

		# signal
		contactMenu.connect(contactMenu, QtCore.SIGNAL("triggered ( QAction * )"),self.groupMenuTriggered)
		return contactMenu

	def groupMenuTriggered(self,action):
		cmd=action.objectName()
		if cmd=="rename":
			name=action.data()
			name=unicode(name.toString())
			group,b=QtGui.QInputDialog.getText(self.main,self.tr("Rename group"),self.tr("Enter new group name"), QtGui.QLineEdit.Normal, "")
			group=unicode(group)
			# if user set new name of group
			if b==True and len(group)!=0:
				for item in self.getAllGroupUsers(name):
					jid=item.jid
					contact=self.main.client.roster['users'][jid]
					for count in range(self.main.client.roster['users'][jid].groups.count(name)):
						self.main.client.roster['users'][jid].groups.remove(name)
					self.main.client.roster['users'][jid].groups.append(group)
					self.main.client.sendRosterUpdate(contact.jid, contact.name, contact.subscription,self.main.client.roster['users'][jid].groups)
		elif cmd=="rename_by_vcard":
			name=action.data()
			name=unicode(name.toString())
			for item in self.getAllGroupUsers(name):
				jid=item.jid
				contact=self.main.client.roster['users'][jid]
				if (contact.name=="" or contact.name==contact.jid) or not contact.name:
					self.main.client.getVCard(jid)
		elif cmd =='custom_status':
			show, name = [unicode(val.toString()) for val in action.data().toList()]
			seznam = []
			for itm in self.getAllGroupUsers(name):
				seznam.append(itm.jid)
			self.main.sendCustomStatus(seznam, show)
		elif cmd=="remove_group":
			name=action.data()
			name=unicode(name.toString())
			ret=QtGui.QMessageBox.question(self,self.tr("Remove group?"), self.tr("Do you want to remove group ")+unicode(name)+self.tr(" from your roster?"),QtGui.QMessageBox.Yes|QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)
			if ret==QtGui.QMessageBox.Yes:
				for item in self.getAllGroupUsers(name):
					jid=item.jid
					contact=self.main.client.roster['users'][jid]
					g=contact.groups
					try:
						g.remove(name)
					except:
						pass
					if self.metaItems.has_key(item.metajid):
						for metaItem in self.metaItems[item.metajid]:
							jid=metaItem.jid
							contact=self.main.client.roster['users'][jid]
							g=contact.groups
							try:
								g.remove(name)
							except:
								pass
							self.main.client.sendRosterUpdate(contact.jid, contact.name, contact.subscription,g)



					self.main.client.sendRosterUpdate(contact.jid, contact.name, contact.subscription,g)

	def breakMetaContacts(self,jid):
		item=self.getUserItems(jid)[0]
		metajid=item.metajid
		for it in self.getUserItems(jid):
			self.users.remove(it)
		for it in self.metaItems[metajid]:
			del self.main.client.roster_meta[it.jid]
			self.main.client.on_UpdateContact(it.jid)
		del self.metaItems[metajid]
		self.main.client.setMetacontacts()
		self.main.client.makeTempMeta()

	def contactMenuTriggered(self,action):
		# contact menu action handler
		cmd=action.objectName()
		if cmd=="delete_action":
			# delete contact from roster
			print "delete contact CLICKED"
			jid=action.data()
			jid=unicode(jid.toString())
			ret=QtGui.QMessageBox.question(self,self.tr("Delete contact?"), self.tr("Do you want to delete this contact from your roster?"),QtGui.QMessageBox.Yes|QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)
			if ret==QtGui.QMessageBox.Yes:
				self.main.client.delContact(jid)
				j = jidT.JID(jid)
				if j.userhost() == j.host:
					if self.main.client.hasIdentity(j.userhost(), 'gateway'):
						ret=QtGui.QMessageBox.question(self,self.tr("Delete gateway?"), self.tr("Do you want to delete associated contacts from your roster?"),QtGui.QMessageBox.Yes|QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)
						if ret==QtGui.QMessageBox.Yes:
							for jd in self.main.client.roster['users'].iterkeys():
								if jd.find(j.host) != -1:
									self.main.client.delContact(jd)

		elif cmd=="fav":
			jid=action.data()
			jid=unicode(jid.toString())
			if unicode(jid) in self.main.config['favUsers']:
				self.main.config['favUsers'].remove(unicode(jid))
			else:
				self.main.config['favUsers'].append(unicode(jid))

		elif cmd=='add_contact':
			jid=action.data()
			jid=unicode(jid.toString())
			dialog=addcontact.addContactDialog(self.main,self.main,jid=jid,group="",name=jid.split('@')[0])
			dialog.exec_()

		elif cmd=="break_up_meta":
			# break up metacontact
			jid=action.data()
			jid=unicode(jid.toString())
			self.breakMetaContacts(jid)
		elif cmd=="rename":
			# rename contact
			jid=action.data()
			jid=unicode(jid.toString())
			try:
				name=unicode(self.main.client.roster['users'][jid].name)
			except:
				name = ''
			if len(name) == 0:
				name = jid.split('@')[0]
			name,b=QtGui.QInputDialog.getText(self.main,self.tr("Rename"),self.tr("Enter new name:"), QtGui.QLineEdit.Normal, name)
			name=unicode(name)
			# if user set new name
			if b==True and len(name)!=0:
				# change name
				contact=self.main.client.roster['users'][jid]
				self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription, self.main.client.roster['users'][jid].groups)
		elif cmd=="new_group":
			# add contact to the new group
			# get contact jid
			jid=action.data()
			jid=unicode(jid.toString())
			name=unicode(self.main.client.roster['users'][jid].name)
			group,b=QtGui.QInputDialog.getText(self.main,self.tr("New group"),self.tr("Add user to new group"), QtGui.QLineEdit.Normal, "")
			group=unicode(group)
			# if user set new name of group
			if b==True and len(group)!=0:
				# add new group
				contact=self.main.client.roster['users'][jid]
				self.main.client.sendRosterUpdate(contact.jid, contact.name, contact.subscription, self.main.client.roster['users'][jid].groups+[group])
		elif cmd=="check_group":
			# change users group
			items=action.data()
			items=items.toList()
			jid=unicode(items[0].toString())
			action=unicode(items[1].toString())[0]
			group=unicode(items[1].toString())[1:]
			self.changeGroup(jid,action,group)
		elif cmd=="vcard":
			# get vcard of selected contact
			jid=action.data()
			jid=unicode(jid.toString())
			#self.main.client.getVCard(jid)
			vcardeditor.vcardEditorDialog(self.main,jid,self.main,False).show()
			#d=self.main.client.getVCard(jid)
			#d.addCallback(self.vcardArrived)
		elif cmd=="chat":
			# chat with selected contact
			jid=action.data()
			jid=unicode(jid.toString())
			#if jid.find("/") == -1:
				#item=self.getUserItems(jid)[0]
				#self.main.chat.addChatTab(item.jid,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
			#else:
				#jid_r, res = jid.split("/", 1)
				#item=self.getUserItems(jid_r)[0]
				#self.main.chat.addChatTab(jid,"%s/%s" % (item.name, res),self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))

			jid=jidT.JID(jid)
			if not jid.resource:
				item=self.getUserItems(jid.userhost())[0]
				#res = self.main.client.roster['users'][jid.userhost()].getHighestResource()
				#if res==None:
				self.main.chat.addChatTab(item.jid,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
				#else:
					#self.main.chat.addChatTab(item.jid+"/"+res,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
			else:
				item=self.getUserItems(jid.userhost())[0]
				self.main.chat.addChatTab(jid.full(),item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
			self.main.chat.activate()
		elif cmd == "invite_gc":
			user_jid, room_jid = [unicode(val.toString()) for val in action.data().toList()]
			reason = self.tr("Hi! I'd love to see you in multichat at ") + room_jid
			self.main.client.sendInvitation(user_jid, room_jid, reason)

		elif cmd == "invite_chat":
			kam, koho = [unicode(val.toString()) for val in action.data().toList()]

			room=str(int(time.time())) # define room name
			# find server when we can host the room
			mucjid = None
			for jid, node in self.main.client.disco.iteritems():
				if not node[None].has_key('identities'):
					continue
				for id in node[None]['identities'].itervalues():
					#print jid, id
					if id.get('category') == 'conference' and id.get('type') == 'text' and jid.startswith('c'):
						mucjid = jid
						break
				if mucjid:
					break
			room+="@"+mucjid # room jabber id

			name = self.getNameByJID(kam) # get name of tab where is this widget showed
			tab, index = self.main.chat.findTab(kam)
			rmIndex=int(index) # get index of this tab
			# join to the room and send invitation
			if self.main.chat.addGroupChatTab(room,self.main.client.jid.user,name=name):
				tab,index=self.main.chat.findTab(room)
				tab.chat.invitation=[unicode(koho),unicode(kam)]
				self.main.client.joinGC(room, self.main.client.jid.user,sendRooms=self.main.config['sendRooms']=="True")
			# remove old user2user conversation tab
			self.main.chat.removeTab(rmIndex)

		elif cmd=="custom_status":
			show, jid = [unicode(val.toString()) for val in action.data().toList()]
			self.main.sendCustomStatus(jid, show)

		elif cmd=="send_file":
			# sends files to contact
			jid=action.data()
			jid=unicode(jid.toString())
			j = jidT.JID(jid)
			if j.resource == None:
				res=self.main.client.roster['users'][jid].getHighestResource()
				if res:
					jid+="/"+unicode(res)

			self.main.sendFiles(jid)
			#file=QtGui.QFileDialog.getOpenFileNames(self.main,"Choose file")
			#file=list(file)
			#if len(file)!=0:
				#new=[]
				#for f in file:
					#new.append(unicode(f))
				#file=new
				#self.dialog=filetransfer.filetransferDialog(self.main,file,jid)
				#self.dialog.show()
		elif cmd == "a_authorize":
			jid=action.data()
			jid=unicode(jid.toString())
			self.main.client.sendPresence(jid, typ="subscribed")
			value = self.main.client.roster['users'][jid].subscription
			if value == "none":
				self.main.client.roster['users'][jid].subscription = "from"
			elif value == "to":
				self.main.client.roster['users'][jid].subscription = "both"
			log.msg("%s authorized" % jid)
		elif cmd == "a_unauthorize":
			jid=action.data()
			jid=unicode(jid.toString())
			self.main.client.sendPresence(jid, typ="unsubscribed")
			value = self.main.client.roster['users'][jid].subscription
			if value == "from":
				self.main.client.roster['users'][jid].subscription = "none"
			elif value == "both":
				self.main.client.roster['users'][jid].subscription = "to"
			log.msg("removed autorization from %s" % jid)
		elif cmd == "a_ask":
			jid=action.data()
			jid=unicode(jid.toString())
			self.main.client.sendPresence(jid, typ="subscribe")
			log.msg("sent subscription request to %s" % jid)

		elif cmd == "privacy_block":
			jid=unicode(action.data().toString())
			self.main.client.privacy.active.blockJID(jid)
			log.msg("Blocking jid %s." % jid)
			self.main.client.sendPresence(jid, typ="unavailable")
		elif cmd == "privacy_unblock":
			jid=unicode(action.data().toString())
			self.main.client.privacy.active.unBlockJID(jid)
			log.msg("Unblocking jid %s." % jid)


		elif cmd == "privacy_allow":
			jid=unicode(action.data().toString())
			self.main.client.privacy.active.allowJID(jid)
			log.msg("Allowing jid %s." % jid)
		elif cmd == "privacy_disallow":
			jid=unicode(action.data().toString())
			self.main.client.privacy.active.disAllowJID(jid)
			log.msg("Disallowing jid %s." % jid)

		elif cmd == "privacy_hide":
			jid=unicode(action.data().toString())
			self.main.client.privacy.active.hideJID(jid)
			log.msg("Hiding jid %s." % jid)
			self.main.client.sendPresence(jid, typ="unavailable")
		elif cmd == "privacy_unhide":
			jid=unicode(action.data().toString())
			self.main.client.privacy.active.unHideJID(jid)
			log.msg("Unhiding jid %s." % jid)
#		elif cmd == "ad_hoc":
#			jid=unicode(action.data().toString())
#			self.cmds = commands.Commands(self.main, jid)
#			self.cmds.dialog.show()
		log.msg("END CONTACT")

	def contactMenuHovered(self,action): #Work In Progress
		print 'hover!'
		cmd=action.objectName()
		if cmd == "ad_hoc" and action.menu() == None:
			jid=unicode(action.data().toString())
			self.cmds = commands.Commands(self.main, jid, action)
#			self.cmds.dialog.show()
		#self.buildContactMenu()
	#def vcardArrived(self,data):
		#self.dialog=vcardview.vcardViewDialog(self.main,data,self)
		#self.dialog.show()
		#self.ve=vcardeditor.vcardEditorDialog(self.main,data,self,False)
		#self.ve.show()


	def changeGroup(self,jid,action,group):
		# change group of users
		name=unicode(self.main.client.roster['users'][jid].name)
		if action=="+":
			contact=self.main.client.roster['users'][jid]
			self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription, self.main.client.roster['users'][jid].groups+[group])
		else:
			contact=self.main.client.roster['users'][jid]
			g=contact.groups
			g.remove(group)
			self.main.client.sendRosterUpdate(contact.jid, name, contact.subscription,g)

	def contextMenuEvent (self,event):
		# show contact context menu
		item=self.itemAt(event.x(),event.y())
		if item.typ=="user":
			if self.item!=item:
				self.selectItem(item)
			group=item.group
			jid=item.jid
			#if self.main.client.roster['users'].has_key(jid):
			contactMenu=self.buildContactMenu(unicode(jid),group)
			#contactMenu.move(event.globalX(),event.globalY())
			contactMenu.popup(QtCore.QPoint(event.globalX(),event.globalY()))
		elif item.typ=="group":
			contactMenu=self.buildGroupMenu(item.name)
			contactMenu.move(event.globalX(),event.globalY())
			contactMenu.popup(QtCore.QPoint(event.globalX(),event.globalY()))
	#}
