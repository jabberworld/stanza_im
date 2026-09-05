#-*- coding: UTF-8 -*-

import sys,os,time, re
sys.path.append('.')
from include import plugins
from twisted.python import log
from configobj import ConfigObj
from twisted.web import xmlrpc, server
from PyQt4 import QtCore, QtGui
from twisted.python import log
from time import time
from twisted.internet import threads
from twisted.words.xish.domish import escapeToXml
import time
from imp import load_source
from include import utils

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'attention'
		self.description = 'Attention, please!'
		self.author = "Josef 'PepeQ' Halicek"
		self.name = 'Attention'
		self.version = '0.25'
		self.category = ['fun']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.delay=30 # how frequently do we want to allow user send attentions
		self.last_sent=int(time.time())-self.delay # sets "last sent atention" - as initial we use now-self.delay seconds, GLOBAL!
		self.last_req=int(time.time())-self.delay # sets "last req. atention" - as initial we use now-self.delay seconds, GLOBAL!
		
		if main:
			self.loadConfig()
			self.registerHandler('on_attention', self.on_attention)
			self.registerHandler('on_authd',self.on_authd)
			self.group=QtGui.QButtonGroup()
			QtCore.QObject.connect(self.group,QtCore.SIGNAL("buttonClicked ( QAbstractButton * )"),self.buttonClicked)
		else:
			self.loadConfig(homedir)

	def on_authd(self):
		self.registerFeature("http://www.xmpp.org/extensions/xep-0224.html#ns")

	def on_attention(self, frm, body, subject, xhtml, error):
		if ((int(time.time())-self.last_req)>self.delay):
			self.main.tray.showMessage(frm,self.tr("requests attention!"), QtGui.QSystemTrayIcon.Information, 4000)
			self.playsound()
			tab,index=self.main.chat.findTab(frm)
			if tab:
				message=self.main.webkitThemeFactory.genChatStatus(self.main.ui.roster.getNameByJID(frm)+self.tr(' has just requested an attention.'),self.main.now())
				tab.chat.textEditWrite(message)
				tab.chat.lastMessageFrom=""
			self.last_req=int(time.time())


	def buildChatWidget(self,jid,layout,widget):
		button=QtGui.QPushButton()
		#button.setText(self.tr('Attention'))
		button.setIconSize(QtCore.QSize(16,16))
		button.setIcon(QtGui.QIcon("%s/attention.png" % self.pluginDir))
		button.jid=unicode(jid)
		
		button.setToolTip(self.tr('Request the attention of the user!'))

		
		self.group.addButton(button)
		layout.addWidget(button)
		widget.registerFeatureForWidget("http://www.xmpp.org/extensions/xep-0224.html#ns",button)
		
		
	def buttonClicked(self, button):
		tab,index=self.main.chat.findTab(button.jid) #trying to find out if the tab with contact is opened
		if ((int(time.time())-self.last_sent)>self.delay):
			self.main.client.sendAttention(button.jid, " ") # TODO: allow user to sed message acording to xep
			self.playsound()
			if tab:
				message=self.main.webkitThemeFactory.genChatStatus(self.tr('You have just sent request for an attention.'),self.main.now())
				tab.chat.textEditWrite(message)
				tab.chat.lastMessageFrom=""
			self.last_sent=int(time.time())
		else:
			message=self.main.webkitThemeFactory.genChatStatus(self.tr("You shouldn't request attention so frequently."),self.main.now())
			tab.chat.textEditWrite(message)
			tab.chat.lastMessageFrom=""
	
	def playsound(self):
		if sys.platform == 'linux2': # linux sounds are produced using aplay
			os.system('aplay -q '+self.pluginDir+'/attention.wav'+' &')
		else:
			QtGui.QSound.play(self.pluginDir+'/attention.wav')
