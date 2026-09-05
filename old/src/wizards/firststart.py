# -*- coding: utf-8 -*- 
from PyQt4 import QtCore, QtGui
import newprofile_ui
from twisted.internet import reactor
from twisted.python import log
from pyxl import register
import registration
import sys
import base64
from twisted.web.client import getPage
from include import rot13
from twisted.words.xish import domish
from twisted.words.xish.domish import Element
from twisted.words.protocols.jabber.xmlstream import IQ
import weakref

class registrationClass(register.RegisteringClient):
	def __init__(self,main, username, server, resource,password, port, reactor):
		register.RegisteringClient.__init__(self, username, server, resource,password, port, reactor)
		self.main=weakref.proxy(main)

	def nicknameConflict(self):
		firstStartWizard=self.main
		self.main.ui.error.setText("<b><font color=\"red\">"+firstStartWizard.tr("This Jabber ID is already registered by someone else.")+"</font></b>")
		self.main.state="pre"
		self.main.ui.stackedWidget_2.setCurrentIndex(0)
		self.main.ui.movie.stop()
		
		
	def _regfailed(self, el):
		for x in el.elements():
			#print unicode(x.toXml())
			if unicode(x.name)=="error":
				if x.hasAttribute("code"):
					if x['code']=="409":
						print "nickname conflict"
						self.reactor.callFromThread(self.nicknameConflict)
						#self.main.error="409"
#						registrationWizard=self.main
						#self.main.label.setTextFormat(QtCore.Qt.RichText)
#						self.main.label.setText("<b><font color=\"red\">"+registrationWizard.tr("This Jabber ID is already registered by someone else.")+"</font></b>")
						#self.main.registered=False
						#self.main.back()

	
	def registered(self):
		self.main.state="registered"
		firstStartWizard=self.main
		self.main.ui.stackedWidget_2.setCurrentIndex(3)
		self.main.ui.registerButton.setEnabled(True)
		self.main.ui.registerButton.setText(firstStartWizard.tr("Finish"))
		self.main.ui.movie.stop()
		
	def _authd(self, el):
		self.reactor.callFromThread(self.registered)

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
		d.addCallback(self.vcard_set).addErrback(self.vcard_set)
	
	def vcard_set(self,data=None):
		self.reactor.callFromThread(self.finished)
	
	def finished(self):
		self.main.state="done"
		self.main.accept()

	
