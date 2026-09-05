# -*- coding: utf-8 -*-

from PyQt4 import QtCore, QtGui
from rostertooltip_ui import *
import weakref
import vcardeditor
from include.utils import replace_url
from include.constants import RESOURCEPATH

class ToolTip(QtGui.QFrame):
	def __init__(self, mainwindow, jid, nick, position, in_muc):
		QtGui.QFrame.__init__(self, None, QtCore.Qt.ToolTip | QtCore.Qt.X11BypassWindowManagerHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint | QtCore.Qt.CustomizeWindowHint)
		self.setFrameStyle(QtGui.QFrame.Plain|QtGui.QFrame.Box)
		self.ui = Ui_RosterToolTip()
		self.ui.setupUi(self)
		self.setMouseTracking(True)
		self.ui.status.setAutoFillBackground(True)
		p = QtGui.QPalette()
		p.setColor(QtGui.QPalette.Base, QtGui.QColor(self.palette().window().color()))
		self.ui.status.setPalette(p)
		self.main = mainwindow
		self.jid = jid
		self.in_muc = in_muc
		self.focus = False
		self.ui.mood.setMouseTracking(True)
		self.ui.mood.enterEvent = self.moodEnterEvent
		self.ui.mood.leaveEvent = self.moodLeaveEvent
		self.ui.activity.setMouseTracking(True)
		self.ui.activity.enterEvent = self.activityEnterEvent
		self.ui.activity.leaveEvent = self.moodLeaveEvent
		self.ui.tune.setMouseTracking(True)
		self.ui.tune.enterEvent = self.tuneEnterEvent
		self.ui.tune.leaveEvent = self.tuneLeaveEvent
		self.status = ""
		self.mood = ""
		self.activity = ""
		self.tune = ""
		self.ui.vcard.setPixmap(QtGui.QPixmap(RESOURCEPATH+"images/16x16/categories/v-card.png"))
		self.ui.vcard.leaveEvent = self.tuneLeaveEvent
		self.ui.vcard.enterEvent = self.vcardEnterEvent
		self.ui.vcard.mousePressEvent = self.vcardMousePressEvent
		self.ui.status.setMaximumHeight(QtGui.QFontMetrics(self.ui.status.font()).height()*4)
		self.ui.metaWidget.hide()
		self.mlayout = QtGui.QHBoxLayout(self.ui.metaWidget)
		self.mlayout.setMargin(0)
		self.mlayout.setSpacing(0)

		if not in_muc:
			self.contact = self.main.client.getContactByJid(jid)
		else:
			self.contact = self.main.client.getMucContactByJid(jid)

		self.ui.nickname.setText("<b>" + nick + "</b>")
		self.initAvatar()
		self.initMetaContacts()
		self.initJid()
		self.initStatus()
		self.initSubscription()
		self.initTune()
		self.initMood()
		self.initActivity()

		self.initPosition(position)

	def initAvatar(self):
		avatar = None
		if self.main.avatarDef.get(self.jid, False):
			if self.main.client.avatarImg.has_key(self.main.avatarDef[self.jid]):
				if self.main.client.avatarImg[self.main.avatarDef[self.jid]] and self.main.avatarDef[self.jid] != "None":
					avatar = QtGui.QPixmap(self.main.realHomeDir + '/avatars/' + unicode(self.main.avatarDef[self.jid]))
		else:
			#if there is no avatar for given JID, then try to use avatar from any metacontact
			meta = self.main.ui.roster.getMetaItems(self.jid)
			print meta
			for itm in meta:
				j = itm[1]
				print j
				if self.main.avatarDef.get(j, False):
					if self.main.client.avatarImg.has_key(self.main.avatarDef[j]):
						if self.main.client.avatarImg[self.main.avatarDef[j]] and self.main.avatarDef[j] != "None":
							avatar = QtGui.QPixmap(self.main.realHomeDir + '/avatars/' + unicode(self.main.avatarDef[j]))
							break
		if avatar:
			avatar = avatar.scaled(64, 64, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
		else:
			avatar = QtGui.QPixmap(self.main.getAvatarSrc("default"))
		self.ui.label.setPixmap(avatar)

	def initMetaContacts(self):
		if not self.in_muc and self.main.client.roster['users'].has_key(self.jid) and self.main.client.roster['users'][self.jid].tag != None:
			tag = self.main.client.roster['users'][self.jid].tag
			meta = []
			for j,user in self.main.client.roster['users'].iteritems():
				if user.tag == tag:
					meta.append(j)
			for mJid in meta:
				print 'meta',mJid
			self.hideMetaContacts()
			self.showMetaContacts(meta)
		else:
			self.hideMetaContacts()

	def initJid(self):
		if self.in_muc and self.contact.truejid:
			self.jid = unicode(self.contact.truejid)
		self.ui.jid.setText(self.jid)

	def initStatus(self):
		try:
			status = self.contact.status
			if not self.in_muc:
				status = status[1]
			if len(status) == 0:
				self.ui.status.hide()
			else:
				self.ui.status.setHtml(replace_url(status.replace('\n', '<br />'), self.main))
				self.ui.status.show()
		except:
			self.ui.status.hide()

	def initSubscription(self):
		if self.in_muc or not self.contact:
			self.ui.subscription.hide()
			return
		subscription = self.contact.subscription
		if unicode(self.contact.subscription) == 'from':
			self.ui.subscription.setText('<b>'+self.main.tr("Subscription:")+'</b> '+self.main.tr(" from"))
			self.ui.subscription.show()
		elif unicode(self.contact.subscription) == 'to':
			self.ui.subscription.setText('<b>'+self.main.tr("Subscription:")+'</b> '+self.main.tr(" to"))
			self.ui.subscription.show()
		elif unicode(self.contact.subscription) == 'none':
			self.ui.subscription.setText('<b>'+self.main.tr("Subscription:")+'</b> '+self.main.tr(" none"))
			self.ui.subscription.show()
		else:
			self.ui.subscription.hide()

	def initTune(self):
		if self.in_muc or not self.contact:
			self.ui.tune.hide()
			return
		tune = self.contact.getPEP('http://jabber.org/protocol/tune')
		if type(tune) == list:
			for x in tune:
				print x
			self.ui.tune.hide()
		elif tune != None:
			artist = title = ''
			for el in tune.elements():
				if el.name == 'artist':
					artist = unicode(el)
				elif el.name == 'title':
					title = unicode(el)
			t = '%s: %s' % (artist, title)
			if len(t.strip()) > 1:
				self.ui.tune.setPixmap(QtGui.QPixmap(RESOURCEPATH+"images/22x22/icons/headphones.png"))
				self.tune = t
			else:
				self.ui.tune.hide()
		else:
			self.ui.tune.hide()

	def initMood(self):
		if self.in_muc or not self.contact:
			self.ui.mood.hide()
			return
		mood = self.contact.getPEP('http://jabber.org/protocol/mood')
		if mood != None:
				if isinstance(mood, list):
					print "mood is list", mood
					if len(mood) != 0:
						mood = mood[0]
					else:
						mood = None
				if mood:
					t = ''
					m = txt = icon = ''
					for el in mood.elements():
						if el.name == 'text':
							txt = unicode(el)
						else:
							m = unicode(self.main.moods.get(el.name))
							if self.main.moodIcons.has_key(el.name):
								self.ui.mood.setPixmap(QtGui.QPixmap(self.main.moodIcons[el.name].src))
								self.ui.mood.show()
							else:
								self.ui.mood.hide()
					if txt != '':
						self.mood = '%s - %s' % (m, txt)
					else:
						self.mood = m
				else:
					self.ui.mood.hide()
		else:
			self.ui.mood.hide()

	def initActivity(self):
		if self.in_muc or not self.contact:
			self.ui.activity.hide()
			return
		activity = self.contact.getPEP('http://jabber.org/protocol/activity')
		if activity != None:
			txt = ''
			general = ''
			spec = ''
			for el in activity.elements():
				if el.name == 'text':
					txt = unicode(el)
				else :
					general = el.name
					#if self.main.activityGroups.has_key(general):
						#general=self.main.activityGroups[general][0]
					spec = el.firstChildElement()
					if spec:
						spec=spec.name
					#if self.main.activities.has_key(spec):
						#spec=self.main.activities[spec]
					if self.main.activityIcons.has_key(spec):
						self.ui.activity.setPixmap(QtGui.QPixmap(self.main.activityIcons[spec].src))
						if self.main.activities.has_key(spec):
							self.activity = self.main.activities[spec]
						else:
							self.activity = spec
						self.ui.activity.show()
					elif self.main.activityIcons.has_key(general):
						self.ui.activity.setPixmap(QtGui.QPixmap(self.main.activityIcons[general].src))
						if self.main.activities.has_key(general):
							self.activity = self.main.activities[general]
						else:
							self.activity = general
						self.ui.activity.show()
					else:
						self.activity = ""
						self.ui.activity.hide()

			#text+='<br /><font size="-1"><b>%s</b> %s %s</font>' % (general, spec, txt)
		else:
			self.ui.activity.hide()

	def initPosition(self, position):
		g = position
		hint = self.sizeHint()
		w = QtGui.QDesktopWidget()
		if w.availableGeometry().y()+w.availableGeometry().height()<g.y()+10+hint.height():
			if g.x()-hint.width()-10>0:
				self.setGeometry(g.x()-hint.width()-10,g.y()-10-hint.height(),hint.width(),hint.height())
			else:
				self.setGeometry(g.x()+10,g.y()-10-hint.height(),hint.width(),hint.height())
		else:
			if g.x()-hint.width()-10>0:
				self.setGeometry(g.x()-hint.width()-10,g.y()+10,hint.width(),hint.height())
			else:
				self.setGeometry(g.x()+10,g.y()+10,hint.width(),hint.height())

	def hideMetaContacts(self):
		for i in range(self.mlayout.count()):
			item = self.mlayout.itemAt(0)
			if item.widget():
				item.widget().setParent(None)
			else:
				self.mlayout.removeItem(item)
		self.ui.metaWidget.hide()

	def showMetaContacts(self,meta):
		self.mlayout.addStretch()
		for item in meta:
			widget = QtGui.QLabel(self.ui.metaWidget)
			widget.setMouseTracking(True)
			widget.setCursor(QtCore.Qt.PointingHandCursor)
			widget.setPixmap(self.main.getIcon(item, status=unicode('online'), size="16x16").pixmap(16,16))
			widget.leaveEvent = self.tuneLeaveEvent
			def gen_enterEvent(item):
				def enterEvent(event):
					self.ui.jid.setText(item)
				return enterEvent
			def gen_mousePressEvent(item):
				roster = weakref.ref(self.main.ui.roster)
				def mousePressEvent(event):
					if event.button() == QtCore.Qt.RightButton:
						it = roster().getUserItems(item)
						if len(it) == 0:
							it = roster().getMetaItems(item)
							it = it[0][0]
						else:
							it = it[0]
						group = it.group
						jid = it.jid
						#if self.main.client.roster['users'].has_key(jid):
						contactMenu = roster().buildContactMenu(unicode(jid), group)
						#contactMenu.move(event.globalX(),event.globalY())
						contactMenu.popup(QtCore.QPoint(event.globalX(), event.globalY()))
					else:
						roster().openChat(item)
				return mousePressEvent
			widget.enterEvent = gen_enterEvent(item)
			widget.mousePressEvent = gen_mousePressEvent(item)
			self.mlayout.addWidget(widget)
		self.ui.metaWidget.show()

	def vcardMousePressEvent(self, event):
		vcardeditor.vcardEditorDialog(self.main, self.jid, self.main, False).show()
		self.hide()

	def vcardEnterEvent(self, event):
		self.ui.jid.setText(self.tr("Show VCard"))

	def tuneEnterEvent(self, event):
		self.ui.jid.setText(self.tune)

	def tuneLeaveEvent(self, event):
		self.ui.jid.setText(self.jid)

	def activityEnterEvent(self, event):
		self.ui.jid.setText(self.activity)

	def moodEnterEvent(self, event):
		self.ui.jid.setText(self.mood)

	def moodLeaveEvent(self, event):
		self.ui.jid.setText(self.jid)

	def enterEvent(self, event):
		self.focus = True
