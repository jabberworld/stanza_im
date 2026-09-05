# -*- coding: utf-8 -*-

import sys,os,time
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui
from urllib import quote, unquote
from twisted.python import log
from include import utils
from pyxl import jid
from PyQt4 import QtWebKit
#exp = re.compile(" (((https?://)|(ftp://)|(www\.))[^\ ]+)|(([^\ ]*\.){2,}[0-9a-z-A-Z]{2,4}(/[^\ ]*)?)")
#exp.search('http://jabbim.cz/').group()

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['notify_tray']={'type':'boolean','label':self.main.tr("Notify in tray"),'value':'True'}
		self.config['notify_show']={'type':'boolean','label':self.main.tr("Show window on new"),'value':'True'}
		self.config['__sort__']=['notify_tray','notify_show']


class NewsTab(QtGui.QWidget):
	def __init__(self, plugin):
		QtGui.QWidget.__init__(self)
		#l=QtGui.QHBoxLayout(self)
		
		#self.horizontalLayoutWidget = QtGui.QWidget(self)
		#self.horizontalLayoutWidget.setObjectName("horizontalLayoutWidget")
		#l.addWidget(self.horizontalLayoutWidget)
		self.horizontalLayout = QtGui.QHBoxLayout(self)
		self.horizontalLayout.setObjectName("horizontalLayout")
		self.treeWidget = QtGui.QTreeWidget(self)
		self.treeWidget.setRootIsDecorated(True)
		self.treeWidget.setHeaderHidden(True)
		self.treeWidget.setObjectName("treeWidget")
		self.treeWidget.setMaximumWidth(200)
		self.horizontalLayout.addWidget(self.treeWidget)
		self.webView = QtWebKit.QWebView(self)
		jid = plugin.main.client.jid.userhost()
		lang=unicode(QtCore.QLocale.system().name())[:2]
		
		self.webView.setUrl(QtCore.QUrl("http://content.jabbim.com/?jid=%s&lang=%s"%(jid,lang)))
		self.webView.setObjectName("webView")
		self.webView.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding))
		#self.webView.set
		self.horizontalLayout.addWidget(self.webView)
		self.unreadEvent = None
		self.unread = 0
		self.lastMessageFrom = ''
		QtCore.QObject.connect(self.treeWidget, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem *, int )"),self.itemClicked)
		self.plugin = plugin
		
	def itemClicked(self, item, col):
		self.webView.load(QtCore.QUrl((item.data(1,0).toString())))
	
	def on_remove(self):
		print "removing tab"


class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'news'
		self.description = 'Headlines window'
		self.author = u"Jiří 'Sef' Gabryš"
		self.name = 'News Plugin'
		self.version = '0.07'
		self.category = ['misc']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.kontakty = {} # jid:contact
		self.installTranslator()
		self.configDialog=config(self)
		if main:
			self.loadConfig()
			#self.installTranslator()
			if self.main.isConnected() and self.main.client.xmlstream:
				self.on_authd()
			else:
				self.registerHandler('on_authd',self.on_authd)
			self.log = False
			self.registerHandler('on_message', self.on_message, priority=4)
		else:
			self.loadConfig(homedir)
	
	def on_authd(self):
			jid = self.main.client.jid.userhost()
			lang=unicode(QtCore.QLocale.system().name())[:2]
		
			url = "http://content.jabbim.com/?jid=%s&lang=%s"%(jid,lang)
			kontakt = Contact('News')
			kontakt.addHeadline('Jabbim Content', '', url)
			self.kontakty['news'] = kontakt

	def buildMainWindowMenu(self):
		menu=self.mainWindowMenu()
		menu.addAction(self.main.tr("Show news"),self.showSlot)
	
	def buildMainWindowToolBar(self):
		self.toolBarButton = self.mainWindowToolBarAction(QtGui.QIcon("images/32x32/status/rss-online.png"),"News",self.showSlot)
	
	def on_remove(self):
		tab, pozice = self.main.chat.findTab('news@plugin', typ = ['news'])
		if tab:
			self.main.chat.removeTab(pozice)

	def showSlot(self):
		#self.window.show()
		tab, pozice = self.main.chat.findTab('news@plugin', typ = ['news'])
		if not tab:
			tab = self.main.chat.addCustomTab('news@plugin', 'nick', 'News', NewsTab, [self], typ='news', icon = QtGui.QIcon("images/32x32/status/rss-online.png"))
			for kontakt in self.kontakty.itervalues():
				for zprava in kontakt.zpravy:
					self.addHeadline(tab, kontakt.jid, zprava.subject, zprava.body, zprava.url)
			
			tab, pozice = self.main.chat.findTab('news@plugin', typ = ['news'])
			self.main.chat.activate()
			self.main.chat.changeTab(pozice)
		else:
			self.main.chat.activate()
			self.main.chat.changeTab(pozice)


	def findUrl(self,body):
		url = ""
		for slovo in body.split(' '):
			if slovo.find('http://') !=-1:
				url = slovo
				continue
			elif slovo.startswith('www.'):
				url = 'http://' + slovo
		return url
	
	def addHeadline(self, tab, jid, subject, body, url = None):
		items = tab.chat.treeWidget.findItems(jid, QtCore.Qt.MatchExactly,0)
		if len(items) == 0:
			item = QtGui.QTreeWidgetItem([jid])
			tab.chat.treeWidget.addTopLevelItem(item)
		else:
			item  = items[0]
		if url == None:
			url = self.findUrl(body)
		headline = QtGui.QTreeWidgetItem([subject, url])
		headline.setToolTip(0,body)
		item.addChild(headline)
		log.msg('headline added')

	def on_message(self, msg):
		frm, typ, body, subject ,  xhtml,chatstate ,  delay, error = msg.legacyUnpack()
		if typ != 'headline':
			return True
		frm = jid.JID(frm)
		kontakt = self.kontakty.get(frm.userhost())
		if not kontakt:
			kontakt = Contact(frm.userhost())
			self.kontakty[frm.userhost()] = kontakt
		kontakt.addHeadline(subject, body)
		tab, pozice = self.main.chat.findTab('news@plugin', typ = ['news'])
		if tab:
			self.addHeadline(tab, frm.userhost(), subject, body)
		
		if self.config['notify_tray']=='True':
			self.main.tray.showMessage("News",subject, QtGui.QSystemTrayIcon.Information, 3000)
		if self.config['notify_show']=='True':
			self.showSlot()
		print 'returning false'
		return False


class Contact:
	def __init__(self, jid,):
		self.jid = jid
		self.zpravy = []

	def addHeadline(self, subject, body, url = None):
		self.zpravy.append(Zprava(subject, body, url))
		return len(self.zpravy)-1

	def neprectene(self):
		n = 0
		for zprava in self.zpravy:
			if zprava.unread:
				n = n+1
		return n

class Zprava:
	def __init__(self, subject, body, url):
		self.subject = subject
		self.body = body
		self.time = time.time()
		self.unread = True
		self.url = url
