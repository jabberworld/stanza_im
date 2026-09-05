from PyQt4 import QtCore, QtGui
from paint_ui import *

class paintArea(QtGui.QWidget):
	def __init__(self,parent=None):
		QtGui.QWidget.__init__(self,parent)
		self.pen=QtGui.QPen(QtGui.QColor(0,0,0),5,QtCore.Qt.SolidLine, QtCore.Qt.RoundCap,QtCore.Qt.RoundJoin)
		self.pen.setWidth(5)
##		gradient=QtGui.QLinearGradient(10,10,20,20)
##		gradient.setColorAt(0.0, QtGui.QColor(128,128,128,63))
##		gradient.setColorAt(1.0, QtGui.QColor(255,255,0, 191))
##		self.pen.setBrush(gradient)
		self.color=QtGui.QColor(0,0,0)
		self.brush=QtGui.QBrush(QtGui.QColor(0,0,0))
		self.newImage(400,400)
		self.penSize=5
		self.tool="pen"
		self.mousePress=[-1,-1]
		self.mouseActual=[-1,-1]
		self.insert=None
		self.keepAspectRatio=False
		self.changeSize=False
		self.lastPoint=[0,0]
		self.setMouseTracking(True)
		self.cursor=None
		self.history=[]
		self.historyIndex=0

	def insertImage(self,image):
		self.insert=image

	def getPenPreviewImage(self):
		i=QtGui.QPixmap(38,38)
		i.fill(QtGui.QColor(255,255,255))
		p=QtGui.QPainter(i)
		self.setupPainter(p)
		p.drawPoint(19,19)
		return i

	def getSquarePreviewImage(self):
		i=QtGui.QPixmap(38,38)
		i.fill(QtGui.QColor(255,255,255))
		p=QtGui.QPainter(i)
		self.setupPainter(p)
		r=QtCore.QRect(8,8,19,19)
		p.drawRect(r)
		return i

	def getPreviewImage(self):
		if self.tool=="pen" or self.tool=="line":
			return self.getPenPreviewImage()
		elif self.tool=='square':
			return self.getSquarePreviewImage()
		return QtGui.QPixmap()

	def colorChanged(self,color):
		self.pen.setColor(color)

	def brushColorChanged(self,color):
		self.brush.setColor(color)

	def penSizeChanged(self,value):
		self.penSize=int(value)
		self.pen.setWidth(self.penSize)

	def toolChanged(self,tool):
		self.tool=unicode(tool)
		if self.tool=="insertImage":
			self.keepAspectRatio=float(self.insert.width())/float(self.insert.height())
		else:
			self.keepAspectRatio=False


	def floodFill(self, x, y):
		get_pixel = self.image.pixel # local variable access is faster in Python
		target_color = get_pixel(x, y)
		if QtGui.QColor(target_color)==self.pen.color():
			return
		painter = QtGui.QPainter(self.image)
		p=QtGui.QPen()
		p.setColor(self.pen.color())
		painter.setPen(p)
		queue = []
		# tuples in the queue will describe horizontal lines: (west_x, east_x, y)
		# we must be careful to only ever enqueue lines that will cover pixels of target_color
		# the initial line is just 1 pixel wide:
		queue.append((x, x, y))
		pixels_filled = 0
		img_width = self.image.width()
		img_height = self.image.height()
		while len(queue) != 0:
			(w, e, y) = queue.pop(0)
			while w > 0 and get_pixel(w-1, y) == target_color:
				w -= 1
			while e+1 < img_width and get_pixel(e+1, y) == target_color:
				e += 1
			if e != w:
				painter.drawLine(w, y, e, y)
			else:
				painter.drawPoint(w, y)
			# complete floodfill can take a while, so repaint once in a while
			# to have visible progress
			pixels_filled += e - w + 1
			if pixels_filled >= 40000:
				self.repaint()
				pixels_filled = 0

			if y > 0:
				was_target = False
				for x in xrange(w, e+1):
					is_target = (get_pixel(x, y-1) == target_color)
					if is_target and not was_target:
						line_west = x
					elif not is_target and was_target:
						queue.append((line_west, x-1, y-1))
					was_target = is_target
				if was_target:
					queue.append((line_west, e, y-1))
			if y + 1 < img_height:
				was_target = False
				for x in xrange(w, e+1):
					is_target = (get_pixel(x, y+1) == target_color)
					if is_target and not was_target:
						line_west = x
					elif not is_target and was_target:
						queue.append((line_west, x-1, y+1))
					was_target = is_target
				if was_target:
					queue.append((line_west, e, y+1))
		self.repaint()

	def newImage(self,w,h):
		self.history=[]
		self.image=QtGui.QImage(w,h,QtGui.QImage.Format_RGB32)
		self.image.fill(QtGui.QColor(255,255,255).rgb())
		self.setMaximumSize(QtCore.QSize(w,h))
		self.setMinimumSize(QtCore.QSize(w,h))

	def loadImage(self,image):
		#self.history=[None,None,None,None,None]
		self.image=image
		self.setMaximumSize(QtCore.QSize(image.width(),image.height()))
		self.setMinimumSize(QtCore.QSize(image.width(),image.height()))

	def getImage(self):
		return self.image
	
	def paintEvent(self,event):
		QtGui.QWidget.paintEvent(self,event)
		p=QtGui.QPainter(self)
		p.drawImage(0,0,self.image)
		x=self.mapFromGlobal(QtGui.QCursor.pos()).x()
		y=self.mapFromGlobal(QtGui.QCursor.pos()).y()
		if self.mousePress[0]!=-1 and self.mouseActual[0]!=-1:
			if self.tool=="square":
				self.paintSquare(p)
			elif self.tool=='line':
				self.paintLine(p)
			elif self.tool=='insertImage':
				self.paintInsertImage(p)
				p.drawRect(self.mousePress[0],self.mousePress[1],int(self.mouseActual[0]-self.mousePress[0]),int(self.mouseActual[1]-self.mousePress[1]))
			else:
				p.drawRect(self.mousePress[0],self.mousePress[1],int(self.mouseActual[0]-self.mousePress[0]),int(self.mouseActual[1]-self.mousePress[1]))
		else:
			if self.tool=="pen":
				self.setupPainter(p)
				p.drawPoint(x,y)

	def mousePressEvent(self,event):
		if self.tool == 'fill':
			self.floodFill(event.x(),event.y())
		elif self.tool!="pen":
			self.mousePress=[int(event.x()),int(event.y())]
		elif self.tool == 'pen':
			pass

	def paintSquare(self, painter):
		self.setupPainter(painter)
		r = QtCore.QRect(self.mousePress[0], self.mousePress[1],
			self.mouseActual[0] - self.mousePress[0], self.mouseActual[1] - self.mousePress[1])
		painter.drawRect(r)

	def paintLine(self, painter):
		self.setupPainter(painter)
		painter.drawLine(self.mousePress[0], self.mousePress[1], self.mouseActual[0], self.mouseActual[1])

	def paintPen(self, painter):
		self.setupPainter(painter)
		painter.drawPoint(self.mouseActual[0], self.mouseActual[1])

	def paintInsertImage(self, painter):
		img = self.insert.scaled(abs(self.mouseActual[0] - self.mousePress[0]),
			abs(self.mouseActual[1] - self.mousePress[1]),
			QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
		left = min(self.mousePress[0], self.mouseActual[0])
		top  = min(self.mousePress[1], self.mouseActual[1])
		painter.drawImage(left, top, img)

	def mouseReleaseEvent(self,event):
		self.mouseActual = [event.x(), event.y()]
		p = QtGui.QPainter(self.image)
		if self.tool=="square":
			self.paintSquare(p)
		elif self.tool=='line':
			self.paintLine(p)
		elif self.tool=="pen":
			self.paintPen(p)
		elif self.tool=="insertImage":
			self.paintInsertImage(p)
		if len(self.history)-1!=self.historyIndex:
			del self.history[:self.historyIndex]
		self.history.append(QtGui.QImage(self.image))
		if len(self.history)>5:
			del self.history[0]
		self.historyIndex=len(self.history)-1
		self.mousePress=[-1,-1]
		self.mouseActual=[-1,-1]
		self.repaint()

	def back(self):
		self.loadImage(self.history[self.historyIndex])
		self.repaint()
		if self.historyIndex-1>=0:
			self.historyIndex-=1

	def mouseMoveEvent(self,event):
		if event.buttons()|QtCore.Qt.NoButton:
			if self.mouseActual[0]!=-1:
				if self.changeSize and event.x()>10 and event.y()>10:
					if self.mouseActual[0]<event.x() or self.mouseActual[1]<event.y():
						w=event.x()
						h=event.y()
						image=QtGui.QImage(w,h,QtGui.QImage.Format_RGB32)
						image.fill(QtGui.QColor(255,255,255).rgb())
						self.setMaximumSize(QtCore.QSize(w,h))
						self.setMinimumSize(QtCore.QSize(w,h))
						p=QtGui.QPainter(image)
						p.drawImage(0,0,self.image)
						#image=newImage(event.x(),event.y())
						self.loadImage(image)
					else:
						self.loadImage(self.image.copy(0,0,event.x(),event.y()))
				else:
					if self.tool=="pen":
						p=QtGui.QPainter(self.image)
						self.setupPainter(p)
						p.drawLine(self.mouseActual[0],self.mouseActual[1],event.x(),event.y())
						self.update(QtCore.QRect(QtCore.QPoint(self.mouseActual[0],self.mouseActual[1]),QtCore.QPoint(event.x(),event.y())).normalized().adjusted(-self.penSize,-self.penSize,self.penSize,self.penSize))
					else:
						self.update(QtCore.QRect(QtCore.QPoint(self.mousePress[0],self.mousePress[1]),QtCore.QPoint(event.x(),event.y())).normalized().adjusted(-self.penSize,-self.penSize,self.penSize,self.penSize).united(QtCore.QRect(QtCore.QPoint(self.mousePress[0],self.mousePress[1]),QtCore.QPoint(self.mouseActual[0],self.mouseActual[1])).normalized().adjusted(-self.penSize,-self.penSize,self.penSize,self.penSize)))
			if self.keepAspectRatio:
	##			if event.x()>self.mousePress[0]:
				left=self.mousePress[0]
	##			right=event.x()
	##			else:
	##				left=event.x()
	##				right=self.mousePress[0]
	##			if event.y()>self.mousePress[1]:
				top=self.mousePress[1]
	##				bottom=event.y()
	##			else:
	##				top=event.y()
	##				bottom=self.mousePress[1]
				
				if abs(event.x()-self.mousePress[0])<abs(event.y()-self.mousePress[1]):
					self.mouseActual=[int(event.x()),top+int(float((event.x()-self.mousePress[0]))/self.keepAspectRatio)]
				else:
					self.mouseActual=[left+int(float((event.y()-self.mousePress[1]))*self.keepAspectRatio),int(event.y())]
			else:
				self.mouseActual=[int(event.x()),int(event.y())]
		else:
			# bottom right corner
			if event.x()>self.width()-10 and event.y()>self.height()-10:
				self.changeSize=True
				self.setCursor(QtCore.Qt.SizeFDiagCursor)
			else:
				self.changeSize=False
				if self.tool=='pen':
					self.setCursor(QtCore.Qt.BlankCursor)
					self.update(QtCore.QRect(QtCore.QPoint(self.lastPoint[0],self.lastPoint[1]),QtCore.QPoint(event.x(),event.y())).normalized().adjusted(-self.penSize,-self.penSize,self.penSize,self.penSize))
					self.lastPoint=[event.x(),event.y()]
				else:
					self.setCursor(QtCore.Qt.ArrowCursor)
		

	def setupPainter(self,p):
		#p.setRenderHint(QtGui.QPainter.Antialiasing, True)
		p.setPen(self.pen)
		p.setBrush(self.brush)

class paintWindow(QtGui.QMainWindow):
	def __init__(self,parent=None,  chatwidget = None):
		QtGui.QMainWindow.__init__(self,parent)
		self.ui=Ui_MainWindow()
		self.ui.setupUi(self)
		l=QtGui.QHBoxLayout(self.ui.container)
		self.paintArea=paintArea(self.ui.container)
		l.addWidget(self.paintArea)
		self.chat = chatwidget

		self.ui.mainColor.setAutoFillBackground(True)
		self.ui.mainColor.mousePressEvent=self.chooseColor
		self.ui.backgroundColor.mousePressEvent=self.backgroundChooseColor
		self.colorWidgets=[self.ui.color1,self.ui.color2,self.ui.color3,self.ui.color4,self.ui.color5,self.ui.color6,self.ui.color7,self.ui.color8,self.ui.color9,self.ui.color10,self.ui.color11,self.ui.color12,self.ui.color13,self.ui.color14,self.ui.color15,self.ui.color16]
		self.ui.mainColor.palette().setColor(QtGui.QPalette.Window,QtGui.QColor("#000000"))
		self.ui.backgroundColor.palette().setColor(QtGui.QPalette.Window,QtGui.QColor("#FFFFFF"))
		defaultColors=["#000000","#000080","#0000FF","#008000","#008080","#00FF00","#800000","#800080","#808000","#808080","#C0C0C0","#FF0000","#FF0000","#FF00FF","#FFFF00","#FFFFFF"]
		for i in range(len(self.colorWidgets)):
			palette = QtGui.QPalette(self.colorWidgets[i].palette())
			palette.setColor(QtGui.QPalette.Window,QtGui.QColor(defaultColors[i]))
			self.colorWidgets[i].setPalette(palette)
			self.colorWidgets[i].setAutoFillBackground(True)
			self.colorWidgets[i].setToolTip(defaultColors[i])
			self.colorWidgets[i].mousePressEvent=self._mousePressEvent
		self.updatePreview()
		QtCore.QObject.connect(self.ui.penSize,QtCore.SIGNAL("valueChanged ( int  )"),self.penSizeChanged)
		QtCore.QObject.connect(self.ui.pen,QtCore.SIGNAL("clicked()"),self.pen)
		QtCore.QObject.connect(self.ui.back,QtCore.SIGNAL("clicked()"),self.back)
		QtCore.QObject.connect(self.ui.square,QtCore.SIGNAL("clicked()"),self.square)
		QtCore.QObject.connect(self.ui.line,QtCore.SIGNAL("clicked()"),self.line)
		QtCore.QObject.connect(self.ui.fill,QtCore.SIGNAL("clicked()"),self.floodFill)
		QtCore.QObject.connect(self.ui.sendButton,QtCore.SIGNAL("clicked()"),self.send)
		QtCore.QObject.connect(self.ui.clearButton,QtCore.SIGNAL("clicked()"),self.clear)
		QtCore.QObject.connect(self.ui.insertImage,QtCore.SIGNAL("clicked()"),self.insertImage)
		QtCore.QObject.connect(self.ui.openImage,QtCore.SIGNAL("clicked()"),self.openImage)

	def back(self):
		self.paintArea.back()

	def openImage(self):
		file=QtGui.QFileDialog.getOpenFileName(self,"Choose image") # get filenames
		if file and len(file)!=0:
			img=QtGui.QImage(file)
			if not img.isNull():
				maxx = self.chat.ui.webkit.width()
				maxy = self.chat.ui.webkit.height()
				print maxx, maxy
				if img.width()>maxx or img.height()>maxy:
					img=img.scaled(maxx*0.9,maxy*0.9,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
			self.open(image=img)
			
	def insertImage(self):
		file=QtGui.QFileDialog.getOpenFileName(self,"Choose image") # get filenames
		if file and len(file)!=0:
			img=QtGui.QImage(file)
			if not img.isNull():
				self.paintArea.insertImage(img)
				self.paintArea.toolChanged("insertImage")
				#self.updatePreview()

	def penSizeChanged(self,value):
		size=int(value)
		self.paintArea.penSizeChanged(size)
		self.updatePreview()

	def _mousePressEvent(self,event):
		colorWidget=self.childAt(self.mapFromGlobal(event.globalPos()))
		if event.button()==QtCore.Qt.RightButton:
			self.ui.backgroundColor.setPalette(colorWidget.palette())
			self.paintArea.brushColorChanged(colorWidget.palette().window().color())
		else:
			self.ui.mainColor.setPalette(colorWidget.palette())
			self.paintArea.colorChanged(colorWidget.palette().window().color())
		self.updatePreview()

	def chooseColor(self,event=None):
		c=QtGui.QColorDialog.getColor(self.ui.mainColor.palette().window().color())
		if c.isValid():
			self.ui.mainColor.palette().setColor(QtGui.QPalette.Window,c)
			self.paintArea.colorChanged(c)
			self.updatePreview()

	def backgroundChooseColor(self,event=None):
		c=QtGui.QColorDialog.getColor(self.ui.backgroundColor.palette().window().color())
		if c.isValid():
			self.ui.backgroundColor.palette().setColor(QtGui.QPalette.Window,c)
			self.paintArea.brushColorChanged(c)
			self.updatePreview()

	def floodFill(self):
		self.paintArea.toolChanged("fill")

	def updatePreview(self):
		self.ui.preview.setPixmap(self.paintArea.getPreviewImage())

	def pen(self):
		self.paintArea.toolChanged("pen")
		self.updatePreview()

	def square(self):
		self.paintArea.toolChanged("square")
		self.updatePreview()
		
	def line(self):
		self.paintArea.toolChanged("line")
		self.updatePreview()	
		
	def send(self):
		self.chat.sendPaint(self.paintArea.image)
	
	def clear(self):
		self.paintArea.newImage(400,400)
		self.paintArea.repaint()

	def open(self,  path = None,  image = None):
		if image == None:
			img = QtGui.QImage(path)
			if not img.isNull():
				self.paintArea.loadImage(img)
			else:
				self.paintArea.newImage(400,400)
		else:
			self.paintArea.loadImage(image)
		self.paintArea.repaint()

if __name__ == "__main__":
	app=QtGui.QApplication([])

	w=paintWindow()
	w.show()

	app.exec_()
