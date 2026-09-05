# -*- coding: utf-8 -*-
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
from PyQt4 import QtCore, QtGui
from chatwidget_ui import *
from configobj import ConfigObj
#from palette import *
import urllib,re,os
from twisted.web.microdom import *
from twisted.web.domhelpers import gatherTextNodes
from widgets import filetransfer
from pyxl import jid as jidT
from pyxl.message import Message
import time
from include import utils
from widgets.chat.abstractchatwidget import abstractChatWidget
from webkitchatwidget import webkitChatWidget
import sys
import weakref
from include.constants import RESOURCEPATH

class FTAskWidget(QtGui.QWidget):
	def __init__(self,file,event,chatwidget,parent=None):
		apply(QtGui.QWidget.__init__,(self,parent))
		self.setObjectName("FTAskWidget")
		self.chatwidget=chatwidget
		#self.main=main
		self.event=event
		self.gridlayout = QtGui.QGridLayout(self)
		self.gridlayout.setMargin(0)
		self.gridlayout.setSpacing(0)
		self.gridlayout.setObjectName("gridlayout")

		self.label=QtGui.QLabel(" <b>"+file+"</b> "+self.tr("Receive this file?"),self)
		self.label.setWordWrap(True)
		self.preview=QtGui.QLabel(self)
		self.preview.hide()
		self.yes=QtGui.QPushButton(self.tr('Yes'),self)
		self.no=QtGui.QPushButton(self.tr('No'),self)
		self.gridlayout.addWidget(self.label,0,0,1,2)
		self.gridlayout.addWidget(self.preview,1,0,1,2)
		self.gridlayout.addWidget(self.yes,2,0,1,1)
		self.gridlayout.addWidget(self.no,2,1,1,1)

		QtCore.QObject.connect(self.yes,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.no,QtCore.SIGNAL("clicked()"),self.reject)

	def setPreview(self,pixmap):
		self.preview.show()
		self.preview.setPixmap(pixmap)

	def accept(self,b=None):
		self.event.submitClicked()
		self.chatwidget.ui.ftwidget.layout().removeWidget(self)
		self.setParent(None)
		self.deleteLater()

	def reject(self,b=None):
		self.event.closeClicked()
		self.chatwidget.ui.ftwidget.layout().removeWidget(self)
		self.setParent(None)
		self.deleteLater()


class FTWidget(QtGui.QWidget):
	def __init__(self,file,item,main,sid,parent=None,stats="",download=False):
		apply(QtGui.QWidget.__init__,(self,parent))
		self.setObjectName("FTWidget")
		self.item=item
		self.main=main
		self.complete=False
		self.sid=sid
		self.gridlayout = QtGui.QGridLayout(self)
		self.gridlayout.setMargin(0)
		self.gridlayout.setSpacing(0)
		self.gridlayout.setObjectName("gridlayout")

		self.gridlayout1 = QtGui.QGridLayout()
		self.gridlayout1.setMargin(0)
		self.gridlayout1.setSpacing(6)
		self.gridlayout1.setObjectName("gridlayout1")

		self.label_2 = QtGui.QLabel(file,self)
		self.label_2.setObjectName("label_2")
		self.label_2.setTextFormat(QtCore.Qt.RichText)
		self.label_2.setWordWrap(True)


		spacerItem = QtGui.QSpacerItem(16,18,QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Minimum)
		#self.hboxlayout.addStretch()

		#self.closeButton = QtGui.QPushButton(self)
		#self.closeButton.setMaximumSize(16,16)
		#self.closeButton.setObjectName("closeButton")
		#self.closeButton.setFlat(True)
		#self.closeButton.setIcon(QtGui.QIcon("images/16x16/actions/process-stop.png"))
		#self.hboxlayout.addWidget(self.closeButton)

		#QtCore.QObject.connect(self.closeButton,QtCore.SIGNAL("clicked()"),self.closeClicked)

		#self.gridlayout1.addLayout(self.hboxlayout,0,0,1,1)

		self.stats = QtGui.QLabel(stats,self)

		self.progressBar = QtGui.QProgressBar(self)

		sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Policy(7),QtGui.QSizePolicy.Policy(1))
		sizePolicy.setHorizontalStretch(0)
		sizePolicy.setVerticalStretch(0)
		sizePolicy.setHeightForWidth(self.progressBar.sizePolicy().hasHeightForWidth())
		self.progressBar.setSizePolicy(sizePolicy)
		self.progressBar.setProperty("value",QtCore.QVariant(0))
		self.progressBar.setOrientation(QtCore.Qt.Horizontal)
		self.progressBar.setObjectName("progressBar")
		self.gridlayout1.addWidget(self.stats,1,0,1,2)
		self.gridlayout1.addWidget(self.progressBar,2,0,1,2)
		if not download:
			self.gridlayout1.addWidget(self.label_2,3,0,1,2)
		self.gridlayout.addLayout(self.gridlayout1,0,0,1,1)
		self.gridlayout.setMargin(1)
		self.gridlayout.setSpacing(0)
		self.gridlayout1.setMargin(1)
		self.gridlayout1.setSpacing(0)
		self.setMinimumHeight(60)

	def reinit(self,file,item,main,sid,parent=None,stats=""):
		self.complete=False
		self.sid=sid
		self.stats.setText(stats)
		self.item=item
		self.progressBar.setProperty("value",QtCore.QVariant(0))
		self.label_2.setText(file)

		self.setMinimumHeight(60)

	def closeClicked(self):
		if self.item:
			if not self.complete:
				try:
					self.main.client.ft[self.sid].protocol.unregisterProducer()
					self.complete=None
				except:
					self.main.ui.eventsListWidget.takeItem(self.main.ui.eventsListWidget.row(self.item))
			elif self.complete==True:
				self.main.ui.eventsListWidget.takeItem(self.main.ui.eventsListWidget.row(self.item))

