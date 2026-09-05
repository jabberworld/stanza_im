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
import gc
from chat_ui import *
from chatwidget import *
from groupchat import *
from include import utils
from include.constants import RESOURCEPATH
import os
from pyxl import jid as jidT
from leaveroom_ui import *
import ctypes
import sys
class leaveMucDialog(QtGui.QDialog):
	def __init__(self,main,jid,parent):
		QtGui.QDialog.__init__(self,parent)
		self.setModal(True)
		self.ui=Ui_leaveroom()
		self.ui.setupUi(self)
		self.main=main
		self.ui.leaveroom.setText(self.tr("You are trying to leave room ")+unicode(jid)+". "+self.tr("Do you realy want to leave this room?"))
		policy=self.ui.leaveroom.sizePolicy()
		policy.setHeightForWidth(True)
		policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
		self.ui.leaveroom.setSizePolicy(policy)
	def accept(self):
		if self.ui.checkBox.isChecked():
			if self.main.config['askBeforeQuitMUC']!="False":
				self.main.config["askBeforeQuitMUC"]="False"
				self.main.config.write()
		self.done(1)

class leaveAllMucDialog(QtGui.QDialog):
	def __init__(self,main,parent):
		QtGui.QDialog.__init__(self,parent)
		self.setModal(True)
		self.ui=Ui_leaveroom()
		self.ui.setupUi(self)
		self.main=main
		self.ui.leaveroom.setText(self.tr("Do you really want to leave all rooms you are connected to?"))
		policy=self.ui.leaveroom.sizePolicy()
		policy.setHeightForWidth(True)
		policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
		self.ui.leaveroom.setSizePolicy(policy)

	def accept(self):
		if self.ui.checkBox.isChecked():
			self.main.config["askBeforeQuitMUC"]="False"
		self.done(1)

class tabWidget(QtGui.QTabBar):
	def __init__(self,parent,main):
		QtGui.QTabBar.__init__(self,parent)
		self.main=main

	def mouseReleaseEvent(self,event):
		if event.button()==QtCore.Qt.MidButton:
			pos=event.pos()
			index=self.tabAt(pos)
			if index!=-1:
				self.main.removeTab(index)
			event.ignore()
			return
		return QtGui.QTabBar.mouseReleaseEvent(self,event)

	def wheelEvent(self,event):
		if event.delta() <= 0:
			self.main.next()
		else:
			self.main.previous()
		event.accept()
		

