from PyQt4 import QtCore, QtGui
import sys
import os
sys.path.append('.')
from include import plugins, utils
import time
from twisted.words.protocols.jabber import jid as jidT

class osd(QtGui.QWidget):
	def __init__(self,main,parent=None):
		QtGui.QWidget.__init__(self,parent,QtCore.Qt.ToolTip | QtCore.Qt.X11BypassWindowManagerHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint | QtCore.Qt.CustomizeWindowHint)
		self.timer=QtCore.QTimer()
		self.timer.setSingleShot(True)
		QtCore.QObject.connect(self.timer,QtCore.SIGNAL("timeout()"),self.hide)
		self.main=main

		self.setFontSize()
		self.text=""
		self.smallText=""
		self.desktop=QtGui.QPixmap()
		self.leftPixmap=None
		self.started=int(time.time())
		self.lastPresence=self.started;
		self.changingPos=False
		self.osdX=int(self.main.config['osd_x'])
		self.osdY=int(self.main.config['osd_y'])
		g=QtGui.QApplication.desktop().screenGeometry()
		self.screenWidth=int(g.width())
		self.screenHeight=int(g.height())

		self.event=None

	def setFontSize(self):
		font=QtGui.QApplication.fontMetrics()
		self.f=QtGui.QApplication.font()
		self.f.setPixelSize(int(self.main.config['osd_bigfont']))
		self.f.setBold(True)

		self.f2=QtGui.QApplication.font()
		self.f2.setPixelSize(int(self.main.config['osd_smallfont']))
		self.f2.setBold(True)


	def paintEvent(self,event):
		painter=QtGui.QPainter(self)
		painter.setClipping(True)
		#rect=event.region().rects()[0]
		painter.fillRect(0,0,self.width(),self.height(),QtGui.QBrush(QtGui.QColor(0,0,0)))

		
		if self.main.config['osd_transparent']!="True":
			g=QtGui.QLinearGradient(QtCore.QPointF(100, 100),QtCore.QPointF(200, 200))
			g.setColorAt(0,self.palette().color(QtGui.QPalette.Active,QtGui.QPalette.Highlight))
			c=self.palette().color(QtGui.QPalette.Active,QtGui.QPalette.Highlight)
			try:
				g.setColorAt(1,c.lighter())
			except:
				g.setColorAt(1,c.light())
			painter.fillRect(1,1,self.width()-2,self.height()-2,QtGui.QBrush(g))
		else:
			painter.drawPixmap(1,1,self.desktop,self.osdX+1,self.osdY+1,self.width()-2,self.height()-2)
			c=self.palette().color(QtGui.QPalette.Active,QtGui.QPalette.Highlight)
			c.setAlpha(200)
			painter.fillRect(1,1,self.width()-2,self.height()-2,QtGui.QBrush(c))
		
		p=painter.pen()
		painter.setPen(QtGui.QPen(self.palette().color(QtGui.QPalette.Active,QtGui.QPalette.HighlightedText)))
		painter.setFont(self.f)
		metrics=QtGui.QFontMetrics(self.f)
		height=int(metrics.height())
		
		bigpart=int((float(self.height())/float(int(self.main.config['osd_bigfont'])+self.smallTextHeight))*int(self.main.config['osd_bigfont']))
		smallpart=int((float(self.height())/float(int(self.main.config['osd_bigfont'])+self.smallTextHeight))*self.smallTextHeight)
		
		if self.leftPixmap:
			if self.smallText:
				painter.setFont(self.f)
				painter.drawText(QtCore.QRectF(65,0,self.width()-70,bigpart),QtCore.Qt.AlignCenter,self.text)
				painter.setFont(self.f2)
				painter.drawText(QtCore.QRectF(65,bigpart,self.width()-70,smallpart-5),QtCore.Qt.AlignCenter|QtCore.Qt.TextWordWrap,self.smallText)
			else:
				painter.drawText(QtCore.QRectF(65,0,self.width()-70,self.height()),QtCore.Qt.AlignCenter,self.text)
			painter.drawPixmap(0,0,self.leftPixmap)
		else:
			if self.smallText:
				painter.setFont(self.f)
				painter.drawText(QtCore.QRectF(0,0,self.width(),bigpart),QtCore.Qt.AlignCenter,self.text)
				painter.setFont(self.f2)
				painter.drawText(QtCore.QRectF(0,bigpart,self.width(),smallpart-5),QtCore.Qt.AlignCenter|QtCore.Qt.TextWordWrap,self.smallText)
			else:
				painter.drawText(QtCore.QRectF(0,0,self.width(),self.height()),QtCore.Qt.AlignCenter,self.text)
		painter.setPen(p)

	def mousePressEvent(self, event):
		if self.changingPos:
			if event.button() == QtCore.Qt.LeftButton:
				self.dragPosition = event.globalPos() - self.frameGeometry().topLeft()
				event.accept()
		else:
			if event.button() != QtCore.Qt.LeftButton:
				if self.event():
					self.event().accept()
			self.hide()
			event.accept()
	
	def mouseMoveEvent(self, event):
		if event.buttons() == QtCore.Qt.LeftButton:
			self.move(event.globalPos() - self.dragPosition)
			event.accept()


	def pos(self,text="Notification test",headline="Notification test"):
		self.changingPos=True
		self.setMouseTracking(True)
		self.text=headline
		# get width and height of text
		metrics=QtGui.QFontMetrics(self.f)
		height=int(metrics.height())
		width=int(metrics.width(headline))
		
		metrics2=QtGui.QFontMetrics(self.f2)
		height2=int(metrics2.height())
		width2=int(metrics2.width(text))

		t=""

		if width2>width:
			x=0
			for word in text.split(' '):
				xx=int(metrics2.width(word))
				if x+xx>width+20-65:
					t+="\n"+word+" "
					x=0
				else:
					t+=word+" "
					x+=xx
		else:
			t=text
		height2=int(metrics2.height())*len(t.split("\n"))
		self.smallTextHeight=height2
		self.smallText=text
		self.desktop=QtGui.QPixmap()
		self.leftPixmap=None


		if height+height2<54:
			height=54
			height2=0
		osdx=int(self.main.config['osd_x'])
		osdy=int(self.main.config['osd_y'])
		self.osdX=osdx
		self.osdY=osdy
		if osdx+width+20>self.screenWidth:
			self.osdX=self.screenWidth-(width+20)-10
		if osdy+height+height2+10>self.screenHeight:
			self.osdY=self.screenHeight-(height+height2+10)-10
		self.setGeometry(self.osdX,self.osdY,width+20,height+height2+10)
		self.show()

	def view(self,leftPixmap,headline,text,event,neco=None):
		if not self.isHidden():
			return
		t=int(time.time())
		self.event=event
		if neco:
			self.event=None
		self.text=headline
		
		metrics=QtGui.QFontMetrics(self.f)
		height=int(metrics.height())
		width=int(metrics.width(headline))
		
		metrics2=QtGui.QFontMetrics(self.f2)
		height2=int(metrics2.height())
		width2=int(metrics2.width(text))

		t=""

		if leftPixmap:
			width+=64

		if width2>width:
			x=0
			for word in text.split(' '):
				xx=int(metrics2.width(word))
				if x+xx>width+20-65:
					t+="\n"+word+" "
					x=0
				else:
					t+=word+" "
					x+=xx
		else:
			t=text
		height2=int(metrics2.height())*len(t.split("\n"))
		self.smallTextHeight=height2
		self.smallText=text
		if self.main.config['osd_transparent']=="True":
			self.desktop=QtGui.QPixmap.grabWindow(QtGui.QApplication.desktop().winId())
		else:
			self.desktop=QtGui.QPixmap()
		self.leftPixmap=leftPixmap

		if height+height2<54:
			height=54
			height2=0
		osdx=int(self.main.config['osd_x'])
		osdy=int(self.main.config['osd_y'])
		self.osdX=osdx
		self.osdY=osdy
		if osdx+width+20>self.screenWidth:
			self.osdX=self.screenWidth-(width+20)-10
		if osdy+height+height2+10>self.screenHeight:
			self.osdY=self.screenHeight-(height+height2+10)-10
		self.setGeometry(self.osdX,self.osdY,width+20,height+height2+10)
		print 'show'
		self.show()
		self.timer.start(int(self.main.config['osd_time'])*1000)
		

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['tray_first_message']={'type':'boolean','label':self.main.tr("Notify on first message from user"),'value':'True','groupbox':self.main.tr('Tray icon'),'tab':self.main.tr("Tray Icon")}
		self.config['tray_muc_highlight']={'type':'boolean','label':self.main.tr("Notify if groupchat message contains your nickname"),'value':'True','groupbox':self.main.tr('Groupchat'),'tab':self.main.tr("OSD")}
		
		self.config['sound_login']={'type':'boolean','label':self.main.tr("Play sound on login"),'value':'True','groupbox':self.main.tr('Sounds'),'tab':self.main.tr("Sounds")}
		self.config['sound_first_message']={'type':'boolean','label':self.main.tr("Play sound on first message from user"),'value':'True','groupbox':self.main.tr('Sounds'),'tab':self.main.tr("Sounds")}
		self.config['sound_message']={'type':'boolean','label':self.main.tr("Play sound on other messages from user"),'value':'True','groupbox':self.main.tr('Sounds'),'tab':self.main.tr("Sounds")}
		self.config['sound_gc_message']={'type':'boolean','label':self.main.tr("Play sound if groupchat message contains your nickname"),'value':'True','groupbox':self.main.tr('Sounds'),'tab':self.main.tr("Sounds")}
		self.config['sound_presence']={'type':'boolean','label':self.main.tr("Play sound on new presence"),'value':'False','groupbox':self.main.tr('Sounds'),'tab':self.main.tr("Sounds")}
		self.config['sound_ft']={'type':'boolean','label':self.main.tr("Play sound on file transfer"),'value':'True','groupbox':self.main.tr('Sounds'),'tab':self.main.tr("Sounds")}

		self.config['osd_transparent']={'type':'boolean','label':self.main.tr("Use transparent background"),'value':'False','groupbox':self.main.tr('Global'),'tab':self.main.tr("OSD")}
		self.config['osd_time']={'type':'number-spin','label':self.main.tr("Display time (seconds):"),'value':'2','groupbox':self.main.tr('Global'),'tab':self.main.tr("OSD")}
		self.config['osd_first_message']={'type':'boolean','label':self.main.tr("Use OSD for first message"),'value':'True','groupbox':self.main.tr('Chat'),'tab':self.main.tr("OSD")}
		self.config['osd_on_message']={'type':'boolean','label':self.main.tr("Use OSD for other messages"),'value':'True','groupbox':self.main.tr('Chat'),'tab':self.main.tr("OSD")}
		self.config['osd_on_gcmessage']={'type':'boolean','label':self.main.tr("Use OSD for all conference messages"),'value':'False','groupbox':self.main.tr('Groupchat'),'tab':self.main.tr("OSD")}
		self.config['osd_x']={'type':'hidden','label':self.main.tr("Use OSD for presences"),'value':'10','groupbox':self.main.tr('Global'),'tab':self.main.tr("OSD")}
		self.config['osd_y']={'type':'hidden','label':self.main.tr("Use OSD for presences"),'value':'10','groupbox':self.main.tr('Global'),'tab':self.main.tr("OSD")}
		self.config['osd_bigfont']={'type':'number-spin','label':self.main.tr("Headline font size"),'value':'20','groupbox':self.main.tr('Global'),'tab':self.main.tr("OSD")}
		self.config['osd_smallfont']={'type':'number-spin','label':self.main.tr("Text font size"),'value':'11','groupbox':self.main.tr('Global'),'tab':self.main.tr("OSD")}
		self.config['osd_on_presence']={'type':'boolean','label':self.main.tr("Use OSD for presences"),'value':'False','groupbox':self.main.tr('Global'),'tab':self.main.tr("OSD")}

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'notification'
		self.installTranslator()
		self.description = self.tr('System tray and sound notification')
		self.author = "Jan 'HanzZ' Kaluza & Josef 'PepeQ' Halicek"
		self.name = self.tr('Notification Plugin')
		self.version = '0.690'
		self.category = ['notification']
		self.url = 'http://dev.jabbim.cz/jabbim'

		if sys.platform == 'win32':
			print "loading snarl support"
			self.snarl=self.loadModule(plugindir+"/PySnarl.py")
			if self.snarl.snGetVersion() == False:
				print "can't connect to snarl app"
				self.snarl=None
			else:
				print "snarl version:",self.snarl.snGetVersion()
		else:
			self.snarl=None
		self.configDialog=config(self)
		if self.snarl:
			self.configDialog.config['osd_transparent']['disabled']=True
			self.configDialog.config['osd_x']['disabled']=True
			self.configDialog.config['osd_y']['disabled']=True
			self.configDialog.config['osd_bigfont']['disabled']=True
			self.configDialog.config['osd_smallfont']['disabled']=True
		self.showInPreferences=True
		self.preferencesIcon=QtGui.QIcon(plugindir+"/audio.png")
		self.osd=None

		if main:
			self.started=int(time.time())
				#else:
					#self.snarl.snRegisterConfig2(int(self.main.winId()), "Jabbim",1025,os.getcwd()+"/images/32x32/apps/jabbim.png")
