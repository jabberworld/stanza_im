import sys,os,time
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui, QtWebKit
from urllib import quote, unquote
from twisted.python import log
from configobj import ConfigObj
from twisted.internet import threads
from pyxl import jid as jidT
import traceback
from twisted.internet import reactor

class calendar(QtGui.QCalendarWidget):
	def __init__(self,parent):
		QtGui.QCalendarWidget.__init__(self,parent)
		self.dates=[]
		self.setFirstDayOfWeek(QtCore.Qt.Monday)

	def setDates(self,dates):
		self.dates=dates
		if len(self.dates)!=0:
			self.setSelectedDate(self.dates[-1].addMonths(1))
			self.setSelectedDate(self.dates[-1])
		#self.repaint()

	def _hide(self):
		if not self.focused:
			self.hide()

	def enterEvent(self,event):
		self.focused=True

	def leaveEvent(self,event):
		self.focused=False
		reactor.callLater(1,self._hide)

	def paintCell(self,painter,rect,date):
		#painter.save()
		#painter.translate(x,y)
		#painter.fillRect(rect,QtGui.QBrush(QtGui.QColor(255,0,0)))
		font=QtGui.QApplication.font()
		
		if not date in self.dates:
			painter.setFont(font)
			color=None
		else:
			font.setBold(True)
			painter.setFont(font)
			color=True
		if date==self.selectedDate():
			painter.fillRect(rect,QtGui.QBrush(self.palette().color(QtGui.QPalette.Highlight)))
			painter.setPen(self.palette().color(QtGui.QPalette.HighlightedText))
			painter.drawText(rect, QtCore.Qt.AlignCenter, str(date.day()))
		else:
			if int(date.month())==int(self.monthShown()):
				#painter.setPen(self.palette().color(QtGui.QPalette.Highlight))
				if color:
					painter.fillRect(rect,QtGui.QBrush(self.palette().color(QtGui.QPalette.AlternateBase)))
				painter.setPen(self.palette().color(QtGui.QPalette.Text))
				painter.drawText(rect, QtCore.Qt.AlignCenter, str(date.day()))
			else:
				painter.setPen(self.palette().color(QtGui.QPalette.Disabled,QtGui.QPalette.Text))
				painter.drawText(rect, QtCore.Qt.AlignCenter, str(date.day()))
				
		#painter.restore()
		#QtGui.QCalendarWidget.paintCell(self,painter,rect,date)