class flowLayout(QtGui.QLayout):
	"""
	Flow layout from Qt4 examples. Used for plugins buttons.
	"""
	def __init__(self, parent=None, margin=0, spacing=-1):
		QtGui.QLayout.__init__(self, parent)

		if parent is not None:
			self.setMargin(2)
		self.setSpacing(spacing)

		self.itemList = []

	def addItem(self, item):
		self.itemList.append(item)

	def count(self):
		return len(self.itemList)

	def itemAt(self, index):
		if index >= 0 and index < len(self.itemList):
			return self.itemList[index]

	def takeAt(self, index):
		if index >= 0 and index < len(self.itemList):
			return self.itemList.pop(index)

	def expandingDirections(self):
		return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

	def hasHeightForWidth(self):
		return True

	def heightForWidth(self, width):
		height = self.doLayout(QtCore.QRect(0, 0, width, 0), True)
		return height

	def setGeometry(self, rect):
		QtGui.QLayout.setGeometry(self, rect)
		self.doLayout(rect, False)

	def sizeHint(self):
		return self.minimumSize()

	def minimumSize(self):
		size = QtCore.QSize()

		for item in self.itemList:
			size = size.expandedTo(item.minimumSize())

		size += QtCore.QSize(2 * self.margin(), 2 * self.margin())
		return size

	def doLayout(self, rect, testOnly):
		x = rect.x()
		y = rect.y()
		lineHeight = 0

		for item in self.itemList:
			nextX = x + item.sizeHint().width() + self.spacing()
			if nextX - self.spacing() > rect.right() and lineHeight > 0:
				x = rect.x()
				y = y + lineHeight + self.spacing()
				nextX = x + item.sizeHint().width() + self.spacing()
				lineHeight = 0

			if not testOnly:
				item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

			x = nextX
			lineHeight = max(lineHeight, item.sizeHint().height())

		return y + lineHeight - rect.y()

class FaderWidget(QtGui.QWidget):
	def __init__(self,parent=None):
		QtGui.QWidget.__init__(self,parent)
		if parent:
			self.startColor = parent.palette().window().color()
		else:
			self.startColor = QtCore.Qt.white
		self._hide=True

		self.currentAlpha = 0
		self.duration = 333

		self.timer = QtCore.QTimer(self)
		QtCore.QObject.connect(self.timer, QtCore.SIGNAL("timeout()"), self.update)

		self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
		self.resize(parent.size())

	def start(self):
		if self._hide:
			self.currentAlpha = 1
		else:
			self.currentAlpha = 255
		self.timer.start(33)
		self.resize(self.parent().size())
		self.show()

	def paintEvent(self,event):
		painter=QtGui.QPainter(self)
		semiTransparentColor = QtGui.QColor(self.startColor)
		semiTransparentColor.setAlpha(self.currentAlpha)
		painter.fillRect(self.rect(), semiTransparentColor)

		if self._hide:
			self.currentAlpha += 255 * self.timer.interval() / self.duration
		else:
			self.currentAlpha -= 255 * self.timer.interval() / self.duration
		if self.currentAlpha <= 0:
			self.timer.stop()
			self.close()
		elif self.currentAlpha >= 255:
			self.currentAlpha=255
			self.timer.stop()
			self._hide=False
			self.emit(QtCore.SIGNAL("hidden()"))