#					self.snarl.snRegisterAlert("Jabbim", unicode(self.tr("Presences")))
					#self.snarl.snRegisterAlert("Jabbim", unicode(self.tr("New first chat messages")))
#					self.snarl.snRegisterAlert("Jabbim", unicode(self.tr("Chat messages")))
					#self.snarl.snRegisterAlert("Jabbim", unicode(self.tr("Groupchat highlights")))
			#self.registerHandler('on_message', self.on_message)
			self.registerHandler('firstChatMessageEvent',self.on_firstChatMessageEvent)
			self.registerHandler('chatMessageEvent',self.on_chatMessageEvent)
			self.registerHandler('groupchatMessageEvent',self.on_groupchatMessageEvent)
			self.registerHandler('groupchatMessageForMeEvent',self.on_groupchatMessageForMeEvent)
			self.registerHandler('presenceEvent',self.on_presence)
			self.registerHandler('on_evil',self.on_evil)
			self.registerHandler('FTStartedEvent',self.on_FTStarted)
			self.registerHandler('FTFinishedEvent',self.on_FTFinished)
			self.loadConfig()
			if self.config['sound_login']=="True":
				self.main.resourceManager.playsound('start')
			self.osd=osd(self)
			self.registerWidget(self.osd)
			self.osd.osdx=int(self.config['osd_x'])
			self.osd.osdy=int(self.config['osd_y'])
			if self.config['osd_transparent']!="True":
				self.osd.transparent=False
			self.lastPresence=None;
			self.afterFirstPresenceTimeout=False;
		else:
			self.loadConfig(homedir)

	#def on_remove(self):
		#if self.snarl:
			#self.snarl.snRevokeConfig(int(self.main.winId()))
			
	def on_FTStarted(self,sid,el):
		if self.config['sound_ft']=='True':
			self.main.resourceManager.playsound('ft_start')
	
	def on_FTFinished(self,sid,error):
		if self.config['sound_ft']=='True':
			self.main.resourceManager.playsound('ft_finish')

	def on_showPreferences(self,dialog):
		if not self.snarl:
			if not self.osd:
				self.osd=osd(self,dialog)
				self.registerWidget(self.osd)
			self.osd.osdx=int(self.config['osd_x'])
			self.osd.osdy=int(self.config['osd_y'])
			self.osd.transparent=False
			self.osd.pos(self.tr("Notification test - can drag"))

	def on_endPreferences(self):
		if not self.snarl:
			if not self.main.client:
				self.unregisterWidget(self.osd)
				self.osd=None
			else:
				self.osd.hide()
	
	def on_saveConfig(self):
		if self.osd:
			rect=self.osd.geometry()
			x=int(rect.x())
			y=int(rect.y())
			self.config['osd_x']=str(x)
			self.config['osd_y']=str(y)
			if not self.main.client:
				self.unregisterWidget(self.osd)
				self.osd=None
			else:
				self.osd.hide()
				self.osd.setFontSize()

	def on_evil(self, frm, typ):
		jid = jidT.JID(frm)
		user=self.main.ui.roster.getUserItems(unicode(jid.userhost()))
		if len(user)==0:
			user=self.main.ui.roster.getMetaItems(jid.userhost())
			if len(user)!=0:
				user=user[0]
		if len(user)!=0:
			#user=self.roster['users'][unicode(frm).rsplit("/")[0]].rosterItems[0]
			it=user[0]
			user=user[0].name
			
		else:
			it=None
			user=unicode(jid.full())
		
		print 'EVIL PANIC!!!'
		pixmap=self.main.getAvatar(jid.userhost().replace('/','%'),frame=False,size="64x64")
		self.osd.view(pixmap,self.tr('WARNING!'),unicode('Evil '+typ+' from '+jid.userhost()),self.addChatTab,[it,jid])
		
	def on_presence(self,jid,user,show,status,first):
		if first or not self.isNotificationEnabled():
			return
		self.lastPresence=time.time();
		if not self.afterFirstPresenceTimeout and (time.time()>10+self.lastPresence):
			return
		self.afterFirstPresenceTimeout=True;
		if self.config['osd_on_presence']=="True":
			if not status:
				status=""
			if self.snarl:
				file=self.main.getAvatarSrc(jid.userhost())
				s = self.snarl.SnarlMessage(unicode(user)+unicode(self.tr(" is now "))+unicode(self.main.status[unicode(show)]),unicode(status))
				s.timeout=int(self.config['osd_time'])
				s.show(icon=file,replyWindow=int(self.main.winId()),replyMsg=1025)
				self.main.snarlMessages[int(s.getID())]=[self.addChatTab,[jid]]
			else:
				pixmap=self.main.getAvatar(jid.userhost(),frame=False,size="64x64")
				self.osd.view(pixmap,user+unicode(self.tr(" is now "))+self.main.status[unicode(show)],unicode(status),self.addChatTab,[jid])
		if self.config['sound_presence']=="True" and int(time.time())>self.main.connectStarted+30:
			if show=="offline":
				self.main.resourceManager.playsound("contact_offline")
			else:
				self.main.resourceManager.playsound("contact_online")

	def addChatTab(self,jid):
		item=self.main.ui.roster.getUserItems(jid.userhost())
		if item:
			item=item[0]
			res = self.main.client.roster['users'][item.jid].getHighestResource()
			
			if res==None:
				self.main.chat.addChatTab(item.jid,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
			else:
				self.main.chat.addChatTab(item.jid+"/"+res,item.name,self.main.getIcon(item.jid,self.main.icons[str(item.status)],size="16x16"))
		else:
			self.main.chat.addChatTab(jid.full(),jid.full(),self.main.getIcon(jid.userhost(),"offline",size="16x16"))
		self.main.chat.activate()

	def on_firstChatMessageEvent(self, msg,event=None):
		if msg.body == None or not self.isNotificationEnabled():
			return
		jid=msg.frm
		user=msg.user
		if msg.body.startswith('/me '):
			msg.body = msg.body.replace('/me', '*'+user)
		# cut message if it's too long
		if len(msg.body)>40:
				traytext=msg.body[:40]+" ..."
		else:
				traytext=msg.body
		if self.config['osd_first_message']=="True" and not self.main.chat.isActiveWindow():
			if self.snarl:
				file=self.main.getAvatarSrc(jid.userhost())
				s = self.snarl.SnarlMessage(unicode(self.tr("New message from "))+unicode(user),unicode(traytext))
				s.timeout=int(self.config['osd_time'])
				s.show(icon=file,replyWindow=int(self.main.winId()),replyMsg=1025)
				self.main.snarlMessages[int(s.getID())]=[event().accept,[]]
			else:
				# get avatar for OSD
				pixmap=self.main.getAvatar(jid.userhost(),frame=False,size="64x64")
				# inform user about newly opened tab
				self.osd.view(pixmap,unicode(self.tr("New message from "))+user,unicode(traytext),event)
		if self.config['sound_first_message']=="True":
			self.main.resourceManager.playsound('new_message')
		if self.config['tray_first_message']=='True':
			self.main.tray.showMessage(unicode(self.tr("New message from "))+unicode(user), traytext, QtGui.QSystemTrayIcon.Information, 4000)

	def on_chatMessageEvent(self,msg,event=None):
		if msg.body == None or not self.isNotificationEnabled():
			return
		jid=msg.frm
		user=msg.user
		if msg.body.startswith('/me '):
			msg.body = msg.body.replace('/me', '*'+user)
		# inform user about new message
		if self.config['osd_on_message']=="True" and not self.main.chat.isActiveWindow():
			if len(msg.body)>40:
				traytext=msg.body[:40]+" ..."
			else:
				traytext=msg.body
			if self.snarl:
				file=self.main.getAvatarSrc(jid.userhost())
				s = self.snarl.SnarlMessage(unicode(self.tr("New message from "))+unicode(user),unicode(traytext))
				s.timeout=int(self.config['osd_time'])
				s.show(icon=file,replyWindow=int(self.main.winId()),replyMsg=1025)
				self.main.snarlMessages[int(s.getID())]=[event().accept,[]]
			else:
				# get avatar for OSD
				pixmap=self.main.getAvatar(jid.userhost(),frame=False,size="64x64")
				# inform user about newly opened tab
				self.osd.view(pixmap,unicode(self.tr("New message from "))+user,unicode(traytext),event)
		if self.config['sound_message']=="True":
			self.main.resourceManager.playsound('message')
	
	def on_groupchatMessageEvent(self,frm,user,body,subject, xhtml):
		if body == None or not self.isNotificationEnabled():
			return
		jid=frm
		user=user
		if body.startswith('/me '):
			body = body.replace('/me', '*'+user)
		# inform user about new message
		if self.config['osd_on_gcmessage']=="True" and not self.main.chat.isActiveWindow():
			if len(body)>40:
				traytext=body[:40]+" ..."
			else:
				traytext=body
			if self.snarl:
				file=self.main.getAvatarSrc(jid.userhost())
				s = self.snarl.SnarlMessage(unicode(self.tr("New message from "))+unicode(user),unicode(traytext))
				s.timeout=int(self.config['osd_time'])
				s.show(icon=file,replyWindow=int(self.main.winId()),replyMsg=1025)
#				self.main.snarlMessages[int(s.getID())]=[event().accept,[]]
			else:
				# get avatar for OSD
				pixmap=self.main.getAvatar(jid.userhost(),frame=False,size="64x64")
				# inform user about newly opened tab
				self.osd.view(pixmap,unicode(self.tr("New message from "))+user,unicode(traytext), None)
		#if self.config['sound_gc_message']=="True":
			#self.main.resourceManager.playsound('message')
	
	def on_groupchatMessageForMeEvent(self,frm,user,body,subject, xhtml):
		if not self.isNotificationEnabled():
			return
		if body.startswith('/me '):
			body = body.replace('/me', '*'+user)
		if self.config['tray_muc_highlight']=="True" and not self.main.chat.isActiveWindow():
			if len(body)>40:
				text=body[:40]+" ..."
			else:
				text=body
			traytext=unicode(user)+": "+text
			if self.snarl:
				file=self.main.getAvatarSrc("jabbimicon")
				s = self.snarl.SnarlMessage(unicode(self.tr("New groupchat message for you")),unicode(traytext))
				s.timeout=int(self.config['osd_time'])
				s.show(icon=file,replyWindow=int(self.main.winId()),replyMsg=1025)
				#self.main.snarlMessages[int(s.getID())]=[self.main.events.getEventByID(eventID).accept,[]]
			else:
#				self.main.tray.showMessage(self.tr("New groupchat message for you"), traytext, QtGui.QSystemTrayIcon.Information, 4000)
				pixmap=self.main.getAvatar(frm.userhost()+"/"+user,frame=False,size="64x64")
				self.osd.view(pixmap,unicode(self.tr("New message from "))+user,unicode(traytext), None)

		if self.config['sound_gc_message']=="True":
			self.main.resourceManager.playsound('message')