class FileBackend:
	def __init__(self,archive):
		#self.archive=archive
		pass
		
	def userChanged(self,archive):
		self.homeDir=unicode(archive.main.homeDir)
		self.jid=archive.jid

		if not os.path.isdir(self.homeDir+'/archive'):
			os.mkdir(self.homeDir+'/archive')

		if not os.path.isdir(self.homeDir+'/archive/'+self.jid):
			os.mkdir(self.homeDir+'/archive/'+self.jid)

		self.convertOldHistoryFiles()

	def getJidList(self):
		"""
		Returns list of jids which are archived.
		@rtype: list of unicode
		@return: list of JabberIDs
		"""
		return os.listdir(self.homeDir+'/archive/'+self.jid)

	def saveMessage(self, to, body, typ, subject, xhtml, direction):
		jid = to.userhost()
		# get local time
		t=time.time()
		# get date in format YYYY-MM-DD
		d=time.localtime(t)
		dat=str(d[0])+"-"+str(d[1])+"-"+str(d[2])
		# open history file or create it
		try:
			fp = open(self.homeDir+'/archive/'+self.jid+'/'+jid+'/'+dat+'.history', 'a')
		except:
			os.mkdir(self.homeDir+'/archive/'+self.jid+'/'+jid)
			fp = open(self.homeDir+'/archive/'+self.jid+'/'+jid+'/'+dat+'.history', 'a')
	
		# prepare message to be saved
		if xhtml != None:
			telo = xhtml.replace('|', '&#124;').replace("\n","<br/>")
		else:
			telo = body.replace('|', '&#124;').replace("\n","<br/>") 
		# saves only user name (resource) for groupchats, because userhost is the same as MUC JID
		if typ=="groupchat" and to.resource:
			jid=to.resource
		# prepare subject to be saved
		if subject==None:
			subject=""
		else:
			subject=subject.replace('|', '&#124;').replace("\n","<br/>")
		# save message
		msg = '|'.join([unicode(t), direction, jid, typ, unicode(subject), telo])
		msg = msg.encode('utf8')
		fp.write(msg+'\n')
		fp.close()
		print "message saved",to,typ,direction

	def getDates(self,jid):
		"""
		Returns list of dates in YYYY-MM-DD format
		"""
		ret=[]
		for file in os.listdir(self.homeDir+'/archive/'+self.jid+'/'+jid):
			if file.split('.')[1]=="history":
				dat=file.split('.')[0]
				ret.append(dat)
		return ret

	def findText(self,jid,text):
		dates=self.getDates(jid)
		if len(dates)==0:
			return {}
		ret={} #: {date:[[timestamp,direction,from,message],]}
		for date in dates:
			# open history file
			try:
				fp = open(self.homeDir+'/archive/'+self.jid+'/'+jid+'/'+date+'.history')
			except:
				log.err('no history file')
				continue
			for msg in fp.xreadlines():
				parsed=msg.split('|')
				if unicode(parsed[5],"utf8").find(text)!=-1:
					if not ret.has_key(date):
						ret[date]=[]
					ret[date].append([float(parsed[0]),str(parsed[1]),unicode(parsed[2],"utf8"),unicode(parsed[5],"utf8").replace('<', '&lt;')])
			fp.close()
		return ret

	def getMessages(self,jid,date,maxTime=None):
		# open history file
		try:
			fp = open(self.homeDir+'/archive/'+self.jid+'/'+jid+'/'+date+'.history')
		except:
			log.err('no history file')
			return None
		ret=[] #: [timestamp,direction,from,message]
		# if there is no maxTime, we can return all messages
		if not maxTime:
			for msg in fp.xreadlines():
				parsed=msg.split('|')
				ret.append([float(parsed[0]),str(parsed[1]),unicode(parsed[2],"utf8"),unicode(parsed[5],"utf8").replace('<', '&lt;')])
		# return only messages which is younger that maxTime
		else:
			maxTime=maxTime.split(":") # [20,0,0]
			now=time.localtime()
			for msg in fp.xreadlines():
				parsed=msg.split('|')
				d=time.localtime(float(parsed[0]))
				#html+=action[5].replace("[time]",str(d[3])+":"+str(d[4])+":"+str(d[5]))
				intervalHour=abs(int(d[3])-int(now[3])) # 20
				intervalMin=abs(int(d[4])-int(now[4])) # 2
				intervalSec=abs(int(d[5])-int(now[5]))
				if intervalHour<int(maxTime[0]):
					ret.append([float(parsed[0]),str(parsed[1]),unicode(parsed[2],"utf8"),unicode(parsed[5],"utf8").replace('<', '&lt;')])
				elif intervalHour<=int(maxTime[0]) and intervalMin<=int(maxTime[1]):
					ret.append([float(parsed[0]),str(parsed[1]),unicode(parsed[2],"utf8"),unicode(parsed[5],"utf8").replace('<', '&lt;')])
		fp.close()
		return ret

	def getLastMessages(self,jid,count,maxTime):
		# get dates
		dates=self.getDates(jid)
		if len(dates)==0:
			return ""
		# get newest date
		d=dates[0]
		print "MAXTIME",maxTime
		if maxTime=="0:0:0":
			# we have to find newest date
			newestStr=unicode(d)
			d=unicode(d).split('-')
			newest=QtCore.QDate(int(d[0]),int(d[1]),int(d[2]))
			for date in dates:
				d=unicode(date).split('-')
				d=QtCore.QDate(int(d[0]),int(d[1]),int(d[2]))
				if d>newest:
					newest=d
					newestStr=unicode(date)
			maxTime=None
		else:
			# we want only message from today, becase maxTime is not 0:0:0.
			d=time.localtime()
			newestStr=str(d[0])+"-"+str(d[1])+"-"+str(d[2])

		
		messages=self.getMessages(jid,newestStr,maxTime)
		if not messages:
			return []
		return messages[-count:]

	def convertOldHistoryFiles(self):
		# Convert old (URL-quoted JIDs) history directories to new-style. Merge files if both forms are present.

		quoted_dir_name = self.homeDir+'/archive/'+quote(self.jid)
		if not os.path.isdir(quoted_dir_name):
			return   # Nothing to convert

		try:
			for q in os.listdir(quoted_dir_name):
				old_dirname = quoted_dir_name+'/'+q
				new_dirname = self.homeDir+'/archive/'+self.jid+'/'+unicode(unquote(q))
				if not os.path.isdir(new_dirname):
					# For this JID we have old history only.
					os.mkdir(new_dirname)

				old_histories = os.listdir(old_dirname)
				new_histories = os.listdir(new_dirname)
				for file in old_histories:
					old_filename = old_dirname+'/'+file
					new_filename = new_dirname+'/'+file
					if file in new_histories:
						new_messages = open(new_filename).readlines()
					else:
						new_messages = []

					old_file = open(old_filename)
					# Merge the two files into one.
					merged_filename = new_filename + '.tmpmerge'
					merged_file = open(merged_filename, 'w')
					j = 0
					old_line = None
					old_eof = False
					while not old_eof or j < len(new_messages):
						if not old_eof and not old_line:
							try:
								parts = old_file.xreadlines().next().split('|')
								old_line = '|'.join([parts[0],parts[1],unquote(parts[2]),parts[3],parts[4],parts[5]])
							except StopIteration:
								old_eof = True
								continue

						if not old_eof and j < len(new_messages):
								new_line = new_messages[j]
								# compare message timestamps
								take_next_from_old = (float(parts[0]) < float(new_line.split('|')[0]))
						elif not old_eof:
							take_next_from_old = True
						else:
							new_line = new_messages[j]
							take_next_from_old = False

						if take_next_from_old:
							merged_file.write(old_line)
							old_line = None
						else:
							merged_file.write(new_line)
							j += 1
					merged_file.close()
					old_file.close()
					os.rename(merged_filename, new_filename)
					os.unlink(old_filename)

				# Everything for this JID has been moved away?
				if os.listdir(old_dirname) == []:
					os.rmdir(old_dirname)

			# Everything moved successfully? Remove the old dir completely then.
			if os.listdir(quoted_dir_name) == []:
				os.rmdir(quoted_dir_name)
		except Exception, ex:
			log.msg('convertOldHistoryFiles failure: ' + str(ex))

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['messagesNumber']={'type':'number-spin','label':self.main.tr("Number of last messages shown:"),'value':'5'}
		self.config['messagesTime']={'type':'time-interval','label':self.main.tr("Don't show messages older than:"),'value':'1:0:0'}

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'archive'
		self.installTranslator()
		self.description = self.tr('Message Archiving')
		self.author = "Jiri 'Sef' Gabrys"
		self.name = self.tr('Archive Plugin')
		self.version = '0.197'
		self.category = ['archive']
		self.url = 'http://dev.jabbim.cz/jabbim'

		self.configDialog=config(self)


		if main:
			self.loadConfig(homedir)

			self.registerHandler('firstChatMessageEvent',self.on_firstChatMessageEvent)
			self.registerHandler('chatMessageEvent',self.on_chatMessageEvent)
			self.registerHandler('groupchatMessageEvent',self.on_groupchatMessageEvent)
			self.registerHandler('on_message_send', self.on_message_send)
			self.loadConfig()
			self.window = self.loadWindow("%s/historyBrowser_ui.py" % self.pluginDir, self.main)
			self.window.setWindowIcon(self.main.windowIcon())
			self.window.ui.text.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
			#layout=QtGui.QHBoxLayout(self.window.ui.calendarWidget)
			self.window.ui.calendar=calendar(self.window)
			self.window.ui.calendar.hide()
			self.registerWidget(self.window.ui.calendar)
			#layout.addWidget(self.window.ui.calendar)
			#log.msg(unicode(dir(self.window)))
			#QtCore.QObject.connect(self.window.ui.seznam, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem * , int ) "),self.itemClicked)
			QtCore.QObject.connect(self.window.ui.seznam, QtCore.SIGNAL("activated ( int) "),self.itemClicked)
			#QtCore.QObject.connect(self.window.ui.searchList, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem * , int ) "),self.searchListClicked)
			QtCore.QObject.connect(self.window.ui.calendar, QtCore.SIGNAL("selectionChanged()"),self.calChanged)
			QtCore.QObject.connect(self.window.ui.search, QtCore.SIGNAL("clicked()"),self.searchClicked)
			QtCore.QObject.connect(self.window.ui.searchText, QtCore.SIGNAL("returnPressed ()"),self.searchClicked)
			QtCore.QObject.connect(self.window.ui.today, QtCore.SIGNAL("clicked()"),self.todayClicked)
			QtCore.QObject.connect(self.window.ui.dateEdit,QtCore.SIGNAL("dateChanged ( const QDate & )"),self.dateChanged)
			QtCore.QObject.connect(self.window.ui.text,QtCore.SIGNAL("linkClicked ( const QUrl &)"),self.webkitLinkClicked)
			short=QtGui.QShortcut("ctrl+c",self.window.ui.text)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.copySelectedText)  # adapted from webkitchatwidget.py
			#self.window.ui.searchList.hide()
			#self.window.ui.search.hide()
			#self.window.ui.searchText.hide()
			self.group=QtGui.QButtonGroup(self.window)
			QtCore.QObject.connect(self.group,QtCore.SIGNAL("buttonClicked ( QAbstractButton * )"),self.buttonClicked)
			self.skin=self.getConfig("%s/gajim.cfg" % self.pluginDir)
			self.skin=self.skin['chatskin']
			self.backend=FileBackend(self)
			#self.window.ui.seznam.header().hide()
			
			self.window.ui.dateEdit.enterEvent=self.dateEditEnterEvent

		else:
			self.loadConfig(homedir)

	def copySelectedText(self):
		text=self.window.ui.text.selectedText()
		if len(text)!=0:
			QtGui.QApplication.clipboard().setText(unicode(text))

	def webkitLinkClicked(self,url):
		# url = http://jid/date
		u = unicode(url.toString())
		print u
		jid = unicode(u.split('/')[2])
		date = unicode(u.split('/')[3]).split('-')
		self.window.ui.dateEdit.setDate(QtCore.QDate(int(date[0]),int(date[1]),int(date[2])))
		#self.window.ui.calendar.setSelectedDate(QtCore.QDate(int(date[0]),int(date[1]),int(date[2])))
		self.itemClicked(self.window.ui.seznam.currentIndex(),setDate=False,highlight=unicode(self.window.ui.searchText.text()))

	def dateEditEnterEvent(self,event):
		point=self.window.ui.dateEdit.mapTo(self.window,QtCore.QPoint(0,self.window.ui.dateEdit.height()))
		self.window.ui.calendar.setGeometry(point.x(),point.y(),200,120)
		self.window.ui.calendar.show()
		self.window.ui.calendar.leaveEvent(None)

	def userChanged(self,jid):
		plugins.PluginBase.userChanged(self,jid)
		self.jid = unicode(jid)
		self.backend.userChanged(self)
		self.jidList=self.backend.getJidList()

	def searchClicked(self):
		text=unicode(self.window.ui.searchText.text())
		if len(text)==0:
			return
		item=self.window.ui.seznam.currentIndex()
		if item==-1:
			return
		jid = unicode(self.window.ui.seznam.itemData(item).toString())

		d=threads.deferToThread(self.searchText,jid,text,self.window.palette().color(QtGui.QPalette.HighlightedText).name(),self.window.palette().color(QtGui.QPalette.Highlight).name())
		d.addCallback(self.gotSearchedText,jid)
	
	def todayClicked(self):
		self.window.ui.dateEdit.setDate(QtCore.QDate.currentDate())

	def searchText(self,jid,text,fg,bg):
		data=self.backend.findText(jid,text) #{date:[[timestamp,direction,from,message],]}
		print data
		html="<table>"
		for date in data.keys():
			for i in range(len(data[date])):
				#index=data[date][i][3].find(text)
				#if index!=-1:
					#start=index-20
					#sText="..."
					#if start<0:
						#start=0
						#sText=""
					#end=index+20
					#eText="..."
					#if end>len(data[date][i][3]):
						#end=len(data[date][i][3])
						#eText=""
					#data[date][i][3]=sText+data[date][i][3][start:end]+eText
					#text=sText+data[date][i][3][start:end]+eText
				text=data[date][i][3]
				_tmp=date.split("-")
				d=unicode(QtCore.QDate(int(_tmp[0]),int(_tmp[1]),int(_tmp[2])).toString("dd.MM.yyyy"))
				html+='<tr><td><a style="margin-right:20px;" href="http://%s/%s">%s</a></td><td>%s</td></tr>' % (jid,date,d,text)
		html+="</table>"
		return html

	def gotSearchedText(self,data,jid):
		#print jid,data
		#self.window.ui.searchList.clear()
		#for date,items in data.iteritems():
			#for item in items:
				
				#i=QtGui.QTreeWidgetItem(self.window.ui.searchList)
				#i.setText(0,date)
				#i.setText(1,item[3])
				#i.jid=jid
				#i.highlight=unicode(self.window.ui.searchText.text())
		#self.window.ui.searchList.sortItems(0,QtCore.Qt.AscendingOrder)
		#self.window.ui.searchList.show()
		self.window.ui.text.setHtml(data)
		#self.window.ui.searchText.setText("")

	def searchListClicked(self,item,index):
		date=unicode(item.text(0)).split("-")
		jid=item.jid
		self.window.ui.calendar.setSelectedDate(QtCore.QDate(int(date[0]),int(date[1]),int(date[2])))
		self.itemClicked(self.window.ui.seznam.currentItem(),setDate=False,highlight=item.highlight)

	def buildMainWindowMenu(self):
		"""
		Builds menu for Jabbim MainWindow
		"""
		menu=self.mainWindowMenu()
		menu.addAction("Archive browser",self.showSlot)
	
	def buildContactMenu(self,menu,contact):
		"""
		Adds QAction to the menu above contact 
		"""
		if unicode(contact.jid) in self.jidList:
			self.action=menu.addAction(self.tr("History"))
			self.action.setData(QtCore.QVariant(unicode(contact.jid)))
			self.action.setObjectName("history")
			self.action.setIcon(QtGui.QIcon("%s/history.png" % self.pluginDir))
			QtCore.QObject.connect(self.action,QtCore.SIGNAL("triggered ( bool )"),self.contactMenuToggled)
	
	def contactMenuToggled(self,b):
		"""
		User choose our QAction from contactMenu (menu above contact)
		"""
		jid=unicode(self.action.data().toString())
		self.showSlot(jid)
		self.action.deleteLater()
	
	def buttonClicked(self,button):
		"""
		Handles buttons from chatWidgets
		"""
		print 'button clicked'
		jid=button.jid
		self.showSlot(jid)

	def buildChatWidget(self,jid,layout,widget):
		jid=self.main.getJid(jid)
		# create Archive button
		button=QtGui.QPushButton()
		button.setIconSize(QtCore.QSize(16,16))
		button.setIcon(QtGui.QIcon("%s/history.png" % self.pluginDir))
		button.jid=unicode(jid.userhost())
		button.setToolTip("History")
		#button.setText(self.tr("History"))
		# add button to buttonGroup
		self.group.addButton(button)
		layout.addWidget(button)
		
		if os.path.isdir(self.main.homeDir+'/archive/'+self.jid+'/'+unicode(jid.userhost())):
			# get user names
			me=unicode(self.main.client.jid.user)
			user=self.main.ui.roster.getNameByJID(jid.userhost())

			# get user avatars
			avatar=widget.file
			selfavatar=widget.selfFile

			jid=unicode(jid.userhost())
			# call getLastMessages in thread
			d=threads.deferToThread(self.getLastMessages,jid,int(self.config['messagesNumber']),self.config['messagesTime'])
			d.addCallback(self.gotLastMessages,widget,me,user,selfavatar,avatar)

	def getLastMessages(self,jid,count,maxTime):
		"""
		Returns last X xhtml formated messages from contact. Called in thread by buildChatWidget.
		"""
		#action=["",jid,count,me,user,my_message,message,color,avatar]
		# get last messages
		messages=self.backend.getLastMessages(jid,count,maxTime)
		if not messages:
			return ""
		return messages
