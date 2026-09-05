"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

This program is free software; you can redistribute it and/or
#modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
from PyQt4 import QtCore, QtGui
import sys; sys.path.append('..')
from widgets.preferences_ui import *
from include import rot13
from include import plugins as pluginTemplate
from pref import jabbim,connection,chat,privacy
from widgets.preferences_bookmarks_ui import *
from configobj import ConfigObj
import os
import pyxl
from imp import load_source
import shutil
from twisted.python import log
import widgets.dataforms as dataforms
from twisted.words.xish import domish
#from twisted.web.microdom import *
import traceback
from widgets.extra import extraDialog
from os.path import basename
from pyxl import jid as jidT
import widgets.webkitthemes as webkitthemes
from widgets.configlib import *
import widgets.privacy as privacyMod
import view
from include.constants import RESOURCEPATH

class preferencesWindow(QtGui.QDialog):
	def __init__(self,main,parent=None,page=0):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.main=main
		self.setModal(False)
		self.ui=Ui_preferences()
		self.ui.setupUi(self)
		self.ui.stackedWidget.setCurrentIndex(page)

		self.ui.saveButton.setIcon(QtGui.QIcon(RESOURCEPATH+'images/16x16/categories/gtk-preferences.png'))
		self.var=[]

		self.justShowed=False
		self.showedPlugins={}

		self.globalCategories={}
		self.globalCategories['notification']=self.tr('Notification')
		self.globalCategories['archive']=self.tr('Archive')
		self.globalCategories['log']=self.tr('Log')
		self.globalCategories['misc']=self.tr('Misc')
		self.globalCategories['jgames']=self.tr('jGames')
		self.globalCategories['disk']=self.tr('Disk')
		self.globalCategories['utils']=self.tr('Utils')
		self.globalCategories['fun']=self.tr('Fun')
		self.globalCategories['other']=self.tr('Other')

		self.preferencesCount=5
		self.preferencesConfig=[]
		# Jabbim
		layout=QtGui.QGridLayout(self.ui.jabbimWidget)
		self.var.append(makePreferences(self.main.config,self.ui.jabbimWidget,layout,jabbim.preferences(self).config)[0])
		self.preferencesConfig.append(jabbim.preferences(self).config)

		# Chat
		layout=QtGui.QGridLayout(self.ui.chatWidget)
		self.var.append(makePreferences(self.main.config,self.ui.chatWidget,layout,chat.preferences(self).config)[0])
		self.preferencesConfig.append(chat.preferences(self).config)

		# connection
		layout=QtGui.QGridLayout(self.ui.connectionWidget)
		self.var.append(makePreferences(self.main.config,self.ui.connectionWidget,layout,connection.preferences(self).config)[0])
		self.preferencesConfig.append(connection.preferences(self).config)

		# privacy
		layout=QtGui.QGridLayout(self.ui.privacyWidget)
		self.var.append(makePreferences(self.main.config,self.ui.privacyWidget,layout,privacy.preferences(self).config)[0])
		self.preferencesConfig.append(privacy.preferences(self).config)
		self.privacyButton=QtGui.QPushButton(self)
		self.privacyButton.setText(self.tr("Privacy editor"))
		QtCore.QObject.connect(self.privacyButton,QtCore.SIGNAL("clicked()"),self.showPrivacyEditor)
		layout.addWidget(self.privacyButton,  0, 0)

		for cfg in self.var:
			for key,value in getVarData(cfg).iteritems():
				if self.main.config['preferencesAdvanced']=="True":
					if self.preferencesConfig[self.var.index(cfg)][key].has_key("category"):
						cfg[key]['widget'].show()
						if cfg[key].has_key("widgets"):
							for widget in cfg[key]["widgets"]:
								widget.show()
				else:
					if self.preferencesConfig[self.var.index(cfg)][key].has_key("category"):
						cfg[key]['widget'].hide()
						if cfg[key].has_key("widgets"):
							for widget in cfg[key]["widgets"]:
								widget.hide()
								
		QtCore.QObject.connect(self.ui.themePackage.page(), QtCore.SIGNAL("frameCreated ( QWebFrame *)"), self.themePackageFrameCreated)

		self.webkitObject=view.webkitObject(self)
		QtCore.QObject.connect(self.ui.themePackage,QtCore.SIGNAL("loadFinished ( bool)"),self.themePackageFinished)
		QtCore.QObject.connect(self.ui.themePackage.page().mainFrame(),QtCore.SIGNAL("javaScriptWindowObjectCleared ()"),self.themePackageCleared)

		# Plugins
		QtCore.QObject.connect(self.ui.applyButton, QtCore.SIGNAL("clicked()"),self.save)
		QtCore.QObject.connect(self.ui.pluginConfiguration, QtCore.SIGNAL("clicked()"),self.pluginConfigurationClicked)
		QtCore.QObject.connect(self.ui.plugins, QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.pluginsContextMenu)
		QtCore.QObject.connect(self.ui.plugins, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem *, int)"),self.pluginSelected)
		QtCore.QObject.connect(self.ui.listWidget, QtCore.SIGNAL("currentItemChanged ( QListWidgetItem * , QListWidgetItem * )"),self.currentItemChanged)
		
		QtCore.QObject.connect(self.ui.morePlugins, QtCore.SIGNAL("clicked()"),self.getMorePlugins)
	
	def loadThemePackages(self):
		self.ui.themePackages.clear()
		packs=os.listdir(RESOURCEPATH+"/themepackages/") + os.listdir(self.main.realHomeDir + "/themepackages/")
		for pack in packs:
			if os.path.isdir(RESOURCEPATH+'/themepackages/'+pack):
				theme = RESOURCEPATH+"/themepackages/" + pack + "/package.cfg"
				if not os.path.isfile(theme):
					theme = self.main.realHomeDir + "/themepackages/" + pack + "/package.cfg"
					if not os.path.isfile(theme):
						continue
				
				themePackage = ConfigObj(theme,encoding='UTF8')
				if len(themePackage)!=0:
					if themePackage.has_key("header"):
						if len(themePackage["header"]["name"])!=0:
							self.ui.themePackages.insertItem(0,themePackage["header"]["name"],QtCore.QVariant(unicode(theme)))
		html, self.chatThemeHtml, self.groupchatThemeHtml, self.emoticonsHtml = view.generateThemePackagePreview(self.main)
		self.webkitObject.setConfig(self.main.config)
		self.ui.themePackage.setHtml(html)

	def themePackageFrameCreated(self, frame, timeout = None):
		if timeout:
			if unicode(frame.frameName()) == "chatThemeFrame" and self.chatThemeHtml[0]:
				frame.setHtml(self.chatThemeHtml[0],QtCore.QUrl("file:///"+self.chatThemeHtml[1]))
			elif unicode(frame.frameName()) == "groupchatThemeFrame" and self.groupchatThemeHtml[0]:
				frame.setHtml(self.groupchatThemeHtml[0],QtCore.QUrl("file:///"+self.chatThemeHtml[1]))
			elif unicode(frame.frameName()) == "emoticonsFrame" and self.emoticonsHtml:
				frame.setHtml(self.emoticonsHtml)
		else:
			self.main.reactor.callLater(0, self.themePackageFrameCreated, frame, True)
	
	def show(self):
		screen = QtGui.QDesktopWidget().screenGeometry()
		size=self.main.preferencesWindow.geometry()
		QtGui.QDialog.show(self)
		self.move((screen.width()-size.width())/2,(screen.height()-size.height())/2)
		if self.main.client:
			self.privacyButton.setEnabled(True)
		else:
			self.privacyButton.setEnabled(False)
		#self.showNormalView()
	
	def showPrivacyEditor(self):
		self.ple=privacyMod.PrivacyListEditorDialog(self,self) 
		self.ple.show()

	def getMorePlugins(self):
		if self.main.client:
			d=extraDialog("plugins",self.main,self.main)
			d.exec_()
		else:
			QtGui.QMessageBox.information(self, self.tr("Informations"),self.tr("You have to be connected to download new plugins."))

	def currentItemChanged(self,item,previous):
		"""
		Called when current preferences item is changed
		"""
		row=self.ui.listWidget.row(item)
		if row==self.preferencesCount-1:
			self.loadThemePackages()
			#self.showNormalView()

		if previous:
			name=unicode(previous.data(32).toString())
			if self.showedPlugins.has_key(name):
				self.plugins[name].on_endPreferences()
		
		name=unicode(item.data(32).toString())
		if self.showedPlugins.has_key(name):
			if not self.showedPlugins[name]:
				plug=self.plugins[name]
				widget=self.ui.stackedWidget.widget(row)
				layout=QtGui.QGridLayout(widget)
				var,row=makePreferences(plug.config,widget,layout,plug.configDialog.config)
				spacerItem = QtGui.QSpacerItem(40,20,QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Expanding)
				layout.addItem(spacerItem,row+1,0)
				self.showedPlugins[name]=var
			self.plugins[name].on_showPreferences(self.ui.stackedWidget.widget(row))

	def reloadPlugins(self):
		for i in range(self.preferencesCount+1,int(self.ui.listWidget.count())):
			self.ui.listWidget.takeItem(self.preferencesCount+1)
			widget=self.ui.stackedWidget.widget(self.preferencesCount+1)
			self.ui.stackedWidget.removeWidget(widget)
			del widget
		for plugin,plug in self.plugins.iteritems():
			if plug.configDialog and plug.showInPreferences and plugin in self.loadedPlugins:
				listItem=QtGui.QListWidgetItem(plug.name,self.ui.listWidget)
				listItem.setData(32,QtCore.QVariant(plugin))
				listItem.setIcon(QtGui.QIcon(plug.preferencesIcon))
				widget=QtGui.QWidget()
				self.ui.stackedWidget.addWidget(widget)
				self.showedPlugins[plugin]=None

	def reloadPreferences(self):
		self.ui.stackedWidget.setCurrentIndex(0)
		self.ui.listWidget.setCurrentRow(0)
		#self.currentTheme=self.main.config['theme']
		self.justShowed=True
		if self.main.client:
			self.ui.profile.hide()
		else:
			self.ui.profile.setText("<b>"+self.tr("Profile:")+"</b> "+unicode(self.main.config['jid']))
			self.ui.profile.show()
		for cfg in self.var:
			updateVarData(cfg,self.main.config)

		self.reloadPlugins_()
		
	def reloadPlugins_(self):
		for i in range(self.preferencesCount+1,int(self.ui.listWidget.count())):
			self.ui.listWidget.takeItem(self.preferencesCount+1)
			widget=self.ui.stackedWidget.widget(self.preferencesCount+1)
			self.ui.stackedWidget.removeWidget(widget)
			del widget
		self.loadedPlugins=self.main.config['plugins']
		self.plugins={}
		self.showedPlugins={}
		self.ui.plugins.clear()
		self.main.pluginManager.findPlugins()
		plugins=self.main.pluginManager.plugins.keys()
		
		categories={}
		for category,translation in self.globalCategories.iteritems():
			categories[category]=QtGui.QTreeWidgetItem(self.ui.plugins)
			categories[category].setText(0,translation)
		for plugin in plugins:
			dir = self.main.pluginManager.plugins[plugin]['dir']
			path = '%s/%s.py' % (dir, plugin)
			try: 
				f=open(path)
			except:
				log.msg('plugin load error: '+plugin)
				continue

			try: 
				plug = load_source(plugin, path, f).Plugin(False, self.main.homeDir, dir)
			except Exception, ex:
				log.msg(plugin+': CHYBA PRI NAHRAVANI => SPATNA SYNTAXE V PLUGINU!')
				message = unicode(traceback.format_exc(), 'utf-8')
				print message
				f.close()
				continue
			plug.main=self.main
			f.close()
			if categories.has_key(plug.category[0]):
				item=QtGui.QTreeWidgetItem(categories[plug.category[0]])
			else:
				item=QtGui.QTreeWidgetItem(categories['other'])
			#widget=QtGui.QCheckBox(self.ui.plugins)
			print plugin,self.loadedPlugins
			item.setFlags(item.flags()|QtCore.Qt.ItemIsUserCheckable)
			if plugin in self.loadedPlugins:
				print "setChecked True"
				#widget.setChecked(True)
				item.setCheckState(0,QtCore.Qt.Checked)
				self.ui.plugins.setItemExpanded(item.parent(),True)
			else:
				item.setCheckState(0,QtCore.Qt.Unchecked)
			#self.ui.plugins.setItemWidget(item,0,widget)
			item.setText(1,plug.name)
			item.setData(32,1,QtCore.QVariant(unicode(plug.description)))
			item.setData(32,0,QtCore.QVariant(unicode(plugin)))
			
			
			self.plugins[plugin]=plug
			if plug.configDialog and plug.showInPreferences and plugin in self.loadedPlugins:
				listItem=QtGui.QListWidgetItem(plug.name,self.ui.listWidget)
				listItem.setData(32,QtCore.QVariant(plugin))
				listItem.setIcon(QtGui.QIcon(plug.preferencesIcon))
				widget=QtGui.QWidget()
				self.ui.stackedWidget.addWidget(widget)
				self.showedPlugins[plugin]=None
			log.msg("plugin "+plugin+" loaded.")
		self.ui.plugins.resizeColumnToContents (0)
		self.ui.plugins.resizeColumnToContents (1)
		for category,item in categories.iteritems():
			if item.childCount()==0:
				self.ui.plugins.setItemHidden(item, True)

	def pluginSelected(self,item,i):
		if item.parent()==None:
			self.ui.pluginConfiguration.setEnabled(False)
			return
		data=item.data(32,0)
		self.ui.pluginDescription.setText(unicode(item.data(32,1).toString()))
		name=unicode(data.toString())
		plugin=self.plugins[name]
		if plugin.configDialog:
			self.ui.pluginConfiguration.setEnabled(True)
		else:
			self.ui.pluginConfiguration.setEnabled(False)

	def pluginsContextMenu(self,pos):
		# make groupchat bookmarks menu
		item=self.ui.plugins.itemFromIndex(self.ui.plugins.indexAt(pos)) # get selected item
		if item.parent()==None:
			return
		data=item.data(32,0)
		name=unicode(data.toString())
		plugin=self.plugins[name]
		if plugin.configDialog:
			menu=QtGui.QMenu(self.ui.plugins) # make menu
			# Join bookmarked groupchat
			action=menu.addAction(self.tr("Plugin Configuration"))
			action.setData(item.data(32,0))
			action.setObjectName("config")
			menu.connect(menu, QtCore.SIGNAL("triggered ( QAction * )"),self.pluginsContextMenuTriggered)
			# set menu position and show
			menu.move(self.ui.plugins.mapToGlobal(pos))
			menu.show()

	def savePluginConfiguration(self,name,var):
		plugin=self.plugins[name]
		plugin.on_saveConfig()
		for key,value in getVarData(var).iteritems():
			plugin.config[key]=value
			print key,"=",unicode(value)
		plugin.writeConfig()
		if self.main.pluginManager.plugins.has_key(name):
			if self.main.pluginManager.plugins[name]['module']:
				self.main.pluginManager.plugins[name]['module'].config=self.plugins[name].config
				self.main.pluginManager.plugins[name]['module'].on_configChanged()

	def pluginConfigurationClicked(self):
		item=self.ui.plugins.currentItem()
		data=item.data(32,0)
		name=unicode(data.toString())
		plugin=self.plugins[name]
		dialog=pluginConfiguration(self.plugins[name],self.ui.plugins)
		dialog.exec_()
		if self.main.pluginManager.plugins.has_key(name):
			if self.main.pluginManager.plugins[name]['module']:
				self.main.pluginManager.plugins[name]['module'].config=self.plugins[name].config
				self.main.pluginManager.plugins[name]['module'].on_configChanged()

	def pluginsContextMenuTriggered(self,action):
		cmd=action.objectName()
		if cmd=="config":
			data=action.data()
			name=unicode(data.toString())
			plugin=self.plugins[name]
			dialog=pluginConfiguration(self.plugins[name],self.ui.plugins)
			dialog.exec_()
		if self.main.pluginManager.plugins.has_key(name):
			if self.main.pluginManager.plugins[name]['module']:
				self.main.pluginManager.plugins[name]['module'].config=self.plugins[name].config
				self.main.pluginManager.plugins[name]['module'].on_configChanged()

	def themePackageCleared(self):
		self.ui.themePackage.page().mainFrame().addToJavaScriptWindowObject("webkitObject",self.webkitObject)

	def themePackageFinished(self,ok):
		pass
		#self.ui.themePackage.page().mainFrame().evaluateJavaScript("makePreview();")

	def save(self):
		#if not self.justShowed:
			
			#self.main.skin=ConfigObj("skins/"+unicode(self.ui.chatSkin_list.currentText()),encoding='UTF8')
			#if not self.main.skin.has_key("spaces_between_lines"):
				#self.main.skin["spaces_between_lines"]='0'

		for name,var in self.showedPlugins.iteritems():
			if var:
				self.savePluginConfiguration(name,var)

		for cfg in self.var:
			for key,value in getVarData(cfg).iteritems():
				if key=='passwd':
					self.main.config[key]=rot13.scramble(unicode(value))
				else:
					self.main.config[key]=value
					if self.main.config['preferencesAdvanced']=="True":
						if self.preferencesConfig[self.var.index(cfg)][key].has_key("category"):
							cfg[key]['widget'].show()
							if cfg[key].has_key("widgets"):
								for widget in cfg[key]["widgets"]:
									widget.show()
					else:
						if self.preferencesConfig[self.var.index(cfg)][key].has_key("category"):
							cfg[key]['widget'].hide()
							if cfg[key].has_key("widgets"):
								for widget in cfg[key]["widgets"]:
									widget.hide()
					
					print key,"=",unicode(value)
		#if not self.justShowed:
			#self.main.config['chatSkin']=unicode(self.ui.chatSkin_list.itemData(self.ui.chatSkin_list.currentIndex()).toString())
		'''if self.main.config['rosterStyle']!=self.webkitObject.rosterstyles:
			self.main.config['rosterStyle']=self.webkitObject.rosterstyles
			self.main.loadRosterStyle()'''
		if self.main.config['chatTheme']!=self.webkitObject.chatTheme or self.main.config['chatTheme']!=self.webkitObject.groupchatTheme:
			if self.webkitObject.chatTheme and self.webkitObject.groupchatTheme:
				self.main.config['chatTheme']=self.webkitObject.chatTheme
				self.main.config['groupchatTheme']=self.webkitObject.groupchatTheme
				self.main.loadSkin()
		if self.main.config['emoticons']!=self.webkitObject.emoticons and self.webkitObject.emoticons:
			self.main.config['emoticons']=self.webkitObject.emoticons
			self.main.emoticonsWidget.reinit()
			#for i in range(self.main.chat.ui.chatTab.count()):
				#w=self.main.chat.ui.chatTab.widget(i)
				#w.chat.loadSmileys()

		#data=item.data(32)
		#file=unicode(data.toString())
		#self.reskin(file)
		
		#self.main.config['jid']=jid
		#self.main.config['resource']=''+resource+''
		#self.main.config['priority']=self.ui.connection_priority.text()
		if self.main.config['theme'] != self.webkitObject.theme and self.webkitObject.theme:
			self.main.config['theme'] = unicode(self.webkitObject.theme)
			self.main.loadTheme()
			
		#if self.main.config['rosterMode']=="compact":
		#	import compactrosterstyle
		#	self.main.ui.roster.setRosterStyle(compactrosterstyle.rosterStyle)
		#elif self.main.config['rosterMode']=='normal':
		#	import defaultrosterstyle
		#	self.main.ui.roster.setRosterStyle(defaultrosterstyle.rosterStyle)
		self.main.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
		QtCore.QObject.disconnect(self.main.scroll.verticalScrollBar(),QtCore.SIGNAL("valueChanged ( int )"),self.main.ui.roster.sliderChanged)
		self.main.ui.roster.setSize()
		self.main.ui.roster.repaint()
		load=False
		for i in range(int(self.ui.plugins.topLevelItemCount())):
			it=self.ui.plugins.topLevelItem(i)
			for child in range(int(it.childCount())):
				item=it.child(child)
				data=item.data(32,0)
				plugin=unicode(data.toString())
				#widget=self.ui.plugins.itemWidget(item,0)
				if item.checkState(0)==QtCore.Qt.Checked and not plugin in self.loadedPlugins:
					if self.main.client:
						self.main.pluginManager.loadPlugin(plugin)
					self.main.config['plugins'].append(plugin)
					self.loadedPlugins=self.main.config['plugins']
					load=True
				elif item.checkState(0)==QtCore.Qt.Unchecked and plugin in self.loadedPlugins:
					if self.main.client:
						self.main.pluginManager.unloadPlugin(plugin)
					self.main.config['plugins'].remove(plugin)
					load=True
		self.main.config.write()
		self.reloadPlugins()

	def accept(self):
		self.save()
		self.done(1)

	def reject(self):
		#if self.main.config['theme']!=self.currentTheme:
			#self.main.config['theme']=self.currentTheme
			#if self.currentTheme!="None":
				#self.reskin(self.currentTheme)
			#else:
				#self.main.loadTheme()
		item=self.ui.listWidget.currentItem()
		print item
		if item:
			name=unicode(item.data(32).toString())
			print name,self.showedPlugins
			if self.showedPlugins.has_key(name):
				self.plugins[name].on_endPreferences()
		return QtGui.QDialog.reject(self)

