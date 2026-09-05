# -*- coding: utf-8 -*- 
from PyQt4 import QtCore, QtGui
from twisted.internet import reactor
from twisted.python import log
import registration
import sys
import pyxl

#def createFirstPage(joinGroupchatWizard):
	## language and server
	#page=QtGui.QWizardPage()
	#page.setTitle(joinGroupchatWizard.tr("Join Groupchat"))

	##joinGroupchatWizard.label=QtGui.QLabel(joinGroupchatWizard.trUtf8("Vítejte ........."))
	##joinGroupchatWizard.label.setWordWrap(True)
	
	#joinGroupchatWizard.address=QtGui.QRadioButton(joinGroupchatWizard.tr("I know room Jabber ID (address)."))
	#joinGroupchatWizard.address.setChecked(True)
	#joinGroupchatWizard.browser=QtGui.QRadioButton(joinGroupchatWizard.tr("I want to browse rooms."))

	#layout=QtGui.QGridLayout()
	##layout.addWidget(joinGroupchatWizard.label,0,0,1,2)
	#layout.addWidget(joinGroupchatWizard.address,1,0,1,2)
	#layout.addWidget(joinGroupchatWizard.browser,2,0,1,2)

	#page.registerField("address",joinGroupchatWizard.address)
	#page.registerField("browser",joinGroupchatWizard.browser)
	#page.setTitle(joinGroupchatWizard.trUtf8("Join Groupchat"))
	#page.setSubTitle(joinGroupchatWizard.trUtf8("Choose one of options"))

	#page.setLayout(layout)
	#return page


def createSecondPage(joinGroupchatWizard):
	# language and server
	page=QtGui.QWizardPage()
	page.setTitle(joinGroupchatWizard.tr("Join Groupchat"))

	#joinGroupchatWizard.label=QtGui.QLabel(joinGroupchatWizard.trUtf8("Type Jabber ID of room where you want to join."))
	#joinGroupchatWizard.label.setWordWrap(True)

	jidLabel=QtGui.QLabel(joinGroupchatWizard.tr("Room Jabber ID:"))
	joinGroupchatWizard.jid=QtGui.QLineEdit()
	QtCore.QObject.connect(joinGroupchatWizard.jid,QtCore.SIGNAL("textEdited ( const QString & )"),joinGroupchatWizard.jidChanged)

	nicknameLabel=QtGui.QLabel(joinGroupchatWizard.tr("Nickname:"))
	joinGroupchatWizard.nickname=QtGui.QLineEdit(unicode(joinGroupchatWizard.main.client.jid.userhost()).split("@")[0])

	passwordLabel=QtGui.QLabel(joinGroupchatWizard.tr("Password:"))
	joinGroupchatWizard.password=QtGui.QLineEdit()
	joinGroupchatWizard.password.setEchoMode(QtGui.QLineEdit.Password)


	joinGroupchatWizard.saveRoom=QtGui.QCheckBox(joinGroupchatWizard.tr("Save room to the bookmarks"))

	bookmarkNameLabel=QtGui.QLabel(joinGroupchatWizard.tr("Bookmark name:"))
	joinGroupchatWizard.bookmarkName=QtGui.QLineEdit()
	joinGroupchatWizard.bookmarkName.setEnabled(False)
	QtCore.QObject.connect(joinGroupchatWizard.saveRoom,QtCore.SIGNAL("stateChanged ( int )"),joinGroupchatWizard.bookmarkName.setEnabled)

	joinGroupchatWizard.autojoin=QtGui.QCheckBox(joinGroupchatWizard.tr("Autojoin"))
	joinGroupchatWizard.autojoin.setEnabled(False)
	QtCore.QObject.connect(joinGroupchatWizard.saveRoom,QtCore.SIGNAL("stateChanged ( int )"),joinGroupchatWizard.autojoin.setEnabled)

	layout=QtGui.QGridLayout()
	#layout.addWidget(joinGroupchatWizard.label,0,0,1,2)
	layout.addWidget(jidLabel,1,0,1,1)
	layout.addWidget(joinGroupchatWizard.jid,1,1,1,1)
	layout.addWidget(nicknameLabel,2,0,1,1)
	layout.addWidget(joinGroupchatWizard.nickname,2,1,1,1)
	layout.addWidget(passwordLabel,3,0,1,1)
	layout.addWidget(joinGroupchatWizard.password,3,1,1,1)
	layout.addWidget(joinGroupchatWizard.saveRoom,4,0,1,2)
	layout.addWidget(bookmarkNameLabel,5,0,1,1)
	layout.addWidget(joinGroupchatWizard.bookmarkName,5,1,1,1)
	layout.addWidget(joinGroupchatWizard.autojoin,6,0,1,2)
	
	page.registerField("jid*",joinGroupchatWizard.jid)
	page.registerField("saveRoom",joinGroupchatWizard.saveRoom)
	page.registerField("bookmarkName*",joinGroupchatWizard.bookmarkName)
	page.registerField("nickname*",joinGroupchatWizard.bookmarkName)
	page.registerField("password",joinGroupchatWizard.bookmarkName)
	page.registerField("autojoin",joinGroupchatWizard.autojoin)
	
	page.setTitle(joinGroupchatWizard.trUtf8("Join Groupchat"))
	page.setSubTitle(joinGroupchatWizard.trUtf8(""))

	page.setLayout(layout)
	return page

