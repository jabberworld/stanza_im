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
from pyxl.xdata import *
from pyxl.adhoc import Stage, CancelStage
from twisted.python import log
from widgets.configlib import jidListWidget
import os.path
from twisted.python.filepath import FilePath
from twisted.enterprise import adbapi
from twisted.internet import  reactor
s = adbapi.safe

def walk(top, topdown=True, onerror=None):
	from os.path import join, isdir, islink
	from os import listdir, error
	# We may not have read permission for top, in which case we can't
	# get a list of the files the directory contains.  os.path.walk
	# always suppressed the exception then, rather than blow up for a
	# minor reason when (say) a thousand readable directories are still
	# left to visit.  That logic is copied here.
	try:
		# Note that listdir and error are globals in this module due
		# to earlier import-*.
		names = listdir(top)
	except error, err:
		if onerror is not None:
			onerror(err)
		return

	dirs, nondirs = [], []
	for name in names:
		try:
			if isdir(join(top, name)):
				dirs.append(name)
			else:
				nondirs.append(name)
		except:
			continue

	if topdown:
		yield top, dirs, nondirs
	for name in dirs:
		try:
			path = join(top, name)
		except:
			continue
			
		if not islink(path):
			for x in walk(path, topdown, onerror):
				yield x
	if not topdown:
		yield top, dirs, nondirs


class ResendFile(Stage):
	def exec_(self):
		self.status = "executing"
		self.actions = {"cancel":CancelStage, "next":ResendFile, 'prev': ResendFile, "execute":ResendFile}
		self.execute = "next"

		print self.session.args
		files = []
		dirs = []

		print self.data

		if self.data == None or len(self.data['file']) == 0:
			if not self.session.args.has_key('last'):
				print 'nemam last'
				pwd = self.session.args['home']
				self.session.args['last'] = pwd
			else:
				if self.session.args['last'] != self.session.args['home']:
					pwd = os.path.split(self.session.args['last'])[0]
				else:
					pwd = self.session.args['home']
		
		else:

			for file in self.data['file']:
				if file == os.path.pardir:
					dirs.insert(0, file)
				elif os.path.isdir(os.path.join(self.session.args['last'], file)):
					dirs.append(file)
				elif os.path.isfile(os.path.join(self.session.args['last'], file)):
					files.append(file)
		
			print dirs, files
			
			if len(files)>0:
				desc = {}
				fajly = []
				for f in files:
					ff = os.path.join(self.session.args['last'], f)
					desc[ff] = 'EasyShare'
					fajly.append(ff)
				self.main.events.addFTUploadEvent(self.session.jid, fajly, desc)
				self.status = "completed"
				self.execute = None
				self.actions={}
				self.xform = None
				return
			elif len(dirs)>0:
				if dirs[0] == os.path.pardir:
					pwd = os.path.split(self.session.args['last'])[0]
				else:
					pwd = os.path.join(self.session.args['last'], dirs[0])
			else:
				pwd = self.session.args['home']
					
#		elif os.path.isdir(os.path.join(self.data["pwd"][0], self.data["file"][0])):
#			if self.data["file"][0] == os.path.pardir:
#				pwd = os.path.split(self.data["pwd"][0])[0]
#			else:
#				pwd = os.path.join(self.data["pwd"][0], self.data["file"][0])
		files = []
		dirs = []
		
		self.session.args['last'] = pwd
		print pwd, pwd ==  self.session.args['home']
		print self.session.args['home']
		for f in os.listdir(unicode(pwd)):
			try:
				if os.access(os.path.join(pwd,f), os.R_OK):
					if os.path.isfile(os.path.join(pwd,f)):
						files.append([f, f])
					else:
						dirs.append(["%s%s" % (f, os.path.sep), f])
			except:
				print 'chyba v listovani'
		files.sort()
		dirs.sort()
		if pwd != self.session.args['home']:
			dirs.insert(0, ["%s%s (%s)" % (os.path.pardir, os.path.sep, self.main.tr("One directory up")), os.path.pardir])
		dirs.extend(files)

		field = Field("file", "list-multi", self.main.tr("Choose file or directory: "), required=True, options=dirs)
#		field2 = Field("pwd", "hidden", values=[pwd])
		self.xform = Xform("form", fields=[field], title=self.main.tr("Resend file"),instructions=[self.main.tr("Choose file you want to resend from remote system or directory you want to browse."),"PWD: %s" % unicode(pwd)]).buildElement()

