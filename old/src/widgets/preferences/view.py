"""
Copyright (C) 2009 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2009	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

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
import os, sys
from widgets import webkitthemes
from widgets.extra import extraDialog
from PyQt4 import QtCore, QtGui
import weakref
from configobj import ConfigObj
from include.constants import RESOURCEPATH

class webkitObject(QtCore.QObject):
	def __init__(self,preferences):
		QtCore.QObject.__init__(self)

		self.preferences = weakref.ref(preferences)
		self.setObjectName("webkitObject")
		self.emoticons = None
		self.chatTheme = None
		self.groupchatTheme = None
		self.rosterstyles = None
		self.theme = None
		self.html = ""

	def setConfig(self,config):
		self.emoticons = unicode(config["emoticons"])
		self.chatTheme = unicode(config["chatTheme"])
		self.groupchatTheme = unicode(config["groupchatTheme"])
		self.rosterstyles = unicode(config["rosterStyle"])
		self.theme = unicode(config["theme"])
		
		if self.rosterstyles.find("/") == -1:
			self.rosterstyles += "/"

	@QtCore.pyqtSignature("",result = "QString")
	def getHtml(self):
		return self.html

	@QtCore.pyqtSignature("QString")
	def getMore(self, typ):
		if self.preferences().main.client:
			d=extraDialog(unicode(typ),self.preferences().main,self.preferences().main)
			d.exec_()
		else:
			mainWindow = self.preferences().main
			QtGui.QMessageBox.information(self.preferences(), mainWindow.tr("Informations"), mainWindow.tr("You have to be connected to download new addons."))

	@QtCore.pyqtSignature("QString, QString")
	def selectChanged(self, typ, value):
		if typ == "emoticons":
			self.emoticons = unicode(value)
			frames = self.preferences().ui.themePackage.page().mainFrame().childFrames()
			for frame in frames:
				if frame.frameName() == "emoticonsFrame":
					frame.setHtml(generateEmoticonsPreview(self.preferences().main,unicode(value)))

		elif typ == "chatTheme":
			self.chatTheme = unicode(value) + "/" + self.chatTheme.split("/")[1]
			self.html, style = populateChatThemeStyleList(self.preferences().main,self.chatTheme)
			self.chatTheme = self.chatTheme.split("/")[0] + "/" + style
			self.preferences().ui.themePackage.page().mainFrame().evaluateJavaScript('document.getElementById("chatThemeStyleDiv").innerHTML = webkitObject.getHtml();')
			frames = self.preferences().ui.themePackage.page().mainFrame().childFrames()
			for frame in frames:
				if frame.frameName() == "chatThemeFrame":
					html, path = generateChatThemePreview(self.preferences().main,self.chatTheme)
					frame.setHtml(html, QtCore.QUrl("file:///" + path))

		elif typ == "groupchatTheme":
			self.groupchatTheme = unicode(value) + "/" + self.groupchatTheme.split("/")[1]
			self.html, style = populateChatThemeStyleList(self.preferences().main,self.groupchatTheme)
			self.html = self.html.replace("\"chatTheme","\"groupchatTheme").replace("'chatTheme","'groupchatTheme")
			self.groupchatTheme = self.groupchatTheme.split("/")[0] + "/" + style
			self.preferences().ui.themePackage.page().mainFrame().evaluateJavaScript('document.getElementById("groupchatThemeStyleDiv").innerHTML = webkitObject.getHtml();')
			frames = self.preferences().ui.themePackage.page().mainFrame().childFrames()
			for frame in frames:
				if frame.frameName() == "groupchatThemeFrame":
					html, path = generateChatThemePreview(self.preferences().main,self.groupchatTheme)
					frame.setHtml(html, QtCore.QUrl("file:///" + path))

		elif typ == "chatThemeVariant":
			self.chatTheme = self.chatTheme.split("/")[0]  + "/" + unicode(value)
			frames = self.preferences().ui.themePackage.page().mainFrame().childFrames()
			for frame in frames:
				if frame.frameName() == "chatThemeFrame":
					html, path = generateChatThemePreview(self.preferences().main,self.chatTheme)
					frame.setHtml(html, QtCore.QUrl("file:///" + path))

		elif typ == "groupchatThemeVariant":
			self.groupchatTheme = self.groupchatTheme.split("/")[0]  + "/" + unicode(value)
			frames = self.preferences().ui.themePackage.page().mainFrame().childFrames()
			for frame in frames:
				if frame.frameName() == "groupchatThemeFrame":
					html, path = generateChatThemePreview(self.preferences().main,self.groupchatTheme)
					frame.setHtml(html, QtCore.QUrl("file:///" + path))
					
	'''	elif typ == "rosterstyles":
			self.rosterstyles = unicode(value) + "/" + self.rosterstyles.split("/")[1]
			self.html, style = populateRosterStylesVariantList(self.preferences().main,self.rosterstyles)
			self.rosterstyles = self.rosterstyles.split("/")[0] + "/" + style
			self.preferences().ui.themePackage.page().mainFrame().evaluateJavaScript('document.getElementById("rosterStyleDiv").innerHTML = webkitObject.getHtml();')

		elif typ == "rosterStylesVariant":
			self.rosterstyles = self.rosterstyles.split("/")[0]  + "/" + unicode(value)
			
		elif typ == "jabbimstyles":
			self.theme = unicode(value)
			self.html = generateJabbimStylePreview(self.preferences().main, self.theme)
			self.preferences().ui.themePackage.page().mainFrame().evaluateJavaScript('document.getElementById("jabbimStyleDiv").innerHTML = webkitObject.getHtml();')'''

def populateJabbimStylesList(mainWindow, config):
	ret = '<form name="jabbimStyleForm"><label>' + unicode(mainWindow.tr("Name: ")) + '<select name="jabbimstyles" size="1" onchange="webkitObject.selectChanged(\'jabbimstyles\',this.options[this.selectedIndex].value);">'
	if config == "None":
		ret += '<option selected value="None">' + unicode(mainWindow.tr("Don't use themes")) + "</option>"
	else:
		ret += '<option value="None">' + unicode(mainWindow.tr("Don't use themes")) + "</option>"
	skins=os.listdir("themes/")
	for skin in skins:
		if os.path.isdir("themes/"+skin) and os.path.exists("themes/"+skin+"/style.css"):
			#preview=QtGui.QIcon('themes/'+skin+"/preview.png")
			conf=ConfigObj("themes/"+skin+"/theme.ini",encoding='UTF8')
			if conf!=None and len(conf)!=0:
				#text="<b>"+self.tr("Name: ")+"</b> "+conf['name']+'<br/>'
				#text+="<b>"+self.tr("Author: ")+"</b> "+conf['author']+'<br/>'
				#text+="<b>"+self.tr("Version: ")+"</b> "+conf['version']
				#text="<b>"+self.tr("Name: ")+"</b> "+conf['name']+'<br/>'
				#text+="<b>"+self.tr("Author: ")+"</b> "+conf['author']+'<br/>'
				#text+="<b>"+self.tr("Version: ")+"</b> "+conf['version']
				try:
					text = conf['name']
				except:
					text = skin
			else:
				text = skin

			if skin==config:
				ret += '<option selected value="' + skin + '" >' + text + "</option>"
			else:
				ret += '<option value="' + skin + '">' + text + "</option>"
	ret += "</select></label></form>"
	return ret


def populateRosterStylesList(mainWindow, config):
	ret = '<form name="rosterStyleForm"><label>' + unicode(mainWindow.tr("Name: ")) + '<select name="rosterstyles" size="1" onchange="webkitObject.selectChanged(\'rosterstyles\',this.options[this.selectedIndex].value);">'
	packs=os.listdir("rosterstyles/")
	loaded=[]
	for pack in packs:
		if os.path.isdir('rosterstyles/'+pack):
			#skins=os.listdir('chatskins/'+pack+"/")
			#for skin in skins:
			path=pack
			if not path in loaded:
				loaded.append(path)
				if path==config.split("/")[0]:
					ret += '<option selected value="' + path + '" >' + path + "</option>"
				else:
					ret += '<option value="' + path + '">' + path + "</option>"

	packs=os.listdir(mainWindow.realHomeDir+'/rosterstyles/')
	for pack in packs:
		if os.path.isdir(mainWindow.realHomeDir+'/rosterstyles/'+pack):
			#skins=os.listdir('chatskins/'+pack+"/")
			#for skin in skins:
			path=pack
			if not path in loaded:
				loaded.append(path)
				if path==config.split("/")[0]:
					ret += '<option selected value="' + path + '" >' + path + "</option>"
				else:
					ret += '<option value="' + path + '">' + path + "</option>"

	ret += "</select></label></form>"
	return ret

def populateRosterStylesVariantList(mainWindow,config):
	ret = '<form name="chatThemeVariantForm"><label>' + unicode(mainWindow.tr("Variant: ")) + '<select name="rosterstylesVariant" size="1" onchange="webkitObject.selectChanged(\'rosterstylesVariant\',this.options[this.selectedIndex].value);">'
	path = config.split("/")[0]
	
	variants=[]
	if os.path.isdir("rosterstyles/"+path):
		variants+=os.listdir("rosterstyles/"+path)
	if os.path.isdir(mainWindow.realHomeDir+"/rosterstyles/"+path):
		variants+=os.listdir(mainWindow.realHomeDir+"/rosterstyles/"+path)
	v=""
	default=""
	for variant in variants:
		if variant.endswith(".cfg"):
			default=unicode(variant)
			if variant==config.split("/")[1]:
				ret += '<option selected value="' + variant + '" >' + variant + "</option>"
				v=unicode(variant)
			else:
				ret += '<option value="' + variant + '">' + variant + "</option>"
				if not v:
					v=unicode(variant)

	ret += "</select></label></form>"
	return ret,v

def populateEmoticonsList(mainWindow,em):
	ret = '<form name="emoticonsForm"><label>' + unicode(mainWindow.tr("Name: ")) + '<select name="emoticons" size="1" onchange="webkitObject.selectChanged(\'emoticons\',this.options[this.selectedIndex].value);">'
	# emoticons from Jabbim root directory
	packs=os.listdir(RESOURCEPATH+"/emoticons/")
	for pack in packs:
		if os.path.isdir(RESOURCEPATH+'/emoticons/'+pack):
			emoticons=os.listdir(RESOURCEPATH+'/emoticons/'+pack+"/")
			for emoticon in emoticons:
				if emoticon.endswith('.cfg'):
					emo=pack+"/"+emoticon
					#config=ConfigObj("emoticons/"+emo,encoding='UTF8')
					loaded,config = mainWindow.resourceManager.loadJabbimExtraConfig(RESOURCEPATH+"/emoticons/"+emo,'emoticons/default/smileys.cfg')
					if loaded:
						if emo == em:
							ret += '<option selected value="' + emo + '" >' + unicode(config['header']['name']) + "</option>"
						else:
							ret += '<option value="' + emo + '">' + unicode(config['header']['name']) + "</option>"
						#if emo==currentEmoticons:
							#item=self.ui.emoticonsList.insertItem(0,QtGui.QIcon('emoticons/'+os.path.dirname(emo)+"/"+unicode(config['header']['frontImage'])),unicode(config['header']['name']),QtCore.QVariant(emo))
						#else:
							#item=self.ui.emoticonsList.addItem(QtGui.QIcon('emoticons/'+os.path.dirname(emo)+"/"+unicode(config['header']['frontImage'])),unicode(config['header']['name']),QtCore.QVariant(emo))
	
	# emoticons from users home directory
	packs=os.listdir(mainWindow.realHomeDir+"/emoticons")
	for pack in packs:
		if os.path.isdir(mainWindow.realHomeDir+"/emoticons/"+pack):
			emoticons=os.listdir(mainWindow.realHomeDir+"/emoticons/"+pack+"/")
			for emoticon in emoticons:
				if emoticon.endswith('.cfg'):
					emo=pack+"/"+emoticon
					#config=ConfigObj(mainWindow.realHomeDir+"/emoticons/"+emo,encoding='UTF8')
					loaded,config = mainWindow.resourceManager.loadJabbimExtraConfig(mainWindow.realHomeDir+"/emoticons/"+emo,'emoticons/default/smileys.cfg')
					if loaded:
						if emo == em:
							ret += '<option selected value="' + emo + '" >' + unicode(config['header']['name']) + "</option>"
						else:
							ret += '<option value="' + emo + '">' + unicode(config['header']['name']) + "</option>"

	ret += "</select></label></form>"
	return ret

def populateChatThemeList(mainWindow,default):
	ret = '<form name="chatThemeForm"><label>' + unicode(mainWindow.tr("Name: ")) + '<select name="chatTheme" size="1" onchange="webkitObject.selectChanged(\'chatTheme\',this.options[this.selectedIndex].value);">'
	# chat skins from Jabbim root directory
	packs=os.listdir(RESOURCEPATH+"/chatskins/")
	for pack in packs:
		if os.path.isdir(RESOURCEPATH+'/chatskins/'+pack) and os.path.isdir(RESOURCEPATH+'/chatskins/'+pack+"/Incoming"):
			if pack == default.split("/")[0]:
				ret += '<option selected value="' + pack + '" >' + pack + "</option>"
			else:
				ret += '<option value="' + pack + '">' + pack + "</option>"

	# chat skins from Jabbim home directory
	packs=os.listdir(mainWindow.realHomeDir+"/chatskins/")
	for pack in packs:
		if os.path.isdir(mainWindow.realHomeDir+'/chatskins/'+pack) and os.path.isdir(mainWindow.realHomeDir+'/chatskins/'+pack+'/Incoming'):
			if pack == default.split("/")[0]:
				ret += '<option selected value="' + pack + '" >' + pack + "</option>"
			else:
				ret += '<option value="' + pack + '">' + pack + "</option>"

	ret += "</select></label></form>"
	return ret

def populateChatThemeStyleList(mainWindow,chatTheme):
	ret = '<form name="chatThemeVariantForm"><label>' + unicode(mainWindow.tr("Variant: ")) + '<select name="chatThemeVariant" size="1" onchange="webkitObject.selectChanged(\'chatThemeVariant\',this.options[this.selectedIndex].value);">'
	path = chatTheme.split("/")[0]
	if os.path.exists(RESOURCEPATH+"/chatskins/"+path+"/Variants"):
		variants=os.listdir(RESOURCEPATH+"/chatskins/"+path+"/Variants")
	else:
		variants=os.listdir(mainWindow.realHomeDir+"/chatskins/"+path+"/Variants")
	v=None
	default=""
	for variant in variants:
		if variant.endswith(".css"):
			default=unicode(variant)
			if variant==chatTheme.split("/")[1]:
				ret += '<option selected value="' + variant + '" >' + variant + "</option>"
				v=unicode(variant)
			else:
				ret += '<option value="' + variant + '">' + variant + "</option>"
				if not v:
					v = unicode(variant)

	ret += "</select></label></form>"
	return ret,v

def generateJabbimStylePreview(mainWindow,skin):
	if os.path.isdir(RESOURCEPATH+"/themes/"+skin) and os.path.exists(RESOURCEPATH+"/themes/"+skin+"/style.css"):
		preview = RESOURCEPATH+'/themes/'+skin+"/preview.png"
		if os.path.isfile(preview):
			return '<img width="128" height="128" src="file://%s" />' % preview
	return ''


def generateEmoticonsPreview(mainWindow,pack):
	src = RESOURCEPATH+'/emoticons/'
	#config=ConfigObj("emoticons/"+path,encoding='UTF8')
	loaded,config = mainWindow.resourceManager.loadJabbimExtraConfig(RESOURCEPATH+"/emoticons/"+pack,'emoticons/default/smileys.cfg')
	if not loaded or len(config)==0:
		#config=ConfigObj(mainWindow.mainWindow.realHomeDir+"/emoticons/"+path,encoding='UTF8')
		src=mainWindow.realHomeDir+'/emoticons/'
		loaded,config = mainWindow.resourceManager.loadJabbimExtraConfig(mainWindow.realHomeDir+"/emoticons/"+pack,'emoticons/default/smileys.cfg')
		if not loaded:
			return None
	html="<html><head></head><body>"
	values=[]
	for k,v in config['emoticons'].iteritems():
		#mainWindow.smileys[k.replace("<","&lt;").replace(">","&gt;")]=v
		if not v in values:
			ppth = os.path.join(src,os.path.dirname(pack),v)
			ppth = os.path.abspath(ppth)
			html+='<img src="file:///'+ppth+'" />'
			values.append(v)
	html += "</body></html>"
	return html

def generateChatThemePreview(mainWindow,pack):
	factory=webkitthemes.webkitThemeFactory(pack,pack,mainWindow.realHomeDir)
	html="""
