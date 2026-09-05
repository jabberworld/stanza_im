import os
from PyQt4 import QtCore, QtGui
from addcontact_ui import *
from search import *
import pyxl
from include.constants import RESOURCEPATH

class addContactDialog(QtGui.QDialog):
	def __init__(self,main,parent=None,jid="",group=None,name="",add=True,check=True):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.ui=Ui_addContact()
		self.ui.setupUi(self)
		self.main=main
		self.add=add
		self.ui.save=self.ui.buttonBox.button(QtGui.QDialogButtonBox.Ok)
		self.ui.buttonBox.button(QtGui.QDialogButtonBox.Cancel).setText(self.tr("Cancel"))
		self.ui.save.setText(self.tr("Add"))
		self.ui.save.setIcon(QtGui.QIcon(RESOURCEPATH+'images/16x16/actions/gtk-add.png'))
		self.ui.search.setIcon(QtGui.QIcon(RESOURCEPATH+'images/16x16/actions/service-discovery.png'))
		self.ui.search.setToolTip(self.tr("Search User"))
		self.ui.search.setText("")
		for k,v in self.main.client.roster['groups'].iteritems():
			if k==group:
				self.ui.add_group.insertItem(0,unicode(k))
			else:
				self.ui.add_group.addItem(unicode(k))
		self.ui.add_group.setCurrentIndex(0)
		self.ui.add_nickname.setText(unicode(name))

		if jid != '' and jid != False:
			jid=self.main.getJid(jid).userhost()
			self.ui.add_jid.setText(unicode(jid))

		if not self.add:
			self.ui.add_jid.setEnabled(False)
			self.ui.add_message.hide()
			self.ui.add_messageLabel.hide()
		else:
			self.jidChanged()
			QtCore.QObject.connect(self.ui.add_jid,QtCore.SIGNAL("textEdited ( const QString & )"),self.jidChanged)
		QtCore.QObject.connect(self.ui.search,QtCore.SIGNAL("clicked()"),self.search)
		#if check:
			#self.ui.add_jid.setEnabled(False)

		self.searchJid=None
		self.muc = False

		for key in self.main.client.disco.keys():
			got=False
			if self.main.client.disco[key][(key,None)].has_key("identities"):
				for identity in self.main.client.disco[key][(key,None)]["identities"].itervalues():
					if identity['category']=="directory" and identity['type']=='user':
						got=True
			if self.main.client.disco[key][(key,None)].has_key("features") and got:
				if "jabber:iq:search" in list(self.main.client.disco[key][(key,None)]['features']):
					#print self.main.client.disco[key]
					self.searchJid=unicode(key)
		print 'searchJid',self.searchJid
		if not self.searchJid or not self.add:
			self.ui.search.hide()

	def jidChanged(self,text=""):
		text=unicode(self.ui.add_jid.text())
		#if text.find('@')!=-1 and text.count('@') == 1:
		jid=self.main.getJid(text)
		if jid:
			self.ui.save.setEnabled(True)
			if self.main.client.bookmarksEnabled:
				host = jid.host
				self.muc = False
				if self.main.client.disco.has_key(host) and self.main.client.disco[host][(host,None)].has_key('identities'):
					for id in self.main.client.disco[host][(host,None)]['identities'].itervalues():
						if id.get('category') == 'conference' and id.get('type') == 'text':
							self.muc = True
				if self.muc == True:
					self.ui.save.setText(self.tr('Add bookmark'))
					self.ui.add_group.setEnabled(False)
					self.ui.search.setEnabled(False)
					self.ui.add_message.hide()
					self.ui.add_messageLabel.hide()
				else:
					self.ui.save.setText(self.tr('Add'))
					self.ui.add_group.setEnabled(True)
					self.ui.search.setEnabled(True)
					self.ui.add_message.show()
					self.ui.add_messageLabel.show()
			return

		
		self.ui.save.setEnabled(False)
	
	def search(self):
		d=self.main.client.getSearchForm(self.searchJid)
		d.addCallback(self._gotSearchForm)
		
	def _gotSearchForm(self,data):
		if not data:
			return
		jid,legacy,form=data
		if form!=None:
			self.dialog=searchDialog(self.main,jid,form,self,self)
			self.dialog.show()


		
	def accept(self):
		jid=unicode(self.ui.add_jid.text())
		nickname=unicode(self.ui.add_nickname.text())
		group=unicode(self.ui.add_group.currentText())
		message=unicode(self.ui.add_message.toPlainText())
		if not self.muc:
			self.main.client.addContact(jid,message,nickname,[group])
		else:
			if self.main.client.bookmarksEnabled:
				if nickname == '':
					nickname = jid.split('@')[0]
				if  not self.main.client.bookmarks['conference'].has_key(nickname):
					self.main.client.bookmarks['conference'][nickname] = pyxl.client.Bookmark(nickname, 'conference', jid, 'false')
					self.main.client.setBookmarks()
					self.main.buildBookmarks()


		self.done(1)