class directoryWidget(QtGui.QLineEdit):
	def getDirectory(self):
		directory=unicode(QtGui.QFileDialog.getExistingDirectory(self,self.tr("Choose directory"),self.text(),QtGui.QFileDialog.ShowDirsOnly| QtGui.QFileDialog.DontResolveSymlinks))
		if len(directory)!=0:
			self.setText(directory)

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['__widget__']=customConfigWidget
		#self.config['default-sharepath']={'type':'directory','label':self.main.tr("Path"),'value':''}
		#self.config['default-sharejids']={'type':'jid-list','label':self.main.tr("Allow JIDs"),'value':[]}
		self.config['dirs']={'type':'hidden','label':self.main.tr("Allow JIDs"),'value':[]}

class customConfigWidget(QtGui.QWidget):
	def __init__(self,main,form,parent=None):
		QtGui.QWidget.__init__(self,parent)
		self.form=dict(form)
		for key,value in main.iteritems():
			self.form[key]={'value':value}
		self.currentFolder=None
		# UI
		layout=QtGui.QGridLayout(self)
		
		self.folders=QtGui.QListWidget(self)
		self.folders.setMaximumWidth(175)
		layout.addWidget(self.folders,0,0,1,1)
		
		self.addFolderButton=QtGui.QPushButton(self)
		self.addFolderButton.setText(self.tr("Add folder"))
		layout.addWidget(self.addFolderButton,1,0,1,1)

		self.removeFolderButton=QtGui.QPushButton(self)
		self.removeFolderButton.setText(self.tr("Remove folder"))
		layout.addWidget(self.removeFolderButton,2,0,1,1)

		self.groupbox=QtGui.QGroupBox(self.tr("Folder info"),self)
		layout.addWidget(self.groupbox,0,1,3,1)
		
		glayout=QtGui.QGridLayout(self.groupbox)
		
		l=QtGui.QHBoxLayout()
		label=QtGui.QLabel(self.tr("Path:"))
		l.addWidget(label)
		self.path=directoryWidget(parent)
		self.path.setText(unicode('Choose directory'))
		chooser=QtGui.QPushButton("...")
		l.addWidget(self.path)
		l.addWidget(chooser)
		glayout.addLayout(l,0,0)
		
		self.jids=jidListWidget(self.groupbox)
		#if isinstance(val,list):
			#for jid in val:
				#QtGui.QListWidgetItem(unicode(jid),widget.jids)
		glayout.addWidget(self.jids,1,0)
		
		self.groupbox.setEnabled(False)
		
		# SIGNALS
		QtCore.QObject.connect(self.addFolderButton,QtCore.SIGNAL("clicked()"),self.addFolder)
		QtCore.QObject.connect(self.removeFolderButton,QtCore.SIGNAL("clicked()"),self.removeFolder)
		QtCore.QObject.connect(self.folders,QtCore.SIGNAL("currentItemChanged ( QListWidgetItem * , QListWidgetItem * )"),self.folderChanged)
		QtCore.QObject.connect(chooser,QtCore.SIGNAL("clicked()"),self.path.getDirectory)
		
		# DATA
		for key in self.form['dirs']['value']:
			item=QtGui.QListWidgetItem(self.folders)
			item.setText(key)

	def folderChanged(self,current,previous):
		if previous and self.currentFolder:
			self.form[self.currentFolder+"-sharepath"]['value']=unicode(self.path.text())
			val=[]
			for i in range(self.jids.jids.count()):
				item=self.jids.jids.item(i)
				val.append(unicode(item.text()))
			self.form[self.currentFolder+"-sharejids"]['value']=val

		if current:
			self.currentFolder=unicode(current.text())
			self.path.setText(self.form[self.currentFolder+"-sharepath"]['value'])
			self.jids.jids.clear()
			for jid in self.form[self.currentFolder+"-sharejids"]['value']:
				QtGui.QListWidgetItem(unicode(jid),self.jids.jids)
			self.groupbox.setEnabled(True)
			self.groupbox.setTitle(self.tr("Folder")+" "+self.currentFolder+" "+self.tr("info"))

	def removeFolder(self):
		item=self.folders.currentItem()
		name=unicode(item.text())
		if item:
			item=self.folders.takeItem(self.folders.row(item))
			del item
			del self.form[name+"-sharepath"]
			del self.form[name+"-sharejids"]
			self.form['dirs']['value'].remove(name)
			self.path.setText("")
			self.jids.jids.clear()

	def addFolder(self):
		name,b=QtGui.QInputDialog.getText(self,self.tr("Add folder"), self.tr("Choose folder name"))
		name=unicode(name)
		if len(name)!=0 and b==True:
			item=QtGui.QListWidgetItem(self.folders)
			item.setText(name)
			self.form[name+"-sharepath"]={'value':''}
			self.form[name+"-sharejids"]={'value':[]}
			self.form['dirs']['value'].append(name)
			#self.main.plugins['easyshare']['plugin'].addDir(name)

	def getData(self):
		# returns dict in format {configKey:value}
		self.folderChanged(None,self.folders.currentItem())
		ret={}
		for key,value in self.form.iteritems():
			if not key.startswith("__"):
				val=value['value']
				ret[key]=val
		return ret

	def updateData(self,form):
		#updates data
		pass

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'easyshare'
		self.installTranslator()
		self.description = self.tr('Easy filesharing')
		self.author = "Jiri 'Sef' Gabrys"
		self.name = self.tr('EasyShare')
		self.version = '0.029'
		self.category = ['utils']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.plugindir = plugindir
		self.configDialog=config(self)
		self.searches = []
		

		if main:
			self.loadConfig()
			
			path = unicode(QtGui.QDesktopServices.storageLocation(QtGui.QDesktopServices.DocumentsLocation)) + "/Jabbim shared folder"
			print "storage location", path
			if not os.path.isdir(path):
				os.mkdir(path)
				self.config["Documents-sharepath"]=path
				self.config["Documents-sharejids"]=[]
				self.config['dirs'].append("Documents")
				self.writeConfig()
			
			self.registerHandler('on_authd',self.on_authd)
			if self.main.isConnected() and self.main.client.xmlstream:
				self.on_authd()
			self.db = adbapi.ConnectionPool('sqlite3', homedir+'/search.db', cp_min=1, cp_max=1)
			self.initDb()
		else:
			self.loadConfig(homedir)
		
	
	def initDb(self):
		def _table_created(res):
			print 'search table created'
		self.db.runQuery('create table files (path text, share text, hash text);').addCallback(_table_created)
	
	def indexShares(self): #manual use only
		for addr in self.config['dirs']:
			reactor.callInThread(self.indexDir, self.config[addr+'-sharepath'],  addr)

	def getPermission(self,  path,  jid):
		try:
			addr = path.split('/')[0]
			if jid in self.config[addr+'-sharejids'] or jid== self.main.client.jid.userhost():
				return True
			else:
				return False
		except:
			log.err('error while getting sharing permissions')
			return False
	
	def getHash(self,  path):
		try:
			fp = open(path, 'rb')
		except:
			return None
		size = 1024*1024
		sh = sha1('')
		rd = fp.read(size)
		while len(rd)>0:
			sh.update(rd)
			rd = fp.read(size)
		fp.close()
		return sh.hexdigest()
	
	def indexDir(self,  directory,  share):
		def _chyba(error):
			print 'CHYBA!'