class firstStartWizard(QtGui.QDialog):
	def __init__(self,main,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.ui=newprofile_ui.Ui_newProfile()
		self.ui.setupUi(self)
		self.main=weakref.proxy(main)
		self.jid=""
		self.state="pre"
		
		self.ui.servers.addItems(QtCore.QStringList([self.tr("Choose server")] + main.jabbimServers))
		self.ui.nickname.setValidator(QtGui.QRegExpValidator(QtCore.QRegExp("^([!#$%(-.0-9;=?a-zA-Z_]+)$"),self.ui.nickname))
		self.ui.registerButton.setEnabled(False)
		
		self.ui.movieLabel=QtGui.QLabel(self.ui.waitWidget)
		self.ui.movieLabel.setFrameShape(QtGui.QFrame.Box)
		self.ui.movieLabel.setFrameStyle(QtGui.QFrame.Plain)
		self.ui.movie=QtGui.QMovie("images/loading.gif")
		
		self.ui.movieLabel.setMovie(self.ui.movie)
		l=QtGui.QHBoxLayout(self.ui.waitWidget)
		l.addWidget(self.ui.movieLabel,0,QtCore.Qt.AlignCenter)
		self.cl=None
		
		QtCore.QObject.connect(self.ui.createAccount,QtCore.SIGNAL("toggled(bool)"),self.showCreateAccount)
		QtCore.QObject.connect(self.ui.useAccount,QtCore.SIGNAL("toggled(bool)"),self.showUseAccount)
		QtCore.QObject.connect(self.ui.servers,QtCore.SIGNAL("activated ( const QString & )"),self.serverChanged)
		QtCore.QObject.connect(self.ui.loadAvatar,QtCore.SIGNAL("clicked ( )"),self.setAvatar)
		QtCore.QObject.connect(self.ui.pushButton_3,QtCore.SIGNAL("clicked ( )"),self.onlineHelp)
		QtCore.QObject.connect(self.ui.servers,QtCore.SIGNAL("editTextChanged ( const QString & )"),self.serverChanged)
		QtCore.QObject.connect(self.ui.nickname,QtCore.SIGNAL("textEdited ( const QString & )"),self.nicknameChanged)
		QtCore.QObject.connect(self.ui.password,QtCore.SIGNAL("textEdited ( const QString & )"),self.passwordEdited)
		QtCore.QObject.connect(self.ui.password2,QtCore.SIGNAL("textEdited ( const QString & )"),self.passwordEdited)
		QtCore.QObject.connect(self.ui.useJid,QtCore.SIGNAL("textEdited ( const QString & )"),self.useJidEdited)
		QtCore.QObject.connect(self.ui.avatars,QtCore.SIGNAL("currentItemChanged ( QListWidgetItem * , QListWidgetItem * )"),self.avatarChanged)
		self.ui.stackedWidget_2.setCurrentIndex(0)

	def onlineHelp(self):
 		anchor="http://live.jabbim.cz/muckl/muckl.html?conf_room=jabbim&nick="
		QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))

	def avatarChanged(self,current,old):
	    pixmap=QtGui.QPixmap(current.icon().pixmap(128,128))
	    self.ui.avatarLabel.setPixmap(pixmap)

	def useJidEdited(self,jid):
		if self.main.getJid(unicode(jid)):
			self.ui.registerButton.setEnabled(True)
		else:
			self.ui.registerButton.setEnabled(False)

	def passwordEdited(self,p):
		self.enableRegister()
	
	def enableRegister(self):
		# FIXME: Tell user that password is zero-length
		samePass=self.ui.password.text()==self.ui.password2.text() and len(self.ui.password.text())!=0
		if self.main.getJid(self.jid) and samePass:
			self.ui.registerButton.setEnabled(True)
			self.ui.error.setText("")
		else:
			if not samePass:
				self.ui.error.setText(self.tr("Passwords are not the same."))
			else:
				self.ui.error.setText("")
			self.ui.registerButton.setEnabled(False)
	
	def nicknameChanged(self,nickname):
		if self.main.getJid(unicode(nickname+"@"+self.ui.servers.currentText())):
			self.jid=unicode(nickname+"@"+self.ui.servers.currentText())
			self.ui.jidLabel.setText("<b>"+self.jid+"</b>")
		else:
			self.ui.jidLabel.setText(self.tr("Nickname or server contains incorrent characters"))
		self.enableRegister()
	
	def serverChanged(self,server):
		server=unicode(server)
		nickname=unicode(self.ui.nickname.text())
		if self.main.getJid(unicode(nickname+"@"+self.ui.servers.currentText())):
			self.jid=nickname+"@"+server
			self.ui.jidLabel.setText("<b>"+self.jid+"</b>")
		else:
			self.ui.jidLabel.setText(self.tr("Nickname or server contains incorrent characters"))
		self.enableRegister()
	
	def showCreateAccount(self):
		self.ui.stackedWidget_2.setCurrentIndex(0)
		self.ui.registerButton.setText(self.tr("Register"))
		self.state="pre"
	
	def showUseAccount(self):
		self.ui.stackedWidget_2.setCurrentIndex(1)
		self.ui.registerButton.setText(self.tr("Create"))
		self.state="existed"

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
			self.ui.avatarLabel.setPixmap(avatar)
			if resized:
				QtGui.QMessageBox.information(self,self.tr("Avatar"),self.tr("Your avatar was too big. He had to be resized to smaller size."))

	def _register(self,data):
			if unicode(data)[0]=="1":
				self.ui.error.setText("<b><font color=\"red\">"+self.tr("This Jabber ID is already registered by someone else.")+"</font></b>")
				self.state="pre"
				#self.ui.stackedWidget_2.setCurrentIndex(0)
				#self.ui.movie.stop()
				self.ui.cancel.setEnabled(True)
			elif unicode(data)[0]=="0":
				j=self.jid.split("@")
				self.ui.stackedWidget_2.setCurrentIndex(2)
				self.ui.movie.start()
				name=j[0]
				server=j[1]
				password=unicode(self.ui.password.text())
				self.cl = registrationClass(self,name,server, 'jab',password, 5222, reactor)
				self.cl.connect()

	def _registerFailed(self,data):
		self.ui.error.setText("<b><font color=\"red\">"+self.tr("Can't connect the server")+"</font></b>")
		self.state="pre"
		#self.ui.stackedWidget_2.setCurrentIndex(0)
		#self.ui.movie.stop()
		self.ui.cancel.setEnabled(True)

			
	def accept(self):
		if self.state=='pre':
			if self.cl:
				self.cl.disconnect()
			self.ui.registerButton.setEnabled(False)
			self.ui.cancel.setEnabled(False)
			self.state="registering"
			self.ui.createAccount.hide()
			self.ui.useAccount.hide()
			j=self.jid.split("@")
			name=j[0]
			server=j[1]
			if server in self.main.jabbimServers:
				url = "http://content.jabbim.com/client/check.php?jid=%s" % self.jid
				d = getPage(str(url),timeout=5)
				d.addCallback(self._register)
				d.addErrback(self._registerFailed)
			else:
				self.ui.stackedWidget_2.setCurrentIndex(2)
				self.ui.movie.start()
				self._register("0")
		elif self.state=="existed":
			jid=unicode(self.ui.useJid.text()).strip()
			savePass=self.ui.useSavepass.isChecked()
			password=unicode(self.ui.usePass.text())
			self.main.newProfile(jid,password,savePass)
			self.main.fillLoginForm()
			if savePass:
				self.main.connect(delay=1.0)
   			self.done(1)
		elif self.state=="registered":
			self.ui.registerButton.setEnabled(False)
			self.ui.cancel.setEnabled(False)
			self.ui.stackedWidget_2.setCurrentIndex(2)
			self.ui.movie.start()
			card={}
			card["N-GIVEN"]=unicode(self.ui.firstname.text())
			card["N-FAMILY"]=unicode(self.ui.surname.text())
			card["EMAIL-INTERNET"]=unicode(self.ui.email.text())
			avatar=self.ui.avatarLabel.pixmap()
			if avatar:
				bytes=QtCore.QByteArray()
				buf=QtCore.QBuffer(bytes)
				buf.open(QtCore.QIODevice.WriteOnly)
				avatar.save(buf, "PNG")
				card["PHOTO-BINVAL"]=base64.encodestring(str(bytes))
			self.cl.setVCard(card)
		elif self.state=="done":
			if self.cl:
				self.cl.disconnect()
			j=self.jid.split("@")
			name=j[0]
			server=j[1]
			password=unicode(self.ui.password.text())
			self.main.newProfile(name+"@"+server,password,True)
			self.main.fillLoginForm()
   			self.main.connect(delay=1.0)
			self.done(1)


	def reject(self):
		if (self.state=="pre" or self.state=="done") or self.state=="existed":
			if self.cl:
				self.cl.disconnect()
			return QtGui.QDialog.reject(self)

	#def finished(self,result):
		#print "finished"
		#if self.cl:
			#self.cl.disconnect()
		#return QtGui.QWizard.finished(self,result)