class editBookmark(QtGui.QDialog):
	def __init__(self,main,room,server,name,nickname,password,autojoin,parent,edit=True):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.parent=parent
		self.room=room
		self.server=server
		self.jid="%s@%s" % (room,server)
		self.main=main
		self.edit=edit
		self.name=name
		self.autojoin=autojoin
		self.setModal(True)
		self.ui=Ui_editbookmark()
		self.ui.setupUi(self)
		self.ui.room.setText(room)
		self.ui.server.setText(server)
		self.ui.name.setText(name)
		self.ui.nickname.setText(nickname)
		self.ui.password.setText(password)
		if ((self.autojoin==True or self.autojoin=="True") or (self.autojoin==1 or self.autojoin=="1")) or self.autojoin=="true":
			self.ui.autojoin.setChecked(True)
		else:
			self.ui.autojoin.setChecked(False)
			
	def accept(self):
		room=unicode(self.ui.room.text())
		server=unicode(self.ui.server.text())
		name=unicode(self.ui.name.text())
		nickname=unicode(self.ui.nickname.text())
		password=unicode(self.ui.password.text())
		autojoin=unicode(self.ui.autojoin.isChecked()).lower()
		if len(name.strip())<1:
			name = room
		edited=False
		if name==self.name:
			self.main.client.bookmarks['conference'][self.jid]=pyxl.client.Bookmark(name, 'conference', room+"@"+server, autojoin, nickname, password)
			#self.done(1)
			edited=True
		else:
			if self.edit==True:
				del self.main.client.bookmarks['conference'][self.jid]
			self.main.client.bookmarks['conference'][self.jid]=pyxl.client.Bookmark(name, 'conference', room+"@"+server, autojoin, nickname, password)
			edited=True
		if edited:
			#self.main.bookmarks=self.bookmarks
			self.main.client.setBookmarks()
			self.main.buildBookmarks()

			self.done(1)