#			print error
			print error.filename

		for root, dirs, fajly in walk(directory,  onerror = _chyba):
			for file in fajly:
				hash = self.getHash(root+'/'+file)
				dir = root.replace(directory, share+'/')
				if hash == None:
					continue
				self.db.runOperation('insert into files (path,share,hash) values("%s","%s","%s")'%(s(dir+'/'+file), s(share), hash))

	
	def addDir(self, dir):
		self.config['dirs'].append(dir)
		self.config[dir+'-sharejids'] = [self.main.client.jid.userhost()]
		self.config[dir+'-sharepath'] = self.plugindir
		self.writeConfig()
	
	
	def on_authd(self):
		for addr in self.config['dirs']:
			self.main.client.commands.registerNode("http://dev.jabbim.cz/jabbim/rc#easyshare-%s"%addr, addr, ResendFile, public = self.config[addr+'-sharejids'], args = {'home':self.config[addr+'-sharepath']})
		self.registerFeature("http://dev.jabbim.cz/jabbim/easyshare")
		self.main.client.rpc.registerHandler('getShares', self.getShares)
		self.main.client.rpc.registerHandler('listShare', self.listShare)
		self.main.client.rpc.registerHandler('getFiles', self.getFiles)
		self.main.client.rpc.registerHandler('searchFiles', self.searchFiles)

	def getShares(self, frm, par = None):
		frm = jidT.JID(frm).userhost()
		available = []
		try:
			for addr in self.config['dirs']:
				if self.getPermission(addr, frm):
					available.append(addr)
			return (available,)
		except:
			print 'getshare problem'
			print frm, par, self.config
			return
	
	def listShare(self, frm, par):
		frm = jidT.JID(frm).userhost()
		share = par[0]
		addr = share.split('/')[0]
		if addr in self.config['dirs']:
			if self.getPermission(addr,  frm):
				return threads.deferToThread(self.listdir, par[0].replace(addr, self.config[addr+'-sharepath']))
