# -*- coding: utf8 -*-
import sys,os,time
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui
from urllib import quote, unquote
from twisted.python import log
from include import utils
import time
import ctypes
from ctypes.util import find_library



class autoAwayThread(QtCore.QThread):
	def __init__(self,main):
		QtCore.QThread.__init__(self,None)
		self.main=main

	def run(self):
		config=self.main.config
		threadRun=True
		self.load_libraries()
		status="online"
		#mutex.lock()
		while True:
			
			awayTime=int(self.main.config['awayTime'])*60000
			idle = self.get_idle_time()
			if status == "online":
				if idle > awayTime:
					self.emit(QtCore.SIGNAL("setAway()"))
					status="away"
					self.main.main.client.last=int(idle/1000)
			else:  # we're in autoaway
				if idle < awayTime:
					self.emit(QtCore.SIGNAL("setOnline()"))
					status="online"
					self.main.main.client.last=0
				else:
					self.main.main.client.last=int(idle/1000)

			if status == "online":
				sleeptime = max(0, awayTime - idle)
			else:
				# Ideally, after going away, we'd like to receive a notification of any user's input.
				# I don't know how to do it, so we'll poll every 10 seconds instead to detect input.
				sleeptime = 10000
					
			self.main.mutex.lock()
			if not self.main.threadRun:
				break
			self.main.finish_cond.wait(self.main.mutex, sleeptime)
			self.main.mutex.unlock()
		#self.main.mutex.unlock()

class XScreenSaverInfo( ctypes.Structure):
	""" typedef struct { ... } XScreenSaverInfo; """
	_fields_ = [('window',      ctypes.c_ulong), # screen saver window
				('state',       ctypes.c_int),   # off,on,disabled
				('kind',        ctypes.c_int),   # blanked,internal,external
				('since',       ctypes.c_ulong), # milliseconds
				('idle',        ctypes.c_ulong), # milliseconds
				('event_mask',  ctypes.c_ulong)] # events

class autoAwayThreadX11(autoAwayThread):
	def __init__(self,main):
		autoAwayThread.__init__(self,main)

	def load_libraries(self):
		xlib = ctypes.cdll.LoadLibrary(find_library("X11"))
		xlib.XOpenDisplay.restype = ctypes.c_void_p # Display*
		xlib.XOpenDisplay.argtypes = [ ctypes.c_char_p ]
		self.dpy = xlib.XOpenDisplay(None)
		xlib.XDefaultRootWindow.restype = ctypes.c_ulong # Window/XID
		xlib.XDefaultRootWindow.argtypes = [ ctypes.c_void_p ]
		self.root = xlib.XDefaultRootWindow(self.dpy)
		self.xss = ctypes.cdll.LoadLibrary(find_library("Xss"))

	def get_idle_time(self):
		self.xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
		xss_info = self.xss.XScreenSaverAllocInfo()
		self.xss.XScreenSaverQueryInfo.argtypes = [ ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XScreenSaverInfo) ]
		self.xss.XScreenSaverQueryInfo(self.dpy, self.root, xss_info)
		return int(xss_info.contents.idle)
		

class LASTINPUTINFO(ctypes.Structure):
	_fields_ = [("cbSize", ctypes.c_uint),
				("dwTime", ctypes.c_uint)]


class autoAwayThreadWin(autoAwayThread):
	def __init__(self,main):
		autoAwayThread.__init__(self,main)

	def load_libraries(self):
		self.GetTickCount = ctypes.windll.kernel32.GetTickCount
		self.GetLastInputInfo = ctypes.windll.user32.GetLastInputInfo
		self.lastInputInfo = LASTINPUTINFO()
		self.lastInputInfo.cbSize = ctypes.sizeof(self.lastInputInfo)

	def get_idle_time(self):
		self.GetLastInputInfo(ctypes.byref(self.lastInputInfo))
		return int(self.GetTickCount() - self.lastInputInfo.dwTime)
		
class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['awayTime']={'type':'number-spin','label':self.main.tr("Away time (minutes):"),'value':'5'}
		self.config['awayMessage']={'type':'text-multi','label':self.main.tr("Away text"),'value':self.main.tr("I'm not here since [last].")}
		self.config['__sort__']=['awayTime','awayMessage']

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'autoaway'
		self.installTranslator()
		self.description = self.tr('Auto away')
		self.author = u"Jan 'HanzZ' Kaluža"
		self.name = self.tr('Autoaway Plugin')
		self.version = '0.022'
		self.category = ['misc']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.kontakty = {} # jid:contact
		self.showInPreferences=True
		self.preferencesIcon=QtGui.QIcon(plugindir+"/autoaway.png")
		#self.config['away_time'] = {'description':'Minutes to autoaway', 'default':'10', 'value': '','type':'text'}
		#self.config['away_text'] = {'description':'Text to show while auto away', 'default':'User is away for %i minutes.', 'value': '','type':'text'}
		#self.config['preserve_show'] = {'description':"Change only status message", 'default':'True', 'value': '','type':'boolean'}
		self.threadRun=True
		self.awayTime=1
		self.configDialog=config(self)
		if main:
			self.loadConfig()
			self.mutex=QtCore.QMutex()
			self.finish_cond=QtCore.QWaitCondition()
