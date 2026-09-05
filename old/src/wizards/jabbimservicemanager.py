# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import jsm_ui
import weakref
from widgets import servicediscovery, dataforms, legacyforms
from widgets.addcontactng import showDict, addDict, showWeather, addWeather
from twisted.internet import defer
from pyxl import jid
import random

class jabbimServiceManager(QtGui.QDialog):
	def __init__(self,main,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.ui=jsm_ui.Ui_JabbimServiceManager()
		self.ui.setupUi(self)
		self.main=weakref.ref(main)
		self.ui.treeWidget.hideColumn(2)
		self.ui.jids.hide()
		self.ui.add.hide()
		self.addFunc=None
		QtCore.QObject.connect(self.ui.treeWidget,QtCore.SIGNAL("currentItemChanged(QTreeWidgetItem *,QTreeWidgetItem *)"),self.itemChanged)
		QtCore.QObject.connect(self.ui.configure,QtCore.SIGNAL("clicked()"),self.configure)
		QtCore.QObject.connect(self.ui.add,QtCore.SIGNAL("clicked()"),self.add)
		QtCore.QObject.connect(self.ui.reg,QtCore.SIGNAL("clicked()"),self.register)
		QtCore.QObject.connect(self.ui.advanced,QtCore.SIGNAL("clicked()"),self.advanced)
		self.loadServices()

	def advanced(self):
		self.discovery=servicediscovery.serviceDiscoveryDialog(self.main,self)
		self.discovery.show()
		self.hide()

	def _onRegister(self,data):
		if not data:
			return
		jid,legacy,form=data
		if form!=None:
			self.dialog=dataforms.dataFormsDialog(self.main(),form,jid,"register",self)
			self.dialog.show()
		else:
			self.dialog=legacyforms.legacyFormsDialog(self.main(),legacy,jid,"disco",self)
			self.dialog.show()

	def register(self):
		item = self.ui.treeWidget.currentItem()
		if not item:
			return
		registered=unicode(item.text(2))[0]=="0"
		jid=unicode(item.data(0,32).toString())
		print jid,registered
		if not registered:
			if jid=="disk.jabbim.cz":
				self.registerJabberDisk()
				self.setItemRegistered(item,True)
			elif jid in ["weather.jabbim.com","dict.jabbim.cz"]:
				self.configure()
			elif jid == 'news.jabbim.cz':
				self.main().client.setRegisterForm('news.jabbim.cz', legacy = {})
				self.setItemRegistered(item,True)
				self.configure()
			else:
				d=self.main().client.getRegisterForm(jid)
				d.addCallback(self._onRegister)
				self.main().autoAdd[jid]={"name":jid,"group":""}
				
		else:
			if jid=="disk.jabbim.cz":
				self.unregisterJabberDisk()
				self.setItemRegistered(item,False)
			elif jid=="dict.jabbim.cz":
				self.removeServiceContacts("dict.jabbim.cz")
				self.setItemRegistered(item,False)
			elif jid=="weather.jabbim.com":
				self.removeServiceContacts("weather.jabbim.com")
				self.setItemRegistered(item,False)
			elif jid == 'news.jabbim.cz':
				self.removeServiceContacts("news.jabbim.cz")
				self.main().client.setRegisterForm('news.jabbim.cz', remove = True, legacy = {})
				self.setItemRegistered(item,False)
			else:
				self.removeServiceContacts(jid)
				self.main().client.setRegisterForm(jid, remove = True, legacy = {})
				self.setItemRegistered(item,False)

	def setItemRegistered(self,item,registered):
		if registered:
			item.setText(2,"0"+unicode(item.data(0,32).toString()))
			item.setIcon(0,QtGui.QIcon("images/16x16/actions/ok.png"))
		else:
			item.setText(2,"1"+unicode(item.data(0,32).toString()))
			item.setIcon(0,QtGui.QIcon())
		self.ui.treeWidget.resizeColumnToContents(0)
		self.ui.treeWidget.sortItems(2,QtCore.Qt.AscendingOrder)
		self.itemChanged(item,None)

	def add(self):
		if self.addFunc:
			self.addFunc(self.main(),self.ui.jids)
		if (self.ui.treeWidget.currentItem().text(2))[0]=="1":
			self.setItemRegistered(self.ui.treeWidget.currentItem(),True)
		self.itemChanged(self.ui.treeWidget.currentItem(),None)

	def configure(self):
		item = self.ui.treeWidget.currentItem()
		if not item:
			return

		if unicode(item.data(0,32).toString())=="dict.jabbim.cz":
			showDict(self,self.main(),self.ui.jids)
			self.ui.reg.hide()
			self.ui.configure.hide()
			self.ui.add.show()
			self.ui.textBrowser.hide()
			self.ui.jids.show()
			self.addFunc=addDict

		elif unicode(item.data(0,32).toString())=='news.jabbim.cz':
			d = self.discoverNewsItems()
			d.addCallback(self.showNewsItems)

		elif unicode(item.data(0,32).toString())=="weather.jabbim.com":
			showWeather(self.main(),self.ui.jids)
			self.ui.reg.hide()
			self.ui.configure.hide()
			self.ui.add.show()
			self.ui.textBrowser.hide()
			self.ui.jids.show()
			self.addFunc=addWeather
		else:
			d=self.main().client.getRegisterForm(unicode(item.data(0,32).toString()))
			d.addCallback(self._onRegister)

	def itemChanged(self,item,old):
		if item:
			self.ui.add.hide()
			if unicode(item.text(2))[0]=="0":
				self.ui.reg.setText(self.tr("Unregister"))
				if not unicode(item.data(0,32).toString()) in ["disk.jabbim.cz"]:
					self.ui.configure.show()
			else:
				self.ui.configure.hide()
				self.ui.reg.setText(self.tr("Register"))
			self.ui.reg.show()
			self.ui.jids.hide()
			self.ui.textBrowser.setHtml(item.data(1,32).toString())
			self.ui.textBrowser.show()

	def loadServices(self):
		self.ui.treeWidget.clear()
		trans=['twitter.jabbim.com','icq.netlab.cz','icq.jabber.cz','icq.jabbim.cz','sms.netlab.cz','sms.jabbim.cz']
		servs=['dict.jabbim.cz','weather.jabbim.com','disk.jabbim.cz', 'news.jabbim.cz']
		transports={}
		services={}
		for transport in trans:
			transports[transport]=False
		for service in servs:
			services[service]=False

		for jd in self.main().client.roster['users'].keys():
			for transport in services:
				if jd.find(transport)!=-1:
					services[transport]=True
					break
			for transport in transports:
				if self.main().getJid(jd).userhost()==transport:
					transports[transport]=True
					break


		self.addService(self.tr("Dictionaries"),"dict.jabbim.cz",self.tr("<b>Dictionaries</b><br/>Dictionaries service allows you to translate words between languages from your Jabbim client."),services["dict.jabbim.cz"])
		self.addService(self.tr("Weather"),"weather.jabbim.com",self.tr("<b>Weather</b><br/>Weather service allows you to see actual weather in big cities."),services["weather.jabbim.com"])
		self.addService(self.tr("Jabber Disk"),"disk.jabbim.cz",self.tr("<b>Jabber Disk</b><br/>Jabber Disk allows you to upload files to Jabbim server where they can be downloaded by your friends."),services["disk.jabbim.cz"])
		self.addService(self.tr('Jabbim News'), 'news.jabbim.cz', self.tr('<b>Jabbim News</b><br/>RSS service with custom RSS feeds for Jabbim VIP users'), services['news.jabbim.cz'])
		self.addService(self.tr("SMS Vodafone/O2"),"sms.netlab.cz",self.tr("<b>SMS Vodafone/O2</b><br/>SMS Vodafone/O2 allows you to send SMS messages straight from your Jabbim Client."),transports["sms.netlab.cz"])
		self.addService(self.tr("Twitter"),"twitter.jabbim.com",self.tr("<b>Twitter</b><br/>Twitter transport allows you to send new tweets to Twitter and chat with your friends who use Twitter."),transports["twitter.jabbim.com"])
		if transports["icq.netlab.cz"]:
			self.addService(self.tr("ICQ"),"icq.netlab.cz",self.tr("<b>ICQ</b><br/>ICQ transport allows you to chat with your friends who use ICQ."),transports["icq.netlab.cz"])
		elif transports["icq.jabbim.cz"]:
			self.addService(self.tr("ICQ"),"icq.jabbim.cz",self.tr("<b>ICQ</b><br/>ICQ transport allows you to chat with your friends who use ICQ."),transports["icq.jabbim.cz"])
		elif transports['icq.jabber.cz']:
			self.addService(self.tr("ICQ"),"icq.jabber.cz",self.tr("<b>ICQ</b><br/>ICQ transport allows you to chat with your friends who use ICQ."),transports["icq.jabber.cz"])
		else:
			if self.main().client.isVip:
				self.addService(self.tr("ICQ"),"icq.jabbim.cz",self.tr("<b>ICQ</b><br/>ICQ transport allows you to chat with your friends who use ICQ."),transports["icq.jabbim.cz"])
			else:
				icq = random.choice(['icq.jabber.cz', 'icq.netlab.cz'])
				self.addService(self.tr("ICQ"),icq,self.tr("<b>ICQ</b><br/>ICQ transport allows you to chat with your friends who use ICQ."),transports[icq])
		#self.addService(self.tr("Weather"),"weather.jabbim.cz",self.tr("<b>Weather</b><br/>Weather service allows you to see actual weather in big cities.<br/>"),transports["weather.netlab.cz"])
		self.ui.treeWidget.resizeColumnToContents(0)
		self.ui.treeWidget.setMaximumWidth(180)
		self.ui.treeWidget.setMinimumWidth(180)
		self.ui.treeWidget.sortItems(2,QtCore.Qt.AscendingOrder)

	def addService(self,name,jid,description,registered=False):
		item=QtGui.QTreeWidgetItem(self.ui.treeWidget)
		item.setText(1,name)
		item.setIcon(1,self.main().getIcon(jid,status="online",size="16x16"))
		item.setData(0,32,QtCore.QVariant(unicode(jid)))
		item.setData(1,32,QtCore.QVariant(unicode(description)))
		if registered:
			item.setIcon(0,QtGui.QIcon("images/16x16/actions/ok.png"))
			item.setText(2,"0"+unicode(jid))
		else:
			item.setIcon(0,QtGui.QIcon())
			item.setText(2,"1"+unicode(jid))

	def _unregisterICQ(self,data=None):
		if not data:
			d=self.main().client.setRegisterForm("icq.jabber.cz",legacy = {}, remove=True)
			d.addCallback(self._unregisterICQ)
		else:
			jid="icq.jabber.cz"
			self.main().client.delContact(jid)
			j = self.main().getJid(jid)
			for jd in self.main().client.roster['users'].iterkeys():
				if jd.find(j.host) != -1:
					self.main().client.delContact(jd)

	def removeServiceContacts(self,jid):
		self.main().client.delContact(jid)
		j = self.main().getJid(jid)
		for jd in self.main().client.roster['users'].iterkeys():
			if jd.find(j.host) != -1:
				self.main().client.delContact(jd)

	def unregisterJabberDisk(self):
		if self.main().client.roster['users'].has_key("public@disk.jabbim.cz"):
			self.main().client.delContact("public@disk.jabbim.cz")
		if self.main().client.roster['users'].has_key("private@disk.jabbim.cz"):
			self.main().client.delContact("private@disk.jabbim.cz")
		if self.main().client.roster['users'].has_key("album@disk.jabbim.cz"):
			self.main().client.delContact("album@disk.jabbim.cz")
		#self.main().client.reactor.callLater(1,self.loadServices)

	def registerJabberDisk(self,data=None):
		if not data:
			d=self.main().client.getRegisterForm("disk.jabbim.cz")
			d.addCallback(self.registerJabberDisk)
		else:
			self.main().autoAdd['public@disk.jabbim.cz']={"name":self.tr("Public"),"group":"Disk"}
			self.main().autoAdd['private@disk.jabbim.cz']={"name":self.tr("Private"),"group":"Disk"}
			self.main().autoAdd['album@disk.jabbim.cz']={"name":self.tr("Album"),"group":"Disk"}
			self.main().client.setRegisterForm("disk.jabbim.cz",legacy={})
			#self.main().client.reactor.callLater(2,self.loadServices)

	def discoverNewsItems(self):
		categories = {}
		def _gotCategories(cat):
			#print cat
			categories = cat
			dl = []
			for key in cat.iterkeys():
				dl.append(self.main().client.getDiscoItems(key))
				categories[key] = {'name':cat[key].get('name', key.split('@')[0]), 'feeds':{}}
			return defer.DeferredList(dl).addCallback(_gotFeeds, categories)
		def _gotFeeds(feeds, categories):
			#print feeds
			for data in feeds:

				if data[0]:
					jd = None
					for feed in data[1].itervalues():
						print feed
						if jd == None:
							jd = jid.JID(feed['jid']).userhost()
						categories[jd]['feeds'][feed['jid']]=feed
						categories[jd]['feeds'][feed['jid']]['registered'] = False
			return self.main().client.getRegisterForm('news.jabbim.cz').addCallback(_gotReg,categories)

		def _gotReg( data, categories):
			print data
			text = data[1]['instructions']
			radky = text.split('\n')[1:]
			kat = None
			for radek in radky:
				if radek.endswith(':'):
					kat = radek.replace(':','').strip()
				else:
					if kat != None:
						feed = radek.strip()
						feed = feed[1:]
						if feed != '':
							categories[kat+'@news.jabbim.cz']['feeds'][kat+'@news.jabbim.cz/'+feed]['registered'] = True
			return categories


		d = self.main().client.getDiscoItems('news.jabbim.cz').addCallback(_gotCategories)
		return d

	def showNewsItems(self, categories):
		def _registerFeeds(mainWindow, treeWidget):
			for i in range(0,int(treeWidget.topLevelItemCount())):
				kategorie=treeWidget.topLevelItem(i)

				for x in range(0,kategorie.childCount()):
					item = kategorie.child(x)

					if item.checkState(0)!=item.registered:
						item.registered=not item.registered
						if item.checkState(0)==QtCore.Qt.Checked:
							print unicode(item.jid)
							mainWindow.client.setRegisterForm(unicode(item.jid), legacy = {})

						else:
							mainWindow.client.setRegisterForm(unicode(item.jid), legacy = {}, remove = True)


		self.ui.jids.clear()
		for kat, val in categories.iteritems():
			kategorie = QtGui.QTreeWidgetItem([val['name']])
			kategorie.jid = kat
			self.ui.jids.addTopLevelItem(kategorie)

			for feed, data in val['feeds'].iteritems():
				feedItem =QtGui.QTreeWidgetItem([data['name']])
				feedItem.jid = feed
				if data['registered']:
					feedItem.registered=QtCore.Qt.Checked
					feedItem.setCheckState(0,QtCore.Qt.Checked)
				else:
					feedItem.setCheckState(0,QtCore.Qt.Unchecked)
					feedItem.registered=QtCore.Qt.Unchecked
				kategorie.addChild(feedItem)
		QtCore.QObject.connect(self.ui.jids,QtCore.SIGNAL("itemDoubleClicked(QTreeWidgetItem * , int)"),self.itemDoubleClicked)
		self.ui.reg.hide()
		self.ui.configure.hide()
		self.ui.add.show()
		self.ui.textBrowser.hide()
		self.ui.jids.show()
		self.addFunc = _registerFeeds
		pass

	def itemDoubleClicked(self, item, col):
		if unicode(item.jid) == 'private@news.jabbim.cz':
			d=self.main().client.getRegisterForm(unicode(item.jid))
			d.addCallback(self._onRegister)
