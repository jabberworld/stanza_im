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
from joingroupchat_ui import *
from mucbrowser import MUCBrowserDialog
import pyxl

from twisted.python import log

class joinGroupChatWindow(QtGui.QDialog):
	def __init__(self,main,room="",server="",parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(True)
		self.ui=Ui_joingroupchat()
		self.ui.setupUi(self)
		self.main=main
		self.ui.bookmarkName.setEnabled(False)
		self.ui.autojoin.setEnabled(False)
		if not self.main.client.bookmarksEnabled:
			self.ui.bookmarkChat.setEnabled(False)
		
		self.ui.buttonBox.button(QtGui.QDialogButtonBox.Cancel).setText(self.tr("Cancel"))
		self.ui.buttonBox.button(QtGui.QDialogButtonBox.Ok).setText(self.tr("Join"))
		self.ui.buttonBox.button(QtGui.QDialogButtonBox.Ok).setIcon(QtGui.QIcon('images/16x16/categories/muc.png'))
		self.ui.buttonBox.button(QtGui.QDialogButtonBox.Ok).setEnabled(False)
		self.ui.browser.setText("")
		self.ui.browser.setToolTip(self.tr("Browse chat rooms"))
		self.ui.browser.setIcon(QtGui.QIcon('images/16x16/actions/service-discovery.png'))
		self.ui.serverName.setDuplicatesEnabled(False)

		self.ui.nickname.setText(self.main.selfName)
		mucjid = []
		for jid,node in self.main.client.disco[self.main.client.jid.host][(self.main.client.jid.host,None)]['items'].iterkeys():
			if not self.main.client.disco.get(jid):
				continue
			#print jid," : ",self.main.client.disco[jid]
			if 'http://jabber.org/protocol/muc' in self.main.client.disco[jid][(jid,node)].get('features',[]):
				mucjid.append(jid)
				self.ui.serverName.addItem(jid)
				if self.main.client.hasIdentity(jid, 'conference', 'text') and jid.startswith('c'):
					self.ui.serverName.setCurrentIndex(self.ui.serverName.count()-1)
				
		for s in self.main.config['groupchatServerHistory']:
			if s not in mucjid:
				if len(mucjid) == self.ui.serverName.count():
					self.ui.serverName.insertSeparator(len(mucjid))
				self.ui.serverName.addItem(s)
				
		
		QtCore.QObject.connect(self.ui.roomName,QtCore.SIGNAL(" textChanged ( const QString &)"),self.ui.bookmarkName.setText)
		QtCore.QObject.connect(self.ui.roomName,QtCore.SIGNAL(" textChanged ( const QString &)"),self.NameChanged)
		QtCore.QObject.connect(self.ui.serverName,QtCore.SIGNAL(" textChanged ( const QString &)"),self.NameChanged)
		QtCore.QObject.connect(self.ui.browser,QtCore.SIGNAL("clicked()"),self.mucBrowser)
		if len(room)!=0:
			self.ui.roomName.setText(room)
		else:
			self.ui.roomName.setFocus(QtCore.Qt.MouseFocusReason)
		if len(server)!=0:
			self.ui.serverName.insertItem(0,server)
			self.ui.serverName.setCurrentIndex(0)

	def mucBrowser(self):
		self.d=MUCBrowserDialog(self.main,unicode(self.ui.serverName.currentText()),self,self)
		self.d.show()

	def accept(self):
		jidobj = self.main.getJid(unicode(self.ui.roomName.text()) + '@' + unicode(self.ui.serverName.currentText()))
		if not jidobj:
			return
		jid = jidobj.full()
		nickname=unicode(self.ui.nickname.text())
		password=unicode(self.ui.password.text())
		saveRoom=self.ui.bookmarkChat.isChecked()
		autojoin=unicode(self.ui.autojoin.isChecked()).lower()
		bookmarkName=unicode(self.ui.bookmarkName.text())

		if self.ui.serverName.currentText() not in self.main.config['groupchatServerHistory']:
			self.main.config['groupchatServerHistory'].append(self.ui.serverName.currentText())

		if saveRoom and not self.main.client.bookmarks['conference'].has_key(jid):
			self.main.client.bookmarks['conference'][jid]=pyxl.client.Bookmark(bookmarkName, 'conference', jid, autojoin, nickname, password)
			self.main.client.setBookmarks()
			self.main.buildBookmarks()

		if len(password)==0:
			password=None
		if self.main.chat.addGroupChatTab(jid,nickname):
			self.main.client.joinGC(jid, nickname, password,self.main.config['sendRooms']=="True")
		self.done(1)

	def NameChanged(self,name):
		jidobj = self.main.getJid(unicode(self.ui.roomName.text()) + '@' + unicode(self.ui.serverName.currentText()))
		valid_jid = not (jidobj is None)
		self.ui.buttonBox.button(QtGui.QDialogButtonBox.Ok).setEnabled(valid_jid)
