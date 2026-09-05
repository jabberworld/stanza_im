#!/usr/bin/env python
import os
import sys, xmlrpclib, traceback
from optparse import OptionParser

from time import time

parser = OptionParser()
parser.add_option("-u","--uri", dest="uri", metavar="XMPP-URI", help="Execute xmpp uri (see RFC 4622)", type="str")
options, args = parser.parse_args()

def getHomeDir():
	# gets homedir on win32 or linux
 	if sys.platform != 'win32' :
 		return unicode(os.path.expanduser( '~' )+'/.jabbim')
 	def valid(path):
 		if path and os.path.isdir(path):
 			return True
 		return False
 	def env(name):
 		return os.environ.get( name, '' )
 	homeDir = env( 'APPDATA' )
 	if not valid(homeDir):
 		homeDir = env( 'HOME' )
 		if not valid(homeDir):
 			homeDir = '%s%s' % (env('HOMEDRIVE'),env('HOMEPATH'))
 			if not valid(homeDir):
 				homeDir = env( 'SYSTEMDRIVE' )
 				if homeDir and (not homeDir.endswith('\\')):
 					homeDir += '\\'
 				if not valid(homeDir):
 					homeDir = 'C:\\'
#	homeDir = os.path.expanduser( '~' )+'/.jabbim'
 	homeDir = homeDir + '\jabbim'
	return unicode(homeDir, sys.getfilesystemencoding())
def readpfile(pfile):
	ports = {}
	for line in open(pfile).read().splitlines():
		timestamp, port, cookie = line.split(":",2)
		ports[timestamp] = (port, cookie)
	return ports

def scanports(): #
	hd = getHomeDir()
	profiledirs = filter(lambda s: "@" in s, os.listdir(hd))
	profs = []
	for dir in profiledirs:
		try:
			profs.append(readpfile(os.path.join(hd,dir,"xmlrpcports")))
		except IOError:
			pass
	p = {}
	for d in profs:
		p.update(d)

	return p[p.keys()[0]]



def handleuri(argv, porty, server):
	print 'handle uri!'
	print argv
	argv = argv[1]
	print argv
	if not argv.startswith('xmpp:'):
		return 'wrong uri'
	uri = argv[5:]
	parts = uri.split('?', 1)
	if len (parts) == 1:
		print 'message'
		print porty
		return server.startChat(parts[0].replace('%40', '@'), porty[1])
	elif parts[1] == 'join':
		print 'muc'
		return server.joinMUC(parts[0].replace('%40', '@'), porty[1])

porty = scanports()	
functions = {'uri': handleuri}#, 'setStatus':setStatus}
server = xmlrpclib.Server('http://localhost:%s/'%porty[0])

if functions.has_key(sys.argv[1]):
	try:	
		print functions[sys.argv[1]](sys.argv[2:])
	except:
		print 'error in command: ', sys.argv[1]
		print traceback.format_exc()
else:
	print	handleuri(sys.argv[1:])
