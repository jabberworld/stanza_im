#-*- coding: UTF-8 -*-

import sys,os,time, re
sys.path.append('.')
from include import plugins
from include.constants import RESOURCEPATH
from twisted.python import log
from configobj import ConfigObj
from twisted.web import xmlrpc, server
from PyQt4 import QtCore, QtGui
from twisted.python import log
from time import time
from twisted.internet import threads
from twisted.words.xish.domish import escapeToXml
import time
try:
	from hashlib import sha1
except:
	log.msg('Please upgrade to python2.5')
	from sha import new as sha1
from imp import load_source
from include import utils
from twisted.internet import  threads,  reactor
from twisted.web.microdom import parseString

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'uniemoticons'
		self.description = 'Universal emoticons'
		self.author = "Jiri 'Sef' Gabrys"
		self.name = 'UniEmoticons'
		self.version = '0.01'
		self.category = ['fun']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.current = {}
		if main:
			self.loadConfig()
			self.registerHandler('on_authd', self.on_authd)
			if self.main.isConnected() and self.main.client.xmlstream:
				self.on_authd()
		else:
			self.loadConfig(homedir)
	
	def on_authd(self):
		threads.deferToThread(self.loadCurrentEmoticons)
	
	def loadCurrentEmoticons(self):
			log.msg('loading new emoticons')
			for k in sorted(self.main.emoticonsWidget.smileys.iterkeys(), key=len, reverse=True):
				v = self.main.emoticonsWidget.smileys[k]
				fp = open(v, 'rb')
				self.current[k] = 'sha1+'+sha1(fp.read()).hexdigest()+'@bob.xmpp.org'
				fp.close()
				if not self.config.has_key('emoticons') or not self.config['emoticons'] == self.main.config['emoticons']:
					self.main.client.bobDef[self.current[k]] = v
			try:
				if not self.config.has_key('emoticons') or not self.config['emoticons'] == self.main.config['emoticons']:
					self.main.client.bobDef.write()
			except:
				print 'emoticons caching failed!'
			self.config['emoticons'] = self.main.config['emoticons']
		#self.loadAllEmoticons()

	def on_messageSend(self,msg):
		print 'msg'
		if  self.main.client.hasFeature(msg.to.full(), 'urn:xmpp:bob') or msg.typ == 'groupchat':
			print 'trying bob'
			if msg.xhtml != None:
				text = msg.xhtml
				for k in sorted(self.current.iterkeys(), key=len, reverse=True):
					v = self.current[k]
					text=text.replace(' '+k,'<img alt="'+k+'" src="cid:'+v+'"/>')
				
				for k, v in self.current.iteritems():
					text.replace('orig'+v, k)
				msg.xhtml = text
			elif msg.body != None:
				text = msg.body
				for k in sorted(self.current.iterkeys(), key=len, reverse=True):
					v = self.current[k]
					text=text.replace(' '+k,'<img alt="'+k+'" src="cid:'+v+'"/>')
				
				for k, v in self.current.iteritems():
					text.replace('orig'+v, k)
				
				print text
				if text != msg.body:
					msg.xhtml = text
		return msg
	
##<<<<<<< .mine
##	def on_message(self,  msg,  typ = 'on_message'):
##		changed = False
##		print "RET!!",msg.xhtml
##		if msg.xhtml != None:
##			dom = parseString(unicode('<p>'+msg.xhtml+'</p>'))
##			#seznam = {}
##
##			for el in dom.getElementsByTagName('img'):
##				src = el.getAttribute('src')
##				if src != None and src.startswith('cid:'):
##					print src
##					cid = src.split(':')[1]
##					link = "file:///"+self.main.client.bobCacheDir+cid
##					el.setAttribute('src', link)
##					el.setAttribute('name',"bob"+str(self.imageId))
##					changed = True
##					d=self.main.client.getBOBData(msg.frm.full(),  cid)
##					d.addCallback(self.refreshImage,"bob"+str(self.imageId),msg.frm)
##					print "RETURN",d
##					self.imageId+=1
##			msg.setXHTML(unicode(dom.toxml()))
##		if changed:
##			reactor.callLater(0.5, self.main.client.dispatcher.publishEvent,typ,  msg)
##			return False
##
##	def refreshImage(self,data,name,frm):
##		print "refreshing image after bob:",data,name
##		if self.main.client.groupchats.has_key(frm.userhost()):
##			tab,tabIndex=self.main.chat.findTab(frm.full(),True)
##		else:
##			tab,tabIndex=self.main.chat.findTab(frm.full())
##		if tab:
##			tab.chat.reloadImage(name,data)
##
##
##	def on_GCmessage(self,  msg,  typ = 'on_GCmessage'):
##		self.on_message(msg,  typ)
##
##=======
##
##>>>>>>> .r3335
	def loadAllEmoticons(self):
		# emoticons from Jabbim root directory
		packs=os.listdir("emoticons/")
		for pack in packs:
			if os.path.isdir('emoticons/'+pack):
				emoticons=os.listdir('emoticons/'+pack+"/")
				for emoticon in emoticons:
					if emoticon.endswith('.cfg'):
						emo=pack+"/"+emoticon
						#config=ConfigObj("emoticons/"+emo,encoding='UTF8')
						loaded,config=self.main.loadJabbimExtraConfig("emoticons/"+emo,'emoticons/default/smileys.cfg')
						if loaded:
							for v in config['emoticons'].itervalues():
								v = RESOURCEPATH+"/emoticons/"+pack+'/'+v
								if not v in self.main.client.bobDef.values():
									try:
										fp = open(v, 'rb')
										hash = sha1(fp.read()).hexdigest()
										fp.close()
										self.main.client.bobDef['sha1+'+hash] = v
									except:
										continue

		# emoticons from users home directory
		packs=os.listdir(self.main.realHomeDir+"/emoticons")
		for pack in packs:
			if os.path.isdir(self.main.realHomeDir+"/emoticons/"+pack):
				emoticons=os.listdir(self.main.realHomeDir+"/emoticons/"+pack+"/")
				for emoticon in emoticons:
					if emoticon.endswith('.cfg'):
						emo=pack+"/"+emoticon
						#config=ConfigObj(self.main.realHomeDir+"/emoticons/"+emo,encoding='UTF8')
						loaded,config=self.main.loadJabbimExtraConfig(self.main.realHomeDir+"/emoticons/"+emo,'emoticons/default/smileys.cfg')
						if loaded:
							for v in config['emoticons'].itervalues():
								v = self.main.realHomeDir+"/emoticons/"+pack+'/'+v
								if not v in self.main.client.bobDef.values():
									try:
										fp = open(v, 'rb')
										hash = sha1(fp.read()).hexdigest()
										fp.close()
										self.main.client.bobDef['sha1+'+hash] = v
									except:
										continue
			self.main.client.bobDef.write()
		
