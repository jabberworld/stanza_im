import os
from PyQt4 import QtCore, QtGui

class rosterStyle:
	def __init__(self,roster):
		self.roster=roster
		self.spaceBetweenGroups=0

	def heightForItem(self,item):
		# normal userItem
		if item.typ=="user":
			if item.statusMessage and len(item.statusMessage)>0:
				doc=QtGui.QTextDocument()
				option=doc.defaultTextOption()
				option.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
				doc.setTextWidth(self.roster.width()-41)
				doc.setHtml("<font size=\"-1\">"+unicode(item.statusMessage)+"</font>")
				height=doc.documentLayout().documentSize().height()
				if height>64:
					text=""
					for word in item.statusMessage.split(' '):
						
						doc.setHtml("<font size=\"-1\">"+unicode(text+word+" ...")+"</font>")
						
						if doc.documentLayout().documentSize().height()>64:
							item.statusMessage=text+"..."
							break
						height=doc.documentLayout().documentSize().height()
						text+=word+" "
			else:
				return 32
			if height-16>=0:
				if 16+height<32:
					return 32
				else:
					return 16+height
			else:
				return 32
		# groupItem
		elif item.typ=="group" and item.main!="special":
			return 32
		# specialItem => used for blank space between users in group and users without group
		else:
			return 32

	def paintSelectedUserItem(self,painter,useritem,x,y):
		height=useritem.height
		#self.roster.selectedHeight=28

		# set pen and brush for item background
		b=painter.brush()
		p=painter.pen()
		if self.roster.theme:
			painter.setBrush(self.roster.main.ui.selectedItemStyle.palette().window())
			pen=QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Text))
		else:
			painter.setBrush(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight))
			color=self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight)
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
		painter.drawRect(1,0,self.roster.width()-2,height+2)
		painter.restore()
		painter.setBrush(b)
		painter.setPen(p)

		## events... TODO: this have to be rewrited in some better way
		#if useritem in self.roster.events:
			#if self.roster.bl:
				#painter.drawPixmap(x+7,y,useritem.icon.pixmap(32,32))
			#else:
				#painter.drawPixmap(x+7,y,useritem.blink.pixmap(32,32))
		#else:
			#if useritem.privacy['block'] or useritem.privacy['hide']:
				#painter.drawPixmap(x+7,y,self.roster.main.getIcon(status="error",size="32x32").pixmap(32,32))
			#else:
				#painter.drawPixmap(x+7,y,useritem.icon.pixmap(32,32))
		
		# get font height
		doc=QtGui.QTextDocument()
		font=QtGui.QApplication.fontMetrics()
		fontHeight=int(font.height())
		
		# show resources count
		res=""
		if len(self.roster.main.client.roster['users'][useritem.jid].resources)>1:
			res=" ("+str(len(self.roster.main.client.roster['users'][useritem.jid].resources))+")"

		# get avatar
		avatar=self.roster.main.client.getAvatarImg(useritem.jid)
		if avatar:
			avatar=avatar[0]
		else:
			avatar=self.roster.main.client.getAvatarImg(None)
			if avatar:
				avatar=avatar[0]
		
		# get foreground font color
		if self.roster.theme:
			fontColor=self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name()
		else:
			fontColor=self.roster.palet.color(QtGui.QPalette.HighlightedText).name()

		if useritem.statusMessage:
			# show contact name
			doc.setHtml("<font color=\""+fontColor+"\">"+useritem.escapedName+res+"</font>")
			painter.save()
			painter.translate(x+41,y+2)
			if avatar:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-43-32,y+32))
			else:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-41,y+32))
			painter.restore()
			# show contact status message
			doc.setHtml("<font size=\"-1\" color=\""+fontColor+"\"><i>"+useritem.statusMessage+"</i></font>")
			painter.save()
			painter.translate(x+41,y+16)
			#if avatar:
				#doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-43-32,y+32))
			#else:
				#doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-41,y+32))
			opt=doc.defaultTextOption()
			opt.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
			doc.setDefaultTextOption(opt)
			doc.setPageSize(QtCore.QSizeF(self.roster.width()-41,useritem.height-16))
			doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-41,y+useritem.height))


			painter.restore()
		else:
			doc.setHtml("<font color=\""+fontColor+"\">"+useritem.escapedName+res+"</font>")
			painter.save()
			painter.translate(x+41,y+(32-fontHeight)/2)
			if useritem.avatar:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38-32,y+28))
			else:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38,y+28))
			painter.restore()
		if avatar:
			painter.drawPixmap(x+7,y,avatar)
			if useritem.mood:
				painter.drawPixmap(self.roster.width()-4-16,y,useritem.mood)
			if useritem.tune:
				painter.drawPixmap(self.roster.width()-4-16,y+16,useritem.tune)

		if useritem in self.roster.events:
			if self.roster.bl:
				painter.drawPixmap(x+7+16,y+16,useritem.icon.pixmap(16,16))
			else:
				painter.drawPixmap(x+7+16,y+16,useritem.blink.pixmap(16,16))
		else:
			if useritem.privacy['block'] or useritem.privacy['hide']:
				painter.drawPixmap(x+7+16,y+16,self.roster.main.getIcon(status="error",size="16x16").pixmap(16,16))
			else:
				painter.drawPixmap(x+7+16,y+16,useritem.icon.pixmap(16,16))
	
	def paintUnselectedUserItem(self,painter,useritem,x,y):
		painter.save()
		painter.translate(x,y)
		background=None
		if useritem==self.roster.selected:
			if self.roster.theme:
				painter.fillRect(0,0,self.roster.width(),useritem.height,QtGui.QBrush(self.roster.main.ui.selectedItemStyle.palette().window()))
			else:
				painter.fillRect(0,0,self.roster.width(),useritem.height,QtGui.QBrush(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight)))
		else:
			if self.roster.theme:
				brush=QtGui.QBrush(self.roster.main.ui.userStyleWidget.palette().window())
				if brush.color().alpha()!=0:
					painter.fillRect(0,0,self.roster.width(),32,brush)
				background=brush.color()
				#painter.fillRect(0,0,self.roster.width(),32,QtGui.QBrush(self.roster.main.ui.userStyleWidget.palette().window()))
			else:
				painter.fillRect(0,0,self.roster.width(),32,QtGui.QBrush(self.roster.palet.color(QtGui.QPalette.Base)))
				background=self.roster.palet.color(QtGui.QPalette.Base)
		painter.restore()
		if self.roster.metaItems.has_key(useritem.metajid) and background:
			if not useritem in self.roster.metaItems[useritem.metajid]:
				painter.save()
				painter.translate(x,y)
				painter.setPen(QtCore.Qt.transparent)
				linearGrad=QtGui.QRadialGradient(QtCore.QPointF(2,16),14)
				if self.roster.theme:
					linearGrad.setColorAt(0,self.roster.main.ui.selectedItemStyle.palette().window().color())
				else:
					linearGrad.setColorAt(0,self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight))
				linearGrad.setColorAt(1, background)
				painter.setBrush(linearGrad)
				painter.drawRect(0,0,15,32)
				if self.roster.theme:
					painter.setPen(QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().text().color()))
				else:
					painter.setPen(QtGui.QPen(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.HighlightedText)))
				if useritem.expanded:
					painter.drawPoint(2,15)# 00000
					painter.drawPoint(3,15)#  000
					painter.drawPoint(4,15)#   0
					painter.drawPoint(5,15)
					painter.drawPoint(6,15)
					painter.drawPoint(3,16)
					painter.drawPoint(4,16)
					painter.drawPoint(5,16)
					painter.drawPoint(4,17)
				else:
					painter.drawPoint(5,16)
					painter.drawPoint(4,15)
					painter.drawPoint(4,16)
					painter.drawPoint(4,17)
					painter.drawPoint(3,14)
					painter.drawPoint(3,15)
					painter.drawPoint(3,16)
					painter.drawPoint(3,17)
					painter.drawPoint(3,18)
				painter.restore()
			
		doc=QtGui.QTextDocument()
		font=QtGui.QApplication.fontMetrics()
		fontHeight=int(font.height())

		res=""
		if len(self.roster.main.client.roster['users'][useritem.jid].resources)>1:
			res=" ("+str(len(self.roster.main.client.roster['users'][useritem.jid].resources))+")"
		
		avatar=self.roster.main.client.getAvatarImg(useritem.jid)
		if avatar:
			avatar=avatar[0]
		else:
			avatar=self.roster.main.client.getAvatarImg(None)
			if avatar:
				avatar=avatar[0]

		if useritem==self.roster.selected:
			if self.roster.theme:
				fontcolor=self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name()
			else:
				fontcolor=self.roster.palet.color(QtGui.QPalette.HighlightedText).name()
		else:
			fontcolor=self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name()
		if useritem.statusMessage:
			doc.setHtml("<font color=\""+fontcolor+"\">"+useritem.escapedName+res+"</font>")
			painter.save()
			painter.translate(x+41,y+2)
			if avatar:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-43-32,y+32))
			else:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-41,y+32))
			painter.restore()
			doc.setHtml("<font size=\"-1\" color=\""+fontcolor+"\"><i>"+useritem.statusMessage+"</i></font>")
			painter.save()
			painter.translate(x+41,y+16)
			#if avatar:
				#doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-43-32,y+32))
			#else:
			opt=doc.defaultTextOption()
			opt.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
			doc.setDefaultTextOption(opt)
			doc.setPageSize(QtCore.QSizeF(self.roster.width()-41,useritem.height-16))
			doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-41,y+useritem.height))
			painter.restore()
		else:
			doc.setHtml("<font color=\""+fontcolor+"\">"+useritem.escapedName+res+"</font>")
			painter.save()
			painter.translate(x+41,y+(32-fontHeight)/2)
			if avatar:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38,y+28))
			else:
				doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width()-38,y+28))
			painter.restore()
		if avatar:
			painter.drawPixmap(x+7,y,avatar)
			if useritem.mood:
				painter.drawPixmap(self.roster.width()-4-16,y,useritem.mood)
			if useritem.tune:
				painter.drawPixmap(self.roster.width()-4-16,y+16,useritem.tune)

		if useritem in self.roster.events:
			if self.roster.bl:
				painter.drawPixmap(x+7+16,y+16,useritem.icon.pixmap(16,16))
			else:
				painter.drawPixmap(x+7+16,y+16,useritem.blink.pixmap(16,16))
		else:
			if useritem.privacy['block'] or useritem.privacy['hide']:
				painter.drawPixmap(x+7+16,y+16,self.roster.main.getIcon(status="error",size="16x16").pixmap(16,16))
			else:
				painter.drawPixmap(x+7+16,y+16,useritem.icon.pixmap(16,16))

	def paintGroupItem(self,painter,item,x,y):
		"""
		paints group item in normal roster
		"""
		if item.main=="special":
			return
		
		# set font
		doc=QtGui.QTextDocument()
		font=QtGui.QApplication.fontMetrics()
		fontHeight=int(font.height())
		#font.setPixelSize(12)
		#doc.setDefaultFont(font)

		# paint background
		painter.save()
		painter.translate(x,y)

		if item==self.roster.selected:
			if self.roster.theme:
				painter.fillRect(0,0,self.roster.width(),30,QtGui.QBrush(self.roster.main.ui.selectedItemStyle.palette().window()))
			else:
				painter.fillRect(0,0,self.roster.width(),30,QtGui.QBrush(self.roster.main.ui.selectedItemStyle.palette().color(QtGui.QPalette.Highlight)))
		else:
			if self.roster.theme:
				painter.fillRect(0,0,self.roster.width(),30,QtGui.QBrush(self.roster.main.ui.groupStyleWidget.palette().window()))
			else:
				painter.fillRect(0,0,self.roster.width(),30,QtGui.QBrush(self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.AlternateBase)))
		
		painter.restore()
		
		# draw status icon of item
		if item.icon:
			painter.drawPixmap(x,y,item.icon.pixmap(32,32))

		if item==self.roster.selected:
			if self.roster.theme:
				fontcolor=self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text).name()
			else:
				fontcolor=self.roster.palet.color(QtGui.QPalette.HighlightedText).name()
		else:
			fontcolor=self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text).name()


		# write the name of the group
		doc.setHtml("<font color=\""+fontcolor+"\">"+item.escapedName+"</font>")
		painter.save()
		painter.translate(x+30,y+(32-fontHeight)/2)
		doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width(),y+32))
		painter.restore()
		width=int(font.width("("+str(item.online)+"/"+str(item.all)+")"))
		doc.setHtml("<font color=\""+fontcolor+"\">("+str(item.online)+"/"+str(item.all)+")</font>")
		painter.save()
		painter.translate((int(self.roster.width())-width-6),y+(32-fontHeight)/2)
		doc.drawContents(painter, QtCore.QRectF(0,0,width+15,y+32))
		painter.restore()

	def paintUserItem(self,painter,useritem,x,y):
		"""
		paints user item in normal roster
		"""
		if useritem==self.roster.item:
			self.paintSelectedUserItem(painter,useritem,x,y)
		else:
			self.paintUnselectedUserItem(painter,useritem,x,y)
	

