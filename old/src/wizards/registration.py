# -*- coding: utf-8 -*- 
from PyQt4 import QtCore, QtGui
from twisted.internet import reactor
from pyxl import register
from twisted.python import log
import sys
from include import rot13
from twisted.words.xish import domish
from twisted.words.xish.domish import Element
##from twisted.internet import reactor, address
from twisted.words.protocols.jabber.xmlstream import IQ
import base64

class firstPage(QtGui.QWizardPage):
	def __init__(self,registrationWizard):
		QtGui.QWizardPage.__init__(self)
		self.setTitle(registrationWizard.tr("Introduction"))
		label=QtGui.QLabel(registrationWizard.trUtf8("Server is where user data are stored."))
		label.setWordWrap(True)
		policy=label.sizePolicy()
		policy.setHeightForWidth(True)
		policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
		label.setSizePolicy(policy)
	
		label2=QtGui.QLabel(registrationWizard.trUtf8("Jabber ID is like email address. It is your identity in Jabber network."))
		label2.setWordWrap(True)
		policy=label2.sizePolicy()
		policy.setHeightForWidth(True)
		policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
		label2.setSizePolicy(policy)
		self.registrationWizard=registrationWizard
		registrationWizard.label=QtGui.QLabel("")
		registrationWizard.label.setWordWrap(True)
	
		registrationWizard.jidLabel=QtGui.QLineEdit()
		registrationWizard.jidLabel.setReadOnly(True)
		
	
		nicknameLabel=QtGui.QLabel(registrationWizard.tr("Nickname:"))
		registrationWizard.nicknameLineEdit=QtGui.QLineEdit()
		registrationWizard.nicknameLineEdit.setValidator(QtGui.QRegExpValidator(QtCore.QRegExp("^([!#$%(-.0-9;=?a-zA-Z]+)$"),registrationWizard.nicknameLineEdit))
		
		passwordLabel=QtGui.QLabel(registrationWizard.tr("Password:"))
		passwordLineEdit=QtGui.QLineEdit()
		passwordLineEdit.setEchoMode(QtGui.QLineEdit.Password)
	
		password2Label=QtGui.QLabel(registrationWizard.tr("Password again:"))
		password2LineEdit=QtGui.QLineEdit()
		password2LineEdit.setEchoMode(QtGui.QLineEdit.Password)
		
		serverLabel=QtGui.QLabel(registrationWizard.tr("Server:"))
		registrationWizard.serverComboBox=QtGui.QComboBox()
		registrationWizard.serverComboBox.addItems(QtCore.QStringList([registrationWizard.tr("Choose server")] + registrationWizard.main.jabbimServers))
		registrationWizard.serverComboBox.setEditable(True)
		QtCore.QObject.connect(registrationWizard.serverComboBox,QtCore.SIGNAL("activated ( const QString & )"),registrationWizard.serverComboBoxActivated)
		QtCore.QObject.connect(registrationWizard.serverComboBox,QtCore.SIGNAL("editTextChanged ( const QString & )"),registrationWizard.serverComboBoxActivated)
		QtCore.QObject.connect(registrationWizard.nicknameLineEdit,QtCore.SIGNAL("textEdited ( const QString & )"),registrationWizard.nicknameChanged)
		
		layout=QtGui.QGridLayout()
		layout.addWidget(registrationWizard.label,0,0,1,2)
		layout.addWidget(label,1,0,1,2)
		layout.addWidget(serverLabel,2,0,1,1)
		layout.addWidget(registrationWizard.serverComboBox,2,1,1,1)
		layout.addWidget(nicknameLabel,3,0,1,1)
		layout.addWidget(registrationWizard.nicknameLineEdit,3,1,1,1)
		layout.addWidget(passwordLabel,4,0,1,1)
		layout.addWidget(passwordLineEdit,4,1,1,1)
		layout.addWidget(password2Label,5,0,1,1)
		layout.addWidget(password2LineEdit,5,1,1,1)
		layout.addWidget(label2,6,0,1,2)
		layout.addWidget(QtGui.QLabel(registrationWizard.trUtf8("Your Jabber ID")),7,0,1,1)
		layout.addWidget(registrationWizard.jidLabel,7,1,1,1)
		self.registerField("server",registrationWizard.serverComboBox)
		self.registerField("nickname*",registrationWizard.nicknameLineEdit)
		self.registerField("password*",passwordLineEdit)
		self.registerField("password2*",password2LineEdit)
		self.registerField("jabberid*",registrationWizard.jidLabel)
		self.setTitle(registrationWizard.trUtf8("Jabber account registration"))
		self.setSubTitle(registrationWizard.trUtf8("Choose server, where you want to register."))
		self.setLayout(layout)

	def isComplete(self):
		if not self.registrationWizard.main.getJid(self.registrationWizard.jid) or unicode(self.field("password").toString())!=unicode(self.field("password2").toString()):
			return False
		else:
			r=QtGui.QWizardPage.isComplete(self)
			return r
			


