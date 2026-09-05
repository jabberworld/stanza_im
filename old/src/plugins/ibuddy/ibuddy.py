# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from socket import *
import sys
import os
sys.path.append('.')
from include import plugins, utils

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.installTranslator()
		self.fname       = 'iBuddy'
		self.description = self.tr("Get your iBuddy working with Jabbim\n\niBuddy is a little figure-shaped USB-connected toy which reacts to chat events by changing color (see http://www.i-buddy.com/).\n\nYou need to have the \'pybuddy\' daemon installed and running before loading this plugin. You can get pybuddy from http://code.google.com/p/pybuddy/")
		self.author      = "Leandro Vazquez Cervantes"
		self.name        = self.tr('iBuddy')
		self.version     = '0.1' 
		self.category    = ['other'] 


		self.host = "localhost"
		self.port = 8888
		self.buf = 1024
		self.addr = (self.host,self.port)

		if main:
			self.UDPSock = socket(AF_INET,SOCK_DGRAM)

			self.registerHandler('firstChatMessageEvent',self.on_firstChatMessageEvent)
			self.registerHandler('chatMessageEvent',self.on_chatMessageEvent)
			self.registerHandler('groupchatMessageEvent',self.on_groupchatMessageEvent)
			self.registerHandler('groupchatMessageForMeEvent',self.on_groupchatMessageForMeEvent)
			self.registerHandler('presenceEvent',self.on_presenceEvent)

	def on_firstChatMessageEvent(self, msg,event=None):
		self.UDPSock.sendto("DEMO",self.addr)

	def on_chatMessageEvent(self, msg, event=None):
		self.UDPSock.sendto("MACRO_FLAP2",self.addr)
		self.UDPSock.sendto("MACRO_GREEN",self.addr)

	def on_groupchatMessageEvent(self,jid,user,body,subject, xhtml):
		self.UDPSock.sendto("MACRO_VIOLET",self.addr)
		#self.UDPSock.sendto("MACRO_HEART2",self.addr)

	def on_groupchatMessageForMeEvent(self,frm,user,body,subject, xhtml):
		self.UDPSock.sendto("MACRO_FLAP",self.addr)
		self.UDPSock.sendto("MACRO_YELLOW",self.addr)

	def on_presenceEvent(self,jid,name,show,statusMessage,first=False):
		if show=="online":
			self.UDPSock.sendto("MACRO_HEART",self.addr)

	def on_remove(self):
		self.UDPSock.close()
