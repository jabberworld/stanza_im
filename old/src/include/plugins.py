"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
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
import sys
from configobj import ConfigObj
from twisted.python import log
from imp import load_source
from PyQt4 import QtCore, QtGui
import utils
from os.path import basename
from widgets.configlib import pluginConfiguration

class PluginBase(object):
	def __init__(self, main, homedir, plugindir):
		self.main = main #: mainWindow
		self.config = None #: configuration loaded by configObj
		self.configDialog = None #: configuration dialog in Jabbim Configuration API format
		self.description = 'basic plugin class' #: plugin description
		self.author = "Jiri 'Sef' Gabrys" #: plugin author
		self.name = 'Basic plugin' #: plugin name
		self.fname = '' #: name of directory where is plugin saved. Directory must have the same name as main plugin file.
		self.version = '0.1' #: plugin version. Must be in float() format
		self.category = ['test', 'misc'] #: plugin category
		self.url = 'dev.jabbim.cz/jabbim' #: link to plugin homepage
		self.homeDir = homedir #: current profile directory (~/.jabbim/your@jabber.id/)
		self.pluginDir = plugindir #: this plugin directory
		self.showInPreferences=False #: True - plugin configuration will be showed in main list in preferences
		self.preferencesIcon=QtGui.QIcon() #: icon for plugin configuration in preferences
		self._handlers = [] #: contains functions which are connected to pyxl
		self._handlersCache = []
		self._translator=None #: QTranslator
		self._loadedWidgets=[] #: widgets loaded by this plugin
		self._registeredFeatures=[] #: features for Caps registered by this plugin
		self._mainWindowActions=[]

	def registerFeature(self,feature):
		"""
		Registers feature for http://jabber.org/protocol/disco#info.
		@type feature: unicode
		@param feature: feature name (for example http://jabber.org/protocol/muc) - U{http://www.xmpp.org/registrar/disco-features.html}
		@rtype: boolean
		@return: True if features was registered. False if feature is already registered.
		@see: L{unregisterFeature}
		"""
		if not feature in self._registeredFeatures:
			self.main.client.registerFeature(feature)
			self.main.client.rebuildCaps()
			self._registeredFeatures.append(feature)
			return True
		return False

	def unregisterFeature(self,feature):
		"""
		Unregisters feature for http://jabber.org/protocol/disco#info.
		@type feature: unicode
		@param feature: feature name (for example http://jabber.org/protocol/muc) - U{http://www.xmpp.org/registrar/disco-features.html}
		@rtype: boolean
		@return: True if features was unregistered. False if feature is not registered.
		@see: L{registerFeature}
		"""
		if feature in self._registeredFeatures:
			self.main.client.unregisterFeature(feature)
			self.main.client.rebuildCaps()
			self._registeredFeatures.remove(feature)
			return True
		return False

	def showPluginConfigDialog(self,name,parent=None):
		if self.main.plugins.has_key(name) and self.main.plugins[name]['module']:
			dialog=pluginConfiguration(self.main.plugins[name]['module'],parent)
			dialog.exec_()
			if self.main.plugins.has_key(name):
				if self.main.plugins[name]['module']:
					#self.main.plugins[name]['module'].config=self.plugins[name].config
					self.main.plugins[name]['module'].on_configChanged()

	def isNotificationEnabled(self):
		if self.main.selfStatus=="dnd" and self.main.config["notifyOnDND"]=="False":
			return False
		return True

	def mainWindowMenu(self):
		"""
		Makes submenu in MainWindow menu and returns it
		@rtype: QtGui.QMenu
		@return: menu
		@see: L{buildMainWindowMenu}
		"""
		menu=self.main.ui.menuPlugins.addMenu(unicode(self.name))
		return menu

	def mainWindowToolBarAction(self,icon,text,callback):
		#button=QtGui.QToolButton(self.main.ui.transportsWidget)
		#self.main.ui.transportsWidget.layout().insertWidget(self.main.ui.transportsWidget.layout().count()-1,button)
		#self.registerWidget(button)
		action = self.main.ui.pluginsToolbar.addAction(icon,text,callback)
		self._mainWindowActions.append(action)
		return action

	def loadModule(self,file):
		f=open(utils.path(file))
		u=None
		u=load_source(basename(file).replace('.','_'), utils.path(file), f)
		f.close()
		return u

	def _loadUi(self,file,wid):
		"""
		Loads widget from ui file.
		"""
		wid.ui=None
		# load python class
		ui = None
		f=open(utils.path(file))
		ui=load_source(basename(file).replace('.','_'), utils.path(file), f)
		f.close()
		# find Ui_ function and setup widget
		for func in dir(ui):
			if func.startswith("Ui_"):
				wid.ui=getattr(ui, func)()
				wid.ui.setupUi(wid)
		if wid.ui==None:
			# something goes wrong
			return None
		# append widget to loaded wigets list and return it
		self._loadedWidgets.append(wid)
		return wid

	def registerSound(self,name,path):
		if not self.main.sounds.has_key(name):
			self.main.sounds[name]=path
			return True
		return False

	def registerWidget(self,widget):
		if not widget in self._loadedWidgets:
			self._loadedWidgets.append(widget)
			return True
		return False
	
	def unregisterWidget(self,widget):
		if widget in self._loadedWidgets:
			
			if widget.parent():
				if widget.parent().layout():
					widget.parent().layout().removeWidget(widget)
				widget.setParent(None)
			widget.hide()
			widget.close()
			self._loadedWidgets.remove(widget)
			widget.deleteLater()
			del widget
			#del widget
			return True
		return False

	#def _translate("MainWindow", "Upload", None, QtGui.QApplication.UnicodeUTF8)):
	def _translate(self,context, text, temp, encoding):
		return self.tr(text,context)

	def loadWidget(self,file,parent=None):
		"""
		Loads QtGui.QWidget from .py file created from .ui by pyuic4.
		@type file: unicode
		@param file: full path to .py file
		@type parent: QtGui.QWidget
		@param parent: parent of widget
		@return: QtGui.QWidget or None if widget was not loaded
		@see: L{loadWindow}, L{loadDialog}, U{QtGui.QWidget<http://www.riverbankcomputing.com/Docs/PyQt4/html/qwidget.html>}
		"""
		wid=QtGui.QWidget(parent)
		wid.translate=self._translate
		return self._loadUi(file,wid)

	def loadWindow(self,file,parent=None):
		"""
		Loads QtGui.QMainWindow from .py file created from .ui by pyuic4.
		@type file: unicode
		@param file: full path to .py file
		@type parent: QtGui.QWidget
		@param parent: parent of window
		@return: QtGui.QMainWindow or None if widget was not loaded
		@see: L{loadWidget}, L{loadDialog}, U{QtGui.QWidget<http://www.riverbankcomputing.com/Docs/PyQt4/html/qmainwindow.html>}
		"""
		wid=QtGui.QMainWindow(parent)
		wid.translate=self._translate
		return self._loadUi(file,wid)

	def loadDialog(self,file,parent=None):
		"""
		Loads QtGui.QDialog from .py file created from .ui by pyuic4.
		@type file: unicode
		@param file: full path to .py file
		@type parent: QtGui.QWidget
		@param parent: parent of window
		@return: QtGui.QDialog or None if widget was not loaded
		@see: L{loadWidget}, L{loadWindow}, U{QtGui.QWidget<http://www.riverbankcomputing.com/Docs/PyQt4/html/qdialog.html>}
		"""
		wid=QtGui.QDialog(parent)
		wid.translate=self._translate
		return self._loadUi(file,wid)

	def installTranslator(self, directory=""):
		"""
		Installs translator and loads translation file according to locales.
		Files are stored in the same directory as main plugin python file of this plugin.
		File name must be in format xx.qm . For example cs.qm or en.qm .
		@see: L{tr}
		"""
		self._translator = utils.loadTranslator(self.pluginDir + '/'+ directory)

	def tr(self,text,cl=None,comment=None,numeric=None):
		"""
		Translate text. L{installTranslator} must be called first otherwise returns untrasnlated text.
		@type text: str
		@param text: text for translation
		@type cl: str
		@param cl: class of translation. None for default class
		@rtype: unicode
		@return: translated text
		@see: L{installTranslator}
		"""
		if not self._translator:
			return text
		if numeric!=None: #plural forms
			if cl:
				trans=self._translator.translate(cl,text,comment,numeric)
			else:
				trans=self._translator.translate("Plugin",unicode(text),comment,numeric)
			if len(trans)==0:
				trans=self._translator.translate("self.main",text,comment,numeric)
				if len(trans)==0:
					#print "cant translate'",text,"'"
					return text.replace("%n",str(numeric))
			return trans.replace("%n",str(numeric))
		else:
			if cl:
				trans=self._translator.translate(cl,text)
			else:
				trans=self._translator.translate("Plugin",text)
			if len(trans)==0:
				trans=self._translator.translate("self.main",text)
				if len(trans)==0:
					#print "cant translate'",text,"'"
					return text
			return trans

	def on_configChanged(self):
		pass

	def getConfig(self,config):
		"""
		Loads external config in INI format.
		@type config: unicode
		@param config: path to config
		@rtype: configObj
		@return: loaded config as configObj class
		"""
		return ConfigObj(config,encoding='UTF8')

	def buildMainWindowToolBar(self):
		pass

	def buildMainWindowMenu(self):
		"""
		Called when mainWindow menu is building. You can make new item to the menu with this example code:
		
		C{menu=self.mainWindowMenu()}
		C{menu.addAction(self.tr("New item"),self.functionCalledByThisItem)}
		@type feature: unicode
		@param feature: feature name (for example http://jabber.org/protocol/muc) - U{http://www.xmpp.org/registrar/disco-features.html}
		@see: L{mainWindowMenu}, L{buildContactMenu}, U{QtGui.QMenu<http://www.riverbankcomputing.com/Docs/PyQt4/html/qmenu.html>}
		"""
		pass
	
	def buildContactMenu(self,menu,contact):
		"""
		Called when menu above contact is building.
		
		C{}
		@type menu: QtGui.QMenu
		@param menu: contact menu
		@type contact: Pyxl.Contact
		@param contact: contact for whom is menu created
		@see: L{buildMainWindowMenu}, L{buildGroupchatContactMenu}, U{QtGui.QMenu<http://www.riverbankcomputing.com/Docs/PyQt4/html/qmenu.html>}
		"""
		pass

	def buildGroupchatContactMenu(self,menu,jid,user):
		"""
		Called when menu above groupchat contact is building.
		
		C{}
		@type menu: QtGui.QMenu
		@param menu: groupchat contact menu
		@type jid: unicode
		@param jid: groupchat contacts JID (for example jabbim@conf.netlab.cz/HanzZ)
		@type user: pyxl.groupchat.MUCContact
		@param user: contact for whom is menu created or None if user is not in pyxl evidence
		@see: L{buildMainWindowMenu}, L{buildContactMenu}, U{QtGui.QMenu<http://www.riverbankcomputing.com/Docs/PyQt4/html/qmenu.html>}
		"""
		pass

	def buildChatWidget(self,jid,layout,widget):
		"""
		Called when new chatWidget is created. Typically here are created plugin buttons
		@type jid: unicode
		@param jid: Jabber ID
		@type layout: QtGui.QHBoxLayout
		@param layout: QHBoxLayout where buttons created in this function can be added
		@type widget: chatWidget
		@param widget: chatWidget
		@see: L{buildGroupchatWidget}, U{QtGui.QHBoxLayout<http://www.riverbankcomputing.com/Docs/PyQt4/html/qhboxlayout.html>}
		"""
		pass

	def buildGroupchatWidget(self,jid,layout,widget):
		"""
		Called when new groupchatWidget is created. Typically here are created plugin buttons
		@type jid: unicode
		@param jid: Jabber ID
		@type layout: QtGui.QHBoxLayout
		@param layout: QHBoxLayout where buttons created in this function can be added
		@type widget: groupchatWidget
		@param widget: groupchatWidget
		@see: L{buildChatWidget}, U{QtGui.QHBoxLayout<http://www.riverbankcomputing.com/Docs/PyQt4/html/qhboxlayout.html>}
		"""
		pass

	def on_saveConfig(self):
		"""
		Called when this plugin configuration is changed.
		"""
		pass

	def on_showPreferences(self,dialog):
		"""
		Called when this plugin preferences dialog is showed.
		@type dialog: QtGui.QWidget
		@parem dialog: QWidget where are preferences showed
		@see: L{on_endPreferences}
		"""
		pass

	def on_endPreferences(self):
		"""
		Called when user rejected this plugin configuration.
		@see: L{on_showPreferences}
		"""
		pass

	def on_messageSend(self,message):
		"""
		Called when user wants to send normal (chat) message. If this function returns True, message will be send by Jabbim.
		If it returns False, message will not be send and it's on plugin what to do.
		@type jid: unicode
		@param jid: Jabber ID of recipient
		@type text: unicode
		@param text: Plain text of message
		@type xhtml: unicode
		@param xhtml: XHTML part of message
		@type composite: unicode
		@param composite: string for U{chat state notification<http://www.xmpp.org/extensions/xep-0085.html>}
		@rtype: boolean
		@return: True - message will be processed by Jabbim too, False - message will be processed only by plugin
		@see: L{on_groupchatMessageSend}
		"""
		return message

	def on_groupchatMessageSend(self,jid,text="",xhtml="",composite=""):
		"""
		Called when user wants to send groupchat message. If this function returns True, message will be send by Jabbim.
		If it returns False, message will not be send and it's on plugin what to do.
		@type jid: unicode
		@param jid: Jabber ID of recipient
		@type text: unicode
		@param text: Plain text of message
		@type xhtml: unicode
		@param xhtml: XHTML part of message
		@type composite: unicode
		@param composite: string for U{chat state notification<http://www.xmpp.org/extensions/xep-0085.html>}
		@rtype: boolean
		@return: True - message will be processed by Jabbim too, False - message will be processed only by plugin
		@see: L{on_messageSend}
		"""
		return True

	def loadConfig(self,homedir=None):
		"""
		Loads default plugin config. Config will be loaded to L{config} dict.
		If it returns False, message will not be send and it's on plugin what to do.
		@see: L{writeConfig}
		"""
		if homedir==None:
			homedir=self.main.homeDir

		self.config = ConfigObj(utils.path(homedir+'/'+self.fname+'-config.ini'),encoding='UTF8')
		if self.configDialog:
			# sets default values for variables which aren't in loaded config file
			for k,v in self.configDialog.config.iteritems():
				if not self.config.has_key(k) and not k.startswith("__"):
					self.config[k] = v['value']
					self.config.write()

	def userChanged(self,jid):
		# load new config
		if self.configDialog:
			self.loadConfig()

	def clientCreated(self):
		print "client created called",self._handlersCache
		for handler in self._handlersCache:
			self.registerHandler(*handler)

	def writeConfig(self):
		"""
		Saves default config.
		@see: L{loadConfig}
		"""
		if self.config:
			self.config.write()
	
	def registerHandler(self, name, method, priority = 5):
		"""
		Registers Jabbim events handler. If Jabbim generates event, all plugins subscribed to this event will
		be informed.
		@type name: unicode
		@param name: event name
		@type method: function
		@param method: function which will be called if the event is generated
		"""
		#print "registerHandler",self.main.client
		if self.main.client:
			self.main.client.dispatcher.registerHandler(name, method, self.name, priority = priority)
			self._handlers.append(name)
		else:
			self._handlersCache.append([name,method,priority])

	def unregisterHandler(self, name):
		if self.main.client:
			self.main.client.dispatcher.unregisterHandler(name, self.name)
	
	def on_remove(self):
		"""
		Called before this plugin unload.
		"""
		pass
	
	def _remove(self):
		"""
		Prepares plugin for unload. Deletes opened windows, unregister features etc...
		"""
		try:
			self.on_remove()
		except:
			print "chyba v on_remove!!!!"
			pass
		# delete windows
		#for window in self._loadedWidgets:
			#window.close()
		for i in range(int(len(self._loadedWidgets))):
			self.unregisterWidget(self._loadedWidgets[0])
			#del self._loadedWidgets[0]
		for i in range(int(len(self._mainWindowActions))):
			self.main.ui.pluginsToolbar.removeAction(self._mainWindowActions[0])
			del self._mainWindowActions[0]
		# save config
		self.writeConfig()
		# unregister pyxl handlers
		for handler in self._handlers:
			self.main.client.dispatcher.unregisterHandler(handler, unicode(self.name))
		# unregister features
		for i in range(len(self._registeredFeatures)):
			self.unregisterFeature(self._registeredFeatures[0])
		self._registeredFeatures=[]
		self.main = None
		self.config = None
		self.configDialog = None
		self.description = 'basic plugin class'
		self.author = "Jiri 'Sef' Gabrys"
		self.name = 'Basic plugin'
		self.version = '0.1'
		self.category = ['test', 'misc']
		self.url = 'dev.jabbim.cz/jabbim'
		self._handlers = []
		self.homeDir = None
		self._translator=None
		self._loadedWidgets=[]
		if sys.modules.has_key(self.fname):
			print "deleting plugin %s from sys.modules" % self.fname
			del sys.modules[self.fname]
		self.fname = ''
