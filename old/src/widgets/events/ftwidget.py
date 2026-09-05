import os,sys
from PyQt4 import QtCore, QtGui
from ftwidget_ui import *
from ftuploadwidget_ui import *
import time
import weakref
from os.path import basename
from include.constants import RESOURCEPATH

#class ElidedLabel : public QLabel {
#public:
    #ElidedLabel(QWidget *parent, Qt::TextElideMode elide) : QLabel(parent) {this->elide = elide;}
    #QSize sizeHint() const {return QSize(1, QLabel::sizeHint().height());}
    #QSize minimumSizeHint() const {return sizeHint();}
#protected:
    #Qt::TextElideMode elide;
    #void paintEvent(QPaintEvent *e) {
        #if (contentsRect().width() < fontMetrics().width(text())) {
            #QString newText = fontMetrics().elidedText(text(), elide, contentsRect().width());
            #QString fullText = text();
            #setText(newText);
            #QLabel::paintEvent(e);
            #setText(fullText);
            #setToolTip(fullText);
        #} else {
            #QLabel::paintEvent(e);
            #setToolTip(QString());
        #}
    #}
#};




class FTDownloadWidget(QtGui.QWidget):
	def __init__(self,event):
		QtGui.QWidget.__init__(self,None)
		self.ui=Ui_FTWidget()
		self.ui.setupUi(self)
		self.metrics=QtGui.QFontMetrics(self.ui.filename.font())
		self.size=0
		self.timestamp=time.time()
		self.transfered=0
		self.event=weakref.proxy(event)
		self.ui.reject.hide()
		self.ui.accept.hide()
		QtCore.QObject.connect(self.ui.accept,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.ui.reject,QtCore.SIGNAL("clicked()"),self.reject)
		self.file=""
		#self.transfered=0
		self.setCurrentFile(self.event.currentFile)
		self.setFileSize(self.event.fileSize)
		self.setFileTransfered(self.event.fileTransfered)
		self.ui.closeButton.setIcon(QtGui.QIcon(RESOURCEPATH+"images/icons/close.png"))
		QtCore.QObject.connect(self.ui.closeButton,QtCore.SIGNAL("clicked()"),self.closeFT)

	def closeFT(self):
		self.event.reject()

	def resizeEvent(self,event):
		print "WIDTH",self.width()
		self.ui.filename.setText(unicode(self.metrics.elidedText(basename(self.file),QtCore.Qt.ElideMiddle, self.width()-10-self.ui.closeButton.width())))
		return QtGui.QWidget.resizeEvent(self,event)

	def eventAccepted(self):
		pass

	def eventRejected(self):
		pass

	def accept(self):
		filename=unicode(self.file)
		if sys.platform == 'win32':
			filename=filename.replace("/","\\")
			print "open win32",[filename]
			os.startfile(filename)
		else:
			print "open linux",[filename]
			os.system(u"xdg-open \"%s\"" % filename.encode('utf8'))
		#self.event.accept()

	def reject(self):
		self.event.reject()

	def setText(self,text):
		return
		self.ui.filename.setText(text)

	def setFileSize(self,size):
		self.size=int(size)

	def setJid(self,jid):
		self.ui.jid.setText(unicode(self.metrics.elidedText(jid,QtCore.Qt.ElideRight, self.width()-10)))

	def setCurrentFile(self,file):
		self.file=file
		self.ui.filename.setText(unicode(self.metrics.elidedText(basename(self.file),QtCore.Qt.ElideMiddle, self.width()-10-self.ui.closeButton.width())))

	
	def transferFinished(self):
		self.ui.progressBar.hide()
		self.ui.accept.show()
		#self.ui.reject.show()
		self.ui.transferInfo.setText(self.tr("Finished"))

	def setFileTransfered(self,transfered):
		if transfered==0:
			return
		self.ui.progressBar.setValue(int((float(transfered)/float(self.size))*100))
		newTimestamp=time.time()
		d=newTimestamp-self.timestamp
		if d>1:
			diff=transfered-self.transfered
			self.transfered=transfered
			self.timestamp=newTimestamp
			ratio=1.0/d
			speed=int(diff*ratio)
			remaining=int((self.size-transfered)/speed)
			self.ui.transferInfo.setText(unicode(self.tr("Remaining:"))+" "+unicode(remaining)+" s "+"("+str(speed/1000)+" kB/s)")