class joinGroupchatWizard(QtGui.QWizard):
	def __init__(self,main,parent=None):
		apply(QtGui.QWizard.__init__,(self,parent))
		self.main=main
		#self.addPage(createFirstPage(self))
		self.addPage(createSecondPage(self))
		self.setWindowTitle(self.tr("Join Groupchat"))
		self.setButtonText(QtGui.QWizard.FinishButton,self.tr("Join"))
		mucjid = None
		for jid,node in self.main.client.disco[self.main.client.jid.host][(self.main.client.jid.host,None)]['items'].iterkeys():
			print jid
			print self.main.client.disco[self.main.client.jid.host][(self.main.client.jid.host,None)]['items'][jid]
			if self.main.client.hasIdentity(jid, 'conference', 'text') and jid.startswith('c'):
				mucjid = jid
				break
		if mucjid:
			self.jid.setText("@"+mucjid)
	#def initializePage(self,i):
		#if i==1:
			#if self.browser.isChecked():
					#self.accept()

	def jidChanged(self,text):
		text=unicode(text)
		if text.find('@')!=-1:
			jid=self.main.getJid(text)
			if jid:
				self.bookmarkName.setText(unicode(jid.userhost()).split("@")[0])

	def accept(self):
		#if self.browser.isChecked():
			#self.hide()
			##self.regwiz=registration.registrationWizard(self.main,self.main)
			##self.regwiz.exec_()
			#self.main.mucBrowser(True)
		#else:
		jid=unicode(self.jid.text())
		nickname=unicode(self.nickname.text())
		password=unicode(self.password.text())
		saveRoom=self.saveRoom.isChecked()
		autojoin=unicode(self.autojoin.isChecked()).lower()
		bookmarkName=unicode(self.bookmarkName.text())
		self.hide()
		#if len(bookmarkName)==0:
			#bookmarkName=jid
			#for bkey in self.main.client.bookmarks['conference'].keys():
				#if self.main.client.bookmarks['conference'][bkey].jid.userhost() == jid:
					#bookmarkName = self.main.client.bookmarks['conference'][bkey].name

		if saveRoom and not self.main.client.bookmarks['conference'].has_key(jid):
			self.main.client.bookmarks['conference'][jid]=pyxl.client.Bookmark(bookmarkName, 'conference', jid, autojoin, nickname, password)
			self.main.client.setBookmarks()
			self.main.buildBookmarks()

		if len(password)==0:
			password=None
		#print "joining",room,nickname
		if self.main.chat.addGroupChatTab(jid,nickname):
			self.main.client.joinGC(jid, nickname, password)

		return QtGui.QWizard.accept(self)

	#def finished(self,result):
		#print "finished"
		#if self.cl:
			#self.cl.disconnect()
		#return QtGui.QWizard.finished(self,result)