##			self.window = self.loadWindow("%s/news.ui.py" % self.pluginDir)
##			self.window.setWindowIcon(self.main.windowIcon())
			self.log = False
			self.currentMessage=""
			#self.registerHandler('onInactivity', self.on_idle, priority=4)
			#self.registerHandler('onActivity', self.on_active, priority=4)
			if sys.platform == 'win32':
				self.thread=autoAwayThreadWin(self)
			else:
				self.thread=autoAwayThreadX11(self)

			QtCore.QObject.connect(self.thread, QtCore.SIGNAL("setAway()"), self.setAway,QtCore.Qt.QueuedConnection)
			QtCore.QObject.connect(self.thread, QtCore.SIGNAL("setOnline()"), self.setOnline,QtCore.Qt.QueuedConnection)
			self.thread.start()
		else:
			self.loadConfig(homedir)
		
		self.message_set = False
		self.idletime = 0
		self.old_show = 'away'
		self.old_status = ''
	
	def setOnline(self):
		print "autoaway online"
		if self.message_set:
			self.message_set=False
			#self.main.ui.statusButton.setIcon(self.main.getIcon(status='online', size="16x16"))
			#self.main.ui.showWidget.setText("")
			#self.main.client.sendPresence(show = 'online', status = "")
			#for muc in self.main.client.groupchats.itervalues():
				#self.main.client.sendPresence(show = 'online', status = "", to = '%s/%s'%(muc.jid, muc.nick))
			self.main.sendPresence(None,'online',self.currentMessage)


	def setAway(self):
		print "autoaway away"
		contact = self.main.client.roster['users'][self.main.client.jid.userhost()]
		if contact.resources[self.main.client.jid.resource].status:
			self.currentMessage=unicode(contact.resources[self.main.client.jid.resource].status)
		else:
			self.currentMessage=""
		if self.main.selfStatus=="online":
			#self.main.ui.statusButton.setIcon(self.main.getIcon(status='away', size="16x16"))
			now=self.main.now(-int(self.config['awayTime'])*60)
			#self.main.ui.showWidget.setText(self.config['awayMessage'].replace('[time]',self.config['awayTime']).replace("[last]",unicode(now)))
			#self.main.client.sendPresence(show = 'away', status = self.config['awayMessage'].replace('[time]',self.config['awayTime']).replace("[last]",unicode(now)))
			#for muc in self.main.client.groupchats.itervalues():
				#self.main.client.sendPresence(show = 'away', status = self.config['awayMessage'].replace('[time]',self.config['awayTime']).replace("[last]",unicode(now)), to = '%s/%s'%(muc.jid, muc.nick))
			self.main.sendPresence(None,'away',self.config['awayMessage'].replace('[time]',self.config['awayTime']).replace("[last]",unicode(now)).replace("[message]",self.currentMessage))
			self.message_set=True




	def on_remove(self):
		print "remove"
		self.mutex.lock()
		self.threadRun=False
		self.mutex.unlock()
		self.finish_cond.wakeAll()
		self.thread.join()

	#def on_idle(self, cas):
		#self.idletime += cas
		#if self.idletime > (int(self.config['away_time']['value'])*60) and not self.message_set:
			#contact = self.main.client.roster['users'][self.main.client.jid.userhost()]
			#self.old_show = contact.resources[self.main.client.jid.resource].show
			#self.old_status = contact.resources[self.main.client.jid.resource].status
			#try:
				#text = self.config['away_text']['value']%(self.idletime/60)
			#except:
				#text = self.config['away_text']['value']
			#self.main.client.sendPresence(show = 'away', status = text)
			#for muc in self.main.client.groupchats.itervalues():
					#self.main.client.sendPresence(show = 'away', status = text, to = '%s/%s'%(muc.jid, muc.nick))
			#self.message_set = True
			#log.msg('idle status poslan')
	
	#def on_active(self):
		#if self.message_set:
			#self.idletime = 0
			#self.message_set = False
			#self.main.client.sendPresence(show = self.old_show, status = self.old_status)
			#for muc in self.main.client.groupchats.itervalues():
				#self.main.client.sendPresence(show = self.old_show, status = self.old_status, to = '%s/%s'%(muc.jid, muc.nick))