class waitPage(QtGui.QWizardPage):
	def __init__(self,registrationWizard):
		QtGui.QWizardPage.__init__(self)
		self.registrationWizard=registrationWizard
		self.setTitle(registrationWizard.trUtf8("Jabber account registration"))
		self.setSubTitle(registrationWizard.trUtf8("Registration in progress, please wait."))

	def isComplete(self):
		self.registrationWizard.button(QtGui.QWizard.BackButton).setEnabled(False)
		return False

class secondPage(QtGui.QWizardPage):
	def __init__(self,registrationWizard):
		QtGui.QWizardPage.__init__(self)
		self.registrationWizard=registrationWizard
		self.setTitle(registrationWizard.trUtf8("Jabber account registration"))
		self.setSubTitle(registrationWizard.trUtf8("Your accont was registered. Now it is recomended to fill in some info about you."))
		
		firstnameLabel=QtGui.QLabel(registrationWizard.tr("Firstname:"))
		firstnameLineEdit=QtGui.QLineEdit()
		
		surnameLabel=QtGui.QLabel(registrationWizard.tr("Surname:"))
		surnameLineEdit=QtGui.QLineEdit()
		
		emailLabel=QtGui.QLabel(registrationWizard.tr("Email:"))
		emailLineEdit=QtGui.QLineEdit()
		emailLineEdit.setValidator(QtGui.QRegExpValidator(QtCore.QRegExp("^[_a-zA-Z0-9-]+(\.[_a-zA-Z0-9-]+)*@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.(([0-9]{1,3})|([a-zA-Z]{2,3})|(aero|coop|info|museum|name))$"),emailLineEdit))
		
		avatarLabel=QtGui.QLabel(registrationWizard.tr("Avatar:"))
		registrationWizard.avatar=QtGui.QLabel("")
		button=QtGui.QPushButton(registrationWizard.tr("Open"))
		QtCore.QObject.connect(button,QtCore.SIGNAL("clicked()"),registrationWizard.setAvatar)
		
		layout=QtGui.QGridLayout()
		#layout.addWidget(label,0,0,1,2)
		layout.addWidget(firstnameLabel,1,0,1,1)
		layout.addWidget(firstnameLineEdit,1,1,1,2)
		layout.addWidget(surnameLabel,2,0,1,1)
		layout.addWidget(surnameLineEdit,2,1,1,2)
		layout.addWidget(emailLabel,3,0,1,1)
		layout.addWidget(emailLineEdit,3,1,1,2)
		layout.addWidget(avatarLabel,4,0,1,1)
		layout.addWidget(registrationWizard.avatar,4,1,1,1)
		layout.addWidget(button,4,2,1,1)
			
		self.registerField("firstname",firstnameLineEdit)
		self.registerField("surname",surnameLineEdit)
		self.registerField("email",emailLineEdit)
		
		self.setLayout(layout)

	def isComplete(self):
		r=QtGui.QWizardPage.isComplete(self)
		self.registrationWizard.button(QtGui.QWizard.BackButton).setEnabled(False)
		return r