class ElidedLabel(QtGui.QLabel):
	def __init__(self,elide,parent=None):
		QtGui.QLabel.__init__(self,parent)
		self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed ))
		self.fullText = ""
		self.elideMode = elide
		self.squeezeTextToLabel()

	def resizeEvent(self,e):
		self.squeezeTextToLabel()

	def minimumSizeHint(self):
		sh=QtGui.QLabel.minimumSizeHint(self)
		sh.setWidth(-1)
		return sh

	#def sizeHint(self):
		#QFontMetrics fm(fontMetrics());
		#int textWidth = fm.width(d->fullText);
		#return QSize(textWidth, QLabel::sizeHint().height());

	def setText(self,text):
		self.fullText = text
		self.squeezeTextToLabel()

	def clear(self):
		self.fulltext=""
		QtGui.QLabel.clear(self)

	def squeezeTextToLabel(self):
		fm=self.fontMetrics()
		labelWidth = self.size().width()
		squeezed = False
		line=unicode(self.fullText)
		lineWidth = fm.width(line)
		if lineWidth > labelWidth:
			squeezed = True
			line=fm.elidedText(line, self.elideMode, labelWidth)

		if squeezed:
			QtGui.QLabel.setText(self,line)
			self.setToolTip(self.fullText)
		else:
			QtGui.QLabel.setText(self,line)
			self.setToolTip(QtCore.QString())