#				return self.listdir(par[0].replace(addr, self.config[addr+'-sharepath']))
		return
	
	def listdir(self, dr):
		print dr
		path = FilePath(dr.encode(sys.getfilesystemencoding()))
		out = []
		for f in path.listdir():
			print type(dr), type(f)
			try:
				cesta = path.child(unicode(f).encode(sys.getfilesystemencoding()))
			except:
				continue
			if cesta.isdir():
				t = (f.encode('utf8', 'xmlcharrefreplace'), '-1')
			else:
				t = (f.encode('utf8', 'xmlcharrefreplace'), unicode(cesta.getsize()))
			out.append(t)
		print out
		return (out,)
	
	def getFiles(self, frm, par):
		print frm, par
		fr = jidT.JID(frm).userhost()
		files = par[0]
		fajly = {}
		desc = {}
		for f in files:
			addr = f.split('/')[0]
			print addr
			if addr in self.config['dirs']:
				if self.getPermission(addr,  fr):
					fajly[os.path.basename(f.replace(addr, self.config[addr+'-sharepath']))]=f.replace(addr, self.config[addr+'-sharepath']) # strip first /
					desc[os.path.basename(f.replace(addr, self.config[addr+'-sharepath']))] = '%s >> %s'%('EasyShare',fr)
		print fajly
		fajly2 = {}
		for rel,  abs in fajly.iteritems():
			if os.path.isdir(abs):
				del desc[rel]
				for root, dirs, files in os.walk(abs):
#					print root, dirs, files
					dir = root.replace(abs, rel)
					for file in files:
						fajly2[dir+'/'+file] =root+'/'+file
						desc[dir+'/'+file] = '%s >> %s'%('EasyShare',fr)
			else:
				fajly2[rel] = abs
		print desc
		print fajly2
		if len(fajly2)>0:
			self.main.events.addFTUploadEvent(frm, fajly2, desc,forceTree=True)
			return (True, )
		else:
			return(False, )
	
	def searchFiles(self,  frm,  par):
		def _results(results):
			res = [] # [(jid, path, hash), ..]
			for result in results:
				if result[0] == True:
					res.append(self.main.client.jid.full(), result[1][0],  result[1][1])
			print 'search results>> ',  res
			if len (res)>0:
				return (res,  )
			else:
				return (False, )

		
		sid = par[1]
		string = par[0]
		try:
			typ = par[2]
		except:
			#to znamena ze tam neni tento parametr a tedy hleda primo jid ze ktereho to prislo
			typ = frm
		shares = self.getShares(typ)[0]
		if len(shares=0) or sid in self.searches:
			return (False, )
		else:
			dl = []
			self.searches.append(sid)
			for share in shares:
				d = self.db.runQuery('select path, hash from files where share="%s" and path like "%%%s%%"'%(s(share),  s(string)))
				dl.append(d)
			return defer.deferredList(dl).addCallback(_results)
			
		
	def on_configChanged(self):
		for addr in self.config['dirs']:
			self.main.client.commands.unregisterNode("http://dev.jabbim.cz/jabbim/rc#easyshare-%s"%addr, addr)

		for addr in self.config['dirs']:
			self.main.client.commands.registerNode("http://dev.jabbim.cz/jabbim/rc#easyshare-%s"%addr, addr, ResendFile, public = self.config[addr+'-sharejids'], args = {'home':self.config[addr+'-sharepath']})
	
	def on_remove(self):
		for addr in self.config['dirs']:
			self.main.client.commands.registerNode("http://dev.jabbim.cz/jabbim/rc#easyshare-%s"%addr, addr, ResendFile, public = self.config[addr+'-sharejids'], args = {'home':self.config[addr+'-sharepath']})
		self.unregisterFeature("http://dev.jabbim.cz/jabbim/easyshare")
		self.main.client.rpc.unregisterHandler('getShares')
		self.main.client.rpc.unregisterHandler('listShare')
		self.main.client.rpc.unregisterHandler('getFiles')
		self.main.client.rpc.unregisterHandler('searchFiles')

	
	def buildContactMenu(self, menu, contact):
		self.menu=menu.addMenu(self.tr("EasyShare"))
		self.menu.setIcon(QtGui.QIcon("%s/easy_share32.png" % self.pluginDir))
		myJid = contact.jid == self.main.client.jid.userhost()
			
		for addr in self.config['dirs']:
			action = self.menu.addAction(addr)
			action.setData(QtCore.QVariant(QtCore.QStringList([unicode(contact.jid), unicode(addr)])))
			action.setObjectName(addr+"share")
			action.setCheckable(True)
			if myJid:
				action.setChecked(True)
				action.setEnabled(False)
			else:
				if unicode(contact.jid) in self.config[addr+'-sharejids']:
					action.setChecked(True)
				else:
					action.setChecked(False)
		QtCore.QObject.connect(self.menu,QtCore.SIGNAL("triggered ( QAction * )"),self.toggled)
		
	def toggled(self, b):
		jid, addr = [unicode(val.toString()) for val in b.data().toList()]
		if jid in self.config[addr+'-sharejids']:
			self.config[addr+'-sharejids'].remove(jid)

		else:
			self.config[addr+'-sharejids'].append(jid)
		self.writeConfig()
		self.on_configChanged()
		self.menu.deleteLater()


