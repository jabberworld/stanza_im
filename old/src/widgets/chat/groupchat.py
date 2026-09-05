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
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA. 
"""
from PyQt4 import QtCore, QtGui
from groupchatwidget_ui import *
from groupchatadmin import *
from configobj import ConfigObj
import urllib,re,os
from twisted.web.microdom import *
from twisted.web.domhelpers import gatherTextNodes
from widgets import dataforms
from twisted.words.protocols.jabber import jid as jidT
from widgets import vcardeditor
from include import utils
#import filetransfer
from abstractchatwidget import abstractChatWidget
from webkitchatwidget import webkitGroupChatWidget
from widgets import addcontact
import pyxl
import weakref
from widgets.tooltip import ToolTip
from include.constants import RESOURCEPATH

class groupChatWidget(abstractChatWidget):
	def __init__(self,main,jid,parent=None,nickname="",ui=Ui_groupchatwidget):
		self.typ="groupchat"
		self.main=weakref.ref(main)
		abstractChatWidget.__init__(self, ui, webkitGroupChatWidget, main, jid, True, parent)
		
		self.nick = nickname #: MUC Jabber ID
		self.affiliation="" #: user affiliation
		self.role="" #: user role
		# these days depracted, but maybe will be used in future
		self.cache={}
		self.lines=0
		self.maxLines=300
		self.tabWord=None #: when user press Tab, contains word where was Tab pressed
		self.name_id=-1 # for tabPressed
		self.ui.disco_info.hide()
		self.lastMessageFrom=""
		self.ui.users.main=self.main()

		# signals
		QtCore.QObject.connect(self.ui.users, QtCore.SIGNAL("itemDoubleClicked ( QTreeWidgetItem * , int )"),self.userClicked)
		#QtCore.QObject.connect(self.ui.users, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem * , int )"),self.userSingleClicked)
		self.ui.users.mouseReleaseEvent=self.userSingleClicked
		QtCore.QObject.connect(self.ui.users, QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.usersContextMenu)

		# shortcuts
		#short=QtGui.QShortcut("tab",self.ui.line)
		#QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.tabPressed)
		
		# make roles in users list
		self.roles={} #: list of possible roles [possible role:QtreeWidgetItem]
		self.addRole("participant",self.tr("Participants"))
		self.addRole("moderator",self.tr("Moderators"))
		self.addRole("visitor",self.tr("Visitors"))
		self.ui.users.header().hide()
		self.ui.users.hideColumn(1)
		self.ui.users.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

		self.sizes={} #: sizes of avatars of other occupants
		self.colors=[] #: colors of other occupants
		self.invitation=[] #: contains JIDs where is send invitation when first presence from MUC arrived (important for converting chat to groupchat)

		# layout for plugins
		self.flowLayout = QtGui.QHBoxLayout()
		self.flowLayout.setMargin(0)
		self.flowLayout.setSpacing(2)

		# use the same height for all buttons
		self.ui.sendButton.setMinimumHeight(self.ui.sendButton.height())
		self.ui.sendButton.setMaximumHeight(self.ui.sendButton.height())
		self.ui.smileys.setMinimumHeight(self.ui.sendButton.height())
		self.ui.smileys.setMaximumHeight(self.ui.sendButton.height())

		# load plugins buttons
		self.main().pluginManager.buildGroupchatWidget(unicode(self.jid),self.flowLayout,self )
		

		# Make "Room Configuration" Menu

		# make global buttons
		self.ui.configButton=QtGui.QToolButton()

		menu=QtGui.QMenu(self.tr("Room configuration"),self.ui.configButton)
		self.ui.admin=menu.addAction(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/register.png"),self.tr("Room administration"),self.roomConfigClicked)
		menu.addAction(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/clear.png"),self.tr("Clear chat"),self.clearChat)
		menu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/edit.png"),self.tr("Change nickname"),self.changeNick)
		isBookmarked=False
		self.bookmarkAction=None
		for bookmark in self.main().client.bookmarks['conference'].values():
			if bookmark.jid.userhost()==jid:
				isBookmarked=True
				break
		if not isBookmarked:
			self.bookmarkAction=menu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/bookmarks.png"),self.tr("Add to bookmark"),self.addToBookmark)
		action=menu.addAction(QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/info.png"),self.tr("Show room info"))
		action.setCheckable(True)
		QtCore.QObject.connect(action,QtCore.SIGNAL("toggled ( bool )"),self.toggleInfo)

		self.ui.configButton.setIconSize(QtCore.QSize(16,16))
		self.ui.configButton.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/register.png"))
		self.ui.configButton.setToolTip(self.tr("Configuration"))
		self.ui.configButton.setMinimumHeight(self.ui.sendButton.height())
		self.ui.configButton.setMaximumHeight(self.ui.sendButton.height())
		self.ui.configButton.setMenu(menu)
		self.ui.configButton.setPopupMode(QtGui.QToolButton.InstantPopup)
		self.ui.configButton.setArrowType(QtCore.Qt.NoArrow)
		self.flowLayout.addWidget(self.ui.configButton)

		#self.ui.admin.setEnabled(False)
		self.flowLayout.addStretch()
		self.ui.pluginWidget.setLayout(self.flowLayout)
		self.on_owner=None

		self.ui.users.viewportEvent=self.usersEvent
		self.ui.users.leaveEvent=self.usersLeaveEvent

		self.unread=0 #: number of unread message

		# label showed until first presence arrive
		self.connecting=QtGui.QLabel(self.tr("Connecting to MUC. This can take a few seconds."),self.ui.webkit)
		self.connecting.adjustSize()

		self.loadSelfAvatar()

		self.disco_features = [] #: list of room features
		log.msg("REQUESTING ROOM INFO")
		self._getInfo()
		self.tool=None

		self.known_commands = [
			# command,  handler, need_param?
			('/google', self.commandGoogle, False),
			('/nick',   self.commandNick,   True ),
			('/join',   self.commandJoin,   True ),
			('/leave',  self.commandLeave,  False),
			('/say',    self.commandSay,    True ),
			('/me',     self.commandMe,     False),
			('/help',  self.commandHelp,  False)
		]
		self.commands_regexps = []
		for cmd in self.known_commands:
			self.commands_regexps.append( (re.compile(cmd[0]+r'(\s+(?P<param>\S.*)?)?$'), cmd[1], cmd[2]) )
		
		self.loadWebkit()

		#nick=self.main().getJid(jid).resource
		#status=self.main().icons[unicode(item.text(1))[0]]
		#if self.main().avatarDef.get(jid, False):
			#if self.main().client.avatarImg[self.main().avatarDef[jid]] and self.main().avatarDef[jid]!="None":
				#width=self.main().client.avatarImg[self.main().avatarDef[jid]][1]
				#height=self.main().client.avatarImg[self.main().avatarDef[jid]][2]
				#height=height/(float(width)/64.0)
				#text+='<td><img src="'+self.main().realHomeDir+'/avatars/'+unicode(self.main().avatarDef[jid])+'" width="64" height="'+str(height)+'"/></td>'
		##if os.path.isfile(self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%")):
			##f=open(self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%"),"rb")
			##image = f.read()
			##f.close()
			##pixmap=QtGui.QPixmap()
			##pixmap.loadFromData(image)
			##pixmap=QtGui.QIcon(pixmap)
			##pixmap=pixmap.pixmap(64,64)
			##text+='<td><img src="'+self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%")+'" width="'+str(pixmap.width())+'" height="'+str(pixmap.height())+'"/></td>'
		#text+='<td><b>'+self.tr("Name:")+'</b> '+nick+'<br/>'
		#if self.main().client.groupchats[self.jid].users[nick].truejid:
			#text+='<b>'+self.tr("JID:")+'</b> '+self.main().client.groupchats[self.jid].users[nick].truejid+'<br/>'
		#else:
			#text+='<b>'+self.tr("JID:")+'</b> '+unicode(self.jid)+'/'+nick+'<br/>'
		#text+='<img src="images/16x16/status/jabber-%s.png">' % status # hodilo by se rozlisit k jakymu poatri transportu
		#text+='<font size="-1">%s</font><br>' % unicode(self.main().client.groupchats[self.jid].users[nick].status).replace("None","")
		#text+="</td></tr></table>"

	def loadSelfAvatar(self):
		if self.main().selfAvatar:
			result=self.main().getAvatar(self.main().selfAvatar,size="64x64",frame=True)
			self.ui.selfAvatar.setPixmap(result)
			self.ui.selfAvatar.setMaximumWidth(64)
		else:
			self.ui.selfAvatar.hide()
			self.ui.lineWidget.setMinimumSize(100,64)

	def usersEvent(self,event):
		# tooltip request:
		#print "event",event.type()
		if int(event.type())==110:
			x = int(event.x())
			y = int(event.y())
			item = self.ui.users.itemAt(x, y)
			if item and item.parent():
				if not self.tool:
					#self._mouseLeaveEvent(None)
					nick = unicode(item.text(0))
					jid = self.jid + "/" + nick
					g = self.ui.users.mapToGlobal(QtCore.QPoint(x, y))
					self.tool = ToolTip(self.main(), jid, nick, g, True)
					self.tool.leaveEvent = self.tooltipLeaveEvent

				self.tool.show()

		return QtGui.QTreeWidget.viewportEvent(self.ui.users,event)

	def tooltipLeaveEvent(self,event):
		self.tool.hide()
		self.tool.deleteLater()
		self.tool = None

	def usersLeaveEvent(self,event):
		self.main().reactor.callLater(0.2,self._usersLeaveEvent)

	def _usersLeaveEvent(self):
		if self.tool and not self.tool.focus:
			self.tooltipLeaveEvent(None)

	def addToBookmark(self):
		"""
		Bookmarks this groupchat.
		"""
		self.main().client.bookmarks['conference'][self.jid]=pyxl.client.Bookmark(self.jid, 'conference', self.jid, False, self.nick, "")
		self.main().client.setBookmarks()
		self.main().buildBookmarks()
		self.bookmarkAction.setEnabled(False)

	def _getInfo(self):
		"""
		Gets room disco#info.
		"""
		self.main().client.getDiscoInfo(self.jid, callback=self._infoReceived)

	def changeTopic(self,topic):
		"""
		Called when rooms topic is changed.
		@type topic: unicode
		@param topic: new topic
		"""
		subject=utils.replace_url(topic,self.main())
		self.ui.info.setHtml(unicode(subject))

	def _infoReceived(self, *a):
		"""
		Called By pyxl when disco#info is received
		"""
		self.disco_features = self.main().client.disco[self.jid][(self.jid,None)]["features"]
		features = []
		possible_features = {
				# http://jabber.org/protocol/muc#register
				# http://jabber.org/protocol/muc#roomconfig
				# http://jabber.org/protocol/muc#roominfo
				"muc_hidden":self.tr("Hidden"),
				"muc_membersonly":self.tr("Members only"),
				"muc_moderated":self.tr("Moderated"),
				"muc_nonanonymous":self.tr("Non anonymous"),
				"muc_open":self.tr("Open"),
				"muc_passwordprotected":self.tr("Password protected"),
				"muc_persistent":self.tr("Persistent"),
				"muc_public":self.tr("Public"),
				# muc_rooms
				"muc_semianonymous":self.tr("Semi-anonymous"),
				"muc_temporary":self.tr("Temporary"),
				"muc_unmoderated":self.tr("Unmoderated"),
				"muc_unsecured":self.tr("Unsecured")
				}
		for f in self.disco_features:
			if f in possible_features.keys():
				if not unicode(possible_features[f]) in features:
					features.append(unicode(possible_features[f]))
			else:
				log.msg("Unknown room feature: %s" % f)
		
		self.ui.disco_info.setText(unicode(", ".join(features)))
		log.msg("ROOM INFO RECEIVED")
		log.msg(unicode(self.disco_features))
		
	
	def showConnecting(self):
		"""
		Shows 'connecting...' QLabel in conversations QTextEdit.
		"""
		pos=self.ui.webkit.mapToGlobal(QtCore.QPoint(0,0))
		x=pos.x()
		y=pos.y()
		self.connecting.setGeometry(self.ui.webkit.width()/2-self.connecting.width()/2,self.ui.webkit.height()/2-self.connecting.height()/2, self.connecting.width(), self.connecting.height())
		self.connecting.show()
		
	def addRoles(self):
		"""
		Adds all roles QTreeWidgetItems to users list (self.ui.users).
		"""
		self.addRole("participant",self.tr("Participants"))
		self.addRole("moderator",self.tr("Moderators"))
		self.addRole("visitor",self.tr("Visitors"))

	def usersContextMenu(self,pos):
		"""
		Called when wants to see context menu.
		"""
		item=self.ui.users.itemFromIndex(self.ui.users.indexAt(pos)) # get selected item
		if not item or item.parent()==None:
			return
		name=unicode(item.text(0)) # get contact name
		menu=QtGui.QMenu(self.ui.users) # make menu
		jid="%s/%s" % (self.jid, name) # contats JID
		# if it's not group item
		if item.parent()!=None:
			# get self affiliation, self role and self contact (user) item
			affiliation=""
			role=""
			user = None
			if self.main().client.groupchats.has_key(self.jid):
				if self.main().client.groupchats[self.jid].users.has_key(name):
					user = self.main().client.groupchats[self.jid].users[name]
					affiliation=self.main().client.groupchats[self.jid].users[name].affiliation
					role=self.main().client.groupchats[self.jid].users[name].role
			# temp array to set priority of affiliations
			affiliations={'none':0,'member':1,'admin':2,'owner':3}

			# add "add user to roster" action if we know true JID
			# open PM
			action = menu.addAction(self.tr('Private message'))
			action.setData(QtCore.QVariant(QtCore.QStringList([jid, name, item.text(1)])))
			action.setObjectName("pm")
			# vcard action
			action=menu.addAction(self.tr("vCard"))
			action.setData(QtCore.QVariant(jid))
			action.setIcon(QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/v-card.png"))
			action.setObjectName("vcard")
			# send file action
			action=menu.addAction(self.tr("Send file"))
			action.setData(QtCore.QVariant(jid))
			action.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/upload.png"))
			action.setObjectName("send_file")
			if user != None:
				if user.truejid != None:
					tjid = jidT.JID(user.truejid).userhost()
					action=menu.addAction(self.tr("Add to roster"))
					action.setData(QtCore.QVariant(QtCore.QStringList([tjid, name])))
					action.setIcon(QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/add-user.png"))
					action.setObjectName("add-user")
			separator=False
			# make kick, ban action and separator
			separator=False
			if (self.role=="moderator" or self.affiliation=="owner") and affiliations[self.affiliation]>affiliations[affiliation]:
				if not separator:
					menu.addSeparator()
					separator=True
				action=menu.addAction(self.tr("Kick"))
				action.setData(QtCore.QVariant(name))
				action.setObjectName("kick")
			if (self.affiliation=="admin" or self.affiliation=="owner") and affiliations[self.affiliation]>affiliations[affiliation]:
				if not separator:
					menu.addSeparator()
					separator=True
				action=menu.addAction(self.tr("Ban"))
				action.setData(QtCore.QVariant(name))
				action.setObjectName("ban")
			
			# make other actions
			if self.affiliation=="owner":
				if not separator:
					menu.addSeparator()
					separator=True
				if affiliation=='owner':
					action=menu.addAction(self.tr("Revoke ownership"))
					action.setData(QtCore.QVariant(name))
					action.setObjectName("revoke_owner")
					separator=True
				else:
					action=menu.addAction(self.tr("Grant ownership"))
					action.setData(QtCore.QVariant(name))
					action.setObjectName("grant_owner")
					separator=True

				if affiliation=='admin':
					action=menu.addAction(self.tr("Revoke admin"))
					action.setData(QtCore.QVariant(name))
					action.setObjectName("revoke_admin")
					separator=True
				else:
					action=menu.addAction(self.tr("Grant admin"))
					action.setData(QtCore.QVariant(name))
					action.setObjectName("grant_admin")
					separator=True
			if affiliations[self.affiliation]>affiliations[affiliation]:
				if self.affiliation=="admin" or self.affiliation=="owner":
					if not separator:
						menu.addSeparator()
						separator=True
					if (affiliation=='member' or affiliation=='none') and role=='moderator':
						action=menu.addAction(self.tr("Revoke moderator"))
						action.setData(QtCore.QVariant(name))
						action.setObjectName("revoke_moderator")
						separator=True
					elif role!='moderator':
						action=menu.addAction(self.tr("Grant moderator"))
						action.setData(QtCore.QVariant(name))
						action.setObjectName("grant_moderator")
						separator=True
					
					if affiliation=='member':
						action=menu.addAction(self.tr("Revoke membership"))
						action.setData(QtCore.QVariant(name))
						action.setObjectName("revoke_member")
						separator=True
					else:
						action=menu.addAction(self.tr("Grant membership"))
						action.setData(QtCore.QVariant(name))
						action.setObjectName("grant_member")
						separator=True
				if self.role=='moderator':
					if "muc_moderated" in self.disco_features:
						if not separator:
							menu.addSeparator()
							separator=True
						if affiliation=='participant':
							action=menu.addAction(self.tr("Revoke voice"))
							action.setData(QtCore.QVariant(name))
							action.setObjectName("revoke_voice")
							separator=True
						else:
							action=menu.addAction(self.tr("Grant voice"))
							action.setData(QtCore.QVariant(name))
							action.setObjectName("grant_voice")
							separator=True
##			if separator:
##				menu.addSeparator()

			# add other actions from plugins
			self.main().pluginManager.buildGroupchatContactMenu(menu, jid, user)
			

		menu.connect(menu, QtCore.SIGNAL("triggered ( QAction * )"),self.usersContextMenuTriggered)
		# set menu position and show
		menu.popup(self.ui.users.mapToGlobal(pos))
	
	def usersContextMenuTriggered(self,action):
		"""
		Called when user choose item from contextMenu.
		"""
		cmd=action.objectName()
		if cmd=="kick":
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				reason,b=QtGui.QInputDialog.getText(self,self.tr("Reason"),self.tr("Enter reason:"), QtGui.QLineEdit.Normal, "")
				reason=unicode(reason)
				if b==True:
					self.main().client.groupchats[self.jid].setRole(name, 'none',  reason)
		elif cmd=='ban':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				reason,b=QtGui.QInputDialog.getText(self,self.tr("Reason"),self.tr("Enter reason:"), QtGui.QLineEdit.Normal, "")
				reason=unicode(reason)
				if b==True:
					self.main().client.groupchats[self.jid].setAffiliation(name, 'outcast',  reason)
		elif cmd=='grant_moderator':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setRole(name, 'moderator')
		elif cmd=='revoke_moderator':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setRole(name, 'participant')
		elif cmd=='grant_voice':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setRole(name, 'participant')
		elif cmd=='revoke_voice':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setRole(name, 'visitor')
		elif cmd=='grant_member':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setAffiliation(name, 'member')
		elif cmd=='revoke_member':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setAffiliation(name, 'none')
		elif cmd=='grant_owner':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setAffiliation(name, 'owner')
		elif cmd=='revoke_owner':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setAffiliation(name, 'none')
		elif cmd=='grant_admin':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setAffiliation(name, 'admin')
		elif cmd=='revoke_admin':
			name=unicode(action.data().toString())
			if self.main().client.groupchats.has_key(self.jid):
				self.main().client.groupchats[self.jid].setAffiliation(name, 'none')
		elif cmd == "vcard":
			jid=action.data()
			jid=unicode(jid.toString())
			vcardeditor.vcardEditorDialog(self.main(), jid, self, False).show()
		elif cmd == "pm":
			jid=action.data()
			jid, nick, ic=[unicode(val.toString()) for val in action.data().toList()]
			icon=self.main().getIcon(status=self.main().icons[unicode(ic)[0]],size="16x16")
			tab=self.main().chat.addChatTab(jid,nick,icon,full=True)
			self.main().chat.activate()
		
		elif cmd == "send_file":
			jid=unicode(action.data().toString())
			self.main().sendFiles(jid)
		elif cmd == 'add-user':
			jid, nick = [unicode(val.toString()) for val in action.data().toList()]
			addcontact.addContactDialog(self.main(),self.main(), jid = jid, name = nick).show()
			

	def userClicked(self,item,i):
		"""
		Called when user doucble clicked on item.
		"""
		if item.parent()==None:
			return
		icon=self.main().getIcon(status=self.main().icons[unicode(item.text(1))[0]],size="16x16")
		tab=self.main().chat.addChatTab(self.jid+"/"+unicode(item.text(0)),item.text(0),icon,full=True)
		self.main().chat.activate()

	def userSingleClicked(self,event):
		"""
		Called when user single clicked on item.
		"""
		if event.button()==QtCore.Qt.MidButton:
			item=self.ui.users.itemAt(event.pos())
			if not item:
				return
			if item.parent()==None:
				return
			text = unicode(self.ui.line.toPlainText())
			if len(text) == 0 or (text.strip()[:-1] in self.main().client.groupchats[self.jid].users.keys() and text.strip()[:-1] != unicode(item.text(0))):
				self.ui.line.setText(unicode(item.text(0))+': ')
			elif text.endswith(unicode(item.text(0))+': '):
				self.ui.line.setText(text.replace(unicode(item.text(0))+': ', ''))
			
			elif text.endswith(unicode(item.text(0))+' '):
				self.ui.line.setText(text[:-(len(unicode(item.text(0)))+1)])								
			else:
				cur=self.ui.line.textCursor()
				if text[-1]==" ":
					cur.insertText(unicode(item.text(0))+" ")
				else:
					cur.insertText(" "+unicode(item.text(0))+" ")
				self.ui.line.setTextCursor(cur)
			self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
			cur=self.ui.line.textCursor()
			cur.movePosition(QtGui.QTextCursor.End)
			self.ui.line.setTextCursor(cur)
		return QtGui.QTreeWidget.mouseReleaseEvent(self.ui.users, event)

	def clearChat(self):
		"""
		Called when user wants to clear chat.
		"""
		ret=QtGui.QMessageBox.question(self,self.tr("Clear chat?"), self.tr("Do you want to clear this conversation? "),QtGui.QMessageBox.Yes|QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)
		if ret==QtGui.QMessageBox.Yes:
			self.lastMessages = []
			self.loadWebkit()

	def toggleInfo(self, b):
		"""
		Show/hide room info
		"""
		log.msg("Info toggled:"+`b`)
		if b:
			self._getInfo()
			self.ui.disco_info.show()
		else:
			self.ui.disco_info.hide()

	def changeNick(self):
		"""
		Called when user wants to change his nickname.
		"""
		nick, b = QtGui.QInputDialog.getText(self,self.tr("Change nick"),self.tr("Enter new nickname:"), QtGui.QLineEdit.Normal, "")
		if nick and b:
			if nick not in self.main().client.groupchats[self.jid].users.keys():
				self.main().client.sendPresence(to=self.jid+"/"+nick)
				self.main().client.groupchats[self.jid].nick=nick
				self.nick=nick
			else:
				#message=self.main().skin["status_message"].replace("[time]",self.main().now()).replace("[message]",unicode(self.tr("Nickname is used by somebody else.")))
				message=self.main().webkitThemeFactory.genChatStatus(unicode(self.tr("Nickname is used by somebody else.")),self.main().now())
				self.textEditWrite(message)
				self.lastMessageFrom=""
		self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)

	def roomConfigClicked(self):
		"""
		Called when user wants to change configuration of room.
		"""
		nick=self.main().client.groupchats[self.jid].nick
		if self.main().client.groupchats[self.jid].users[nick].affiliation=="owner" :
			d=self.main().client.getMUCConfig(self.jid)
			d.addCallback(self._onRoomConfig)
		elif self.main().client.groupchats[self.jid].users[nick].affiliation=="admin":
			self.dialog=groupchatAdminDialog(self.main(),self.jid,None,self,subject=unicode(self.ui.info.toPlainText()), admin = True)
			self.dialog.show()
		else:
			self.dialog=groupchatAdminDialog(self.main(),self.jid,None,self,subject=unicode(self.ui.info.toPlainText()))
			self.dialog.show()

	def _onRoomConfig(self,data):
		"""
		Called when configuration form arrived.
		"""
		jid=data[0]
		form=data[1]
		if form!=None:
			self.dialog=groupchatAdminDialog(self.main(),jid,form,self,subject=unicode(self.ui.info.toPlainText()), admin = True)
			self.dialog.show()

	def getUserItems(self,name):
		"""
		Returns user items according to name.
		@type name: unicode
		@param name: Name of contact in room
		@rtype: list of QTreeWidgetItem
		@return: list of QTreeWidgetItems or empty list
		"""
		items=self.ui.users.findItems(unicode(name), QtCore.Qt.MatchFixedString| QtCore.Qt.MatchCaseSensitive|QtCore.Qt.MatchRecursive,0)
		if len(items)!=0:
			return items
		return []

	def getUserName(self,jid):
		"""
		Return username of contact according to his true jid.
		@type jid:unicode
		@param jid: True JID of contact
		@rtype: unicode
		@return: nickname or the same jid as first param (jid)
		"""
		for nick,user in self.main().client.groupchats[self.jid].users.iteritems():
			if user.truejid==jid:
				return nick
		return jid

	def addRole(self,role,name):
		"""
		Adds role to the user list.
		"""
		self.roles[role]=QtGui.QTreeWidgetItem(self.ui.users)
		self.roles[role].setBackground(0,QtGui.QBrush(self.ui.users.palette().color(QtGui.QPalette.AlternateBase)))
		self.roles[role].setIcon(0,QtGui.QIcon(RESOURCEPATH+"images/32x32/categories/system-users.png"))
		self.roles[role].setText(0,unicode(name))
		self.roles[role].setText(1,unicode(name))
		self.ui.users.setItemExpanded(self.roles[role],True)
		self.ui.users.setItemHidden(self.roles[role],True)

	def refreshStats(self):
		"""
		Recount number of users in groups.
		"""
		for k,v in self.roles.iteritems():
			v.setText(0,unicode(v.text(1))+" ("+str(v.childCount())+")")
			if int(v.childCount())>0:
				self.ui.users.setItemHidden(v,False)
			else:
				self.ui.users.setItemHidden(v,True)

	def isUser(self,nick):
		"""
		Returns True if user is in room.
		@type nick: unicode
		@param nick: user name
		@rtype: boolean
		@return: True if user is in room, otherwise False
		"""
		if len(self.getUserItems(nick))==0:
			return False
		return True

	def removeUser(self,nick,codes=[],reason="",actor=None,n=None):
		nick=unicode(nick)
		if not reason:
			reason=""
		if self.main().client.groupchats[self.jid].nick==nick:
			if u'307' in codes:
				self.ui.line.setEnabled(False)
				self.ui.users.clear()
				self.addRoles()
				if actor and len(reason)!=0:
					name=self.getUserName(actor)
					message=self.main().webkitThemeFactory.genGroupchatStatus(unicode(self.tr("You have been kicked from the room by %s. Reason: %s.")) % (unicode(name),unicode(reason)),self.main().now())
				elif actor:
					name=self.getUserName(actor)
					message=self.main().webkitThemeFactory.genGroupchatStatus(unicode(self.tr("You have been kicked from the room by %s.")) % unicode(name),self.main().now())
				elif len(reason)!=0:
					message=self.main().webkitThemeFactory.genGroupchatStatus(unicode(self.tr("You have been kicked from the room. Reason: %s.")) % unicode(reason),self.main().now())
				else:
					message=self.main().webkitThemeFactory.genGroupchatStatus(unicode(self.tr("You have been kicked from the room.")),self.main().now())
				self.textEditWrite(message)
				self.lastMessageFrom=""
				return
			elif u'301' in codes:
				self.ui.line.setEnabled(False)
				self.ui.users.clear()
				self.addRoles()
				message=self.main().webkitThemeFactory.genGroupchatStatus(unicode(self.tr("You have been banned for the room.")),self.main().now())
				self.textEditWrite(message)
				self.lastMessageFrom=""
				return
		if u'307' in codes:
			message=self.main().webkitThemeFactory.genGroupchatStatus(nick+unicode(self.tr(" has been kicked from this room.")),self.main().now())
			self.textEditWrite(message)
			self.lastMessageFrom=""
		elif u'301' in codes:
			message=self.main().webkitThemeFactory.genGroupchatStatus(nick+unicode(self.tr(" has been banned for this room.")),self.main().now())
			self.textEditWrite(message)
			self.lastMessageFrom=""
		elif u'303' in codes:
			message=self.main().webkitThemeFactory.genGroupchatStatus(nick+unicode(self.tr(" has been renamed to "))+unicode(n)+".",self.main().now())
			self.textEditWrite(message)
			self.lastMessageFrom=""
		item=self.getUserItems(nick)[0]
		parent=item.parent()
		parent.takeChild(int(parent.indexOfChild(item)))

		self.refreshStats()

	def editUser(self,nick,status,role=None,affiliation=None):
		if not self.connecting.isHidden():
			self.connecting.hide()
			for inv in self.invitation:
				reason = self.tr("Hi! I'd love to see you in multichat at ") + self.jid
				self.main().client.sendInvitation(inv, self.jid,reason, cont=True)
		new=False
		if self.isUser(unicode(nick))==False:
			new=True
			if self.roles.has_key(role):
				item=QtGui.QTreeWidgetItem(self.roles[role])
			else:
				item=QtGui.QTreeWidgetItem(self.ui.users)
			item.setText(0,unicode(nick))
			self.colors.append(item)
		else:
			item=self.getUserItems(nick)[0]
			if item.parent()!=self.roles[role]:
				self.removeUser(nick)
				new=True
				if self.roles.has_key(role):
					item=QtGui.QTreeWidgetItem(self.roles[role])
				else:
					item=QtGui.QTreeWidgetItem(self.ui.users)
				item.setText(0,unicode(nick))
				self.colors.append(item)


		if self.main().client.groupchats[self.jid].nick==nick:
			self.affiliation=affiliation
			self.role=role
			if affiliation=="owner":
				self.ui.admin.setEnabled(True)
				if self.on_owner:
					self.on_owner(self)
			if role=='moderator':
				self.ui.admin.setEnabled(True)
		

		#if self.ui.users.verticalScrollBar().isVisible():
			#self.ui.users.setColumnWidth(0,int(self.ui.users.width())-38-int(self.ui.users.verticalScrollBar().width()))
		#else:
			#self.ui.users.setColumnWidth(0,int(self.ui.users.width())-38)

		# Nastaveni stavu
		status = unicode(status)
		if status!="None":
			item.setIcon(0,self.main().getIcon(status=status,size="32x32"))
			item.setText(1,self.main().shows[status]+unicode(nick.lower()))
		else:
			item.setIcon(0,self.main().getIcon(status="online",size="32x32"))
			item.setText(1,self.main().shows['online']+unicode(nick.lower()))
			status="online"

		if new:
			item.setIcon(1,QtGui.QIcon(RESOURCEPATH+"images/32x32/apps/jabbim.png"))
			self.main().client.on_avatarUpdate(self.jid+"/"+unicode(item.text(0)))

		jid=self.jid+"/"+nick
		#item.setToolTip(0,self.getGroupchatTooltip(jid,item))
		
		avatar=item.icon(1)
		if not avatar.isNull():
			#avatar=avatar.pixmap(28,28)
			result=self.main().getAvatar(avatar,size="32x32",frame=False,status=self.main().icons[unicode(item.text(1))[0]])
			item.setIcon(0,QtGui.QIcon(result))

		

		# Tooltip
		#user.setToolTip('<font color="blue"><b>'+unicode(user.text(2))+'</b></font><hr>'+unicode(e[2].getStatus())+'<br/><b>Jabber ID: </b>'+str(jid)+'')
		# serazeni
		self.ui.users.sortItems (1,QtCore.Qt.AscendingOrder)
		self.refreshStats()

	def getGroupchatTooltip(self,jid,item):
		return ""
		text='<table><tr>'
		nick=self.main().getJid(jid).resource
		status=self.main().icons[unicode(item.text(1))[0]]
		if self.main().avatarDef.get(jid, False):
			if self.main().client.avatarImg[self.main().avatarDef[jid]] and self.main().avatarDef[jid]!="None":
				width=self.main().client.avatarImg[self.main().avatarDef[jid]][1]
				height=self.main().client.avatarImg[self.main().avatarDef[jid]][2]
				height=height/(float(width)/64.0)
				text+='<td><img src="'+self.main().realHomeDir+'/avatars/'+unicode(self.main().avatarDef[jid])+'" width="64" height="'+str(height)+'"/></td>'
		#if os.path.isfile(self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%")):
			#f=open(self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%"),"rb")
			#image = f.read()
			#f.close()
			#pixmap=QtGui.QPixmap()
			#pixmap.loadFromData(image)
			#pixmap=QtGui.QIcon(pixmap)
			#pixmap=pixmap.pixmap(64,64)
			#text+='<td><img src="'+self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%")+'" width="'+str(pixmap.width())+'" height="'+str(pixmap.height())+'"/></td>'
		text+='<td><b>'+self.tr("Name:")+'</b> '+nick+'<br/>'
		if self.main().client.groupchats[self.jid].users[nick].truejid:
			text+='<b>'+self.tr("JID:")+'</b> '+self.main().client.groupchats[self.jid].users[nick].truejid+'<br/>'
		else:
			text+='<b>'+self.tr("JID:")+'</b> '+unicode(self.jid)+'/'+nick+'<br/>'
		text+='<img src="'+RESOURCEPATH+'images/16x16/status/jabber-%s.png">' % status # hodilo by se rozlisit k jakymu poatri transportu
		text+='<font size="-1">%s</font><br>' % unicode(self.main().client.groupchats[self.jid].users[nick].status).replace("None","")
		text+="</td></tr></table>"
		return text

	#def setTooltip(self,item,jid):
		##jid=self.jid+"/"+nick
		#nick=unicode(jidT.JID(jid).resource)
		#status=self.main().client.groupchats[self.jid].users[nick].show
		#item=self.getUserItems(nick)[0]
		#text='<table><tr>'
		#if os.path.isfile(self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%")):
			#f=open(self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%"),"rb")
			#image = f.read()
			#f.close()
			#pixmap=QtGui.QPixmap()
			#pixmap.loadFromData(image)
			#pixmap=QtGui.QIcon(pixmap)
			#pixmap=pixmap.pixmap(64,64)
			#text+='<td><img src="'+self.main().homeDir+'/avatars/'+unicode(jid).replace("/","%")+'" width="'+str(pixmap.width())+'" height="'+str(pixmap.height())+'"/></td>'
		#text+='<td><b>'+self.tr("Name:")+'</b> '+nick+'<br/>'
		#if self.main().client.groupchats[self.jid].users[nick].truejid:
			#text+='<b>'+self.tr("JID:")+'</b> '+self.main().client.groupchats[self.jid].users[nick].truejid+'<br/>'
		#else:
			#text+='<b>'+self.tr("JID:")+'</b> '+unicode(self.jid)+'/'+nick+'<br/>'
		#text+='<img src="images/16x16/status/jabber-%s.png">' % status # hodilo by se rozlisit k jakymu poatri transportu
		#text+='<font size="-1">%s</font><br>' % unicode(self.main().client.groupchats[self.jid].users[nick].status).replace("None","")
		#text+="</td></tr></table>"
		#item.setToolTip(0,text)

	def logButton(self,button):
		if button==self.actual:
			self.ui.textEdit.setHtml(self.cache['actual'])
		else:
			time=unicode(button.text())
			self.cache['actual']=self.ui.textEdit.toHtml()
			self.ui.textEdit.setHtml(self.cache[time])
	
	def commandHelp(self,  dummy):
		text = unicode(self.tr('Available commands: '))
		for command in self.known_commands:
			text = text + command[0] + '  '
		self.ui.line.clear()
		self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		message=self.main().webkitThemeFactory.genChatStatus(text,self.main().now())
		self.textEditWrite(message)
		self.lastMessageFrom=""
		return False

	def commandGoogle(self, query):
		if query:
			anchor="http://www.google.com/search?q="+query
		else:
			anchor="http://www.google.com/"
		QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))
		self.ui.line.clear()
		self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		return False

	def commandNick(self, nick):
		if not self.main().client.groupchats[self.jid].users.has_key(nick):
			self.main().client.sendPresence(to=self.jid+"/"+nick)
			self.main().client.groupchats[self.jid].nick = nick
			self.nick = nick
		else:
			message=self.main().webkitThemeFactory.genGroupchatStatus(unicode(self.tr("Nickname is used by somebody else.")),self.main().now())
			self.textEditWrite(message)
			self.lastMessageFrom=""
		self.ui.line.clear()
		self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		return False

	def commandJoin(self, roomname):
		#self.main().client.sendPresence(to=self.jid+"/"+nick)
		#self.main().client.groupchats[self.jid].nick=nick
		if self.main().chat.addGroupChatTab(roomname,self.main().client.groupchats[self.jid].nick):
			self.main().client.joinGC(roomname, self.main().client.groupchats[self.jid].nick,sendRooms=self.main().config['sendRooms']=="True")
		self.ui.line.clear()
		#self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		return False

	def commandLeave(self, dummy):
		tab,tabIndex=self.main().chat.findTab(unicode(self.jid))
		self.main().chat.removeTab(tabIndex, False)
		self.ui.line.clear()
		return False

	def commandSay(self, text):
		self.ui.line.setPlainText(text)
		return True  # continue like it's a normal message text

	def commandMe(self, text):
		# Don't do anything, '/me' is handled by the receiver
		return True  # continue, it's a normal message text

	def sendButtonClicked(self):
		# sends message
		if len(unicode(self.ui.line.toPlainText()))!=0:
			services=unicode(self.ui.line.toPlainText())

			# Handle known commands '/...'
			command_handled = False
			for command in self.commands_regexps:
				m = command[0].match(services)
				if m:
					# does this command require a param?
					if command[2] and not m.group('param'):
						return  # do nothing, let the user complete the command
					go_on = command[1](m.group('param'))
					if not go_on:
						return  # command fully handled
					command_handled = True
					break

			if not command_handled and services.startswith("/"):
				# maybe a plugin will know the command
				try:
					cmd, args = services.split(" ", 1)
					args = args.split(" ")
				except ValueError:
					cmd = services
					args = []
				cmd = cmd[1:]
				passed = self.main().client.dispatcher.publishEvent("onCommand", cmd, args, self, "groupchat")
				if not passed:
					# it was a recognized command and a subscriber handled the event
					self.ui.line.clear()
					self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
					return
				# Otherwise it's a normal message. Proceed.

			if self.main().config['chatMode']=="normal":
				text=unicode(self.ui.line.toPlainText())
				#text=unicode(text, 'utf-8')
				#text=unescape(text)
			else:
				text=unicode(self.ui.line.toHtml())
				a=parseString(text)
				for el in a.getElementsByTagName('img'):
					path=el.attributes['src'].split('/')[-1]
					for k,v in self.smileys.iteritems():
						if v==path:
							path=k
					newnode = parseString("<div> "+path+"</div>").documentElement
					el.parentNode.replaceChild(newnode,el)
				for el in a.getElementsByTagName('br'):
					newnode = parseString("<div> "+unichr(2028)+"</div>").documentElement
					el.parentNode.replaceChild(newnode,el)
				b=a.getElementsByTagName('body')
				c=parseString(b[0].toxml())
				text=gatherTextNodes(c)
				text=unicode(text, 'utf-8')
				text=text.replace(unichr(2028),"\n")
				#text=unescape(text)

			# get message in Qt html format
			xhtml=self.ui.line.toHtml()
			xhtml,same=self.qtHtmlToXhtml(xhtml,text)
			ret=[]
			if same:
				self.main().pluginManager.on_groupchatMessageSend(unicode(self.jid),text,'',"active")
				
				if not False in ret:
					self.main().client.sendMessage(unicode(self.jid),text,'groupchat',composing="active")
			else:
				self.main().pluginManager.on_groupchatMessageSend(unicode(self.jid),text,'',"active")
				
				if not False in ret:
					self.main().client.sendMessage(unicode(self.jid),text,'groupchat',xhtml=xhtml,composing="active")

			#self.main().client.sendMessage(self.jid, text, 'groupchat')
			self.sent.append(text)
			self.hindex = len(self.sent)
			#self.ui.line.clear()
			#self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
			self.clearLine()
			if self.main().chat.active==False:
				self.main().client.dispatcher.publishEvent('onActivity')
				self.main().chat.active=True
				self.main().chat.timer.stop()

			#self.ui.line.setMaximumHeight(int(self.ui.line.currentFont().pointSize())+15)

	def tabPressed(self):
		# nick completion
		original=unicode(self.ui.line.toPlainText())
		users=self.main().client.groupchats[self.jid].users.keys()
		for user in users:
			original=original.replace(user,user.replace(" ","/"))
		t=unicode(original).lower()
		text=t
		if len(text)==0:
			return
		cur=self.ui.line.textCursor()
		#cur.select(QtGui.QTextCursor.WordUnderCursor)
		#cur.movePosition(QtGui.QTextCursor.Left, QtGui.QTextCursor.KeepAnchor)
		#self.ui.line.setTextCursor(cur)

		i=0
		newt=""
		for word in text.split(" "):
			if cur.position()>i and cur.position()<=i+1+len(word) and len(word)!=0:
				text=word
				break
			else:
				newt=word+" "
			i=i+1+len(word)
		if not self.tabWord:
			self.name_id=-1
			self.tabWord=text
		#text=unicode(cur.selectedText()).lower()
		#text=text[0]
		repeat=False
		if self.nick in users:
			users.remove(self.nick)
		#print text
		for i in range(len(users)):
			if unicode(users[i]).lower()[:len(self.tabWord)]==unicode(self.tabWord).lower():
				if i>self.name_id:
					#cur=self.ui.line.textCursor()
					#cur.movePosition(QtGui.QTextCursor.End)
					#self.ui.line.setTextCursor(cur)
					#self.ui.line.setPlainText(users[i]+": ")
					cur=self.ui.line.textCursor()
					#cur.clearSelection()
					#cur.removeSelectedText()
					#cur.insertText(users[i]+": ")
					x=0 #first letter of word index in string
					newt=""
					pos=0
					ending = " " #ending of the sugested nick, set to space by default, example "Sef "
					for word in original.split(" "):
						if cur.position()>x and cur.position()<=x+1+len(word) and len(word)!=0:
							if x == 0: #if the nick is the first word in string, ending will be ": ", example - "Sef: "
								ending = ": "
							newt+=users[i].replace(" ","/")+ending
							pos=x+len(users[i]+ending)
						else:
							newt+=word+" "
						x=x+1+len(word)
					if len(word)==0:
						newt=newt[:-1]
					#cur.movePosition(QtGui.QTextCursor.NextWord, QtGui.QTextCursor.KeepAnchor)
					for user in users:
						newt=newt.replace(user.replace(" ","/"),user)
					self.ui.line.setPlainText(newt)
					cur.setPosition(pos)
					self.ui.line.setTextCursor(cur)
					self.name_id=i
					return
				#if unicode(users[i]).lower()[:len(text)]==text:
					#repeat=True
				repeat=True
		self.name_id=-1
		if repeat==True:
		#if len(users)!=0:
			self.tabPressed()
			