def createSecondPage(registrationWizard):
	
	page=QtGui.QWizardPage()
	#page.setTitle(registrationWizard.tr("Email and Nickname"))
	page.setTitle(registrationWizard.trUtf8("Jabber account registration"))
	page.setSubTitle(registrationWizard.trUtf8("Your accont was registered. Now it is recomended to fill in some info about you."))
	
	firstnameLabel=QtGui.QLabel(registrationWizard.tr("Firstname:"))
	firstnameLineEdit=QtGui.QLineEdit()
	
	surnameLabel=QtGui.QLabel(registrationWizard.tr("Surname:"))
	surnameLineEdit=QtGui.QLineEdit()
	
	emailLabel=QtGui.QLabel(registrationWizard.tr("Email:"))
	emailLineEdit=QtGui.QLineEdit()
	emailLineEdit.setValidator(QtGui.QRegExpValidator(QtCore.QRegExp("^[_a-zA-Z0-9-]+(\.[_a-zA-Z0-9-]+)*@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.(([0-9]{1,3})|([a-zA-Z]{2,3})|(aero|coop|info|museum|name))$"),emailLineEdit))

	avatarLabel=QtGui.QLabel(registrationWizard.tr("Avatar:"))
	registrationWizard.avatar=QtGui.QLabel("")
	button=QtGui.QPushButton(registrationWizard.tr("Open"))
	QtCore.QObject.connect(button,QtCore.SIGNAL("clicked()"),registrationWizard.setAvatar)
	
	layout=QtGui.QGridLayout()
	#layout.addWidget(label,0,0,1,2)
	layout.addWidget(firstnameLabel,1,0,1,1)
	layout.addWidget(firstnameLineEdit,1,1,1,2)
	layout.addWidget(surnameLabel,2,0,1,1)
	layout.addWidget(surnameLineEdit,2,1,1,2)
	layout.addWidget(emailLabel,3,0,1,1)
	layout.addWidget(emailLineEdit,3,1,1,2)
	layout.addWidget(avatarLabel,4,0,1,1)
	layout.addWidget(registrationWizard.avatar,4,1,1,1)
	layout.addWidget(button,4,2,1,1)
		
	page.registerField("firstname*",firstnameLineEdit)
	page.registerField("surname*",surnameLineEdit)
	page.registerField("email*",emailLineEdit)
	
	page.setLayout(layout)
	return page

def createFinishPage(registrationWizard):
	
	page=QtGui.QWizardPage()
	page.setTitle(registrationWizard.trUtf8("Jabber account registration"))
	page.setSubTitle(registrationWizard.trUtf8("Your registration was successfully completed."))
	return page

class registrationClass(register.RegisteringClient):
	def __init__(self,main, username, server, resource,password, port, reactor):
		register.RegisteringClient.__init__(self, username, server, resource,password, port, reactor)
		self.main=main

	def _regfailed(self, el):
		for x in el.elements():
			#print unicode(x.toXml())
			if unicode(x.name)=="error":
				if x.hasAttribute("code"):
					if x['code']=="409":
						print "nickname conflict"
						self.main.error="409"
						registrationWizard=self.main
						self.main.label.setTextFormat(QtCore.Qt.RichText)
						self.main.label.setText("<b><font color=\"red\">"+registrationWizard.tr("This Jabber ID is already registered by someone else.")+"</font></b>")
						self.main.registered=False
						self.main.back()

	def _authd(self, el):
		self.main.registered=True
		self.main.next()

	def setVCard(self, card):
		""" Posle vlastni vcard """
#		log.msg( 'requesting vcard for ' + unicode(jid))
		iq = IQ(self.xmlstream, 'set')
#		iq['to'] = jid
		vcard = iq.addElement('vCard', 'vcard-temp')
		for k,v in card.iteritems():
			s = k.split('-')
			if len(s)>1:
				found = False
				for el in vcard.elements():
					if el.name == s[0]:
						el.addElement(s[1], content = v)
						found = True
						break
				if not found:
					el = vcard.addElement(s[0])
					el.addElement(s[1], content = v)
			else:
				el = vcard.addElement(k, content = v)
				
					
		#self.disp(iq['id'])
		iq.timeout = 60
		d = iq.send()
		log.msg("END: setVCard")
		#self.main.next()
		#return d


