#-*- coding: UTF-8 -*-

import sys,os,time
sys.path.append('.')
from include import plugins
from twisted.python import log
from configobj import ConfigObj
from twisted.words.protocols.jabber import jid as jidT
from twisted.web import xmlrpc, server
from PyQt4 import QtCore, QtGui
from twisted.python import log
from time import time

try:
	from hashlib import sha1
except:
	log.msg('Please upgrade to python2.5')
	from sha import new as sha1

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'remote'
		self.description = 'XMLRPC Remote Control'
		self.author = "Jiri 'Sef' Gabrys"
		self.name = 'XMLRPC Remote'
		self.version = '0.02'
		self.category = ['utils']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.functions = {}

		if main:
			self.pfilename = os.path.join(homedir,"xmlrpcports")
			self.loadConfig(homedir)
			self.loadConfig()
			self.cookie = generateCookie()
			r = Remote(main, self)
			from twisted.internet import reactor
			self.server = server.Site(r)
			port = 7080
			while True:
				try:
					self.conn = reactor.listenTCP(port, self.server, interface = 'localhost')
					break
				except:
					port += 1
					if port>65535:
						break
					#not very probably situation ..., but ;)
			pfile = open(self.pfilename, "w")
			pfile.write("%s:%s:%s\n" % (time(), port, self.cookie)) # timstamp (float): port (int) : cookie (str)
			self.registerPluginFunc("showRoster",self.showRoster)
			self.registerPluginFunc("sendFileDialog",r.xmlrpc_sendFile)
			pfile.close()
			set_xmpp_handler()
		else:
			self.loadConfig(homedir)

	def on_remove(self):
		#remove factory and listening port here

		self.conn.stopListening()
		os.remove(self.pfilename)

	def registerPluginFunc(self, name, func):
		self.functions[name] = func

	def unregisterPluginFunc(self, name):
		try:
			del self.functions[name]
		except:
			pass

	def runPluginFunc(self, name, arg):
		print 'XMLRPC RUN: ', name
		print  arg
		print self.functions
		if self.functions.has_key(name):
			print 'XMLRPC OK: function '+name+' started'
			return self.functions[name](arg)
		else:
			print 'XMLRPC ERROR:function not in ',[self.functions];
		    	return False

	def showRoster(self,arg):
		print [self.main.config['autoJoin']]
		if self.main.config['autoJoin']=='True':
			self.main.show()
			self.main.raise_()
			self.main.activateWindow()
			self.main.ui.roster.setFocus(QtCore.Qt.MouseFocusReason)
			return True
		else:
			return False

def generateCookie():
	magic = unicode(globals())+unicode(time())
	return sha1(magic).hexdigest()

def checkCookie(incoming, mine):
	if incoming != mine:
		print 'bad cookie'
		print mine, incoming
		return False
	else:
		return True


class Remote(xmlrpc.XMLRPC):
	"""An example object to be published."""
	allowNone = True
	def __init__(self, main, plugin):
		self.main = main
		self.cookie = plugin.cookie
		self.plugin = plugin
		
	def xmlrpc_runPluginFunc(self, name, arg, cookie):
		if not checkCookie(cookie, self.cookie):
			print 'bad cookie'
			return False
		print 'runPluginFunc'
		return self.plugin.runPluginFunc(name, arg)
		
	def xmlrpc_setStatus(self, show, status):
		self.main.sendPresence(None, show, status)
		return True
	
	def xmlrpc_startChat(self, jid, cookie, nick = None):
		print 'startChat from RPC'
		if not checkCookie(cookie, self.cookie):
			print 'bad cookie'
			return False
		print jid
		jid = self.main.getJid(jid)
		if  jid :
			if nick == None:
				nick = jid.user
			self.main.chat.addChatTab(jid.userhost(), nick, QtGui.QIcon(self.main.getIcon(status="offline",size="16x16")))
			return True
		else:
			return False
	
	def xmlrpc_joinMUC(self, jid, cookie):
		if not checkCookie(cookie, self.cookie):
			return False
		jid = self.main.getJid(jid)
		if jid:
			nickname = self.main.client.jid.user
			if self.main.chat.addGroupChatTab(jid.userhost(),nickname):
					self.main.client.joinGC(jid.userhost(), nickname)
					return True
			else:
				return False
		else:
			return False
				
	def xmlrpc_addContact(self, jid):
		jid = self.main.getJid(jid)
		if jid:
			self.main.addContactMainWindow(jid)
			return True
		else:
			return False
	
	def xmlrpc_sendFile(self,params):
		jid,file = params
		if jid and file:
			self.main.showFiletransferDialog([file],jid);
			return True
		else:
			return False

def set_xmpp_handler():
	if sys.platform == 'win32' :
		print os.getcwd()
		if sys.argv[0].find('jabbim.py') != -1:
			cesta = 'c:\Python25\python.exe "' + os.getcwd() + '\\jabbim.py" --uri=%1' #hack!
		else:
			cesta = '"' + os.getcwd() + '\\jabbim.exe" --uri=%1'
		import _winreg
		reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CLASSES_ROOT)
		xmpp = _winreg.CreateKey(reg, 'xmpp')
		_winreg.CloseKey(xmpp)
  		xmpp = _winreg.OpenKey(reg, 'xmpp', 0, _winreg.KEY_WRITE)
		_winreg.SetValueEx(xmpp,'EditFlags', 0, _winreg.REG_DWORD, 2)
		_winreg.SetValueEx(xmpp,'', 0, _winreg.REG_SZ, 'URL:XMPP Protocol')
		_winreg.SetValueEx(xmpp,'URL Protocol', 0, _winreg.REG_SZ, '')
		_winreg.CloseKey(xmpp)
		comm = _winreg.CreateKey(reg, 'xmpp\\shell\\open\\command')
		_winreg.CloseKey(comm)
		comm = _winreg.OpenKey(reg, 'xmpp\\shell\\open\\command', 0, _winreg.KEY_WRITE)
		_winreg.SetValueEx(comm,'', 0, _winreg.REG_SZ, cesta)
		_winreg.CloseKey(comm)

 	path_to_dot_kde = os.path.expanduser('~/.kde')
	if os.path.exists(path_to_dot_kde):
		path_to_kde_file = os.path.join(path_to_dot_kde, 
			'share/services/xmpp.protocol')
	else:
		path_to_kde_file = None

	def set_jabbim_as_xmpp_handler(is_checked=None):

			command = 'jabbim.sh --uri=%s'

			# setting for GNOME/Gconf
			client.set_bool('/desktop/gnome/url-handlers/xmpp/enabled', True)
			client.set_string('/desktop/gnome/url-handlers/xmpp/command', command)
			client.set_bool('/desktop/gnome/url-handlers/xmpp/needs_terminal', False)

			# setting for KDE
			if path_to_kde_file is not None: # user has run kde at least once
				try:
					f = open(path_to_kde_file, 'a')
					f.write('''\
[Protocol]
exec=%s "%%u"
protocol=xmpp
input=none
output=none
helper=true
listing=false
reading=false
writing=false
makedir=false
deleting=false
icon=jabbim
Description=xmpp
''' % command)
					f.close()
				except IOError:
					log.debug("I/O Error writing settings to %s", repr(path_to_kde_file))


	try:
		import gconf
		# in try because daemon may not be there
		client = gconf.client_get_default()
	except:
		return

	we_set = True


	if we_set:
		set_jabbim_as_xmpp_handler()
