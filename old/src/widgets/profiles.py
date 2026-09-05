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
import sys; sys.path.append('..')
import os
from profiles_ui import *
from include import utils
import shutil
from twisted.python import log
from include.constants import RESOURCEPATH

try:
	from wizards import firststart
except:
	pass

class passwordChangeDialog(QtGui.QDialog):
	def __init__(self,main,parent):
		QtGui.QDialog.__init__(self,parent)
		self.main=main
		layout=QtGui.QGridLayout(self)
		self.setWindowTitle(self.tr("Password Change"))
		header=QtGui.QLabel(self.tr('Enter your new password:'),self)
		header2=QtGui.QLabel(self.tr('Confirm password:'),self)
		self.dif=QtGui.QLabel(self.tr('Passwords vary.'))
		self.pass1=QtGui.QLineEdit(self)
		self.pass1.setEchoMode(QtGui.QLineEdit.Password)
		self.pass2=QtGui.QLineEdit(self)
		self.pass2.setEchoMode(QtGui.QLineEdit.Password)
		QtCore.QObject.connect(self.pass1,QtCore.SIGNAL("textChanged ( const QString & )"),self.textChanged)
		QtCore.QObject.connect(self.pass2,QtCore.SIGNAL("textChanged ( const QString & )"),self.textChanged)
		
		no=QtGui.QPushButton(self.tr("Cancel"),self)
		self.ok=QtGui.QPushButton(self.tr("Change"),self)
		QtCore.QObject.connect(self.ok,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(no,QtCore.SIGNAL("clicked()"),self.reject)
		self.ok.setEnabled(False)
		
		layout.addWidget(header,0,0,1,2)
		layout.addWidget(self.pass1,1,0,1,2)
		layout.addWidget(header2,2,0,1,2)
		layout.addWidget(self.pass2,3,0,1,2)
		layout.addWidget(no,4,0,1,1)
		layout.addWidget(self.ok,4,1,1,1)
		layout.addWidget(self.dif,5,0,1,2)

	def textChanged(self,text):
		if self.pass1.text()==self.pass2.text() and len(unicode(self.pass1.text()))!=0:
			self.ok.setEnabled(True)
			self.dif.setText(self.tr('Passwords identify.'))
		else:
			self.ok.setEnabled(False)
			self.dif.setText(self.tr('Passwords vary.'))
			
	def accept(self):
		text=unicode(self.pass1.text())
		self.main.client.setRegisterForm(self.main.client.jid.host,{'username':self.main.client.jid.user,'password':text})
		self.done(1)
		
class profilesWindow(QtGui.QMainWindow):
	def __init__(self,main,parent=None):
		apply(QtGui.QMainWindow.__init__,(self,parent))
		self.main=main
		self.ui=Ui_profilesWindow()
		self.ui.setupUi(self)
		self.loadProfiles()
		QtCore.QObject.connect(self.ui.profilesList, QtCore.SIGNAL("itemSelectionChanged()"),self.profileChanged)
		QtCore.QObject.connect(self.ui.removeProfile, QtCore.SIGNAL("clicked()"),self.removeProfile)
		QtCore.QObject.connect(self.ui.newProfile, QtCore.SIGNAL("clicked()"),self.newProfile)
		QtCore.QObject.connect(self.ui.changePassword, QtCore.SIGNAL("clicked()"),self.changePassword)
		self.ui.removeProfile.setEnabled(False)
		self.ui.changePassword.setEnabled(False)

	def changePassword(self):
		if not self.main.client:
			QtGui.QMessageBox.information(self,self.tr('Error'),self.tr("You have to be connected to change password."))
		else:
			#text,ok=QtGui.QInputDialog.getText(self,self.tr('Change password'), self.tr("Your new password:"),QtGui.QLineEdit.Password)
			#text=unicode(text)
			#if ok==True and len(text)!=0:
				#self.main.client.setRegisterForm(self.main.client.jid.host(),{'username':self.main.client.jid.user(),'password':text})
			d=passwordChangeDialog(self.main,self)
			d.exec_()

	def loadProfiles(self):
		self.ui.removeProfile.setEnabled(False)
		self.ui.changePassword.setEnabled(False)
		self.ui.profilesList.clear()
		profiles=utils.getProfiles(self.main.realHomeDir)
		for profile in profiles:
			jid=profile.replace('-profile','')
	
			if os.path.isfile(self.main.realHomeDir+"/"+profile+"/avatars/"+unicode(jid)):
				avatar=QtGui.QPixmap(self.main.realHomeDir+"/"+profile+"/avatars/"+unicode(jid)).scaled(22,22,QtCore.Qt.KeepAspectRatio)
				result=QtGui.QPixmap(22,22)
				result.fill(QtCore.Qt.transparent)
				painter=QtGui.QPainter(result)
				painter.drawPixmap((22-avatar.width())/2,(22-avatar.height())/2,avatar)
				painter.end()
				result=QtGui.QIcon(result)
			else:
				result=QtGui.QIcon(RESOURCEPATH+"images/22x22/apps/jabbim.png")
	
			#self.ui.profilesList.addItem(result,jid)
			item=QtGui.QListWidgetItem(result,jid,self.ui.profilesList)
		return profiles

	def newProfile(self):
		fs=firststart.firstStartWizard(self.main,self.main)
		fs.exec_()
		self.loadProfiles()

	def removeProfile(self):
		item=self.ui.profilesList.currentItem()
		jid=unicode(item.text())
		ret=QtGui.QMessageBox.question(self,self.tr("Remove profile?"), self.tr("Do you really want to remove profile ")+unicode(jid)+"?",QtGui.QMessageBox.Yes|QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)  
		if ret==QtGui.QMessageBox.Yes:
			shutil.rmtree(self.main.realHomeDir+"/"+jid+"-profile",True)
			profiles=self.loadProfiles()
			print profiles
			if len(profiles)>0:
				print "profilechanged"
				self.main.profileChanged(profiles[0].replace("-profile",''))
			self.main.fillLoginForm()

	def profileChanged(self):
		if self.ui.profilesList.currentItem():
			self.ui.removeProfile.setEnabled(True)
			self.ui.changePassword.setEnabled(True)
		else:
			self.ui.removeProfile.setEnabled(False)
			self.ui.changePassword.setEnabled(False)