<html xmlns="http://www.w3.org/1999/xhtml">
<meta http-equiv="content-type" content="text/html; charset=utf-8" />
<style type="text/css" media="screen,print"> @import url( "main.css" ); </style>
<style id="mainStyle" type="text/css" media="screen,print"> %s </style>
</head>
<body>
<div id="Chat">
<div id="myDiv"> </div>
	""" % factory.genChatStyleSheet()

	html+="""
</div>
<a name='bottom'></a>
</body>
</html>
	"""

	jabbim_icon = RESOURCEPATH + "/images/32x32/apps/jabbim.png"
	html+=factory.genIncomingContent(unicode(mainWindow.tr("User")),unicode(mainWindow.tr("Message for me")),mainWindow.now(),jabbim_icon)
	html+=factory.genIncomingNextContent(unicode(mainWindow.tr("User")),unicode(mainWindow.tr("Second message for me")),mainWindow.now(),jabbim_icon)
	html+=factory.genChatStatus(unicode(mainWindow.tr("User is now away")),mainWindow.now())
	html+=factory.genOutgoingContent(unicode(mainWindow.tr("Me")),unicode(mainWindow.tr("Message for user")),mainWindow.now(),jabbim_icon)
	html+=factory.genOutgoingNextContent(unicode(mainWindow.tr("Me")),unicode(mainWindow.tr("Second message for user")),mainWindow.now(),jabbim_icon)
	
	return html, factory.cPath

def generateThemePackagePreview(mainWindow):
	config=mainWindow.config
	ret = "<html><head></head><body>"

	emoticons = generateEmoticonsPreview(mainWindow,config["emoticons"])
	ret += "<h3>" + unicode(mainWindow.tr("Emoticons")) + "<span style=\"float: right;text-align:right;\"><a href=\"#\" onclick=\"webkitObject.getMore('emoticons')\">" + unicode(mainWindow.tr("Get more!")) + "</a></span></h3>"
	ret += populateEmoticonsList(mainWindow,config["emoticons"])
	ret += '<iframe src="blank" width="100%" height="120" frameborder="0" name="emoticonsFrame"></iframe>'

	chatTheme, cPath = generateChatThemePreview(mainWindow,config["chatTheme"])
	ret += "<h3>" + unicode(mainWindow.tr("Chat theme")) + "<span style=\"float: right;text-align:right;\"><a href=\"#\" onclick=\"webkitObject.getMore('chatskins')\">" + unicode(mainWindow.tr("Get more!")) + "</a></span></h3>"
	ret += populateChatThemeList(mainWindow,config["chatTheme"])
	ret += "<div id=\"chatThemeStyleDiv\">" + populateChatThemeStyleList(mainWindow,config["chatTheme"])[0] + "</div>"
	ret += '<iframe src="blank" width="100%" height="120" frameborder="0" name="chatThemeFrame"></iframe>'

	groupchatTheme, gPath = generateChatThemePreview(mainWindow,config["groupchatTheme"])
	ret += "<h3>" + unicode(mainWindow.tr("Groupchat theme")) + "<span style=\"float: right;text-align:right;\"><a href=\"#\" onclick=\"webkitObject.getMore('chatskins')\">" + unicode(mainWindow.tr("Get more!")) + "</a></span></h3>"
	ret += populateChatThemeList(mainWindow,config["groupchatTheme"]).replace("\"chatTheme","\"groupchatTheme").replace("'chatTheme","'groupchatTheme")
	ret += "<div id=\"groupchatThemeStyleDiv\">" + populateChatThemeStyleList(mainWindow,config["groupchatTheme"])[0].replace("\"chatTheme","\"groupchatTheme").replace("'chatTheme","'groupchatTheme") + "</div>"
	ret += '<iframe src="blank" width="100%" height="120" frameborder="0" name="groupchatThemeFrame"></iframe>'
	
	'''	#rosterstyles = generateRosterStylesPreview(mainWindow,config["rosterStyle"])
	ret += "<h3>" + unicode(mainWindow.tr("Roster style")) +"</h3>"
	ret += populateRosterStylesList(mainWindow,config["rosterStyle"])
	ret += "<div id=\"rosterStyleDiv\">" + populateRosterStylesVariantList(mainWindow,config["rosterStyle"])[0] + "</div>"
	#ret += '<iframe src="blank" width="100%" height="120" frameborder="0" name="rosterStyleFrame"></iframe>'
	
	ret += "<h3>" + unicode(mainWindow.tr("Jabbim theme")) +"</h3>"
	ret += populateJabbimStylesList(mainWindow,config["theme"])
	ret += "<div id=\"jabbimStyleDiv\">" + generateJabbimStylePreview(mainWindow,config["theme"]) + "</div>"'''

	ret += "</body></html>"
	return ret, (chatTheme, cPath), (groupchatTheme, gPath), emoticons
	
	
	
	
	
