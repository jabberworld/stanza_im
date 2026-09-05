from PyQt4 import QtCore, QtGui
import sys
import os
sys.path.append('.')
from include import plugins, utils
from widgets import dataforms
from widgets.chat import groupchat
import time
from twisted.words.protocols.jabber.xmlstream import IQ
from pyxl.xmlrpclib import loads, dumps
from twisted.words.xish.domish import Element

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'styler'
		self.description = 'Roster Styler'
		self.author = "Jan 'HanzZ' Kaluza"
		self.name = 'Roster Styler'
		self.version = '0.1'
		self.category = ['roster']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.installTranslator()
		if main:
			self.loadConfig()
			self.window=self.loadWindow(self.pluginDir+"/window_ui.py",self.main)
			QtCore.QObject.connect(self.window.ui.gHeight,QtCore.SIGNAL("valueChanged ( int )"),self.gHeightChanged)
			QtCore.QObject.connect(self.window.ui.gFontSize,QtCore.SIGNAL("valueChanged ( int )"),self.gFontSize)
			QtCore.QObject.connect(self.window.ui.gTextCoordinates0,QtCore.SIGNAL("valueChanged ( int )"),self.gTextCoordinates0Changed)
			QtCore.QObject.connect(self.window.ui.gTextCoordinates1,QtCore.SIGNAL("valueChanged ( int )"),self.gTextCoordinates1Changed)
			QtCore.QObject.connect(self.window.ui.gIconCoordinates0,QtCore.SIGNAL("valueChanged ( int )"),self.gIconCoordinates0Changed)
			QtCore.QObject.connect(self.window.ui.gIconCoordinates1,QtCore.SIGNAL("valueChanged ( int )"),self.gIconCoordinates1Changed)
			QtCore.QObject.connect(self.window.ui.pushButton,QtCore.SIGNAL("clicked()"),self.preview)
			QtCore.QObject.connect(self.window.ui.save,QtCore.SIGNAL("clicked()"),self.save)
			QtCore.QObject.connect(self.window.ui.cancel,QtCore.SIGNAL("clicked()"),self.window.close)
			QtCore.QObject.connect(self.window.ui.gBackgroundColor,QtCore.SIGNAL("clicked()"),self.gBackgroundColor)
			QtCore.QObject.connect(self.window.ui.rBackgroundColor,QtCore.SIGNAL("clicked()"),self.rBackgroundColor)
			QtCore.QObject.connect(self.window.ui.rBackground,QtCore.SIGNAL("clicked(bool)"),self.rBackground)
			QtCore.QObject.connect(self.window.ui.gFontColor,QtCore.SIGNAL("clicked()"),self.gFontColor)
			
			QtCore.QObject.connect(self.window.ui.uHeight,QtCore.SIGNAL("valueChanged ( int )"),self.uHeightChanged)
			QtCore.QObject.connect(self.window.ui.uBackgroundColor,QtCore.SIGNAL("clicked()"),self.uBackgroundColor)
			QtCore.QObject.connect(self.window.ui.uIconCoordinates0,QtCore.SIGNAL("valueChanged ( int )"),self.uIconCoordinates0Changed)
			QtCore.QObject.connect(self.window.ui.uIconCoordinates1,QtCore.SIGNAL("valueChanged ( int )"),self.uIconCoordinates1Changed)
			QtCore.QObject.connect(self.window.ui.uFontSize,QtCore.SIGNAL("valueChanged ( int )"),self.uFontSize)
			QtCore.QObject.connect(self.window.ui.uTextCoordinates0,QtCore.SIGNAL("valueChanged ( int )"),self.uTextCoordinates0Changed)
			QtCore.QObject.connect(self.window.ui.uTextCoordinates1,QtCore.SIGNAL("valueChanged ( int )"),self.uTextCoordinates1Changed)
			QtCore.QObject.connect(self.window.ui.uTextCoordinates2,QtCore.SIGNAL("valueChanged ( int )"),self.uTextCoordinates2Changed)
			QtCore.QObject.connect(self.window.ui.uTextCoordinates3,QtCore.SIGNAL("valueChanged ( int )"),self.uTextCoordinates3Changed)
			QtCore.QObject.connect(self.window.ui.uIconSize0,QtCore.SIGNAL("valueChanged ( int )"),self.uIconSize0Changed)
			QtCore.QObject.connect(self.window.ui.uIconSize1,QtCore.SIGNAL("valueChanged ( int )"),self.uIconSize1Changed)
			QtCore.QObject.connect(self.window.ui.uFontColor,QtCore.SIGNAL("clicked()"),self.uFontColor)
			QtCore.QObject.connect(self.window.ui.uAvatarSize0,QtCore.SIGNAL("valueChanged ( int )"),self.uAvatarSize0Changed)
			QtCore.QObject.connect(self.window.ui.uAvatarSize1,QtCore.SIGNAL("valueChanged ( int )"),self.uAvatarSize1Changed)
			QtCore.QObject.connect(self.window.ui.uAvatarCoordinates0,QtCore.SIGNAL("valueChanged ( int )"),self.uAvatarCoordinates0Changed)
			QtCore.QObject.connect(self.window.ui.uAvatarCoordinates1,QtCore.SIGNAL("valueChanged ( int )"),self.uAvatarCoordinates1Changed)
			
			QtCore.QObject.connect(self.window.ui.uStatusFontSize,QtCore.SIGNAL("valueChanged ( int )"),self.uStatusFontSize)
			QtCore.QObject.connect(self.window.ui.uStatusTextCoordinates0,QtCore.SIGNAL("valueChanged ( int )"),self.uStatusTextCoordinates0Changed)
			QtCore.QObject.connect(self.window.ui.uStatusTextCoordinates1,QtCore.SIGNAL("valueChanged ( int )"),self.uStatusTextCoordinates1Changed)
			QtCore.QObject.connect(self.window.ui.uStatusTextCoordinates2,QtCore.SIGNAL("valueChanged ( int )"),self.uStatusTextCoordinates2Changed)
			QtCore.QObject.connect(self.window.ui.uStatusTextCoordinates3,QtCore.SIGNAL("valueChanged ( int )"),self.uStatusTextCoordinates3Changed)
			QtCore.QObject.connect(self.window.ui.uBackgroundAlpha,QtCore.SIGNAL("valueChanged ( int )"),self.uBackgroundAlphaChanged)
			QtCore.QObject.connect(self.window.ui.gBackgroundAlpha,QtCore.SIGNAL("valueChanged ( int )"),self.gBackgroundAlphaChanged)
			QtCore.QObject.connect(self.window.ui.uStatusFontColor,QtCore.SIGNAL("clicked()"),self.uStatusFontColor)
			QtCore.QObject.connect(self.window.ui.uStatusHeight,QtCore.SIGNAL("valueChanged ( int )"),self.uStatusHeight)
			QtCore.QObject.connect(self.window.ui.comboBox,QtCore.SIGNAL("activated ( int )"),self.typChanged)
			self.typ="useritem"
			self.loadRosterStyle()
		else:
			self.loadConfig(homedir)


	def typChanged(self,index):
		if index==0:
			self.typ="useritem"
			self.loadRosterStyle()
		elif index==1:
			self.typ="selected useritem"
			self.loadRosterStyle()
			
	def save(self):
		self.preview()
		d=self.main.realHomeDir+"/rosterstyles/"+unicode(self.window.ui.styleDirectory.text())
		c=unicode(self.window.ui.styleConfig.text())
		if not os.path.isdir(d):
			os.mkdir(d)
		
		self.window.ui.styleConfig.setText(self.main.ui.roster.rosterStyle.configPath.split("/")[-1])
		f=open(d+"/"+c+".cfg",'w')
		self.main.ui.roster.rosterStyle.config.write(f)
		f.close()

		#self.main.ui.roster.rosterStyle.config.write()

	def preview(self):
		self.main.ui.roster.rosterStyle.config['groupitem']['height']=str(self.window.ui.gHeight.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['fontSize']=str(self.window.ui.gFontSize.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['textCoordinates'][0]=str(self.window.ui.gTextCoordinates0.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['textCoordinates'][1]=str(self.window.ui.gTextCoordinates1.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['openedIcon'][0]=str(self.window.ui.gIconCoordinates0.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['openedIcon'][1]=str(self.window.ui.gIconCoordinates1.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['closedIcon'][0]=str(self.window.ui.gIconCoordinates0.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['closedIcon'][1]=str(self.window.ui.gIconCoordinates1.value())
		self.main.ui.roster.rosterStyle.config['groupitem']['textFormat']=unicode(self.window.ui.textFormat.toPlainText())
		
		self.main.ui.roster.rosterStyle.config[self.typ]['height']=str(self.window.ui.uHeight.value())
		self.main.ui.roster.rosterStyle.config[self.typ]['iconCoordinates'][0]=str(self.window.ui.uIconCoordinates0.value())
		self.main.ui.roster.rosterStyle.config[self.typ]['iconCoordinates'][1]=str(self.window.ui.uIconCoordinates1.value())
		self.main.ui.roster.rosterStyle.config[self.typ]['textFormat']=unicode(self.window.ui.uTextFormat.toPlainText())
		self.main.ui.roster.rosterStyle.config[self.typ]['statusTextFormat']=unicode(self.window.ui.uStatusTextFormat.toPlainText())

		self.main.ui.roster.rosterStyle.config['header']['name']=unicode(self.window.ui.styleName.text())
		self.main.ui.roster.rosterStyle.config['header']['author']=unicode(self.window.ui.styleAuthor.text())
		self.main.ui.roster.rosterStyle.config['header']['version']=unicode(self.window.ui.styleVersion.text())
		if self.window.ui.rBackgroundImage.isEnabled():
			if self.main.ui.roster.rosterStyle.config['colors'].has_key('rosterBackground'):
				del self.main.ui.roster.rosterStyle.config['colors']['rosterBackground']
			self.main.ui.roster.rosterStyle.config['images']['rosterBackground']=unicode(self.window.ui.rBackgroundImage.text())
		else:
			if self.main.ui.roster.rosterStyle.config['images'].has_key('rosterBackground'):
				del self.main.ui.roster.rosterStyle.config['images']['rosterBackground']
		
		self.main.ui.roster.rosterStyle.reloadResources()
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def rBackground(self,value):
		if value:
			self.main.ui.roster.rosterStyle.config['colors']['rosterBackground']=["0","0","0"]
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()
		else:
			if self.main.ui.roster.rosterStyle.config['colors'].has_key("rosterBackground"):
				del self.main.ui.roster.rosterStyle.config['colors']['rosterBackground']
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()		
	def gBackgroundAlphaChanged(self,value):
		if len(self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config['groupitem']['backgroundColor'][4]])==4:
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config['groupitem']['backgroundColor'][4]][3]=str(value)
		else:
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config['groupitem']['backgroundColor'][4]].append(str(value))
		self.main.ui.roster.rosterStyle.reloadResources()
		self.main.ui.roster.repaint()

	def uBackgroundAlphaChanged(self,value):
		if len(self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['backgroundColor'][4]])==4:
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['backgroundColor'][4]][3]=str(value)
		else:
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['backgroundColor'][4]].append(str(value))
		self.main.ui.roster.rosterStyle.reloadResources()
		self.main.ui.roster.repaint()

	def rBackgroundColor(self):
		if self.main.ui.roster.rosterStyle.colors.has_key("rosterBackground"):
			color=QtGui.QColorDialog.getColor(self.main.ui.roster.rosterStyle.colors["rosterBackground"])
		else:
			color=QtGui.QColorDialog.getColor()
		if self.main.ui.roster.rosterStyle.config['images'].has_key('rosterBackground'):
			del self.main.ui.roster.rosterStyle.config['images']['rosterBackground']
		if color.isValid():
			self.main.ui.roster.rosterStyle.config['colors']["rosterBackground"]=[str(color.red()),str(color.green()),str(color.blue())]
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()
		
	def gFontColor(self):
		color=QtGui.QColorDialog.getColor(self.main.ui.roster.rosterStyle.colors[self.main.ui.roster.rosterStyle.config['groupitem']['fontColor']])
		if color.isValid():
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config['groupitem']['fontColor']]=[str(color.red()),str(color.green()),str(color.blue())]
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()

	def uFontColor(self):
		color=QtGui.QColorDialog.getColor(self.main.ui.roster.rosterStyle.colors[self.main.ui.roster.rosterStyle.config[self.typ]['fontColor']])
		if color.isValid():
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['fontColor']]=[str(color.red()),str(color.green()),str(color.blue())]
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()

	def uStatusFontColor(self):
		color=QtGui.QColorDialog.getColor(self.main.ui.roster.rosterStyle.colors[self.main.ui.roster.rosterStyle.config[self.typ]['statusFontColor']])
		if color.isValid():
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['statusFontColor']]=[str(color.red()),str(color.green()),str(color.blue())]
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()

			
	def gBackgroundColor(self):
		color=QtGui.QColorDialog.getColor(self.main.ui.roster.rosterStyle.colors[self.main.ui.roster.rosterStyle.config['groupitem']['backgroundColor'][4]])
		if color.isValid():
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config['groupitem']['backgroundColor'][4]]=[str(color.red()),str(color.green()),str(color.blue())]
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()
	
	def uBackgroundColor(self):
		color=QtGui.QColorDialog.getColor(self.main.ui.roster.rosterStyle.colors[self.main.ui.roster.rosterStyle.config[self.typ]['backgroundColor'][4]])
		if color.isValid():
			self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['backgroundColor'][4]]=[str(color.red()),str(color.green()),str(color.blue())]
			self.main.ui.roster.rosterStyle.reloadResources()
			self.main.ui.roster.repaint()
	
	def loadRosterStyle(self):
		self.window.ui.styleDirectory.setText(self.main.ui.roster.rosterStyle.configPath.split("/")[-2])
		self.window.ui.styleConfig.setText(self.main.ui.roster.rosterStyle.configPath.split("/")[-1].replace(".cfg",""))
		self.window.ui.styleName.setText(self.main.ui.roster.rosterStyle.config['header']['name'])
		self.window.ui.styleAuthor.setText(self.main.ui.roster.rosterStyle.config['header']['author'])
		self.window.ui.styleVersion.setText(self.main.ui.roster.rosterStyle.config['header']['version'])
		
		self.window.ui.gHeight.setValue(int(self.main.ui.roster.rosterStyle.config['groupitem']['height']))
		self.window.ui.gFontSize.setValue(int(self.main.ui.roster.rosterStyle.config['groupitem']['fontSize']))
		self.window.ui.gTextCoordinates0.setValue(int(self.main.ui.roster.rosterStyle.config['groupitem']['textCoordinates'][0]))
		self.window.ui.gTextCoordinates1.setValue(int(self.main.ui.roster.rosterStyle.config['groupitem']['textCoordinates'][1]))
		self.window.ui.gIconCoordinates0.setValue(int(self.main.ui.roster.rosterStyle.config['groupitem']['openedIcon'][0]))
		self.window.ui.gIconCoordinates1.setValue(int(self.main.ui.roster.rosterStyle.config['groupitem']['openedIcon'][1]))
		self.window.ui.textFormat.setPlainText(self.main.ui.roster.rosterStyle.config['groupitem']['textFormat'])
		
		self.window.ui.uHeight.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['height']))
		self.window.ui.uIconCoordinates0.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['iconCoordinates'][0]))
		self.window.ui.uIconCoordinates1.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['iconCoordinates'][1]))
		self.window.ui.uTextFormat.setPlainText(self.main.ui.roster.rosterStyle.config[self.typ]['textFormat'])
		self.window.ui.uFontSize.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['fontSize']))
		self.window.ui.uTextCoordinates0.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][0]))
		self.window.ui.uTextCoordinates1.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][1]))
		self.window.ui.uTextCoordinates2.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][2]))
		self.window.ui.uTextCoordinates3.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][3]))
		self.window.ui.uIconSize0.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['iconSize'][0]))
		self.window.ui.uIconSize1.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['iconSize'][1]))
		self.window.ui.uAvatarSize0.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['avatarSize'][0]))
		self.window.ui.uAvatarSize1.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['avatarSize'][1]))
		self.window.ui.uAvatarCoordinates0.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['avatarCoordinates'][0]))
		self.window.ui.uAvatarCoordinates1.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['avatarCoordinates'][1]))
		if len(self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['backgroundColor'][4]])==4:
			self.window.ui.uBackgroundAlpha.setValue(int(self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config[self.typ]['backgroundColor'][4]][3]))
		else:
			self.window.ui.uBackgroundAlpha.setValue(255)
		if len(self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config['groupitem']['backgroundColor'][4]])==4:
			self.window.ui.gBackgroundAlpha.setValue(int(self.main.ui.roster.rosterStyle.config['colors'][self.main.ui.roster.rosterStyle.config['groupitem']['backgroundColor'][4]][3]))
		else:
			self.window.ui.gBackgroundAlpha.setValue(255)
		
		self.window.ui.uStatusTextFormat.setPlainText(self.main.ui.roster.rosterStyle.config[self.typ]['statusTextFormat'])
		self.window.ui.uStatusTextCoordinates0.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][0]))
		self.window.ui.uStatusTextCoordinates1.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][1]))
		self.window.ui.uStatusTextCoordinates2.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][2]))
		self.window.ui.uStatusTextCoordinates3.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][3]))
		self.window.ui.uStatusFontSize.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['statusFontSize']))
		self.window.ui.uStatusHeight.setValue(int(self.main.ui.roster.rosterStyle.config[self.typ]['statusHeight']))
		#pozadi_okrove_srafovane.png
		if self.main.ui.roster.rosterStyle.config['images'].has_key("rosterBackground"):
			self.window.ui.rBackgroundImage.setText(self.main.ui.roster.rosterStyle.config['images']['rosterBackground'])
			self.window.ui.rBackground.setChecked(True)
			self.window.ui.rBackgroundImage1.setChecked(True)
			self.window.ui.rBackgroundColor1.setChecked(False)
		if self.main.ui.roster.rosterStyle.config['colors'].has_key("rosterBackground"):
			self.window.ui.rBackground.setChecked(True)
			self.window.ui.rBackgroundImage1.setChecked(False)
			self.window.ui.rBackgroundColor1.setChecked(True)
		
	def uStatusHeight(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['statusHeight']=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def gFontSize(self,value):
		self.main.ui.roster.rosterStyle.config['groupitem']['fontSize']=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def uFontSize(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['fontSize']=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		

	def uStatusFontSize(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['statusFontSize']=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def uHeightChanged(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['height']=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def gHeightChanged(self,value):
		self.main.ui.roster.rosterStyle.config['groupitem']['height']=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def gIconCoordinates0Changed(self,value):
		self.main.ui.roster.rosterStyle.config['groupitem']['openedIcon'][0]=str(value)
		self.main.ui.roster.rosterStyle.config['groupitem']['closedIcon'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def gIconCoordinates1Changed(self,value):
		self.main.ui.roster.rosterStyle.config['groupitem']['openedIcon'][1]=str(value)
		self.main.ui.roster.rosterStyle.config['groupitem']['closedIcon'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def uIconSize0Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['iconSize'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def uIconSize1Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['iconSize'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def uAvatarSize0Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['avatarSize'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def uAvatarSize1Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['avatarSize'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def uAvatarCoordinates0Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['avatarCoordinates'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def uAvatarCoordinates1Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['avatarCoordinates'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def uIconCoordinates0Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['iconCoordinates'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def uIconCoordinates1Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['iconCoordinates'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def gTextCoordinates0Changed(self,value):
		self.main.ui.roster.rosterStyle.config['groupitem']['textCoordinates'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def gTextCoordinates1Changed(self,value):
		self.main.ui.roster.rosterStyle.config['groupitem']['textCoordinates'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def uStatusTextCoordinates0Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def uStatusTextCoordinates1Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def uStatusTextCoordinates2Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][2]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def uStatusTextCoordinates3Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['statusTextCoordinates'][3]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

		
	def uTextCoordinates0Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][0]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def uTextCoordinates1Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][1]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()

	def uTextCoordinates2Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][2]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
	
	def uTextCoordinates3Changed(self,value):
		self.main.ui.roster.rosterStyle.config[self.typ]['textCoordinates'][3]=str(value)
		self.main.ui.roster.refreshSizes()
		self.main.ui.roster.repaint()
		
	def testSlot(self):
		self.window.show()
	
	def buildMainWindowMenu(self):
		menu=self.mainWindowMenu()
		menu.addAction(self.tr("Edit current roster style"),self.testSlot)