class chatWindow(QtGui.QMainWindow):
	"""
	MainWindow for conversations (chat)
	"""
	def __init__(self,parent,main):
		apply(QtGui.QMainWindow.__init__,(self,None))
		self.main=main #: Jabbim mainWindow
		self.ui=Ui_chatWindow()
		self.ui.setupUi(self)

		# make QTabWidget
		self.tabBar=tabWidget(self,self) #: QTabWidget for conversations
		self.ui.chatTab.setTabBar(self.tabBar)
		self.ui.chatTab.removeTab(0)
		self.ui.tabCloseButton=QtGui.QPushButton(QtGui.QIcon(RESOURCEPATH+"images/icons/close.png"),"",self.ui.chatTab)
		self.ui.chatTab.setCornerWidget(self.ui.tabCloseButton)
		self.active=False #: depracted
		self.timer=QtCore.QTimer() #: depracted
		self.flashStatus=False #: True if window is flashing in windows bar

		QtCore.QObject.connect(self.ui.tabCloseButton, QtCore.SIGNAL("clicked ()"),self.removeTab)
		QtCore.QObject.connect(self.ui.chatTab, QtCore.SIGNAL("currentChanged ( int )"),self.changeTab)
		QtCore.QObject.connect(self.timer, QtCore.SIGNAL("timeout ()"),self.inactive)

	#{ Private functions

	def startFlash(self):
		"""
		Starts windows flashing
		"""
		print 'flash!'
		self.flashStatus=True
		if sys.platform == 'win32':
			print "starting flash timer"
			ctypes.windll.user32.FlashWindow(int(self.winId()),True)
			self.main.client.reactor.callLater(1,self.flash)

	def flash(self):
		"""
		Called by flash timer, changes flash state
		"""
		print 'flash timer...'
		ctypes.windll.user32.FlashWindow(int(self.winId()),True)
		if self.flashStatus:
			self.main.client.reactor.callLater(1,self.flash)
		else:
			ctypes.windll.user32.FlashWindow(int(self.winId()),False)

	def inactive(self):
		"""
		Sends incative composing message when chat window is inactive
		"""
		if self.active==False and self.main.client != None:
			print "sending inactive chatstate to all tabs"
			for i in range(self.ui.chatTab.count()):
				w=self.ui.chatTab.widget(i)
				if w.typ=="chat":
					w.active=False
					self.main.client.sendMessage(unicode(w.jid),"",composing="inactive")
			self.active=None

	def event(self,ev):
		"""
		QWidgets event handler
		"""
		handler=QtGui.QMainWindow.event(self,ev)
		# activated
		t=ev.type()
		if t==24 or t==17:
			if self.isActiveWindow():
				widget=self.ui.chatTab.widget(self.ui.chatTab.currentIndex())
				if widget:
					# sends activity event to current tab, if we sent inactive before
					if self.active==None and widget.typ=="chat":
						widget.active=True
						self.main.client.sendMessage(unicode(widget.jid),"",composing="active")
					index=int(self.ui.chatTab.currentIndex())
					self.changeTab(index)
					self.active=True

				self.timer.stop()
		# inactive
		elif t==25:
			if self.active:
				self.active=False
				self.timer.start(30000)
		return handler

	#{ Shortcuts

	def tabOne(self):
		self.ui.chatTab.setCurrentIndex(0)
	def tabTwo(self):
		self.ui.chatTab.setCurrentIndex(1)
	def tabThree(self):
		self.ui.chatTab.setCurrentIndex(2)
	def tabFour(self):
		self.ui.chatTab.setCurrentIndex(3)
	def tabFive(self):
		self.ui.chatTab.setCurrentIndex(4)
	def tabSix(self):
		self.ui.chatTab.setCurrentIndex(5)
	def tabSeven(self):
		self.ui.chatTab.setCurrentIndex(6)
	def tabEight(self):
		self.ui.chatTab.setCurrentIndex(7)
	def tabNine(self):
		self.ui.chatTab.setCurrentIndex(8)

	def moveRight(self):
		i=int(self.ui.chatTab.currentIndex())+1
		if i<self.ui.chatTab.count():
			widget=self.ui.chatTab.currentWidget()
			text=unicode(self.ui.chatTab.tabText(i-1))
			oldtext=unicode(self.ui.chatTab.tabText(i))
			oldicon=self.ui.chatTab.tabIcon(i)
			self.ui.chatTab.insertTab(i,widget,self.ui.chatTab.tabIcon(i-1),text)
			self.ui.chatTab.setTabText(i-1,oldtext)
			self.ui.chatTab.setTabIcon(i-1,oldicon)
			self.ui.chatTab.setTabText(i,text)
			QtCore.QObject.disconnect(self.ui.chatTab, QtCore.SIGNAL("currentChanged ( int )"),self.changeTab)
			self.ui.chatTab.setCurrentIndex(i)
			QtCore.QObject.connect(self.ui.chatTab, QtCore.SIGNAL("currentChanged ( int )"),self.changeTab)
			tab=self.ui.chatTab.widget(self.ui.chatTab.currentIndex())
			tab.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)

	def moveLeft(self):
		i=int(self.ui.chatTab.currentIndex())-1
		if i>=0:
			widget=self.ui.chatTab.currentWidget()
			text=unicode(self.ui.chatTab.tabText(i+1))
			oldtext=unicode(self.ui.chatTab.tabText(i))
			oldicon=self.ui.chatTab.tabIcon(i)
			self.ui.chatTab.insertTab(i,widget,self.ui.chatTab.tabIcon(i+1),text)
			self.ui.chatTab.setTabText(i+1,oldtext)
			self.ui.chatTab.setTabIcon(i+1,oldicon)
			QtCore.QObject.disconnect(self.ui.chatTab, QtCore.SIGNAL("currentChanged ( int )"),self.changeTab)
			self.ui.chatTab.setCurrentIndex(i)
			QtCore.QObject.connect(self.ui.chatTab, QtCore.SIGNAL("currentChanged ( int )"),self.changeTab)
			tab=self.ui.chatTab.widget(self.ui.chatTab.currentIndex())
			tab.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)



	def next(self):
		i=int(self.ui.chatTab.currentIndex())+1
		if i<self.ui.chatTab.count():
			self.ui.chatTab.setCurrentIndex(i)
		if i>=self.ui.chatTab.count() and self.main.config['tabCycling'] == 'True':
			self.ui.chatTab.setCurrentIndex(0)

	def previous(self):
		i=int(self.ui.chatTab.currentIndex())-1
		if i>=0:
			self.ui.chatTab.setCurrentIndex(i)
		if i < 0 and self.main.config['tabCycling'] == 'True':
			self.ui.chatTab.setCurrentIndex(self.ui.chatTab.count()-1)


	#{ Public Functions

	def keyPressEvent(self, event): 
		key = event.key() 
		if key == QtCore.Qt.Key_Escape: 
			self.removeTab() 

	def getUnreadMessages(self):
		count=0
		for i in range(self.ui.chatTab.count()):
			w=self.ui.chatTab.widget(i)
			if w.typ in ['chat','groupchat']:
				#try:
				count+=int(w.chat.unread)
				#except:
					#pass
		return count

	def findTab(self,jid=None,full=None,typ=['chat','groupchat']):
		if full==True:
			for i in range(self.ui.chatTab.count()):
				w=self.ui.chatTab.widget(i)
				if self.main.getJid(w.jid).full()==self.main.getJid(jid).full() and w.typ in typ:
					return w,i # tab, index
		elif full==False:
			userhost=self.main.getJid(jid).userhost()
			for i in range(self.ui.chatTab.count()):
				w=self.ui.chatTab.widget(i)
				if self.main.getJid(w.jid).userhost()==userhost and not self.main.getJid(w.jid).resource and w.typ in typ:
					return w,i # tab, index
		else:
			for i in range(self.ui.chatTab.count()):
				w=self.ui.chatTab.widget(i)
				if self.main.getJid(w.jid).full()==self.main.getJid(jid).full() and w.typ in typ:
					return w,i # tab, index

			for i in range(self.ui.chatTab.count()):
				w=self.ui.chatTab.widget(i)
				if self.main.getJid(w.jid).userhost()==self.main.getJid(jid).userhost() and w.typ in typ:
					return w,i # tab, index
		return None,0 # tab, index

	def findTabByMeta(self,jid):
		userhost=self.main.getJid(jid).userhost()
		for i in range(self.ui.chatTab.count()):
			w=self.ui.chatTab.widget(i)
			if w.typ=="chat":
				if w.chat.hasMetacontact(userhost):
					return w,i # tab, index
		return None,0

	def changeTab(self,index):
		if index == -1:
			return
		try:
			self.ui.chatTab.widget(index).chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		except: pass
		jid=unicode(self.ui.chatTab.widget(index).jid)
		typ=unicode(self.ui.chatTab.widget(index).typ)
		if len(unicode(jid).rsplit("/"))!=1:
			resource=unicode(jid).rsplit("/")[1]
			jid=unicode(jid).rsplit("/")[0]
			#res=self.main.ui.roster.getResourceItems(jid)

			#show=self.main.icons[unicode(res[resource].text(1))[0]]
			#icon=self.main.getIcon(jid,show,size="16x16")
		if typ=="chat":
			#icon=self.main.getIcon(jid,self.main.icons[unicode(self.main.ui.roster.getUserItems(jid)[0].status)],size="16x16")
			self.ui.chatTab.setTabIcon(index,self.ui.chatTab.widget(index).ic)
		elif typ == 'groupchat':
			self.ui.chatTab.setTabIcon(index,QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/muc.png"))

		color=self.ui.chatTab.tabBar().palette().color(QtGui.QPalette.Foreground)
		self.ui.chatTab.tabBar().setTabTextColor(index,color)

		widget=self.ui.chatTab.widget(self.ui.chatTab.currentIndex())
		if not widget:
			return
		if typ in ['chat','groupchat']:
			widget.chat.unread=0
			self.ui.chatTab.setTabText(index,widget.tabName)

			if widget.chat.unreadEvent and widget.chat.unreadEvent():
				widget.chat.unreadEvent().reject()
			widget.chat.unreadEvent=None

##		ev=list(self.main.events.events)
##		for event in ev:
##			jid=self.main.getJid(event['name'])
##			if jid:
##				if jid.userhost()==self.main.getJid(widget.jid).userhost() and (event['type']=="newMessage" or event['type']=="message"):
##					event['widget'].closeClicked()
##					#break
##					self.main.events.refreshTray()
		self.flashStatus=False
		unread=int(self.getUnreadMessages())
		if unread>0:
			self.setWindowTitle("("+str(unread)+") "+unicode(self.ui.chatTab.tabText(index)).replace("&",""))
		else:
			self.setWindowTitle(unicode(self.ui.chatTab.tabText(index)).replace("&",""))
		self.setWindowIcon(self.ui.chatTab.tabIcon(index))

		if widget.typ=="chat":
			self.main.client.sendMessage(unicode(widget.jid),"",composing="active")
		widget.active=True

		for i in range(self.ui.chatTab.count()):
			w=self.ui.chatTab.widget(i)
			if w:
				if w.active==True and w!=widget:
					if w.typ=="chat":
						self.main.client.sendMessage(unicode(w.jid),"",composing="inactive")
					w.active=False
				if w.typ in ['chat','groupchat']:
					if not w.active and w.chat.lastMessageFrom!="lineSeparator":
						if not w.chat.separator:
							w.chat.ui.webkit.removeElementById("separateLine")
							w.chat.textEditWrite("<hr id=\"separateLine\"/>")
							w.chat.lastMessageFrom="lineSeparator"
						w.chat.separator=True
					else:
						w.chat.separator=False

	def isActiveWindow(self):
		if sys.platform=="win32":
			return self.isVisible() and not self.windowState() & QtCore.Qt.WindowMinimized and QtGui.QApplication.activeWindow()==self
		else:
			return QtGui.QMainWindow.isActiveWindow(self)

	def activate(self,jid=None):
		print "activate"
		self.show()
		self.setWindowState(self.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
		self.raise_()
		self.activateWindow()
		if jid:
			frm=jid
			tab=None
			tabIndex=0
			for i in range(self.main.chat.ui.chatTab.count()):
				w=self.main.chat.ui.chatTab.widget(i)
				if unicode(w.jid)==unicode(frm):
					tab=w
					tabIndex=i
					break
				if unicode(w.jid).rsplit("/")[0]==unicode(frm).rsplit("/")[0]:
					tab=w
					tabIndex=i
			# we found tab
			if tab!=None:
				self.ui.chatTab.setCurrentWidget(tab)
				#self.changeTab()
				return
		try:
			tab=self.ui.chatTab.widget(self.ui.chatTab.currentIndex())
			tab.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		except:
			pass

	def reconnect(self):
		for i in range(self.ui.chatTab.count()):
			w=self.ui.chatTab.widget(i)
			if unicode(w.typ)=="groupchat":
				w.chat.ui.line.setEnabled(True)
				#message=self.main.skin["status_message"].replace("[time]",self.main.now()).replace("[message]",self.tr("You are now online."))
				message=self.main.webkitThemeFactory.genGroupchatStatus(unicode(self.tr("You are now online.")),self.main.now())
				w.chat.textEditWrite(message)
				self.main.client.joinGC(w.jid, w.chat.nick,sendRooms=self.main.config['sendRooms']=="True")

	def onGCMessage(self,w,i,body,delay,subject,user,xhtml):
		oldbody=body
		if xhtml:
			body=xhtml
			body=body.replace("  ","&nbsp;&nbsp;").replace("\t","&nbsp;&nbsp;&nbsp;")
		body=body.replace(' '+unicode(w.chat.nick)+' '," <b>"+unicode(w.chat.nick)+"</b> ")
		countMessage=False
		if int(self.ui.chatTab.currentIndex())!=i:
			if self.ui.chatTab.tabBar().tabTextColor(i).name()!=QtGui.QColor(255,0,0).name():
				self.ui.chatTab.setTabIcon(i,QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/message.png"))
				self.ui.chatTab.tabBar().setTabTextColor(i,QtGui.QColor(0,128,0))
			self.main.chat.ui.chatTab.setTabText(i,"("+unicode(w.chat.unread+1)+") "+w.tabName)
			countMessage=True
		if not self.main.chat.isActiveWindow():
			self.main.chat.setWindowTitle("("+unicode(int(self.getUnreadMessages())+1)+") "+w.tabName.replace("&",""))
			countMessage=True
		# set room topic
		if subject!=None:
			w.chat.changeTopic(unicode(subject))
			#w.chat.ui.info.setCursorPosition(0)

		# get truejid
		if self.main.client.groupchats[w.jid].users.has_key(user):
			truejid = self.main.client.groupchats[w.jid].users[user].truejid
			if truejid:
				truejid=unicode(jidT.JID(truejid).userhost())
		else:
			truejid = None

		file = None
		#print self.main.client.avatars
		if self.main.avatarDef.has_key(w.jid+'/'+user):
			file = self.main.realHomeDir+'/avatars/'+str(self.main.avatarDef[w.jid+'/'+user])
		elif truejid != None and self.main.avatarDef.has_key(truejid):
			file = self.main.realHomeDir+'/avatars/'+str(self.main.avatarDef[truejid])
		else:
			#self.getVCard(frm+'/'+user) #tohle asi neni potreba
			pass

		if not os.path.isfile(unicode(file)):
			print truejid, w.jid, user
			#sef@njs.netlab.cz/Doma jabber@conf.netlab.cz Sef
			file = RESOURCEPATH+ u"/images/32x32/apps/jabbim.png"
		if unicode(user)==unicode(w.jid):
			file = RESOURCEPATH+ u"/images/32x32/categories/conferences.png"
		cIndex=None
		if len(w.chat.getUserItems(user))!=0:
			item=w.chat.getUserItems(user)[0]
			if item in w.chat.colors:
				cIndex=w.chat.colors.index(item)

		# no delay message
		if delay==None:
			# it's our message
			if unicode(w.chat.nick)==unicode(user):
				if w.chat.lastMessageFrom==unicode(user):
					insert=True
					message=self.main.webkitThemeFactory.genGroupchatOutgoingNextContent(user,body,self.main.now(),file)
				else:
					insert=False
					message=self.main.webkitThemeFactory.genGroupchatOutgoingContent(user,body,self.main.now(),file)
				w.chat.appendLastMessage(["out",user,body,self.main.now(),file])
			else:
				w.chat.appendLastMessage(["in",user,body,self.main.now(),file])
				print 'groupchatMessageEvent'
				self.main.client.dispatcher.publishEvent('groupchatMessageEvent', self.main.getJid(w.jid),user,oldbody,subject, xhtml)
				# it's message for us
				if utils.need_highlight(unicode(w.chat.nick), unicode(oldbody)):
					print 'groupchatMessageForMeEvent'
					self.main.client.dispatcher.publishEvent('groupchatMessageForMeEvent', self.main.getJid(w.jid),user,oldbody,subject, xhtml)
					if int(self.ui.chatTab.currentIndex())!=i:
						if self.ui.chatTab.tabBar().tabTextColor(i).name()!=QtGui.QColor(255,0,0).name():
							self.ui.chatTab.setTabIcon(i,QtGui.QIcon(RESOURCEPATH+"images/16x16/actions/message.png"))
							self.ui.chatTab.tabBar().setTabTextColor(i,QtGui.QColor(255,0,0))
					if w.chat.lastMessageFrom==unicode(user):
						insert=True
						message=self.main.webkitThemeFactory.genGroupchatIncomingNextContent(user,body,self.main.now(),file,cIndex,"highlight")
					else:
						insert=False
						message=self.main.webkitThemeFactory.genGroupchatIncomingContent(user,body,self.main.now(),file,cIndex,"highlight")
				else:
					if w.chat.lastMessageFrom==unicode(user):
						insert=True
						message=self.main.webkitThemeFactory.genGroupchatIncomingNextContent(user,body,self.main.now(),file,cIndex)
					else:
						insert=False
						message=self.main.webkitThemeFactory.genGroupchatIncomingContent(user,body,self.main.now(),file,cIndex)
			if countMessage:
				w.chat.unread+=1
			w.chat.textEditWrite(message,insert)
			w.chat.lastMessageFrom=unicode(user)
			return
		else:
			delay=time.strftime('%Y-%m-%d&nbsp;%H:%M:%S', time.localtime(delay))
			# our delayed message
			if utils.need_highlight(unicode(w.chat.nick), unicode(body)):
				highlight="highlight"
			else:
				highlight=""
			if unicode(w.chat.nick)==unicode(user):
				w.chat.appendLastMessage(["out",user,body,delay,file])
				#message=self.main.skin["my_message_history"].replace("[time]",delay).replace("[user]",user).replace("[message]",unicode(body))
				if w.chat.lastMessageFrom==unicode(user):
					insert=True
					message=self.main.webkitThemeFactory.genGroupchatOutgoingNextContent(user,body,delay,file,cIndex)
				else:
					insert=False
					message=self.main.webkitThemeFactory.genGroupchatOutgoingContent(user,body,delay,file,cIndex)
			else:
				w.chat.appendLastMessage(["in",user,body,delay,file])
				if w.chat.lastMessageFrom==unicode(user):
					insert=True
					message=self.main.webkitThemeFactory.genGroupchatIncomingNextContent(user,body,delay,file,cIndex,highlight)
				else:
					insert=False
					message=self.main.webkitThemeFactory.genGroupchatIncomingContent(user,body,delay,file,cIndex,highlight)
			w.chat.lastMessageFrom=unicode(user)

			w.chat.textEditWrite(message,insert)


	def addChatTab(self,jid,name,icon,new=None,full=False):
		#for i in range(self.ui.chatTab.count()):
			#w=self.ui.chatTab.widget(i)
			#try:
				#tabjid=w.jid
			#except:
				#tabjid=""
			#if tabjid==jid:
		if full:
			print "finding",jid
			tab,index=self.findTab(jid,full)
			print tab
		else:
			print "finding",jid
			tab,index=self.findTab(jid,None)
			print tab
		if tab:
			self.show()
			self.raise_()
			self.activateWindow()
			tab.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
			self.ui.chatTab.setCurrentIndex(index)
			return tab
		item=self.main.ui.roster.getUserItems(jidT.JID(jid).userhost())
		metaitem=self.main.ui.roster.getMetaItems(jidT.JID(jid).userhost())

		tab=QtGui.QWidget(self.ui.chatTab)
		tab.jid=jid
		tab.typ="chat"
		tab.ic=icon
		tab.active=True
		layout=QtGui.QHBoxLayout(tab)
		layout.setMargin(1)
		layout.setSpacing(1)
		tab.chat=chatWidget(self.main,jid,tab,name)
		it=[]
		result=self.main.getAvatar(self.main.getJid(unicode(jid)).userhost(),size="64x64",frame=True)
		if not result:
			result=self.main.getAvatar(self.main.getJid(unicode(jid)).full(),size="64x64",frame=True)
			if not result:
				result=self.main.getAvatar(QtGui.QPixmap(RESOURCEPATH+"images/48x48/apps/jabbim.png"),size="64x64",frame=True)
		tab.chat.ui.avatar.setPixmap(result)


		layout.addWidget(tab.chat)
		print "adding new tab...", icon
		tab.tabName=unicode("&"+unicode(name))
		self.ui.chatTab.addTab(tab,icon,"&"+unicode(name))
		if new:
			if not self.isActiveWindow() or self.windowState() & QtCore.Qt.WindowMinimized:
				self.startFlash()
		else:
			self.ui.chatTab.setCurrentIndex(self.ui.chatTab.indexOf(tab))
			self.setWindowTitle(unicode(name))
			self.setWindowIcon(icon)
			tab.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		tab.chat.name=name
		tab.chat.refreshLabel()

		return tab

	def addGroupChatTab(self,room,nickname,affiliation="",name=None):
		for i in range(self.ui.chatTab.count()):
			w=self.ui.chatTab.widget(i)
			try:
				tabjid=w.jid
			except:
				tabjid=""
			if w.jid==room:
				self.show()
				self.raise_()
				self.activateWindow()
				w.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
				self.ui.chatTab.setCurrentIndex(i)
				return False
		tab=QtGui.QWidget(self.ui.chatTab)
		tab.jid=room
		tab.name=unicode(nickname)
		tab.typ="groupchat"
		layout=QtGui.QHBoxLayout(tab)
		layout.setMargin(1)
		layout.setSpacing(1)
		tab.chat=groupChatWidget(self.main,room,tab,nickname)
		# splitter size
		tab.chat.ui.splitter.setSizes([800,64])
		tab.chat.ui.splitter_2.setSizes(list(self.main.config['groupchatSplitSizes2']))
		tab.chat.ui.splitter_3.setSizes(list(self.main.config['groupchatSplitSizes3']))
		#tab.chat.ui.admin.hide()
		layout.addWidget(tab.chat)
		jmeno = room
		if unicode(self.main.config["useMUCNames"])=="True":
			for nick, bookmark  in self.main.client.bookmarks['conference'].iteritems():
				if bookmark.jid.userhost() == room:
					jmeno = bookmark.name
		if name:
			jmeno=name
		if len(jmeno)>22:
			jmeno=jmeno[:22]+"..."
		tab.tabName=unicode(jmeno)
		self.ui.chatTab.addTab(tab,QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/muc.png"), jmeno)
		self.setWindowTitle(unicode(jmeno))
		self.ui.chatTab.setCurrentIndex(self.ui.chatTab.indexOf(tab))

		self.show()
		self.raise_()
		self.activateWindow()
		tab.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
		tab.chat.showConnecting()
		return True

	def addCustomTab(self,jid,nickname,name,widget,widgetList,typ="chat",full=False,icon=None):
		if full:
			tab,index=self.findTab(jid,full)
		else:
			tab,index=self.findTab(jid,None)
		if tab:
			self.show()
			self.raise_()
			self.activateWindow()
			#tab.chat.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
			#self.ui.chatTab.setCurrentIndex(index)
			return tab
		if not icon:
			icon=QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/muc.png")
		tab=QtGui.QWidget(self.ui.chatTab)
		tab.jid=jid
		tab.typ=typ
		tab.ic=icon
		tab.active=True
		tab.name=nickname
		layout=QtGui.QHBoxLayout(tab)
		layout.setMargin(1)
		layout.setSpacing(1)
		tab.chat=widget(*widgetList)

		layout.addWidget(tab.chat)
		print "adding new custom tab", icon
		tab.tabName=unicode("&"+unicode(name))
		self.ui.chatTab.addTab(tab,icon,"&"+unicode(name))
		self.setWindowTitle(unicode(name))

		return tab

	def closeEvent(self,e):
		ask=False
		for i in range(self.ui.chatTab.count()):
			w=self.ui.chatTab.widget(i)
			if unicode(w.typ)=='groupchat':
				ask=True
				break

		if ask and self.main.config["askBeforeQuitMUC"]=="True" and self.main.app.shutdown==False:
			d=leaveAllMucDialog(self.main,self)
			if d.exec_()==1:
				for index in range(self.ui.chatTab.count()):
					self.removeTab(0,ask=False)
				e.accept()
			else:
				e.ignore()
		else:
			for index in range(self.ui.chatTab.count()):
				self.removeTab(0,ask=False)
			e.accept()

	def removeTab(self,index=None,ask=True):
		if index==None:
			index=self.ui.chatTab.currentIndex()
		w=self.ui.chatTab.widget(index)
		if w.typ=="chat":
			print w.chat.ui.splitter.sizes()
			self.main.config['chatSplitterSizes']=list(w.chat.ui.splitter.sizes())
			#self.main.config['chatSplitter2Sizes']=list(w.chat.ui.splitter_2.sizes())
			self.main.client.sendMessage(unicode(w.jid),"",composing="gone")


		if w.typ=="groupchat":
			try:
				self.main.config['groupchatSplitSizes3']=list(w.chat.ui.splitter_3.sizes())
				self.main.config['groupchatSplitSizes1']=list(w.chat.ui.splitter.sizes())
				self.main.config['groupchatSplitSizes2']=list(w.chat.ui.splitter_2.sizes())
			except:
				pass
		w.chat.on_remove()
		removed=False
		if unicode(w.typ)=="groupchat" and self.main.client!=None:
			print self.main.config["askBeforeQuitMUC"]
			if ask and self.main.config["askBeforeQuitMUC"]=="True" and self.main.app.shutdown==False:
				d=leaveMucDialog(self.main,w.jid,self)
				if d.exec_()==1:
					if self.main.client.groupchats.has_key(w.jid):
						self.main.client.leaveGC(w.jid)
					self.ui.chatTab.removeTab(index)
					if int(self.ui.chatTab.count())==0:
						self.hide()
					removed=True
			else:
				if self.main.client.groupchats.has_key(w.jid):
					self.main.client.leaveGC(w.jid)
				self.ui.chatTab.removeTab(index)
				if int(self.ui.chatTab.count())==0:
					self.hide()
				removed=True
		else:
			self.ui.chatTab.removeTab(index)
			if int(self.ui.chatTab.count())==0:
				self.hide()
			removed=True
		if removed:
			w.deleteLater()
			w.setParent(None)
			w.close()
			w.chat.parent=None
			w.chat.main=None
