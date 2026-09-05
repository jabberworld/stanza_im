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
from albumfiletransfer_ui import *
from os.path import basename,isfile
from twisted.internet import threads, reactor
from include import utils

class albumFiletransferDialog(QtGui.QDialog):
	def __init__(self,main,files,jid,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.ui=Ui_albumFiletransferDialog()
		self.ui.setupUi(self)
		self.main=main
		self.files=files
		self.jid=jid
		self.descriptions={}
		for file in self.files:
			item=QtGui.QListWidgetItem(self.ui.files)
			item.setText(basename(unicode(file)))
			item.setData(32,QtCore.QVariant(unicode(file)))
		self.currentFile=None
		self.ui.photo.setText("")
		QtCore.QObject.connect(self.ui.files,QtCore.SIGNAL("currentItemChanged ( QListWidgetItem *, QListWidgetItem *)"),self.itemChanged)
		QtCore.QObject.connect(self.ui.addFiles,QtCore.SIGNAL("clicked()"),self.addFiles)

	def addFiles(self):
		# get files
		dialog = QtGui.QFileDialog()
		dialog.setResolveSymlinks(True)
		file=dialog.getOpenFileNames(self,self.tr("Choose files"))
		file=list(file)

		new=[] # temp variable
		for f in file:
			if unicode(f).endswith('.lnk'):
				f = utils.getFilenameFromLnk(unicode(f))
			if isfile(unicode(f)):
				new.append(unicode(f))
		file=new # path to files
		self._addFiles(file)
		
	def _addFiles(self, files):
		if len(files)!=0:
			self.files+=files
			for f in files:
				item=QtGui.QListWidgetItem(self.ui.files)
				item.setText(basename(unicode(f)))
				item.setData(32,QtCore.QVariant(unicode(f)))

	def loadPhoto(self,file):
		img=QtGui.QImage(file)
		image=img.scaledToWidth(300)#,QtCore.Qt.SmoothTransformation)
		if image.height()>300:
			image=img.scaledToHeight(300)
		return image
	
	def gotPhoto(self,image):
		self.ui.photo.setPixmap(QtGui.QPixmap.fromImage(image))

	def isImage(self,file):
		if unicode(file).lower().endswith('.jpg'):
			return True
		if unicode(file).lower().endswith('.png'):
			return True
		if unicode(file).lower().endswith('.gif'):
			return True
		if unicode(file).lower().endswith('.jpeg'):
			return True
		if unicode(file).lower().endswith('.bmp'):
			return True
		if unicode(file).lower().endswith('.tiff'):
			return True
		return False

	def itemChanged(self,item,old):
		file=unicode(item.data(32).toString())
		if self.currentFile:
			description=unicode(self.ui.description.toPlainText())
			self.descriptions[self.currentFile]=description
		if self.isImage(file):
			self.ui.photo.show()
			d=threads.deferToThread(self.loadPhoto,file)
			d.addCallback(self.gotPhoto)
		else:
			self.ui.photo.hide()
		
		if self.descriptions.has_key(file):
			self.ui.description.setText(self.descriptions[file])
		else:
			self.ui.description.setText("")
		self.currentFile=file

	def reject(self):
		print 'cancel'
		reactor.callLater(0, self.removeDialog)
		self.done(1)
		
		
	def removeDialog(self):
		#tohle asi nedelam dobre
		self.main.senddialog = None

	def accept(self):
		print 'accept'
		if self.currentFile:
			description=unicode(self.ui.description.toPlainText())
			self.descriptions[self.currentFile]=description
		descriptions={}#self.descriptions
		for file in self.files:
			descriptions[file]=""
			if self.descriptions.has_key(file):
				descriptions[file]=self.descriptions[file]
			
		#for i in range(int(self.ui.files.topLevelItemCount())):
			#child=self.ui.treeWidget.topLevelItem(i)
			#it=child.data(32,0)
			#file=unicode(it.toString())
			#descriptions[file]=unicode(child.text(1))
		jid=self.jid
		file=self.files

		self.main.events.addFTUploadEvent(jid,file,descriptions)
		reactor.callLater(0, self.removeDialog)
		self.done(1)
		