#		html=""
	#	for msg in messages:
		#	d=time.localtime(msg[0]) # date
#			t=self.formatTime(d[3],d[4],d[5]) # formated time
	#		if msg[1]=='to':
		#		who=me
			#	html+=my_message.replace("[time]",t).replace("[user]",who.replace("<","&lt;").replace(">","&gt;").replace("\n","<br/> ")).replace("[message]",msg[3]).replace("<br/><br/>","<br/>").replace('[avatar]',selfavatar)
#			else:
	#			if user:
		#			who=user
			#	else:
				#	who=msg[2]
#				html+=message.replace("[time]",t).replace("[user]",who.replace("<","&lt;").replace(">","&gt;").replace("\n","<br/> ")).replace("[message]",msg[3]).replace("[foreground]",color[0]).replace("[background]",color[1]).replace("<br/><br/>","<br/>").replace('[avatar]',avatar)
	#	return html

	def formatTime(self,h,m,s):
		"""
		Returns formated time in format hh:mm:ss from integers.
		"""
		text=""
		for item in [h,m,s]:
			if item<10:
				text+="0"+str(item)+":"
			else:
				text+=str(item)+":"
		return text[:-1]
		

	def gotLastMessages(self,messages,widget,me,user,selfavatar,avatar):
		"""
		Write history messages to the chatWidget. Called when getLastMessages finished.
		"""
		if len(messages)!=0:
			self.main.webkitThemeFactory.genChatHtml(messages,me,user,selfavatar,avatar,widget)
		#old=widget.ui.textEdit.toHtml()
		#widget.ui.textEdit.setHtml("")
		#widget.textEditWrite(html,True)
		#widget.textEditWrite(old)
		self.jidList=self.backend.getJidList()


	def buildGroupchatWidget(self,jid,layout,widget):
		jid=self.main.getJid(jid).userhost()
		button=QtGui.QToolButton()
		button.setIconSize(QtCore.QSize(16,16))
		button.setIcon(QtGui.QIcon("%s/history.png" % self.pluginDir))
		button.jid=unicode(jid)
		button.setToolTip("History")
		button.setMinimumHeight(widget.ui.sendButton.height())
		button.setMaximumHeight(widget.ui.sendButton.height())
		self.group.addButton(button)
		layout.addWidget(button)
		self.jidList=self.backend.getJidList()

	
	def showSlot(self,j=None):
		"""
		Called when user wants to see archive browser main window
		@type j: unicode
		@param jid: Jabber ID of contact whos history is showed at first
		"""
		# clear widgets
		self.window.ui.seznam.clear()
		self.window.ui.calendar.setDates([])
		self.window.ui.text.setHtml('')
		# add top level items to the JID list
		#contact=QtGui.QTreeWidgetItem(self.window.ui.seznam)
		#contact.setText(0,self.tr("Contacts in roster"))
		#others=QtGui.QTreeWidgetItem(self.window.ui.seznam)
		#others.setText(0,self.tr("Others"))
		# expand them
		#self.window.ui.seznam.expandItem(contact)
		#self.window.ui.seznam.expandItem(others)
		# change background 
		#contact.setBackground(0,QtGui.QBrush(self.window.ui.seznam.palette().color(QtGui.QPalette.AlternateBase)))
		#others.setBackground(0,QtGui.QBrush(self.window.ui.seznam.palette().color(QtGui.QPalette.AlternateBase)))
		# get list of JIDs
		seznam = self.backend.getJidList()
		if self.main.isConnected():
			self.window.ui.seznam.insertSeparator(0)
			for jid in seznam:
				# we have this JID in roster
				if self.main.client.roster['users'].has_key(unicode(jid)):
					#item=QtGui.QTreeWidgetItem(contact)
					name=self.main.client.roster['users'][unicode(jid)].name
					if not name or len(name)==0:
						#item.setText(0,unicode(jid))
						self.window.ui.seznam.insertItem(0,unicode(jid),QtCore.QVariant(unicode(jid)))
					else:
						self.window.ui.seznam.insertItem(0,name,QtCore.QVariant(unicode(jid)))
						#item.setText(0,name)
				# this contact is unkown, so we will use Others group
				else:
					#item=QtGui.QTreeWidgetItem(others)
					self.window.ui.seznam.insertItem(-1,unicode(jid),QtCore.QVariant(unicode(jid)))
				#item.setData(0,32,QtCore.QVariant(unicode(jid)))
				# if user wants to see this contact just now, we save its item
			# we've got item which user wants to see
			if j:
				choosedItem=self.window.ui.seznam.findData(QtCore.QVariant(unicode(j)))
				if choosedItem!=-1:
					self.window.ui.seznam.setCurrentIndex(choosedItem)
					self.itemClicked(choosedItem)
		# show main window
		self.window.show()
	
	def calChanged(self):
		self.window.ui.dateEdit.setDate(self.window.ui.calendar.selectedDate())

	def dateChanged(self,date=None):
		self.itemClicked(self.window.ui.seznam.currentIndex(),setDate=False)
		self.window.ui.calendar.setSelectedDate(date)
	
	def getDates(self,jid):
		dates=self.backend.getDates(jid)
		print "got dates"
		all=[]
		last=None
		for date in list(dates):
			d=unicode(date).split('-')
			qdate=QtCore.QDate(int(d[0]),int(d[1]),int(d[2]))
			if not qdate in all:
				if not last:
					last=qdate
				elif qdate>last:
					all.append(last)
					last=qdate
				else:
					all.append(qdate)
		if last:
			all.append(last)
		self.window.ui.calendar.setDates(all)
		#item=self.window.ui.seznam.currentItem()
		jid = unicode(self.window.ui.seznam.itemData(self.window.ui.seznam.currentIndex()).toString())
		
		self.window.ui.text.setHtml('')
		datum=self.window.ui.dateEdit.date()
		me=unicode(self.main.client.jid.user)

		user=self.main.ui.roster.getUserItems(unicode(jid))
		if len(user)!=0:
			user=user[0].name
		else:
			user=None
		d=threads.deferToThread(self.getMessages,jid,str(datum.year())+"-"+str(datum.month())+"-"+str(datum.day()),me,user,unicode(self.skin["my_message"]),unicode(self.skin["message"]),self.skin['color1'],self.window.palette().color(QtGui.QPalette.HighlightedText).name(),self.window.palette().color(QtGui.QPalette.Highlight).name())
		d.addCallback(self.gotMessages)

	def getMessages(self,jid,datum,me,user,my_message,message,color,fg="",bg="",highlight=None):
		action=["",jid,datum,me,user,my_message,message,color]
		messages=self.backend.getMessages(action[1],action[2])
		if not messages:
			return ""
		
		html=""
		me=action[3]
		user=action[4]
		print "get_messages",highlight,fg,bg
		for msg in messages:
			d=time.localtime(msg[0])
			#qdate=QtCore.QDate(d[0],d[1],d[2])
			#if datum==qdate:
			message_=msg[3]
			if highlight:
				message_=message_.replace(highlight,"<font color=\""+fg+"\" style=\"background-color:"+bg+";\">"+highlight+"</font>")
			if msg[1]=='to':
				who=me
				html+=action[5].replace("[time]",self.formatTime(d[3],d[4],d[5])).replace("[user]",who.replace("<","&lt;").replace(">","&gt;").replace("\n","<br/> ")).replace("[message]",message_).replace("<br/><br/>","<br/>")
			else:
				if user:
					who=user
				else:
					who=msg[2]
				html+=action[6].replace("[time]",self.formatTime(d[3],d[4],d[5])).replace("[user]",who.replace("<","&lt;").replace(">","&gt;").replace("\n","<br/> ")).replace("[message]",message_).replace("[foreground]",action[7][0]).replace("[background]",action[7][1]).replace("<br/><br/>","<br/>")
		return html

	def gotMessages(self,html):
		print "got messages"
		self.window.ui.text.setHtml(html)

	def itemClicked(self, item,column=0,setDate=True,highlight=None):
		jid = unicode(self.window.ui.seznam.itemData(item).toString())
		if setDate:
			self.getDates(jid)
			#self.window.ui.searchList.hide()
			#self.window.ui.searchText.show()
			#self.window.ui.search.show()
			self.window.ui.searchText.setFocus(QtCore.Qt.MouseFocusReason)
		else:
			self.window.ui.text.setHtml('')
			datum=self.window.ui.dateEdit.date()
			me=unicode(self.main.client.jid.user)
	
			user=self.main.ui.roster.getUserItems(unicode(jid))
			if len(user)!=0:
				user=user[0].name
			else:
				user=None
			d=threads.deferToThread(self.getMessages,jid,str(datum.year())+"-"+str(datum.month())+"-"+str(datum.day()),me,user,unicode(self.skin["my_message"]),unicode(self.skin["message"]),self.skin['color1'],self.window.palette().color(QtGui.QPalette.HighlightedText).name(),self.window.palette().color(QtGui.QPalette.Highlight).name(),highlight)
			d.addCallback(self.gotMessages)

	def on_groupchatMessageEvent(self,jid,user,body,subject, xhtml):
		if body == None:
			return
		jid.resource=user
		self.backend.saveMessage(jid, body, "groupchat", subject, xhtml, "from")

	def on_firstChatMessageEvent(self, msg,event=None):
		if msg.body == None:
			return
		self.backend.saveMessage(msg.frm, msg.body, "chat", msg.subject, msg.xhtml, "from")

	def on_chatMessageEvent(self,msg,event=None):
		if msg.body == None:
			return
		self.backend.saveMessage(msg.frm, msg.body, "chat", msg.subject, msg.xhtml, "from")

	def on_message_send (self, msg):
		to, body, typ, subject,composing, xhtml,  muc = msg.legacyUnpackSend()
		if not muc and body != None and len(body)!=0:
			self.backend.saveMessage(self.main.getJid(to), body, typ, subject, xhtml, "to")

