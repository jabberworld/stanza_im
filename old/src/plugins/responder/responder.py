import sys,os,time
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui
from urllib import quote, unquote
from twisted.python import log

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['message']={'type':'text-multi','label':unicode(self.main.tr("Auto reply")),'value':unicode(self.main.tr('This is an automatic reply. This ICQ number has been discontinued by its owner, who now uses Jabber exclusively. You can contact him/her on the JabberID [JID]. If you do not know how, visit http://www.jabbim.com/services-start.html\nHave a nice day.'))}
		self.config['exclude']={'type':'jid-list','label':self.main.tr("Allow JIDs"),'value':[]}

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'responder'
		self.installTranslator()
		self.description = self.tr('CAREFUL!\n' +
			'Do not enable this plugin unless you intend to cut down a little on your ICQ usage.\n\n' +
			'ICQ auto responder is meant for the ICQ transport users who want to quit ICQ for good.\n' +
			'If you enable this plugin, contacts trying to write to you over ICQ will receive an automatic reply ' +
			'telling them how to reach you properly. You will NOT see their messages. ' +
			'The exact text of the automatic reply is customizable.')
		self.author = "Jiri 'Sef' Gabrys"
		self.name = self.tr('ICQ Responder')
		self.version = '0.033'
		self.category = ['misc']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.count = 0
		self.configDialog=config(self)
		if main:
			self.registerHandler('on_message', self.on_message, priority = 4)

			self.loadConfig()
		else:
			self.loadConfig(homedir)

	def buildMainWindowMenu(self):
		menu=self.mainWindowMenu()
		menu.addAction(self.tr("Show statistics"), self.showSlot)
	def on_message(self,msg):
		frm, typ, body, subject, xhtml, chatstate, delay, error = msg.legacyUnpack()
		jid = self.main.getJid(frm)
		if jid.host.startswith('icq') and not jid.userhost() in self.config['exclude'] and body != None:
			# XXX Debug what sometimes makes us send spurious messages:
			print "responder on_message going to reply to: frm=%s type=%s. toXml is:" % (frm, typ)
			print "%s" % msg.toXml()
			self.main.client.sendMessage(frm, self.config['message'].replace('[JID]', self.main.client.jid.userhost()))
			self.count = self.count +1
			return False
			
	def showSlot(self):
		self.main.tray.showMessage(self.tr('ICQ Responder'), self.tr('Messages sent: ') + unicode(self.count), QtGui.QSystemTrayIcon.Information, 3000)
