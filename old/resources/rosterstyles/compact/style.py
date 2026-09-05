from PyQt4 import QtCore, QtGui

class rosterStyle:
	def __init__(self,roster,config=None):
		self.roster=roster
		self.spaceBetweenGroups=0
		self.avatarCache={}
		self.firstColor=self.roster.main.ui.userStyleWidget.palette().window()
		self.secondColor=self.roster.palet.color(QtGui.QPalette.Base)

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
		doc.setHtml("<font color=\""+unicode(self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text).name())+"\">"+unicode(item.escapedName)+"</font>")
		painter.save()
		painter.translate(x+30,y+(22-fontHeight)/2)
		doc.drawContents(painter, QtCore.QRectF(0,0,self.roster.width(),y+22))
		painter.restore()
		width=int(font.width("("+str(item.online)+"/"+str(item.all)+")"))
		doc.setHtml("<font color=\""+unicode(self.roster.main.ui.groupStyleWidget.palette().color(QtGui.QPalette.Text).name())+"\">("+str(item.online)+"/"+str(item.all)+")</font>")
		painter.save()
		painter.translate((int(self.roster.width())-width-6),y+(22-fontHeight)/2)
		doc.drawContents(painter, QtCore.QRectF(0,0,width+15,y+20))
		painter.restore()

	def paintUserItem(self,painter,useritem,x,y,last):
		"""
		paints user item in normal roster
		"""
		if useritem==self.roster.item:
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
					doc.setHtml("<font color=\""+unicode(self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name())+"\">"+useritem.escapedName+res+"</font>")
				else:
					doc.setHtml("<font color=\""+unicode(self.roster.palet.color(QtGui.QPalette.HighlightedText).name())+"\">"+useritem.escapedName+res+"</font>")

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
				brush=QtGui.QBrush(self.firstColor)
				if brush.color().alpha()!=0:
					painter.fillRect(0,0,self.roster.width(),22,brush)
				background=brush.color()

			else:
				painter.fillRect(0,0,self.roster.width(),22,QtGui.QBrush(self.secondColor))
				background=self.secondColor
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

			if self.avatarCache.has_key(useritem.jid):
				avatar=self.roster.main.client.getAvatarImg(useritem.jid)
				if avatar:
					if avatar[3]==self.avatarCache[useritem.jid].file:
						avatar=self.avatarCache[useritem.jid]
					else:
						if avatar:
							f=unicode(avatar[3])
							avatar=avatar[0]
						else:
							avatar=self.roster.main.client.getAvatarImg(None)
							f=unicode(avatar[3])
							if avatar:
								avatar=avatar[0]
						avatar=avatar.scaled(22,22,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
						avatar.file=f
						self.avatarCache[useritem.jid]=avatar
				else:
					avatar=self.avatarCache[useritem.jid]
			else:
				avatar=self.roster.main.client.getAvatarImg(useritem.jid)
				if avatar:
					f=unicode(avatar[3])
					avatar=avatar[0]
				else:
					avatar=self.roster.main.client.getAvatarImg(None)
					f=unicode(avatar[3])
					if avatar:
						avatar=avatar[0]
				avatar=avatar.scaled(22,22,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
				avatar.file=f
				self.avatarCache[useritem.jid]=avatar

			#if useritem.avatar:
				#pixmap=useritem.avatar.pixmap(22,22)
			res=""
			if len(self.roster.main.client.roster['users'][useritem.jid].resources)>1:
				res=" ("+str(len(self.roster.main.client.roster['users'][useritem.jid].resources))+")"
			#self.roster.main.ui.userStyleWidget.palette().color(QtGui.QPalette.Text).name()
			doc.setHtml("<font color=\""+"#000000"+"\">"+useritem.escapedName+res+"</font>")
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

