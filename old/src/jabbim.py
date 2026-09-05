# -*- coding: utf-8 -*-
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

import  getopt, xmlrpclib
from include.constants import RESOURCEPATH
import sys


sys.path.append('.')
from include import utils
try:
	OPTIONS,params = getopt.getopt(sys.argv[1:],'h:u:p:', ['home=', 'uri=', 'plugin=','usage','help'])
except getopt.GetoptError, err:
	print str(err)
	sys.exit(2)

for opt, arg in OPTIONS:
	if opt == '-u' or opt == '--uri':
		try:
			porty = utils.scanports()
		except:
			print 'no ports'
			sys.exit(2)
		server = xmlrpclib.Server('http://localhost:%s/'%porty[0])
		utils.handleuri(arg, porty, server)
		sys.exit()
	elif opt == '-p' or opt == '--plugin':
		#format: --plugin="pluginName_func args"
		try:
			porty = utils.scanports()
		except:
			print 'no ports'
			sys.exit(2)
		args=''
		try:
			name, args = arg.split(' ',1)
		except ValueError:
			name=arg;
		server = xmlrpclib.Server('http://localhost:%s/'%porty[0])
		server.runPluginFunc(name, params, porty[1])

		sys.exit()
	elif opt == '--usage' or opt == '--help':
		print "Jabbim XMPP client commandline options\n\n\
	-h --home\n		- set directory to save profiles and settings(default ~/.jabbim)\n\n\
	-p --plugin=<remotefunction> <arguments>\n		-invoke xmlrpc remote function\n\n\
	-u --uri\n		- handle xmpp uri\n\
	--help --usage\n		- show this help message and exit\n\n\
more info on http://dev.jabbim.cz/jabbim"
		sys.exit(0);
#this function prevents(not 100%) jabbim not to run twice in same profile :-)
def singleRun():
	try:
		porty = utils.scanports()
	except:
		return False
	try:
		server = xmlrpclib.Server('http://localhost:%s/'%porty[0])
		rv=server.runPluginFunc('showRoster', '', porty[1])
	except:
		rv=False;
	return rv
if singleRun():
	#roster shown, so I can exit now !
	sys.exit(0);
	

from PyQt4 import QtCore, QtGui

#if sys.argv[1]=="remote":
#	app=QtCore.QCoreApplication([])

import qt4reactor
#if sys.platform=="win32":
	#import win32gui



class jabbimApplication(QtGui.QApplication):
	"""
	Main Jabbim application class.
	"""
	def __init__(self,args=[]):
		QtGui.QApplication.__init__(self,args)
		self.shutdown=False
		self.sleep=False
		self.setApplicationName("Jabbim")

	def winEventFilter(self,msg):
		message = msg.message
		# WM_POWERBROADCAST
		if message==536:
			# PBT_APMSUSPEND
			if msg.wParam==4 and not self.sleep:
				log.msg( "emit sleep()")
				self.emit(QtCore.SIGNAL("sleep()"))
				self.sleep=True
			elif msg.wParam==7 and self.sleep:
				log.msg( "emit wakeup()")
				self.emit(QtCore.SIGNAL("wakeUp()"))
				self.sleep=False
			return (True,1)
		# Snarl clicked (notification.py hook)
		elif message==1025:
			if msg.wParam==34:
				if self.main.snarlMessages.has_key(int(msg.lParam)):
					self.main.snarlMessages[int(msg.lParam)][0](*self.main.snarlMessages[int(msg.lParam)][1])
					del self.main.snarlMessages[int(msg.lParam)]
				return (True,1)
		return (False,1)

#	def x11EventFilter(self,e):
#		#print e,type(e),dir(e)
#		return False

	def commitData(self,manager):
		"""
		Called when application is closed by Window manager
		"""
		log.msg( "data commited")
		self.shutdown=True
		manager.release()

app = jabbimApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
qt4reactor.install()
from twisted.internet import reactor

from twisted.python import log

from core.MainWindow import mainWindow

MainWindow=None

def main():
	translator = utils.loadTranslator(RESOURCEPATH+'locales/jabbim_')
	app.installTranslator(translator)

	global MainWindow
	MainWindow = mainWindow(app=app)

	if MainWindow.config['startInTray']=="True":
		MainWindow.close()
	else:
		MainWindow.show()
	reactor.run()

if __name__ == "__main__":
	#import hotshot
	#prof = hotshot.Profile("hotshot_edi_stats")
	#prof.runcall(main)
	#prof.close()
	main()