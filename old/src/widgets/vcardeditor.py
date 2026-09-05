import os
from PyQt4 import QtCore, QtGui
from vcardeditor_ui import *
import base64
from twisted.words.xish.domish import Element
from twisted.internet.defer import DeferredList 
from include.constants import RESOURCEPATH

try:
	from hashlib import sha1
except:
	log.msg('Please upgrade to python2.5')
	from sha import new as sha1

class vcardEditorDialog(QtGui.QDialog):
	def __init__(self,main,jid,parent=None,editable=True):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.ui=Ui_VCardEdit()
		self.ui.setupUi(self)
		self.main=main
		self.photo = None
		#print self.main.styleSheetText
		if jid not in [self.main.client.jid.full(), self.main.client.jid.userhost()]:
			self.setWindowTitle(jid+" - "+self.tr("vCard"))
		else:
			self.setWindowTitle(self.tr("VCard Editor"))
		
		layout=QtGui.QHBoxLayout(self.ui.versionWidget)
		layout.setMargin(0)
		self.scroll=QtGui.QScrollArea(self.ui.versionWidget)
		w=QtGui.QWidget()
		l=QtGui.QVBoxLayout(w)
		self.widget=QtGui.QWidget(w)
		self.widget.setLayout(QtGui.QVBoxLayout())
		l.addWidget(self.widget)
		l.addStretch()
		l.setMargin(0)
		self.scroll.setWidget(w)
		self.scroll.setWidgetResizable(True)
		layout.addWidget(self.scroll)
		
		self.data=None
		vysledky = []
		d=self.main.client.getVCard(jid)
		d.addCallback(self.vcardArrived)
		d.addErrback(self.noVcard)
		vysledky.append(d)
		jidt=self.main.getJid(jid)
		if jidt.resource:
			resources=[jidt.resource]
		else:
			resources=[]
		if self.main.client.roster['users'].has_key(jidt.userhost()):
			resources=self.main.client.roster['users'][jidt.userhost()].resources.keys()
			while None in resources:
				resources.remove(None)
		for res in resources:
			#s = self.main.client.getLast(jidt.userhost()+"/"+res)
			#s.addCallback(self.lastReceived,res)
			#s.addErrback(self.lastErrReceived,res)
			d = self.main.client.getVersion(jidt.userhost()+"/"+res)
			d.addCallback(self.versionReceived,res)
			d.addErrback(self.versionErrReceived,res)
			vysledky.append(d)
		if len(resources)==0:
			s = self.main.client.getLast(jidt.userhost())
			s.addCallback(self.lastReceived,None)
			s.addErrback(self.lastErrReceived,None)
			
		DeferredList(vysledky).addCallback(self._vysledky)
		self.ui.tabWidget.setEnabled(False)

		self.ui.avatar.setPixmap(QtGui.QPixmap())
		self.ui.clearAvatar.hide()

		self.ui.avatar.setText("")
		text=""
		#if data.has_key("N-GIVEN"):
			#self.ui.name.setText(data['N-GIVEN'])
		#if data.has_key("N-FAMILY"):
			#self.ui.surname.setText(data['N-FAMILY'])
		#if data.has_key("PHOTO-BINVAL"):
			#image=base64.decodestring(str(data["PHOTO-BINVAL"]))
			#pixmap=QtGui.QPixmap()
			#pixmap.loadFromData(image)
			#pixmap=QtGui.QIcon(pixmap)
			#self.ui.avatar.setPixmap(pixmap.pixmap(128,128))
		#if data.has_key("NICKNAME"):
			#self.ui.nickname.setText(data['NICKNAME'])
		#if data.has_key("FN"):
			#self.ui.fullname.setText(data['FN'])
		#<ADR>
			#<WORK/>
			#<EXTADD>Suite 600</EXTADD>
			#<STREET>1899 Wynkoop Street</STREET>
			#<LOCALITY>Denver</LOCALITY>
			#<REGION>CO</REGION>
			#<PCODE>80202</PCODE>
			#<CTRY>USA</CTRY>
		#</ADR>
		self.editable=editable
		self.ui.pushButton.setIcon(QtGui.QIcon(RESOURCEPATH+'images/16x16/categories/v-card.png'))
		
		if not self.editable:
			self.ui.name.setReadOnly(True)
			self.ui.nickname.setReadOnly(True)
			self.ui.fullname.setReadOnly(True)
			self.ui.surname.setReadOnly(True)
			self.ui.pushButton.hide()
			self.ui.setAvatar.hide()
			self.ui.homeextadd.setReadOnly(True)
			self.ui.homestreet.setReadOnly(True)
			self.ui.homelocality.setReadOnly(True)
			self.ui.homecountry.setReadOnly(True)
			self.ui.homepcode.setReadOnly(True)
			self.ui.about.setReadOnly(True)
			self.ui.homepage_edit.hide()
		else:
			QtCore.QObject.connect(self.ui.setAvatar, QtCore.SIGNAL("clicked()"),self.setAvatar)
			QtCore.QObject.connect(self.ui.clearAvatar, QtCore.SIGNAL("clicked()"),self.clearAvatar)
			self.ui.homepage_label.hide()
	
	def _vysledky(self, vysl):
		print 'list end', vysl
		if len(vysl) == 1:
			#version info neprislo
			if vysl[0][0] == 1:
				self.ui.download.hide()
				self.ui.tabWidget.setEnabled(True)
				return
			else:
				self.ui.download.show()
				self.ui.tabWidget.setEnabled(False)
		else:
			for res in vysl[1:]:
				if res[0] == 1:
					self.ui.download.hide()
					self.ui.tabWidget.setEnabled(True)
	
	def noVcard(self,data=None):
		print 'no vcard', data
		self.ui.download.setText(self.tr("Can't download vCard of this contact."))
		
	def vcardArrived(self,data):
		self.data=data
		if self.data:
			for x in self.data.elements():
				name=unicode(x.name)
				if name=="NICKNAME":
					self.ui.nickname.setText(unicode(x))
				elif name=="FN":
					self.ui.fullname.setText(unicode(x))
				elif name=="URL":
					if self.editable:
						self.ui.homepage_edit.setText(unicode(x))
					else:
						ht = unicode(x)
						ht = '<a href="%s">%s</a>' % (ht, ht)
						self.ui.homepage_label.setText(ht)
				elif name=="ADR":
					typ=""
					for y in x.elements():
						child=unicode(y.name)
						if child=="HOME":
							typ="HOME"
					if typ=="HOME":
						for y in x.elements():
							child=unicode(y.name)
							if child=="EXTADD":
								self.ui.homeextadd.setText(unicode(y))
							elif child=="STREET":
								self.ui.homestreet.setText(unicode(y))
							elif child=="LOCALITY":
								self.ui.homelocality.setText(unicode(y))
							elif child=="CTRY":
								self.ui.homecountry.setText(unicode(y))
							elif child=="PCODE":
								self.ui.homepcode.setText(unicode(y))
				elif name == "DESC":
					self.ui.about.setText(unicode(x))
				else:
					for y in x.elements():
						child=unicode(y.name)
						if name=="N" and child=="GIVEN":
							self.ui.name.setText(unicode(y))
						elif name=="N" and child=="FAMILY":
							self.ui.surname.setText(unicode(y))
						elif name=="PHOTO" and child=="BINVAL" and len(str(unicode(y)))!=0:
							image=base64.decodestring(str(unicode(y)))
							pixmap=QtGui.QPixmap()
							pixmap.loadFromData(image)
							pixmap=QtGui.QIcon(pixmap)
							self.ui.avatar.setPixmap(pixmap.pixmap(128,128))
							if self.editable:
								self.ui.clearAvatar.show()
			self.ui.download.hide()
			self.ui.tabWidget.setEnabled(True)
		else:
			self.data = Element(('vcard-temp','vCard'))
			self.ui.download.setText(self.tr("Can't download vCard of this contact."))
			if self.editable:
				self.ui.download.hide()
				self.ui.tabWidget.setEnabled(True)
	
	def makeVersionWidget(self,res):
		box=QtGui.QGroupBox(res,self.widget)
		l=QtGui.QGridLayout(box)
		labelName=QtGui.QLabel(self.tr('Name:'),box)
		labelOs=QtGui.QLabel(self.tr('Operating System:'),box)
		labelVersion=QtGui.QLabel(self.tr('Version:'),box)
		lineName=QtGui.QLineEdit(box)
		lineName.setReadOnly(True)
		lineOs=QtGui.QLineEdit(box)
		lineOs.setReadOnly(True)
		lineVersion=QtGui.QLineEdit(box)
		lineVersion.setReadOnly(True)
		l.addWidget(labelName,0,0)
		l.addWidget(lineName,0,1)
		l.addWidget(labelVersion,1,0)
		l.addWidget(lineVersion,1,1)
		l.addWidget(labelOs,2,0)
		l.addWidget(lineOs,2,1)
		self.widget.layout().addWidget(box)
		return lineName,lineOs,lineVersion
	
	def makeLastWidget(self,res):
		if res==None:
			res=self.tr("Offline Information")
			box=QtGui.QGroupBox(res,self.widget)
			l=QtGui.QGridLayout(box)
			labelLast=QtGui.QLabel(self.tr('Last Active:'),box)
			lineLast=QtGui.QLineEdit(box)
			lineLast.setReadOnly(True)
			labelLastStatus=QtGui.QLabel(self.tr('Last Status:'),box)
			lineLastStatus=QtGui.QLineEdit(box)
			lineLastStatus.setReadOnly(True)
			l.addWidget(labelLast,0,0)
			l.addWidget(lineLast,0,1)
			l.addWidget(labelLastStatus,1,0)
			l.addWidget(lineLastStatus,1,1)
		#else:
			#box=QtGui.QGroupBox(res,self.widget)
			#l=QtGui.QGridLayout(box)
			#labelLast=QtGui.QLabel(self.tr('Last Active:'),box)
			#lineLast=QtGui.QLineEdit(box)
			#lineLast.setReadOnly(True)
			#l.addWidget(labelLast,3,0)
			#l.addWidget(lineLast,3,1)
		self.widget.layout().addWidget(box)
		return lineLast,lineLastStatus
	
	def versionReceived(self, el,res):
		lineName,lineOs,lineVersion=self.makeVersionWidget(res)
		query = el.firstChildElement()
		os = None
		for x in query.elements():
			if x.name == "name":
				lineName.setText(unicode(x))
			elif x.name == "version":
				lineVersion.setText(unicode(x))
			elif x.name == "os":
				os = unicode(x)
		if os != None:
			lineOs.setText(os)
		else:
			lineOs.setText(self.tr("Unable to retrieve."))
		self.ui.download.hide()
		self.ui.tabWidget.setEnabled(True)
	
	def lastReceived(self, el,res):
		lineLast,lineLastStatus=self.makeLastWidget(res)
		query = el.firstChildElement()
		lineLast.setText(unicode(self.main.utils.elapsed_time(self.main, int(query['seconds']), separator=', ')))
		lineLastStatus.setText(unicode(query))
		self.ui.download.hide()
		self.ui.tabWidget.setEnabled(True)

	def versionErrReceived(self, err,res):
		print err
		lineName,lineOs,lineVersion=self.makeVersionWidget(res)
		lineName.setText(self.tr("Unable to retrieve."))
		lineVersion.setText(self.tr("Unable to retrieve."))
		lineOs.setText(self.tr("Unable to retrieve."))
	
	def lastErrReceived(self, err,res):
		print err
		lineLast,lineLastStatus=self.makeLastWidget(res)
		lineLast.setText(self.tr("Unable to retrieve."))
		lineLastStatus.setText(self.tr("Unable to retrieve."))
		
	def clearAvatar(self):
		self.ui.avatar.setPixmap(QtGui.QPixmap())
		self.ui.clearAvatar.hide()

	def setAvatar(self):
		file=list(QtGui.QFileDialog.getOpenFileNames(self,"Choose picture"))
		if len(file)!=0:
			resized=False
			file=unicode(file[0])
			avatar=QtGui.QPixmap(file)
			print int(avatar.width()), int(avatar.height())
			if int(avatar.width())>128 or int(avatar.height())>128:
				avatar=avatar.scaled(128,128,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
				resized=True
			self.ui.avatar.setPixmap(avatar)
			if resized:
				QtGui.QMessageBox.information(self,self.tr("Avatar"),self.tr("Your avatar was too big. He had to be resized to smaller size."))

	def accept(self):
		if self.editable and self.data:
			name2=unicode(self.ui.name.text())
			nickname=unicode(self.ui.nickname.text())
			fullname=unicode(self.ui.fullname.text())
			surname=unicode(self.ui.surname.text())
			about=unicode(self.ui.about.toPlainText())

			homeextadd=unicode(self.ui.homeextadd.text())
			homestreet=unicode(self.ui.homestreet.text())
			homelocality=unicode(self.ui.homelocality.text())
			homecountry=unicode(self.ui.homecountry.text())
			homepcode=unicode(self.ui.homepcode.text())
			url=unicode(self.ui.homepage_edit.text())

			avatar=self.ui.avatar.pixmap()
			n=False
			photo=False
			homeadr=False
			for x in self.data.elements():
				name=unicode(x.name)
				if name=="NICKNAME" and nickname!=None:
					x.children = []
					x.children.append(nickname)
					nickname=None
					#x.addElement('value', content = unicode(widget.text()))
				elif name=="FN" and fullname!=None:
					x.children = []
					x.children.append(fullname)
					fullname=None

				elif name=="DESC" and about != None:
					x.children = []
					x.children.append(about)
					about=None
				elif name=="URL" and url != None:
					x.children = []
					x.children.append(url)
					about=None

				elif name=="ADR":
					typ=""
					for y in x.elements():
						child=unicode(y.name)
						if child=="HOME":
							typ="HOME"
							homeadr=x
					if typ=="HOME":
						for y in x.elements():
							child=unicode(y.name)
							if child=="EXTADD":
								y.children = []
								y.children.append(homeextadd)
								homeextadd=None
							elif child=="STREET":
								y.children = []
								y.children.append(homestreet)
								homestreet=None
							elif child=="LOCALITY":
								y.children = []
								y.children.append(homelocality)
								homelocality=None
							elif child=="CTRY":
								y.children = []
								y.children.append(homecountry)
								homecountry=None
							elif child=="PCODE":
								y.children = []
								y.children.append(homepcode)
								homepcode=None


				else:
					for y in x.elements():
						child=unicode(y.name)
						if name=="N":
							n=x
						if name=="PHOTO":
							photo=x
						if name=="N" and child=="GIVEN" and name2!=None:
							y.children = []
							y.children.append(name2)
							name2=None
							#self.ui.name.setText(unicode(y))
						elif name=="N" and child=="FAMILY" and surname!=None:
							y.children = []
							y.children.append(surname)
							surname=None
						elif name=="PHOTO" and child=="BINVAL" and avatar!=None:
							#avatar=self.ui.avatar.pixmap()
							y.children = []
							if not avatar.isNull():
								bytes=QtCore.QByteArray()
								buf=QtCore.QBuffer(bytes)
								buf.open(QtCore.QIODevice.WriteOnly)
								avatar.save(buf, "PNG")
								self.photo = str(bytes)
								y.children.append(base64.encodestring(str(bytes)))
							avatar=None
			if name2!=None:
				if len(name2)!=0:
					if not n:
						n=self.data.addElement('N')
					n.addElement('GIVEN', content = unicode(name2))
			if surname!=None:
				if len(surname)!=0:
					if not n:
						n=self.data.addElement('N')
					n.addElement('FAMILY', content = unicode(surname))
			if homeextadd!=None:
				if len(homeextadd)!=0:
					if not homeadr:
						homeadr=self.data.addElement('ADR')
						homeadr.addElement('HOME')
					homeadr.addElement('EXTADD', content = unicode(homeextadd))
			if homestreet!=None:
				if len(homestreet)!=0:
					if not homeadr:
						homeadr=self.data.addElement('ADR')
						homeadr.addElement('HOME')
					homeadr.addElement('STREET', content = unicode(homestreet))
			if homelocality!=None:
				if len(homelocality)!=0:
					if not homeadr:
						homeadr=self.data.addElement('ADR')
						homeadr.addElement('HOME')
					homeadr.addElement('LOCALITY', content = unicode(homelocality))
			if homecountry!=None:
				if len(homecountry)!=0:
					if not homeadr:
						homeadr=self.data.addElement('ADR')
						homeadr.addElement('HOME')
					homeadr.addElement('CTRY', content = unicode(homecountry))
			if homepcode!=None:
				if len(homepcode)!=0:
					if not homeadr:
						homeadr=self.data.addElement('ADR')
						homeadr.addElement('HOME')
					homeadr.addElement('PCODE', content = unicode(homepcode))
			if avatar!=None:
				if not avatar.isNull():
					bytes=QtCore.QByteArray()
					buf=QtCore.QBuffer(bytes)
					buf.open(QtCore.QIODevice.WriteOnly)
					avatar.save(buf, "PNG")
					if not photo:
						photo=self.data.addElement('PHOTO')
					self.photo = str(bytes)
					photo.addElement('BINVAL', content = base64.encodestring(str(bytes)))
			if nickname!=None:
				if len(nickname)!=0:
					self.data.addElement('NICKNAME',content = unicode(nickname))
			if fullname!=None:
				if len(fullname)!=0:
					self.data.addElement('FN',content = unicode(fullname))
			if about != None:
				if len(about) != 0:
					self.data.addElement('DESC', content = unicode(about))
			if url != None:
				if len(url) != 0:
					self.data.addElement('URL', content = unicode(url))
			self.ui.download.setText(self.tr("Saving VCard"))
			self.ui.download.show()
			self.ui.pushButton.setEnabled(False)
			self.ui.pushButton_2.setEnabled(False)
			self.main.client.setVCard(self.data).addCallback(self.vcard_set).addErrback(self.vcard_set_error)
			
		else:
			self.done(1)
	
	def vcard_set(self,data=None):
		self.main.client.getVCard(self.main.client.jid.userhost())
		contact = self.main.client.getContactByJid(self.main.client.jid.userhost())
		#print contact
		show = contact.resources[self.main.client.jid.resource].show
		status=contact.resources[self.main.client.jid.resource].status
		if status == None:
			status = ''
		#print 'vcard set ',status, show
		#print self.photo
		if self.photo != None:
			hash = sha1(self.photo).hexdigest()
			self.main.avatarDef[self.main.client.jid.userhost()] = hash
		self.main.sendPresence(None, show = show, message = status)
		
		self.done(1)

	def vcard_set_error(self,data=None):
		self.ui.download.setText(self.tr("Can't send VCard to the server"))
		self.ui.download.show()
		self.ui.pushButton.setEnabled(True)
		self.ui.pushButton_2.setEnabled(True)
		#self.done(1)
	
	#def getVCard_(self,data,jid):
		#return self.main.client.getVCard(self,jid)
