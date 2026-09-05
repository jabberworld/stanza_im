import os
from PyQt4 import QtCore, QtGui

class rosterStyle:
	def __init__(self,roster):
		self.roster=roster
		self.spaceBetweenGroups=0

	def heightForItem(self,item):
		return 22

	def paintGroupItem(self,painter,item,x,y):
		"""
		paints group item in compact roster
		"""
		if item.main=="special":
			# we don't want to paint `special` item
			return

		# set the font size for text
		doc=QtGui.QTextDocument()
		#font=doc.defaultFont()
		font=QtGui.QApplication.fontMetrics()
		fontHeight=int(font.height())
		#font.setPixelSize(12)
		#doc.setDefaultFont(font)

		# paint background of item
		painter.save()
		painter.translate(x,y)
		painter.fillRect(0,0,self.roster.width(),22,QtGui.QBrush(self.roster.main.ui.groupStyleWidget.palette().window()))
		painter.restore()

		
		p=painter.pen()
		painter.setPen(self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text))

		#painter.save()
		#painter.translate(x,y+5)
		#painter.drawText(self.roster.width()-52,12,unicode(item.online))
		#painter.drawPixmap(self.roster.width()-45,0,self.roster.main.getIcon(status="online",size="16x16").pixmap(16,16))
		#painter.drawText(self.roster.width()-28,12,unicode(item.all))
		#painter.drawPixmap(self.roster.width()-21,0,self.roster.main.getIcon(status="offline",size="16x16").pixmap(16,16))
		#painter.restore()

		painter.setPen(p)
		
		if item.icon:
			painter.drawPixmap(x,y,item.icon.pixmap(22,22))

		#doc.setHtml("<font color=\""+self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text).name()+"\">"+item.escapedName+" ("+str(item.online)+"/"+str(item.all)+")</font>")

		#painter.save()
		#painter.translate(x+30,y+(22-fontHeight)/2)
		#doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width(),y+20))
		#painter.restore()

		# write the name of the group
		doc.setHtml("<font color=\""+self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text).name()+"\">"+item.escapedName+"</font>")
		painter.save()
		painter.translate(x+30,y+(22-fontHeight)/2)
		doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width(),y+22))
		painter.restore()
		width=int(font.width("("+str(item.online)+"/"+str(item.all)+")"))
		doc.setHtml("<font color=\""+self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text).name()+"\">("+str(item.online)+"/"+str(item.all)+")</font>")
		painter.save()
		painter.translate((int(self.roster.width())-width-6),y+(22-fontHeight)/2)
		doc.drawContents(painter, QtCore.QRectF(0,0,width+15,y+20))
		painter.restore()

	def paintUserItem(self,painter,useritem,x,y):
		"""
		paints user item in normal roster
		"""
		if useritem==self.roster.item:
			#if self.roster.metaItems.has_key(useritem.metajid) or self.roster.main.config['bigOnClick']=="True":

				#height=79
				##if not useritem.statusMessage:
					##height-=32
				##if not self.roster.metaItems.has_key(useritem.metajid):
					##height-=16
				#self.roster.selectedHeight=height+20
	
	
				## paint roster background
				##painter.save()
				##painter.translate(x,y)
				##painter.fillRect(0,0,self.roster.width(),32,QtGui.QBrush(self.roster.palet.color(QtGui.QPalette.Base)))
				##painter.restore()
	
				## set pen and brush for item background
				#b=painter.brush()
				#p=painter.pen()
				#if self.roster.theme:
					#painter.setBrush(self.roster.main.ui.selectedItemStyle.palette().window())
					#pen=QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Text))
				#else:
					#painter.setBrush(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight))
					#color=self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight)
					## Qt4.2 uses .light() but Qt4.3 uses lighter(), so we have to try both of them because of compatibility
					#try:
						#pen=QtGui.QPen(color.lighter())
					#except:
						#pen=QtGui.QPen(color.light())
				#pen.setWidth(0)
				#painter.setPen(pen)
	
				## paint item background and border
				#painter.save()
				#painter.translate(x,y)
				#painter.drawRect(5,5,self.roster.width()-10,height+3)
				#painter.restore()
				#painter.setBrush(b)
				#painter.setPen(p)
				
				## paint user status icon
				#if useritem in self.roster.events:
					#if self.roster.bl:
						#painter.drawPixmap(x+7,y+11,useritem.icon.pixmap(32,32))
					#else:
						#painter.drawPixmap(x+7,y+11,useritem.blink.pixmap(32,32))
				#else:
					#if useritem.privacy['block'] or useritem.privacy['hide']:
						#painter.drawPixmap(x+7,y+11,self.roster.main.getIcon(status="error",size="32x32").pixmap(32,32))
					#else:
						#painter.drawPixmap(x+7,y+11,useritem.icon.pixmap(32,32))
	
				## set font
				#doc=QtGui.QTextDocument()
				#font=QtGui.QApplication.fontMetrics()
				#fontHeight=int(font.height())
				##font=doc.defaultFont()
				##font.setPixelSize(12)
				##doc.setDefaultFont(font)
	
				## paint user name 
				#res=""
				#if len(self.roster.main.client.roster['users'][useritem.jid].resources)>1:
					#res=" ("+str(len(self.roster.main.client.roster['users'][useritem.jid].resources))+")"
				#if self.roster.theme:
					#doc.setHtml("<font color=\""+self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name()+"\">"+useritem.escapedName+res+"</font>")
				#else:
					#doc.setHtml("<font color=\""+self.roster.palet.color(QtGui.QPalette.HighlightedText).name()+"\">"+useritem.escapedName+res+"</font>")
				#painter.save()
				#painter.translate(x+41,y+8+(32-fontHeight)/2)


				
				#if useritem.avatar:
					#doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-33-32,y+28))
				#else:
					#doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-33,y+28))
				#painter.restore()
	
				## show activeWidget
				#if self.roster.statusLabel:
					#if self.roster.reshow:
						#buttons=[]
						## get metacontact items
						#if self.roster.metaItems.has_key(useritem.metajid) and not self.roster.searchMode:
							#for meta in self.roster.metaItems[useritem.metajid]:
								#buttons.append([meta,self.roster.main.getIcon(meta.jid,size="16x16",status=self.roster.main.icons[unicode(meta.status)])])
						## change activeWidget data and geometry
						#self.roster.statusLabel.setData(useritem,buttons)
						#self.roster.statusLabel.setGeometry(41,y+7,self.roster.width()-46,height)
						#self.roster.statusLabel.show()
						#self.roster.reshow=False
					#elif self.roster.changePos:
						#self.roster.statusLabel.setGeometry(41,y+7,self.roster.width()-46,height)
						#self.roster.changePos=False
			#elif self.roster.main.config['bigOnClick']=="False":
			if True:
				height=28
				self.roster.selectedHeight=28
				#painter.save()
				#painter.translate(x,y)
				#painter.fillRect(0,0,self.roster.width(),32,QtGui.QBrush(self.roster.palet.color(QtGui.QPalette.Base)))
				#painter.restore()


				# set pen and brush for item background
				b=painter.brush()
				p=painter.pen()
				background=None
				if self.roster.theme:
					painter.setBrush(self.roster.main.ui.selectedItemStyle.palette().window())
					pen=QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Text))
					background=self.roster.main.ui.selectedItemStyle.palette().window().color()
				else:
					painter.setBrush(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight))
					color=self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight)
					background=self.roster.palet.color(QtGui.QPalette.Base)
					# Qt4.2 uses .light() but Qt4.3 uses lighter(), so we have to try both of them because of compatibility
					try:
						pen=QtGui.QPen(color.lighter())
					except:
						pen=QtGui.QPen(color.light())
					

				pen.setWidth(0)
				painter.setPen(pen)
	
				# paint item background and border
				painter.save()
				painter.translate(x,y-2)
				painter.drawRect(1,0,self.roster.width()-2,height-5)
				painter.restore()
				painter.setBrush(b)
				painter.setPen(p)


				if useritem in self.roster.events:
					if self.roster.bl:
						painter.drawPixmap(x+7,y,useritem.icon.pixmap(22,22))
					else:
						painter.drawPixmap(x+7,y,useritem.blink.pixmap(22,22))
				else:
					if useritem.privacy['block'] or useritem.privacy['hide']:
						painter.drawPixmap(x+7,y,self.roster.main.getIcon(status="error",size="22x22").pixmap(22,22))
					else:
						painter.drawPixmap(x+7,y,useritem.icon.pixmap(22,22))
				doc=QtGui.QTextDocument()
				font=QtGui.QApplication.fontMetrics()
				fontHeight=int(font.height())
				#font=doc.defaultFont()
				#font.setPixelSize(12)
				#font.setWeight(18)
				#doc.setDefaultFont(font)

				avatar=self.roster.main.client.getAvatarImg(useritem.jid)
				if avatar:
					avatar=avatar[0]
				else:
					avatar=self.roster.main.client.getAvatarImg(None)
					if avatar:
						avatar=avatar[0]
				avatar=avatar.scaled(22,22,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
				#if useritem.avatar:
					#pixmap=useritem.avatar.pixmap(22,22)
				res=""
				if len(self.roster.main.client.roster['users'][useritem.jid].resources)>1:
					res=" ("+str(len(self.roster.main.client.roster['users'][useritem.jid].resources))+")"

				if self.roster.theme:
					doc.setHtml("<font color=\""+self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name()+"\">"+useritem.escapedName+res+"</font>")
				else:
					doc.setHtml("<font color=\""+self.roster.palet.color(QtGui.QPalette.HighlightedText).name()+"\">"+useritem.escapedName+res+"</font>")

				painter.save()
				painter.translate(x+41,y+(22-fontHeight)/2)
				if avatar:
					doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38-22,y+14))
				else:
					doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38,y+14))
				painter.restore()

			if self.roster.metaItems.has_key(useritem.metajid) and background:
				if not useritem in self.roster.metaItems[useritem.metajid]:
					painter.save()
					painter.translate(x,y)
					painter.setPen(QtCore.Qt.transparent)
					#linearGrad=QtGui.QRadialGradient(QtCore.QPointF(2,16),14)
					#if self.roster.theme:
						#linearGrad.setColorAt(0,self.roster.main.ui.selectedItemStyle.palette().window().color())
					#else:
						#linearGrad.setColorAt(0,self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight))
					#linearGrad.setColorAt(1, background)
					#painter.setBrush(linearGrad)
					#painter.drawRect(0,0,15,32)
					if self.roster.theme:
						painter.setPen(QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().text().color()))
					else:
						painter.setPen(QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.HighlightedText)))
					if useritem.expanded:
						painter.drawPoint(2,10)# 00000
						painter.drawPoint(3,10)#  000
						painter.drawPoint(4,10)#   0
						painter.drawPoint(5,10)
						painter.drawPoint(6,10)
						painter.drawPoint(3,11)
						painter.drawPoint(4,11)
						painter.drawPoint(5,11)
						painter.drawPoint(4,12)
					else:
						painter.drawPoint(5,11)
						painter.drawPoint(4,10)
						painter.drawPoint(4,11)
						painter.drawPoint(4,12)
						painter.drawPoint(3,9)
						painter.drawPoint(3,10)
						painter.drawPoint(3,11)
						painter.drawPoint(3,12)
						painter.drawPoint(3,13)
					painter.restore()

			if avatar:
				painter.drawPixmap(self.roster.width()-4-16+(int((16-avatar.width())/2)),y,avatar)
			if useritem.mood:
				painter.drawPixmap(self.roster.width()-4-35,y+3,useritem.mood)
		else:

			painter.save()
			painter.translate(x,y)
			if self.roster.theme:
				brush=QtGui.QBrush(self.roster.main.ui.userStyleWidget.palette().window())
				if brush.color().alpha()!=0:
					painter.fillRect(0,0,self.roster.width(),22,brush)
				background=brush.color()

			else:
				painter.fillRect(0,0,self.roster.width(),22,QtGui.QBrush(self.roster.palet.color(QtGui.QPalette.Base)))
				background=self.roster.palet.color(QtGui.QPalette.Base)
			painter.restore()



			if useritem in self.roster.events:
				if self.roster.bl:
					painter.drawPixmap(x+7,y,useritem.icon.pixmap(22,22))
				else:
					painter.drawPixmap(x+7,y,useritem.blink.pixmap(22,22))
			else:
				if useritem.privacy['block'] or useritem.privacy['hide']:
					painter.drawPixmap(x+7,y,self.roster.main.getIcon(status="error",size="22x22").pixmap(22,22))
				else:
					painter.drawPixmap(x+7,y,useritem.icon.pixmap(22,22))
			doc=QtGui.QTextDocument()
			font=QtGui.QApplication.fontMetrics()
			fontHeight=int(font.height())
			#font=doc.defaultFont()
			#font.setPixelSize(12)
			#font.setWeight(18)
			#doc.setDefaultFont(font)

			avatar=self.roster.main.client.getAvatarImg(useritem.jid)
			if avatar:
				avatar=avatar[0]
			else:
				avatar=self.roster.main.client.getAvatarImg(None)
				if avatar:
					avatar=avatar[0]
			avatar=avatar.scaled(22,22,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)

			#if useritem.avatar:
				#pixmap=useritem.avatar.pixmap(22,22)
			res=""
			if len(self.roster.main.client.roster['users'][useritem.jid].resources)>1:
				res=" ("+str(len(self.roster.main.client.roster['users'][useritem.jid].resources))+")"

			doc.setHtml("<font color=\""+self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name()+"\">"+useritem.escapedName+res+"</font>")
			painter.save()
			painter.translate(x+41,y+(22-fontHeight)/2)
			if useritem.avatar:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38-22,y+14))
			else:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38,y+14))
			painter.restore()

			if self.roster.metaItems.has_key(useritem.metajid) and background:
				if not useritem in self.roster.metaItems[useritem.metajid]:
					painter.save()
					painter.translate(x,y)
					painter.setPen(QtCore.Qt.transparent)
					#linearGrad=QtGui.QRadialGradient(QtCore.QPointF(2,16),14)
					#if self.roster.theme:
						#linearGrad.setColorAt(0,self.roster.main.ui.selectedItemStyle.palette().window().color())
					#else:
						#linearGrad.setColorAt(0,self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight))
					#linearGrad.setColorAt(1, background)
					#painter.setBrush(linearGrad)
					#painter.drawRect(0,0,15,32)
					if self.roster.theme:
						painter.setPen(QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().text().color()))
					else:
						painter.setPen(QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.HighlightedText)))
					if useritem.expanded:
						painter.drawPoint(2,10)# 00000
						painter.drawPoint(3,10)#  000
						painter.drawPoint(4,10)#   0
						painter.drawPoint(5,10)
						painter.drawPoint(6,10)
						painter.drawPoint(3,11)
						painter.drawPoint(4,11)
						painter.drawPoint(5,11)
						painter.drawPoint(4,12)
					else:
						painter.drawPoint(5,11)
						painter.drawPoint(4,10)
						painter.drawPoint(4,11)
						painter.drawPoint(4,12)
						painter.drawPoint(3,9)
						painter.drawPoint(3,10)
						painter.drawPoint(3,11)
						painter.drawPoint(3,12)
						painter.drawPoint(3,13)
					painter.restore()

			if avatar:
				painter.drawPixmap(self.roster.width()-4-16+(int((16-avatar.width())/2)),y,avatar)
				if useritem.mood:
					painter.drawPixmap(self.roster.width()-4-35,y+3,useritem.mood)
	

