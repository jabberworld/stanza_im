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
import sys, os
from configobj import ConfigObj
from include.constants import RESOURCEPATH

class emoticonsWidget(QtGui.QLabel):
	"""
	QLabel for choosing emoticons
	"""
	def __init__(self,main,parent=None):
		apply(QtGui.QLabel.__init__,(self,parent))
		self.setWindowFlags(QtCore.Qt.Popup)
		self.setObjectName('emoticonList')
		self.main=main #: mainWindow
		self.acceptor=None #: chatWidget or groupchatWidget which accepts request for addEmoticon
		self.l=[] #: list of emoticons [[':)',':(',...],[':*',':/',...],[],]
		self.emoWidth=None #: width of first emoticon
		self.emoHeight=None # height of first emoticon
		self.reinit()

	def event(self,event):
		"""
		Shows tooltip according to mouse pointer.
		"""
		# tooltip request:
		if int(event.type())==110:
			x=event.x()
			y=event.y()
			if x>0 and y>0 and x<self.pixmap.width()-5 and y<self.pixmap.height()-5:
				e=unicode(self.emoticonAt(x,y)).replace("<","&lt;").replace(">","&gt;")
				self.setToolTip("<img src=\""+self.smileys[e]+"\"/> "+e)
			else:
				self.setToolTip("")
		return QtGui.QLabel.event(self,event)

	def emoticonAt(self,x,y):
		"""
		Returns emoticon according to x,y.
		@type x: integer
		@param x: x
		@type y: integer
		@param y: y
		@rtype: unicode
		@return: emoticon (for example ":)")
		"""
		x=int(x/(self.emoWidth+2))
		y=int(y/(self.emoHeight+2))
		return self.l[y][x]
		
	def mousePressEvent(self,event):
		"""
		Calls acceptors function addEmoticon(choosed_emoticon) and unchecks acceptors ui,smileys button.
		"""
		if self.emoWidth:
			x=event.x()
			y=event.y()
			if x>0 and y>0 and x<self.pixmap.width()-5 and y<self.pixmap.height()-5:
				x=int(x/(self.emoWidth+2))
				y=int(y/(self.emoHeight+2))
				if self.acceptor:
					self.acceptor.addEmoticon(self.l[y][x])
			if self.acceptor:
				self.acceptor.ui.smileys.setChecked(False)
		self.hide()

	def reinit(self):
		"""
		Loads emoticon pack according to self.main.config['emoticons'].
		"""
		# load emoticons pack
		#smileys=ConfigObj("emoticons/"+self.main.config['emoticons'],encoding='UTF8')
		loaded,smileys=self.main.resourceManager.loadJabbimExtraConfig(RESOURCEPATH+"emoticons/"+self.main.config['emoticons'],RESOURCEPATH+'emoticons/default/smileys.cfg')
		src = RESOURCEPATH + '/emoticons/'
		if not loaded or len(smileys)==0:
			#smileys=ConfigObj(self.main.realHomeDir+"/emoticons/"+self.main.config['emoticons'],encoding='UTF8')
			loaded,smileys=self.main.resourceManager.loadJabbimExtraConfig(self.main.realHomeDir+"/emoticons/"+self.main.config['emoticons'],'emoticons/default/smileys.cfg')
			src=self.main.realHomeDir+'/emoticons/'
		if not loaded:
			self.main.config['emoticons'] = RESOURCEPATH+'/default/smileys.cfg'
		if len(smileys)==0:
			# emotions pack doesn't exist
			return

		# load images
		self.smileys={} #: images for emoticons. for example {":-)":"emoticons/default/smile.png"}
		for k,v in smileys['emoticons'].iteritems():
			self.smileys[k.replace("<","&lt;").replace(">","&gt;")]=src+os.path.dirname(self.main.config['emoticons'])+"/"+v
		
		added=[]
		x=0
		y=0
		self.emoWidth=None
		self.emoHeight=None
		self.l=[[]]
		
		# get first image height and width
		# fill self.l list
		for k,v in smileys['emoticons'].iteritems():
			if added.count(v)==0:
				added.append(v)
				if not self.emoWidth:
					p=QtGui.QPixmap(src+os.path.dirname(self.main.config['emoticons'])+"/"+v)
					self.emoWidth=int(p.width())
					self.emoHeight=int(p.height())
				self.l[-1].append(unicode(k))
				y+=1
				if y==6:
					self.l.append([])
					y=0
					x+=1
		if self.emoWidth:
			# count width and height for all images
			width=6*(self.emoWidth+2)+10
			height=(x+1)*(self.emoHeight+2)+10
			# make QPixmap with counted width and height
			self.pixmap=QtGui.QPixmap(width,height)
			self.pixmap.fill(self.palette().base().color())

		
			added=[]
			x=0
			y=0
			# paint emoticons to the self.pixmap
			painter=QtGui.QPainter(self.pixmap)
			for k,v in smileys['emoticons'].iteritems():
				if added.count(v)==0:
					added.append(v)
					p=QtGui.QPixmap(src+os.path.dirname(self.main.config['emoticons'])+"/"+v)
					em=p.scaled(self.emoWidth,self.emoHeight,QtCore.Qt.KeepAspectRatio)
					painter.drawPixmap(5+y*self.emoWidth+y*2,5+x*self.emoHeight+x*2,em)
					y+=1
					if y==6:
						y=0
						x+=1
			pen=QtGui.QPen()
			pen.setWidth(2)
			pen.setBrush(QtGui.QBrush(self.palette().dark().color()))
			painter.setPen(pen)
			painter.drawRect(0,0,width,height)
			painter.end()
			# set self.pixmap as background for QLabel
			self.setPixmap(self.pixmap)
