# -*- coding: utf-8 -*-
from PyQt4 import QtCore,QtGui
from include import plugins
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.internet.error import ProcessDone, ProcessTerminated
import re, os

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['stateAfterstart']={'type':'boolean-radio','label':main.tr('Initial state after startup'),'value':'last','options':{'off':main.tr('off'),'on':main.tr('on'),'last':main.tr('previous state')}}
		self.config['exportChat']={'type':'boolean','label':main.tr('read chats'),'value':'True'}
		self.config['exportMucMe']={'type':'boolean','label':main.tr('read MUC messages directed at me'),'value':'False'}
		self.config['exportMuc']={'type':'boolean','label':main.tr('read other MUC messages'),'value':'False'}
		self.config['state']={'type':'hidden','value':'True'}
		self.config['__sort__']=['exportChat','exportMucMe','exportMuc','stateAfterstart','state']

class FestivalProtocol(protocol.ProcessProtocol):
	def __init__(self, reader):
		self.reader = reader
		self.received = ''
	def connectionMade(self):
		assert self.reader.state == "starting"
		self.reader.state = "busy"
	def outReceived(self, data):
		assert self.reader.state == "busy"
		self.received += data
		if self.received.endswith("festival> "):
			self.reader.state = "ready"
			self.received = ''
			if len(self.reader.queue) > 0:
				self.reader.say_one_from_queue()
	def processEnded(self, reason):
		print "festival process ended"
		self.reader.state = "off"

class Reader:
	def __init__(self):
		self.queue = []
		self.proto = None
		self.state = "off"  # "starting", "busy", "ready"
	def say(self, message):
		self.queue.append(message)
		if self.state == "off":
			self.state = "starting"
			self.proto = FestivalProtocol(self)
			print "spawning festival process"
			reactor.spawnProcess(self.proto, "festival", ["festival", "-i"], env=os.environ)
		elif self.state == "ready":
			self.say_one_from_queue()
	def say_one_from_queue(self):
		assert self.state == "ready"
		self.state = "busy"
		text = self.queue.pop(0)
		# escape backslashes and double quotes
		text = text.replace('\\', '\\\\').replace('"','\\"')
		# XXX should not hardcode encoding
		self.proto.transport.write('(SayText "%s")\n' % text.encode('latin2', 'ignore'))
	def stop(self):
		if self.state == "off":
			return
		self.state = "busy"
		self.proto.transport.signalProcess('TERM')
		#self.proto.transport.signalProcess('KILL')
		# XXX ^^^ is still not brutal enough :-(
		# Festival spawns pacat (or audsp) to play the sound. Problems with that:
		#  (1) pacat does not get killed and always finishes the sentence
		#  (2) /tmp/audiofile_* does not get unlinked
		# A more gentle method. Solves only (2):
		#self.proto.transport.write('(quit)')
		# Process groups could solve (1) but not (2).
		# XXX proper solution?: fix festival to use pipes instead of tmp files, or to support sound (PA?) directly
		# how does it make sounds on Windows, btw?
		self.queue = []

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'festival'
		self.installTranslator()
		self.description = self.tr('Reads messages with synthesized voice via Festival\n\nFor this plugin to work, you need to have Festival installed and found in $PATH. To verify that Festival works for you, run the command:\necho Hello | festival --tts');
		self.author = "Ondra Kunc triak@jabber.cz, Michal 'michich' Schmidt"
		self.name = self.tr('Festival voice synthesizer')
		self.version = '0.001'
		self.category = ['notification']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.configDialog = config(self);
		if main:
			self.loadConfig()
			self.reader = Reader()
			self.registerHandler('chatMessageEvent', self.on_chatMessageEvent);
			self.registerHandler('firstChatMessageEvent', self.on_chatMessageEvent);
			self.registerHandler('groupchatMessageEvent', self.on_groupchatMessageEvent);
			self.registerHandler('groupchatMessageForMeEvent', self.on_groupchatMessageForMeEvent);
		else:
			self.loadConfig(homedir)

	def buildMainWindowToolBar(self):
		#self.button = self.mainWindowToolBarButton()
		#self.button.setIconSize(QtCore.QSize(16,16))
		self.button = self.mainWindowToolBarAction(QtGui.QIcon(),"",self.clicked)
		self.button.setCheckable(True)
		start_state = (self.config['stateAfterstart'] == 'on' or
			self.config['stateAfterstart'] == 'last' and self.config['state'] == 'True')
		if self.config['state'] != unicode(start_state):
			self.config['state'] = unicode(start_state)
			self.config.write()
		self.set_icon_state(start_state)
		#QtCore.QObject.connect(self.button, QtCore.SIGNAL("clicked(bool)"), self.clicked)

	def on_chatMessageEvent(self, msg, event=None):
		if (self.config['state'] != 'True' or
				self.config['exportChat'] != 'True' or
				msg.body == None):
			return
		jid = msg.frm
		message = unicode(msg.body)
		user = unicode(msg.user)
		self.say(unicode(self.tr("%s writes: %s")) % (user, message))

	def on_groupchatMessageEvent(self, jid, user, oldbody, subject, xhtml):
		if (self.config['state'] != 'True' or
				self.config['exportMuc'] != 'True' or
				oldbody == None):
			return
		self.say(unicode(self.tr("%s writes: %s")) % (user, oldbody))

	def on_groupchatMessageForMeEvent(self,jid,user,oldbody,subject,xhtml):
		if (self.config['state'] != 'True' or
				self.config['exportMuc'] == 'True' or # to prevent reading it twice
				self.config['exportMucMe'] != 'True' or
				oldbody == None):
			return
		self.say(unicode(self.tr("%s writes: %s")) % (user, oldbody))

	def say(self, message):
		self.reader.say(message)

	def clicked(self, state=None):
		if not state:
			state = self.button.isChecked()
		self.set_icon_state(state)
		self.config['state'] = unicode(state)
		self.config.write()
		if not state:
			self.reader.stop()

	def set_icon_state(self, state):
		self.button.setChecked(state);
		self.button.setIcon(QtGui.QIcon("%s/export-%s.png" % (self.pluginDir, ['off','on'][state])))

	def on_remove(self):
		self.reader.stop()
