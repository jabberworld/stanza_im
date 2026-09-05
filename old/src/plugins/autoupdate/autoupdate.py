#-*- coding: UTF-8 -*-

import sys,os,time, re
sys.path.append('.')
from include import plugins
from twisted.python import log
from configobj import ConfigObj
from pyxl import jid as jidT
from twisted.web import xmlrpc, server
from PyQt4 import QtCore, QtGui
from twisted.python import log
from time import time
from twisted.internet import threads
from twisted.words.xish.domish import escapeToXml
try:
	from hashlib import sha1
except:
	log.msg('Please upgrade to python2.5')
	from sha import new as sha1
from imp import load_source
from include import utils

class config:
	def __init__(self, main):
		self.main=main
		self.config = {}
		self.config['check_jabbim'] = {
			'type':'boolean',
			'label':self.main.tr("Notify about new versions of Jabbim"),
			'value':'True'
		}
		self.config['check_plugins'] = {
			'type':'boolean',
			'label':self.main.tr("Notify about plugin updates"),
			'value':'True'
		}

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'autoupdate'
		self.installTranslator()
		self.description = self.tr('Updates plugins')
		self.author = "Jiri 'Sef' Gabrys"
		self.name = self.tr('Autoupdate')
		self.version = '0.022'
		self.category = ['utils']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.plugindir = plugindir
		self.configDialog = config(self)
		
		if main:
			self.loadConfig()
			self.registerHandler('on_authd',self.on_authd)
			self.registerHandler('on_ftEnd', self.on_ftEnd, priority = 4)
		else:
			self.loadConfig(homedir)

	def on_ftEnd(self, sid, error = None): #pokud je error None je vse v poradku, jinak strucny popis chyby.
		if error == None and self.main.client.ft[sid].fromjid.user.find("rpc")!=-1:
			if self.main.client.ft[sid].file.find("plugins/")!=-1:
				QtGui.QMessageBox.information(self.main,self.tr("Plugin updated"), self.tr("Please restart Jabbim to apply changes."))
			

	def on_authd(self):
		self.main.client.callRemote('rpc@jabbim.cz/service', 'updateCore', (self.main.client.jid.host, sha1(self.main.client.jid.userhost()).hexdigest(), self.main.client.client_os, self.main.client.version)).addCallback(self._update)
		if self.config['check_plugins'] == 'True':
			self.main.client.reactor.callLater(1,self.checkPlugins)

	def checkPlugins(self):
		self.main.client.callRemote('rpc@jabbim.cz/service', 'getList', ('plugins/',)).addCallback(self._listArrived)

	def _listArrived(self,data):
		plugins=data[0][0]
		for name,desc in plugins.iteritems():
			version=float(desc[0].replace(",","."))
			plugin=name

			if name in self.main.config['plugins'] and self.main.pluginManager.plugins.has_key(plugin):
				if self.main.pluginManager.plugins[plugin]['module']:
					if float(self.main.pluginManager.plugins[plugin]['module'].version)<version:
						self.main.tray.showMessage(self.tr("Autoupdate"),self.tr("New version of plugin")+" "+plugin+" "+self.tr('is available'), QtGui.QSystemTrayIcon.Information, 3000)
						self.main.events.addBooleanEvent(self.main.startExtraDonwload,["plugins/"+name],None,[],name+self.main.tr("update"),text=self.tr("Do you want to update this plugin?"),name=unicode("update")+name,typ="update")
						#self.addBooleanEvent(self.main.client.sendPresence,[jid,None,status,None,'subscribed'],self.main.client.sendPresence,[jid,None,status,None,'unsubscribed'],header=mainWindow.tr('Subscribe request'),text=mainWindow.tr('From:')+" "+unicode(jid),name=jid,typ="subscribe")

	def _update(self, vysledek):
		print vysledek
		if self.config['check_jabbim'] != 'True':
			return
		if vysledek[0][0] == False:
			#nemame posledni verzi
			self.main.tray.showMessage(self.tr("Autoupdate"),self.tr("New version of Jabbim is available! Get it from www.jabbim.cz"), QtGui.QSystemTrayIcon.Information, 5000)
			self.main.events.addBooleanEvent(self.getNewVersion, [], None, [], self.tr('Jabbim update'), text = self.tr("Do you want to download new version?"), name = u'updateJabbim', typ='update')
	
	def getNewVersion(self):
		QtGui.QDesktopServices.openUrl(QtCore.QUrl('http://dev.jabbim.cz/releases/detect.php?rel='+self.main.client.version))
	
