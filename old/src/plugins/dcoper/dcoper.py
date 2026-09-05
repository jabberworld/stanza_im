#-*-coding:utf-8-*-
import sys,os,time
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui
from urllib import quote, unquote
from twisted.python import log
import commands

class config:
	def __init__(self, main):
		self.main = main
		self.config={}
		self.config["format"] = {
				"type": "text-multi",
				"label": self.main.tr("Format of message. %artist is replaced by artist's name, %title by track name and so on for %album, %genre, %year, %type and %totalTime"),
				"value": unicode("/me plays: (8) %artist - %title (%album) (8)", "utf-8")
				}
		self.config["amarok_off"] = {
				"type": "text-single",
				"label": self.main.tr("Message when amaroK is not running."),
				"value": "/me has amaroK turned off :'("
				}
		self.config["amarok_paused"] = {
				"type": "text-single",
				"label": self.main.tr("Message when nothing is being played in amaroK."),
				"value": "/me isn't listening to anything at the moment."
				}

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'DCOPer'
		self.description = 'DCOP plugin for /amarok'
		self.author = "Josef 'Pepeq' Halicek & Jachym 'kamahl' Barvinek"
		self.name = 'dcoper'
		self.version = '0.1'
		self.category = ['misc']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.count = 0

		self.installTranslator()	

		self.configDialog=config(self)

		if main:
			#jid = quote(unicode(self.main.client.jid.userhost()))
			#if not os.path.isdir(self.main.homeDir+'/dcoper'):
				#os.mkdir(self.main.homeDir+'/dcoper')
			#if not os.path.isdir(self.main.homeDir+'/dcoper/'+ jid):
				#os.mkdir(self.main.homeDir+'/dcoper/'+ jid)
			self.registerHandler("onCommand", self.commandCalled, priority=5)
			self.loadConfig()
		else:
			self.loadConfig(homedir)

	def commandCalled(self, cmd, args, chat, typ):
		if cmd != "amarok":
			return
		title = unicode(commands.getoutput("dcop amarok player title"), "utf-8")
		if title == u"call failed":
			msg = self.config["amarok_off"]
		if title == u"":
			msg = self.config["amarok_paused"]
		else:
			msg = self.config["format"]
			msg = msg.replace("%title", title)
			msg = msg.replace("%artist", unicode(commands.getoutput("dcop amarok player artist"),"utf-8"))
			msg = msg.replace("%album", unicode(commands.getoutput("dcop amarok player album"),"utf-8"))
			msg = msg.replace("%genre", unicode(commands.getoutput("dcop amarok player genre"),"utf-8"))
			msg = msg.replace("%year", unicode(commands.getoutput("dcop amarok player year"),"utf-8"))
			msg = msg.replace("%type", unicode(commands.getoutput("dcop amarok player type"),"utf-8"))
			msg = msg.replace("%totalTime", unicode(commands.getoutput("dcop amarok player totalTime"),"utf-8"))
		#playing=unicode(commands.getoutput("dcop amarok player nowPlaying"), "utf-8")
		log.msg("Playing: "+`msg`)
		self.main.client.sendMessage(unicode(chat.jid), msg, typ)
		# We handled the command. Do not propagate the event further:
		return False

