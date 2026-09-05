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
from privacy_ui import *

from twisted.python import log

class PrivacyListEditorDialog(QtGui.QDialog):
	def __init__(self,main,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(True)
		self.ui=Ui_PrivacyListEditor()
		self.ui.setupUi(self)
		self.main=main.main
		self.changes={}

		for useritem in self.main.ui.roster.users:
			if useritem.privacy["block"] or useritem.privacy["hide"]:
				item=QtGui.QTreeWidgetItem(self.ui.privacyList)
				item.setText(0,useritem.name)
				
				widget=QtGui.QWidget(self.ui.privacyList)
				layout=QtGui.QHBoxLayout(widget)
				layout.setMargin(0)
				gr=QtGui.QButtonGroup(self)
				QtCore.QObject.connect(gr,QtCore.SIGNAL("buttonClicked ( QAbstractButton * )"),self.buttonClicked)

				hide=QtGui.QRadioButton("Hide",widget)
				hide.jid=unicode(useritem.jid)
				hide.typ="hide"
				if useritem.privacy['hide']:
					hide.setChecked(True)
				gr.addButton(hide)
				
				block=QtGui.QRadioButton("Block",widget)
				block.jid=unicode(useritem.jid)
				block.typ="block"
				if useritem.privacy['block']:
					hide.setChecked(True)
				gr.addButton(block)

				none=QtGui.QRadioButton("None",widget)
				none.jid=unicode(useritem.jid)
				none.typ="none"
				gr.addButton(none)

				layout.addWidget(block)
				layout.addWidget(hide)
				layout.addWidget(none)
				layout.addStretch()
				widget.setMinimumHeight(16)
				self.ui.privacyList.setItemWidget(item,1,widget)
		self.ui.privacyList.resizeColumnToContents(0)
			#useritem.privacy["block"] = self.isBlockedJID(item.value) and True
			#useritem.privacy["allow"] = self.isAllowedJID(item.value) and True
			#useritem.privacy["hide"] = self.isHiddenJID(item.value) and True
	
	def buttonClicked(self,button):
		self.changes[button.jid]=button.typ
		print self.changes

	def accept(self):
		for jid,value in self.changes.iteritems():
			if value=="block":
				self.main.client.privacy.active.unHideJID(jid)
				self.main.client.privacy.active.blockJID(jid)
				self.main.client.sendPresence(jid, typ="unavailable")
			elif value=="hide":
				self.main.client.privacy.active.unBlockJID(jid)
				self.main.client.privacy.active.hideJID(jid)
				self.main.client.sendPresence(jid, typ="unavailable")
			elif value=="none":
				self.main.client.privacy.active.unBlockJID(jid)
				self.main.client.privacy.active.unHideJID(jid)
		self.done(1)

	#def reject(self):
		#self.close()