class registrationWizard(QtGui.QWizard):
	def __init__(self,main,parent=None):
		apply(QtGui.QWizard.__init__,(self,parent))
		self.main=main
		self.addPage(firstPage(self))
		#self.addPage(createThirdPage(self))
		self.addPage(waitPage(self))
		self.addPage(secondPage(self))
		self.addPage(createFinishPage(self))
		self.setWindowTitle(self.tr("Registration Wizard"))
		self.cl=None
		self.error=None
		self.registered=False
		self.jid=""
		QtCore.QObject.connect(self,QtCore.SIGNAL("currentIdChanged ( int ) "),self.idChanged)
		#self.setOption(QtGui.QWizard.IndependentPages,True)

	def idChanged(self,i):
		self.button(QtGui.QWizard.BackButton).setEnabled(False)

	def setAvatar(self):
		file=list(QtGui.QFileDialog.getOpenFileNames(self,self.tr("Choose avatar")))
		if len(file)!=0:
			resized=False
			file=unicode(file[0])
			avatar=QtGui.QPixmap(file)
			print int(avatar.width()), int(avatar.height())
			if int(avatar.width())>128 or int(avatar.height())>128:
				avatar=avatar.scaled(128,128,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
				resized=True
			self.avatar.setPixmap(avatar)
			if resized:
				QtGui.QMessageBox.information(self,self.tr("Avatar"),self.tr("Your avatar was too big. He had to be resized to smaller size."))


	def nicknameChanged(self,nickname):
		if self.main.getJid(unicode(nickname+"@"+self.serverComboBox.currentText())):
			self.jid=unicode(nickname+"@"+self.serverComboBox.currentText())
			self.jidLabel.setText(self.jid)

	def serverComboBoxActivated(self,server):
		server=unicode(server)
		nickname=unicode(self.field("nickname").toString())
		self.jid=nickname+"@"+server
		self.jidLabel.setText(self.jid)
		self.page(0).emit(QtCore.SIGNAL("completeChanged()"))

	def initializePage(self,i):
		#page=self.page(i)
		#print i,self.error
		#if i==2 and self.error!=None:
			#if self.error=="409":
				
			#self.error=None
		#if i==2:
			#server=servers[int(self.field("server").toString())-1]
			#self.serverLabel.setText("@"+server)
		if i==1:
			#server=servers[int(self.field("server").toString())-1]
			#jid=unicode(self.field("jid").toString())
			#password=unicode(self.field("password").toString())
			self.button(QtGui.QWizard.BackButton).setEnabled(False)
			j=self.jid.split("@")
			name=j[0]
			server=j[1]
			password=unicode(self.field("password").toString())

			self.cl = registrationClass(self,name,server, 'jab',password, 5222, reactor)
			#log.startLogging(sys.stdout)
			self.cl.connect()
			reactor.run()
		elif i==2:
			self.button(QtGui.QWizard.BackButton).setEnabled(False)
			self.registered=True
		elif i==3:
			self.button(QtGui.QWizard.BackButton).setEnabled(False)
			card={}
			card["N-GIVEN"]=unicode(self.field("firstname").toString())
			card["N-FAMILY"]=unicode(self.field("surname").toString())
			card["EMAIL-INTERNET"]=unicode(self.field("email").toString())
			avatar=self.avatar.pixmap()
			if avatar:
				bytes=QtCore.QByteArray()
				buf=QtCore.QBuffer(bytes)
				buf.open(QtCore.QIODevice.WriteOnly)
				avatar.save(buf, "PNG")
				card["PHOTO-BINVAL"]=base64.encodestring(str(bytes))
			self.cl.setVCard(card)
		return

	def validateCurrentPage(self):
		if int(self.currentId())==1:
			if self.registered==True:
				return True
			else:
				return False
		elif int(self.currentId())==0:
			if unicode(self.field("password").toString())==unicode(self.field("password2").toString()):
				return True
			else:
				self.label.setText(self.trUtf8("Passwords are not same."))
				return False
		else:
			return self.currentPage().validatePage()

	def reject(self):
		
		if self.cl:
			self.cl.disconnect()
		if self.registered:
			j=self.jid.split("@")
			name=j[0]
			server=j[1]
			password=unicode(self.field("password").toString())
			
			self.main.config['passwd']=rot13.scramble(password)
			self.main.config['jid']=name+"@"+server
			self.main.config['savePasswd']="True"
			self.main.fillLoginForm()
			self.main.connect()
		return QtGui.QWizard.reject(self)

	def accept(self):
		if self.cl:
			self.cl.disconnect()
		if self.registered:
			j=self.jid.split("@")
			name=j[0]
			server=j[1]
			password=unicode(self.field("password").toString())

			#self.main.config['passwd']=rot13.scramble(password)
			#self.main.config['jid']=name+"@"+server
			#self.main.config['savePasswd']="True"
			self.main.newProfile(name+"@"+server,password,"True")
			self.main.fillLoginForm()
			self.main.connect(delay=0.5)
		return QtGui.QWizard.accept(self)

	def finished(self,result):
		print "finished"
		if self.cl:
			self.cl.disconnect()
		return QtGui.QWizard.finished(self,result)