class FTUploadWidget(QtGui.QWidget):
	def __init__(self,event):
		QtGui.QWidget.__init__(self,None)
		self.ui=Ui_FTUploadWidget()
		self.ui.setupUi(self)
		self.metrics=QtGui.QFontMetrics(self.ui.filename.font())
		self.text=""
		self.queue={}
		self.size=0
		self.timestamp=time.time()
		self.transfered=0
		self.event=weakref.proxy(event)
		self.ui.reject.hide()
		self.ui.more.hide()
		QtCore.QObject.connect(self.ui.reject,QtCore.SIGNAL("clicked()"),self.reject)
		#self.ui.accept.hide()
		self.setQueue(self.event.queue)
		self.uploaded=0
		self.ui.closeButton.setIcon(QtGui.QIcon(RESOURCEPATH+"images/icons/close.png"))
		QtCore.QObject.connect(self.ui.closeButton,QtCore.SIGNAL("clicked()"),self.closeFT)

		#self.transfered=0

	def closeFT(self):
		self.event.reject()

	def resizeEvent(self,event):
		self.ui.filename.setText(self.metrics.elidedText(self.text,QtCore.Qt.ElideMiddle, self.width()-20-self.ui.toolButton.width()-self.ui.closeButton.width()))
		text=""
		for file in self.queue.keys():
			text+=unicode(self.metrics.elidedText(basename(file),QtCore.Qt.ElideMiddle, self.width()-10))+'<br/>'
		self.ui.more.setText(text)
		return QtGui.QWidget.resizeEvent(self,event)

	def eventAccepted(self):
		pass

	def eventRejected(self):
		pass

	def reject(self):
		self.event.reject()

	def setText(self,text):
		self.text=unicode(text)
		self.ui.filename.setText(self.metrics.elidedText(text,QtCore.Qt.ElideMiddle, self.width()-20-self.ui.toolButton.width()-self.ui.closeButton.width()))

	def setQueue(self,queue):
		if len(self.queue)==0:
			self.queue=queue
			text=""
			for file in self.queue.keys():
				text+=unicode(self.metrics.elidedText(basename(file),QtCore.Qt.ElideMiddle, self.width()-10))+'<br/>'
			self.ui.more.setText(text)
		self.queue=queue

	def setJid(self,jid):
		self.ui.jid.setText(unicode(self.metrics.elidedText(jid,QtCore.Qt.ElideRight, self.width()-10)))

	def setCurrentFile(self,file):
		self.uploaded+=1
		self.setText(basename(file))

	def setFileSize(self,size):
		self.size=int(size)

	def transferFinished(self):
		self.ui.progressBar.hide()
		self.ui.more.hide()
		self.ui.toolButton.hide()
		#self.ui.accept.show()
		#self.ui.reject.show()
		self.ui.transferInfo.setText(self.tr("Finished"))

	def setFileTransfered(self,transfered):
		if transfered==0:
			return
		self.ui.progressBar.setValue(int((float(transfered)/float(self.size))*100))
		newTimestamp=time.time()
		d=newTimestamp-self.timestamp
		if d>1:
			diff=transfered-self.transfered
			self.transfered=transfered
			self.timestamp=newTimestamp
			ratio=1.0/d
			speed=int(diff*ratio)
			if speed!=0:
				remaining=int((self.size-transfered)/speed)
			else:
				remaining="N/A"
			self.ui.transferInfo.setText(unicode(self.tr("Remaining:"))+" "+unicode(remaining)+" s "+"("+str(speed/1000)+" kB/s)")