class chatWidget(abstractChatWidget):
	def __init__(self,main,jid,parent=None,name=""):
		jidt=jidT.JID(jid)
		self.name=name
		self.main=weakref.ref(main)
		xhtml=main.client.hasFeature(jid,'http://jabber.org/protocol/xhtml-im')
		self.typ="chat"
		abstractChatWidget.__init__(self, Ui_chatwidget, webkitChatWidget, main, jid, xhtml, parent)

		self.coolWidgets=[]
		self.coolLayout=QtGui.QHBoxLayout(self.ui.cool)
		self.faderWidget=None

		self.ui.label=ElidedLabel(QtCore.Qt.ElideRight,self.ui.widget)
		self.ui.horizontalLayout.insertWidget(0,self.ui.label)

		self.ui.infoWidget=QtGui.QWidget(self.ui.widget) # because of fade effect
		l=QtGui.QHBoxLayout(self.ui.infoWidget)
		l.setMargin(0)

		self.ui.infoLabel = ElidedLabel(QtCore.Qt.ElideRight,self.ui.infoWidget)
		sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
		sizePolicy.setHorizontalStretch(100)
		sizePolicy.setVerticalStretch(0)
		sizePolicy.setHeightForWidth(self.ui.infoWidget.sizePolicy().hasHeightForWidth())
		self.ui.infoWidget.setSizePolicy(sizePolicy)
		self.ui.infoLabel.setObjectName("infoLabel")
		self.ui.infoPixmap=QtGui.QLabel(self.ui.infoWidget)
		self.ui.infoPixmap.setMaximumWidth(32)
		l.addWidget(self.ui.infoPixmap)
		l.addWidget(self.ui.infoLabel)
		self.ui.horizontalLayout_2.insertWidget(0,self.ui.infoWidget)

		self.loadAvatars()
		self.loadWebkit()

		self.metaJids=[]
		# set splitters sizes
		#self.ui.splitter.setSizes(list(self.main().config['chatSplitterSizes']))
		self.ui.splitter.setSizes([800,64])
		#self.ui.splitter_2.setSizes(list(self.main().config['chatSplitter2Sizes']))
		#widget=self.ui.splitter_2.widget(1)
		#widget.setMaximumWidth(128)

		# Maximum width of avatar Widget
		self.ui.avatar.setMaximumWidth(64)
		self.ui.avatar.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
		QtCore.QObject.connect(self.ui.avatar,QtCore.SIGNAL("customContextMenuRequested ( const QPoint & )"),self.contactMenu)
		self.noColor=True
		self.lastMessageFrom=""

		# plugins buttons
		#self.flowLayout = QtGui.QHBoxLayout()
		self.main().pluginManager.buildChatWidget(unicode(self.jid),self.ui.verticalLayout,self)
		#self.flowLayout.addStretch()
		hasFeature=False
		self.ui.metaLabel.hide()
		self.ui.metaButton.hide()

		# sendFile buttons
		self.ui.sendFile=QtGui.QPushButton()
		self.ui.sendFile.setIconSize(QtCore.QSize(16,16))
		self.ui.sendFile.setIcon(QtGui.QIcon(RESOURCEPATH+"images/32x32/actions/upload.png"))
		self.ui.sendFile.setToolTip(self.tr("Send file"))
		self.ui.sendFile.hide()
		self.registerFeatureForWidget('http://jabber.org/protocol/si/profile/file-transfer',self.ui.sendFile)
		self.ui.verticalLayout.addWidget(self.ui.sendFile)
		QtCore.QObject.connect(self.ui.sendFile, QtCore.SIGNAL("clicked ()"),self.sendFiles)

		self.ui.paintButton=QtGui.QPushButton()
		self.ui.paintButton.setIconSize(QtCore.QSize(16,16))
		self.ui.paintButton.setIcon(QtGui.QIcon(RESOURCEPATH+"images/22x22/actions/draw-brush.png"))
		self.ui.paintButton.setToolTip(self.tr("Paint"))
		self.ui.paintButton.hide()
		self.registerFeatureForWidget('urn:xmpp:bob',self.ui.paintButton)
		self.ui.verticalLayout.addWidget(self.ui.paintButton)
		QtCore.QObject.connect(self.ui.paintButton,QtCore.SIGNAL("clicked()"),self.paint)
		self.ui.verticalLayout.addStretch()



		if self.main().client.groupchats.has_key(jidt.userhost()):
			#print "features:",self.main().client.groupchats[jidt.userhost()].users[jidt.resource].features
			hasFeature='http://jabber.org/protocol/si/profile/file-transfer' in self.main().client.groupchats[jidt.userhost()].users[jidt.resource].features
			self.ui.resourceButton.hide()
			self.ui.resourceLabel.hide()
			if hasFeature:
				self.ui.sendFile.show()
		else:
			if main.client.roster['users'].has_key(jidt.userhost()):
				self.buildResourceMenu()
				self.buildMetaMenu()
			else:
				self.ui.resourceButton.hide()
				self.ui.resourceLabel.hide()

		#self.ui.pluginWidget.setLayout(self.flowLayout)
		self.ui.ftwidget.setLayout(QtGui.QVBoxLayout())
		self.filetransfer={}

		self.refreshToolTip()
		self.infoText={}
		self.infoKeys=[]
		self.currentInfoIndex=0
		#self.main().reactor.callLater(2,self.infoLabelShowNext)

	def addInfoText(self,key,text,icon=None):
		#self.infoText[key]=[unicode(text),icon]
		#self.infoKeys=list(self.infoText.keys())
		#self.infoKeys.sort()
		pass

	def removeInfoText(self,key):
		#del self.infodText[key]
		#self.infoKeys.remove(key)
		pass

	def infoLabelShowNext(self):
		#if len(self.infoKeys)!=0:
			#if self.currentInfoIndex+1<=len(self.infoKeys)-1:
				#self.currentInfoIndex+=1
			#else:
				#self.currentInfoIndex=0
			#self.setInfoText(self.infoText[self.infoKeys[self.currentInfoIndex]][0],self.infoText[self.infoKeys[self.currentInfoIndex]][1])
		#self.main().reactor.callLater(10,self.infoLabelShowNext)
		pass

	def setInfoText(self,text,icon=None):
		#if self.faderWidget:
			#self.faderWidget.close()
		#self.faderWidget=FaderWidget(self.ui.infoWidget)
		#self.faderWidget.text=unicode(text)
		#self.faderWidget.icon=icon
		#QtCore.QObject.connect(self.faderWidget,QtCore.SIGNAL("hidden()"),self.infoTextHidden)
		#self.faderWidget.start()
		pass

	#def infoTextHidden(self):
		#self.ui.infoLabel.setText(self.faderWidget.text)
		#if self.faderWidget.icon:
			#self.ui.infoPixmap.setPixmap(self.faderWidget.icon)
		#else:
			#self.ui.infoPixmap.setPixmap(QtGui.QPixmap())
		#self.main().reactor.callLater(0,self.faderWidget.start)

	def addCoolWidget(self,widget):
		self.coolWidgets.append(widget)
		self.coolLayout.addWidget(widget)

	def removeCoolWidget(self,widget):
		self.coolWidgets.remove(widget)

	def setName(self, name):
		self.name = name
		self.refreshToolTip()
		self.refreshLabel()
		self.parent.tabName = name
		currentIndex=self.main().chat.ui.chatTab.currentIndex()
		self.main().chat.ui.chatTab.setTabText(currentIndex,self.parent.tabName)

	def loadAvatars(self):
		# avatar of user who is chatting with us
		self.file=""
		if self.main().avatarDef.has_key(unicode(jidT.JID(self.jid).userhost())):
			self.file=self.main().realHomeDir+'/avatars/'+str(self.main().avatarDef[unicode(jidT.JID(self.jid).userhost())]) #: path to users avatar
		elif self.main().avatarDef.has_key(unicode(jidT.JID(self.jid).full())):
			self.file=self.main().realHomeDir+'/avatars/'+str(self.main().avatarDef[unicode(jidT.JID(self.jid).full())]) #: path to users avatar
		if not os.path.isfile(self.file):
			# use default avatar if users avatar doesn't exist
			self.file = RESOURCEPATH+"/images/32x32/apps/jabbim.png"
		self.file = os.path.abspath(self.file)

		# our avatar
		f=""
		if self.main().avatarDef.has_key(self.main().client.jid.userhost()):
			f=self.main().realHomeDir+'/avatars/'+str(self.main().avatarDef[self.main().client.jid.userhost()])
		if not os.path.isfile(f):
			self.selfFile=RESOURCEPATH+"images/32x32/apps/jabbim.png"
		else:
			self.selfFile=f

		self.loadSelfAvatar()	
	
	def loadSelfAvatar(self):
		# set our avatar label
		result=self.main().getAvatar(self.main().client.jid.userhost(),size="64x64",frame=True)
		if result:
			self.ui.selfAvatar.setPixmap(result)
			self.ui.selfAvatar.setMaximumWidth(64)
		else:
			self.ui.selfAvatar.hide()
			self.ui.lineWidget.setMinimumSize(100,64)

	def refreshLabel(self,change=[]):
		text=""
		contact=self.main().client.getContactByJid(self.jid)
		if not contact:
			text=unicode(self.main().status.get("offline", ''))
			self.ui.label.setText(text)
			return
		s=None
		show=None
		jid=self.main().getJid(self.jid)
		if contact != None:
			if jid.resource:
				if contact.resources.has_key(jid.resource):
					s = contact.resources[jid.resource].status
					show = contact.resources[jid.resource].show
					show = unicode(self.main().status.get(contact.resources[jid.resource].show, ''))
			else:
				res=self.main().client.roster['users'][jid.userhost()].getHighestResource()
				if contact.resources.has_key(res):
					s = contact.resources[res].status
					show = unicode(self.main().status.get(contact.resources[res].show, ''))
		if not s:
			s=""
		else:
			s=" - "+s
		if show:
			#process status message
			text+=show+s


		mood = contact.getPEP('http://jabber.org/protocol/mood')
		if mood != None:
			t = ''
			m = txt = icon = ''
			ic=QtGui.QPixmap()
			for el in mood.elements():
				if el.name == 'text':
					txt = unicode(el)
				else:
					m = unicode(self.main().moods.get(el.name))
					if self.main().moodIcons.has_key(el.name):
						icon="<img src=\"file:///%s\" />" % self.main().moodIcons[el.name].src
						ic=QtGui.QPixmap(self.main().moodIcons[el.name].src)
					else:
						icon=""
			if txt != '':
				t = '%s - %s' % (m, txt)
			else:
				t = m
			#text+='<br />%s <font size="-1">&nbsp; %s</font>' % (icon.replace("file:///",""),t)
			if self.main().config['showMoodChanges']=='True' and "mood" in change:
				user=unicode(self.main().ui.roster.getNameByJID(self.jid))
				message=icon+"&nbsp;"+user+" "+unicode(self.tr("is now"))+" "+ t
				self.textEditWrite(self.main().webkitThemeFactory.genChatStatus(unicode(message),self.main().now()))
			#self.addInfoText("mood",'%s' % (t),ic)
			self.ui.infoLabel.setText(t)
			self.ui.infoPixmap.setPixmap(ic)
		tune = contact.getPEP('http://jabber.org/protocol/tune')
		if type(tune) == list:
			for x in tune:
				print x
		elif tune!=None:
			artist = title = ''
			for el in tune.elements():
				if el.name == 'artist':
					artist = unicode(el)
				elif el.name == 'title':
					title = unicode(el)
			t = '%s: %s'%(artist, title)
			if len(t.strip())>1:
				#text+='<br /><img src="images/22x22/icons/headphones.png" /><font size="-1">&nbsp; %s</font>' % (t) #ikonka se este muze menit ;)
				if self.main().config['showTuneChanges']=='True' and "tune" in change:
					user=unicode(self.main().ui.roster.getNameByJID(self.jid))
					message='<img src="file:///'+os.path.abspath(RESOURCEPATH)+'/images/22x22/icons/headphones.png" />&nbsp;'+user+" "+unicode(self.tr("is now listening:"))+" "+ t
					self.textEditWrite(self.main().webkitThemeFactory.genChatStatus(unicode(message),self.main().now()))
				self.addInfoText("tune",'%s' % (t),QtGui.QPixmap(RESOURCEPATH+'images/22x22/icons/headphones.png'))

		activity = contact.getPEP('http://jabber.org/protocol/activity')
		if activity != None:
			txt = ''
			general = ''
			spec = ''
			ic=QtGui.QPixmap()
			for el in activity.elements():
				if el.name == 'text':
					txt = unicode(el)
				else :
					general = el.name
					if self.main().activityGroups.has_key(general):
						general=self.main().activityGroups[general][0]
						if self.main().activityIcons.has_key(general):
							ic=QtGui.QPixmap(self.main().activityIcons[general].src)
					spec = el.firstChildElement()
					if spec:
						spec=spec.name
						if self.main().activityIcons.has_key(spec):
							ic=QtGui.QPixmap(self.main().activityIcons[spec].src)
					if self.main().activities.has_key(spec):
						spec=self.main().activities[spec]

				#if self.main().activityIcons.has_key(spec):
					#ic=QtGui.QPixmap(self.main().activityIcons[spec].src)
				#if self.main().activityIcons.has_key(general):
					#ic=QtGui.QPixmap(self.main().activityIcons[general].src)
				#else:
					#ic=QtGui.QPixmap()

			self.addInfoText("activity",'%s %s %s' % (general, spec, txt),ic)
			#text+='<br /><font size="-1"><b>%s</b> %s %s</font>' % (general, spec, txt)


		self.ui.label.setText(text)

	def contactMenu(self,pos):
		items=self.main().ui.roster.getUserItems(self.main().getJid(self.jid).userhost())
		if len(items)==0:
			contactMenu=self.main().ui.roster.buildJidMenu(self.jid)
		else:
			item=items[0]
			group=item.group
			jid=item.jid
			contactMenu=self.main().ui.roster.buildContactMenu(unicode(jid),group)
		contactMenu.popup(self.ui.avatar.mapToGlobal(pos))

	def hasMetacontact(self,metacontact):
		return metacontact in self.metaJids

	def buildMetaMenu(self):
		jidt=self.main().getJid(self.jid)
		if self.main().client.roster['users'][jidt.userhost()].tag!=None:
			self.metaMenu=QtGui.QMenu(self.ui.metaButton)
			self.ui.metaLabel.show()
			self.ui.metaButton.show()
			meta=[]
			tag=self.main().client.roster['users'][jidt.userhost()].tag
			for jid,user in self.main().client.roster['users'].iteritems():
				if user.tag==tag:
					meta.append(jid)
			self.metaJids=meta
			for mJid in meta:

				name=self.main().ui.roster.getNameByJID(mJid)
				icon=self.main().ui.roster.getIconByJID(mJid)
				action=self.metaMenu.addAction(icon,name)
				action.setData(QtCore.QVariant(unicode(mJid)))
				if mJid==jidt.userhost():
					self.ui.metaButton.setText(action.text())
					self.ui.metaButton.setIcon(action.icon())
			self.metaMenu.connect(self.metaMenu, QtCore.SIGNAL("triggered ( QAction * )"),self.metaMenuTriggered)
			self.ui.metaButton.setMenu(self.metaMenu)


	def buildResourceMenu(self):
		jidt=self.main().getJid(self.jid)
		self.resourceMenu=QtGui.QMenu(self.ui.resourceButton)
		#action=self.resourceMenu.addAction(self.tr("Automatic"))
		#self.ui.resourceButton.setText(action.text())
		#try:
			#hasFeature=self.main().client.roster['users'][jidt.userhost()].resources[self.main().client.roster['users'][jidt.userhost()].getHighestResource()].hasFeature('http://jabber.org/protocol/si/profile/file-transfer')
		#except:
			#hasFeature=False
		count=0
		found=False
		for name,resource in self.main().client.roster['users'][jidt.userhost()].resources.iteritems():
			if name:
				count+=1
				action=self.resourceMenu.addAction(self.main().getIcon(unicode(jidt.userhost()),status=resource.show),name)
				if jidt.resource==name:
					self.ui.resourceButton.setText(action.text())
					self.ui.resourceButton.setIcon(action.icon())
					found=True
					#try:
						#hasFeature=self.main().client.roster['users'][jidt.userhost()].resources[name].hasFeature('http://jabber.org/protocol/si/profile/file-transfer')
					#except:
						#hasFeature=False
		if not found:
			self.ui.resourceButton.setText(self.tr("Automatic"))
			self.jid=self.main().getJid(self.jid).userhost()
			self.parent.jid=self.jid
		#if hasFeature:
			#self.ui.sendFile.show()
		#else:
			#self.ui.sendFile.hide()
		self.showFeaturedWidgets()
		if count<2:
			self.ui.resourceButton.hide()
			self.ui.resourceLabel.hide()
		else:
			self.ui.resourceButton.setEnabled(True)
			self.ui.resourceButton.show()
			self.ui.resourceLabel.show()
		self.resourceMenu.connect(self.resourceMenu, QtCore.SIGNAL("triggered ( QAction * )"),self.resourceMenuTriggered)
		self.ui.resourceButton.setMenu(self.resourceMenu)

	def metaMenuTriggered(self,action):
		self.ui.metaButton.setText(action.text())
		self.ui.metaButton.setIcon(action.icon())
		jidt=self.main().getJid(unicode(action.data().toString()))
		res = self.main().client.roster['users'][jidt.userhost()].getHighestResource()
		if res:
			jidt.resource=unicode(res)
		self.jid=unicode(jidt.full())
		self.parent.jid=self.jid
		self.buildResourceMenu()
		self.parent.tabName=unicode(action.text())
		self.parent.ic=action.icon()
		currentIndex=self.main().chat.ui.chatTab.currentIndex()
		self.main().chat.ui.chatTab.setTabIcon(currentIndex,self.parent.ic)
		self.main().chat.ui.chatTab.setTabText(currentIndex,self.parent.tabName)
		self.main().chat.setWindowTitle(unicode(self.main().chat.ui.chatTab.tabText(currentIndex)).replace("&",""))

	def resourceMenuTriggered(self,action):
		self.ui.resourceButton.setText(action.text())
		self.ui.resourceButton.setIcon(action.icon())
		jid=self.main().getJid(self.jid)
		if action.text()==self.tr("Automatic"):
			jid.resource=None
		else:
			jid.resource=unicode(action.text())
		self.jid=jid.full()
		self.parent.jid=self.jid

	def refreshToolTip(self):
		if self.main().client:
			text = self.main().getToolTip(self.jid)
			self.ui.avatar.setToolTip(text)

	def sendFiles(self):
		"""
		Shows filetransfer dialog and sends files to user who chats with us.
		"""
		self.main().sendFiles(self.jid)
		#file=QtGui.QFileDialog.getOpenFileNames(self,"Choose file")
		#file=list(file)
		#if len(file)!=0:
			#new=[]
			#for f in file:
				#new.append(unicode(f))
			#file=new
			## show filetransfer dialog and send files
			#self.dialog=filetransfer.filetransferDialog(self.main(),file,self.jid)
			#self.dialog.show()

	def sendButtonClicked(self):
		"""
		Sends message writed in self.ui.line or call command if message starts with "/".
		"""
		if len(unicode(self.ui.line.toPlainText()))!=0:
			# execute commands if message starts with "/"
			services=unicode(self.ui.line.toPlainText())
			m = re.match(r'/google(\s+(\S.*)?)?$', services)
			if m:
				if m.group(2):
					anchor="http://www.google.com/search?q="+m.group(2)
				else:
					anchor="http://www.google.com/"
				QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))
				self.ui.line.clear()
				self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
				self.ui.line.composing=False
				return

			elif services.startswith("/"):
				try:
					cmd, args = services.split(" ", 1)
					args = args.split(" ")
				except ValueError:
					cmd = services
					args = []
				cmd = cmd[1:]
				# publish onCommand event for events subscribers (mainly plugins)
				passed = self.main().client.dispatcher.publishEvent("onCommand", cmd, args, self, "chat")
				if not passed:
					# A plugin stopped the event propagation.
					# It must have recognized the command and handled it.
					self.ui.line.clear()
					self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
					self.ui.line.composing=False
					return
				# Otherwise it was not a recognized command. Let's behave like it's a normal message.
			#d=self.main().cache.set_stats(self.main().getJid(self.jid).userhost())
			#d.addErrback(self.main()._error)
			self.main().userRating.reward(self.main().getJid(self.jid).userhost())
			# get plain text message
			text=unicode(self.ui.line.toPlainText())
			ret=False
			if self.xhtml:
				xhtml=self.ui.line.toHtml()
				xhtml,same=self.qtHtmlToXhtml(xhtml,text)
			if self.xhtml and not same:
				# get message in Qt html format
				#xhtml=self.ui.line.toHtml()
				#xhtml,same=self.qtHtmlToXhtml(xhtml,text)
				# send message
				m=Message(unicode(self.jid))
				m.setBody(text)
				m.setXHTML(xhtml)
				m.setComposing("active")
				for key,value in self.main().pluginManager.plugins.iteritems():
					if value['module']:
						ret=self.main().pluginManager.runPluginCommand(value['module'].on_messageSend,[m])
						if ret:
							m=ret
						else:
							return
				self.main().client.message.sendMessage(msg=m)

				# prepare message for showing in GUI
				message=xhtml.replace("&quot;",'"')
				if m.receiptId != None and self.main().config['showReceipts']=='True':
					message = '<img id="' + m.receiptId + '" src="%s/images/16x16/actions/message.png?receipt%s" />' % (RESOURCEPATH, m.receiptId) + message
				#file=self.main().homeDir+'/avatars/'+unicode(self.main().client.jid.userhost())
				#if not os.path.isfile(file):
					#file="images/32x32/apps/jabbim.png"
				#skin=self.main().skin["my_message"]
				#if self.lastMessageFrom==unicode(self.main().client.jid.user):
					#if self.main().skin.has_key('my_message_continue'):
						#skin=self.main().skin["my_message_continue"]
				#message=skin.replace("[time]",self.main().now()).replace("[user]",unicode(self.main().client.jid.user)).replace("[message]",message).replace("[avatar]","<img src=\""+self.selfFile+"\" width=\"32\" height=\""+str(self.selfHeight)+"\" />")
				self.appendLastMessage(['out',self.main().client.jid.user,message,self.main().now(),self.selfFile])
				message=self.main().webkitThemeFactory.genOutgoingContent(self.main().client.jid.user,message,self.main().now(),self.selfFile)
				insert=False
			else:
				# send message
				#text=unescape(text)
				m=Message(unicode(self.jid))
				m.setBody(text)
				m.setComposing("active")
				for key,value in self.main().pluginManager.plugins.iteritems():
					if value['module']:
						ret=self.main().pluginManager.runPluginCommand(value['module'].on_messageSend,[m])
						if ret:
							m=ret
						else:
							return
				self.main().client.message.sendMessage(msg=m)

				# prepare message for showing in GUI
				text=unicode(text).replace("<","&lt;").replace(">","&gt;").replace("\n","<br/> ")
				text=utils.replace_url(text,self.main(),self)
				text=text.replace("  ","&nbsp;&nbsp;").replace("\t","&nbsp;&nbsp;&nbsp;")
				if m.receiptId != None and self.main().config['showReceipts']=='True':
					text = '<img id="' + m.receiptId + '" src="%s/images/16x16/actions/message.png?receipt%s" />' % (RESOURCEPATH, m.receiptId) + text

				#file=self.main().homeDir+'/avatars/'+unicode(self.main().client.jid.userhost())
				#if not os.path.isfile(file):
					#file="images/32x32/apps/jabbim.png"
				#if unicode(text).startswith("/me"):
					#message=self.main().skin["my_me_message"]#.replace("[time]",self.main().now()).replace("[user]",unicode(self.main().client.jid.user)).replace("[message]",text[3:]).replace("[avatar]","<img src=\""+file+"\" width=\"32\" height=\""+str(self.selfHeight)+"\" />")
					#if self.lastMessageFrom==unicode(self.main().client.jid.user):
						#if self.main().skin.has_key('my_me_message_continue'):
							#message=self.main().skin["my_me_message_continue"]
					#message=message.replace("[time]",self.main().now()).replace("[user]",unicode(self.main().client.jid.user)).replace("[message]",text[3:]).replace("[avatar]","<img src=\""+self.selfFile+"\" width=\"32\" height=\""+str(self.selfHeight)+"\" />")
				#else:
					#message=self.main().skin["my_message"]
					#if self.lastMessageFrom==unicode(self.main().client.jid.user):
						#if self.main().skin.has_key('my_message_continue'):
							#message=self.main().skin["my_message_continue"]
					#message=message.replace("[time]",self.main().now()).replace("[user]",unicode(self.main().client.jid.user)).replace("[message]",text).replace("[avatar]","<img src=\""+self.selfFile+"\" width=\"32\" height=\""+str(self.selfHeight)+"\" />")
				self.appendLastMessage(['out',self.main().client.jid.user,text,self.main().now(),self.selfFile])
				if self.lastMessageFrom==unicode(self.main().client.jid.user):
					message=self.main().webkitThemeFactory.genOutgoingNextContent(self.main().client.jid.user,text,self.main().now(),self.selfFile)
					insert=True
				else:
					message=self.main().webkitThemeFactory.genOutgoingContent(self.main().client.jid.user,text,self.main().now(),self.selfFile)
					insert=False


			self.lastMessageFrom=unicode(self.main().client.jid.user)
			# show message
			self.textEditWrite(message,insert)
			# add message to 'sent messages history'
			self.sent.append(m.getBody())
			self.hindex = len(self.sent)

			#self.ui.line.clear()
			#self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
			self.clearLine()
			self.ui.line.composing=False
			# depracted
			if self.main().chat.active==False:
				self.main().client.dispatcher.publishEvent('onActivity')
				self.main().chat.active=True
