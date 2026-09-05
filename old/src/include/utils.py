"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

Copyright (C) 2003-2006 Yann Le Boulanger <asterix@lagaule.org>
Copyright (C) 2005-2006 Nikos Kouremenos <kourem@gmail.com>
Copyright (C) 2005
                   Dimitur Kirov <dkirov@gmail.com>
                   Travis Shirk <travis@pobox.com>
Copyright (C) 2007 Lukas Petrovicky <lukas@petrovicky.net>

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
import os,sys, re,platform,time
from configobj import ConfigObj, ConfigObjError
import zipfile, socket
from cStringIO import StringIO
#from urllib import urlopen

from PyQt4 import QtCore, QtGui
from include.constants import RESOURCEPATH
	
def extractZip( filename, dir ):
	zf = zipfile.ZipFile( filename )
	namelist = zf.namelist()
	dirlist = filter( lambda x: x.endswith( '/' ), namelist )
	filelist = filter( lambda x: not x.endswith( '/' ), namelist )
	if len(dirlist)==0:
		for d in namelist:
			if not os.path.dirname(d) in dirlist and os.path.dirname(d)!='':
				dirlist.append(os.path.dirname(d))
	print "directories to extract:",dirlist
	print "files to extract:",filelist
	# make base
	pushd = os.getcwd()
	if not os.path.isdir( dir ):
		os.mkdir( dir )
	os.chdir( dir )
	# create directory structure
	dirlist.sort()
	root=dirlist[0]

	for dirs in dirlist:
		dirs = dirs.split( '/' )
		prefix = ''
		for dir in dirs:
			dirname = os.path.join( prefix, dir )
			if dir and not os.path.isdir( dirname ):
				os.mkdir( dirname )
			prefix = dirname
	# extract files
	for fn in filelist:
		try:
			out = open( fn, 'wb' )
			buffer = StringIO( zf.read( fn ))
			buflen = 2 ** 20
			datum = buffer.read( buflen )
			while datum:
				out.write( datum )
				datum = buffer.read( buflen )
			out.close()
		finally:
			print fn
	os.chdir( pushd )
	return root
	
def cprint(color,text):
	text=unicode(text)
	if color=="yellow":
		return "\033[1;33m"+text+" \033[0m"
	elif color=="red":
		return "\033[0;31m"+text+" \033[0m"
	elif color=="green":
		return "\033[0;32m"+text+" \033[0m"
	elif color=="lightblue":
		return "\033[1;34m"+text+" \033[0m"
	elif color=="lightgray":
		return "\033[0;37m"+text+" \033[0m"
	elif color=="lightcyan":
		return "\033[1;36m"+text+" \033[0m"
	else:
		return text

def makeHomeDir(homeDir):
	if not os.path.isdir(homeDir):
		os.mkdir(homeDir)
		os.mkdir(homeDir+"/emoticons")
		os.mkdir(homeDir+"/chatskins")
		os.mkdir(homeDir+"/sounds")
		os.chmod(homeDir, 0700)
	if not os.path.isdir(homeDir+"/emoticons"):
		os.mkdir(homeDir+"/emoticons")
	if not os.path.isdir(homeDir+"/chatskins"):
		os.mkdir(homeDir+"/chatskins")
	if not os.path.isdir(homeDir+"/sounds"):
		os.mkdir(homeDir+"/sounds")
	if not os.path.isdir(homeDir+"/temp"):
		os.mkdir(homeDir+"/temp")
	if not os.path.isdir(homeDir+"/rosterstyles"):
		os.mkdir(homeDir+"/rosterstyles")
	if not os.path.isdir(homeDir+"/rosterstyles/ng"):
		os.mkdir(homeDir+"/rosterstyles/ng")
	if not os.path.isdir(homeDir+"/themepackages"):
		os.mkdir(homeDir+"/themepackages")
		
def loadConfig(main,status):
	# loads config and repairs config file
	w=QtGui.QDesktopWidget()
	configs={"jid":"",
			"passwd":"",
			"savePasswd":"",
			"advancedPrefs":"False",
			"autoJoin":"False",
			"autoDownload":"False",
			"autoDownloadPath": getDesktopPath(main.homeDir),
			"rosterIconSize":"16x16",
			"chat_skin":"cool.conf",
			"chatSkin":"cool/cool.cfg",
			"emoticons":"default/smileys.cfg",
			"theme":"template",
			"log":"true",
			"resource":"jabbim",
			"autoPriority":"True",
			"priority":"0",
			"autoPriority_chat":25,
			"autoPriority_online":20,
			"autoPriority_away":15,
			"autoPriority_xa":10,
			"autoPriority_dnd":5,
			"logfile":"jabbim.log",
			"windowGeometry":[w.availableGeometry().x(),w.availableGeometry().y(),200,w.availableGeometry().height()],
			"chatGeometry":[w.availableGeometry().x(),w.availableGeometry().y(),None,None],
			"chatSplitterSizes":[500,70],
			"chatSplitter2Sizes":[500,128],
			"groupchatSplitterSizes":[500,120],
			"groupchatSplitter2Sizes":[45,500,70],
			"groupchatSplitSizes1":[500,70],
			"groupchatSplitSizes2":[500,120],
			"groupchatSplitSizes3":[45,500],
			"groupchatServerHistory": [],
			"chatDialogHistory": [],
			"sendPep":"True",
			"favUsers":[],
			"textSizeMultiplier":"1.0",
			"saveGeometry":"True",
			"saveExpandedGroups":"True",
			"chatTheme":"minimal-mod/Blue vs Grey.css",
			"groupchatTheme":"minimal-mod/Blue vs Grey.css",
			"expandedGroups":[],
			"plugins":['notification', 'archive', 'autoaway', 'autoupdate', 'jdm', 'tune', 'remote',  'uniemoticons'],
			"rosterMode":"normal",
			"rosterStyle":"compact",
			"themePackage":"default/package.cfg",
			"chatMode":"normal",
			"statusMessages":list(status),
			"notifyOnDND":"True",
			"keepStatus":"False",
			"keepedStatus":'',
            "keepedShow":'',
			"showChatStatusChanges":"True",
			"showMucStatus":"True",
			"showMucJoinPart":"True",
			"showMoodChanges":"True",
			"showTuneChanges":"True",
			"useMUCNames":"True",
			"sendByCtrl":"False",
			"showTransports":"False",
			"oneWindow":"False",
			"askBeforeQuitMUC":"True",
			"bigOnClick":"False",
			"specifyHost":"False",
			"connectHost": "",
			"connectPort": "5222",
			"showOffline":"True",
			"soundPack":"default/default.cfg",
			"allowChatstate": "True",
			"adhocAllow": [],
			"discoHistory": [],
			"startInTray": "False",
			"sendOSInfo": "True",
			"sendTune": "True",
			"sendMood": "True",
			"sendActivity": "True",
			"sendRooms": "True",
			"boshURL": '',
			"proxyHost":"", 
			"proxyPort":"", 
			"autoJoinMUC": 'True',
			"autochangenickMUC": 'True',
			"FTHost": '',
			"FTPort": '',
			"tabCycling" : "True", #cyklovanie medzi tabmi...
			'startInTray':"False",
			'commandsInTray':[],
			'moods':'default/default.cfg',
			'activities':'default/default.cfg',
			'preferencesAdvanced':'False',
 			##shortcuts
 			"nextTab" : "Alt+Right",
 			"previousTab" : "Alt+Left",
 			
 			"removeTab" : "Ctrl+F4",
 			"tabOne" : "Alt+1",
 			"tabTwo" : "Alt+2",
 			"tabThree" : "Alt+3",
 			"tabFour" : "Alt+4",
 			"tabFive" : "Alt+5",
 			"tabSix" : "Alt+6",
 			"tabSeven" : "Alt+7",
 			"tabEight" : "Alt+8",
 			"tabNine" : "Alt+9",
 			
 			"moveRight" : "Ctrl+Right",
 			"moveLeft" : "Ctrl+Left",
			'activeShortcuts':['nextTab','previousTab','removeTab','tabOne','tabTwo','tabThree','tabFour','tabFive','tabSix','tabSeven','tabEight','tabNine','moveRight','moveLeft'],
			'useXHTML': 'True',
			'showReceipts':'True',
			'usePsyco': 'False',
			'lastUploadDir': getDesktopPath(),
			'lastDownloadDir': getDesktopPath(),
			'remoteMucList': "True",
			"askForOffline" : "False"
			}

	# Start with optimism and hope a valid config is there.
	rewrite = False
	try:
		main.config = ConfigObj(main.homeDir+'/config', encoding='UTF8')
	except ConfigObjError, e:
		# damaged config file. parts of it may be alright
		# => salvage lines that are syntactically correct
		main.config = e.config
		rewrite = True
	except UnicodeDecodeError, e:
		# complete nonsense bytes in the config file. we
		# don't get even a partial result here, so we must
		# create a completely new config.
		print "UnicodeDecodeError parsing the ConfigObj. Will create new config."
		main.config = ConfigObj(encoding='UTF8')
		main.config.filename = main.homeDir+'/config'

	# If no line at all was parsed, a reasonable explanation is that the
	# homeDir does not even exist yet, so try to create it. If it in fact
	# existed, this causes no harm. There's no need to redo the creation of
	# the ConfigObj instance, the one we already have will work.
	if len(main.config) == 0:
		makeHomeDir(main.homeDir)
		rewrite = True
	# Fill any missing keys with default values.
	for k,v in configs.iteritems():
		try:
			main.config[k]
		except:
			main.config[k] = v
			rewrite = True
	# emoticon test
	loaded,cf=main.resourceManager.loadJabbimExtraConfig(RESOURCEPATH+"emoticons/"+main.config['emoticons'],main.realHomeDir+"/emoticons/"+main.config['emoticons'])
	if loaded==None and not cf:
		main.config['emoticons']="default/smileys.cfg"
		rewrite=True

	# chatskin test
	loaded,cf=main.resourceManager.loadJabbimExtraConfig(RESOURCEPATH+"chatskins/"+main.config['chatSkin'],main.realHomeDir+"/chatskins/"+main.config['chatSkin'])
	if loaded==None and not cf:
		main.config['chatSkin']="cool/cool.cfg"
		rewrite=True

	if rewrite:
		main.config.write()
	main.config["chatSplitterSizes"]=map(int, main.config["chatSplitterSizes"])
	main.config["chatSplitter2Sizes"]=map(int, main.config["chatSplitter2Sizes"])
	main.config["groupchatSplitterSizes"]=map(int, main.config["groupchatSplitterSizes"])
	main.config["groupchatSplitter2Sizes"]=map(int, main.config["groupchatSplitter2Sizes"])
	main.config["groupchatSplitSizes1"]=map(int, main.config["groupchatSplitSizes1"])
	main.config["groupchatSplitSizes2"]=map(int, main.config["groupchatSplitSizes2"])
	main.config["groupchatSplitSizes3"]=map(int, main.config["groupchatSplitSizes3"])
	if not os.path.isdir(main.homeDir+'/avatars'):
		os.mkdir(main.homeDir+'/avatars')
	if not os.path.isdir(main.homeDir+'/bobCache'):
		os.mkdir(main.homeDir+'/bobCache')	
	if not os.path.isdir(main.homeDir+'/plugins'):
		os.mkdir(main.homeDir+'/plugins')

def getProfiles(homedir):
	makeHomeDir(homedir)
	profiles=[]
	for file in os.listdir(homedir):
		if os.path.isdir(homedir+u"/"+unicode(file)):
			if file.endswith("-profile"):
				profiles.append(file)
	return profiles

def getDesktopPath(default = './'):
	folder=None 
	if sys.platform=="win32": 
		import _winreg
		hkcu = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER) 
		folders=_winreg.OpenKey(hkcu, r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') 
		try: 
			(folder, typ) = _winreg.QueryValueEx(folders, "Desktop") 
		except WindowsError: 
			folder=None
	else:
		folder = '~/Desktop'
	if folder:
		return folder
	else:
		return default

def getHomeDir():
	# return homedir from cmdline if present
	for x in range(0,len(sys.argv)):
		if sys.argv[x] == '--home':
			return(sys.argv[x+1]);

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

def path(cesta):
  return cesta.encode(sys.getfilesystemencoding())

def need_highlight(nick, text):
		n=len(nick)
		t=len(text)
		if t-n<0:
			return False
		
		for c in range(0,t):
			found=text.find(nick,c)#,(t-n+1)
			if found!=-1:
				#start nick
				if found==0: #at the start of text
					s=True
				else:
					refer_to_nick_char=text[found-1:found]
					if (refer_to_nick_char != ''):
						refer_to_nick_char_code = ord(refer_to_nick_char)
						if ((refer_to_nick_char_code < 65 or \
						refer_to_nick_char_code > 123) or \
						(refer_to_nick_char_code < 97 and \
						refer_to_nick_char_code > 90)):
							s=True
						else:
							s=False
							continue
					else:
						s=True
				
				#end nick
				refer_to_nick_char=text[found+n:found+n+1]
				if (refer_to_nick_char != ''):
					refer_to_nick_char_code = ord(refer_to_nick_char)
					if ((refer_to_nick_char_code < 65 or \
					refer_to_nick_char_code > 123) or \
					(refer_to_nick_char_code < 97 and \
					refer_to_nick_char_code > 90)):
						e=True
					else:
						e=False
						continue
				else:
					e=True
				if s==True and e==True:
					return True
		return False
		
		
		# upraveno z gajimu - need edit to more words nicks
		#special_words = []
		#special_words.append(nick)
		## Strip empties: ''.split(';') == [''] and would highlight everything.
		## Also lowercase everything for case insensitive compare.
		#special_words = [word.lower() for word in special_words if word]
		#text = text.lower()

		#text_splitted = text.split()
		#for word in text_splitted: # get each word of the text
			#for special_word in special_words:
				#if word.startswith(special_word):
					## get char after the word that highlight us
					#char_position = len(special_word)
					#refer_to_nick_char = \
						#word[char_position:char_position+1]
					#if (refer_to_nick_char != ''):
						#refer_to_nick_char_code = ord(refer_to_nick_char)
						#if ((refer_to_nick_char_code < 65 or \
						#refer_to_nick_char_code > 123) or \
						#(refer_to_nick_char_code < 97 and \
						#refer_to_nick_char_code > 90)):
							#return True
						#else: 
							## This is A->Z or a->z, we can be sure our nick is the
							## beginning of a real word, do not highlight. Note that we
							## can probably do a better detection of non-punctuation
							## characters
							#return False
					#else: # Special word == word, no char after in word
						#return True 
		#return False

distro_info = {
	'Arch Linux': '/etc/arch-release',
	'Aurox Linux': '/etc/aurox-release',
	'Conectiva Linux': '/etc/conectiva-release',
	'CRUX': '/usr/bin/crux',
	'Debian GNU/Linux': '/etc/debian_release',
	'Debian GNU/Linux': '/etc/debian_version',
	'Fedora Linux': '/etc/fedora-release',
	'Gentoo Linux': '/etc/gentoo-release',
	'Linux from Scratch': '/etc/lfs-release',
	'Mandrake Linux': '/etc/mandrake-release',
	'Slackware Linux': '/etc/slackware-release',
	'Slackware Linux': '/etc/slackware-version',
	'Solaris/Sparc': '/etc/release',
	'Source Mage': '/etc/sourcemage_version',
	'SUSE Linux': '/etc/SuSE-release',
	'Sun JDS': '/etc/sun-release',
	'PLD Linux': '/etc/pld-release',
	'Yellow Dog Linux': '/etc/yellowdog-release',
	# many distros use the /etc/redhat-release for compatibility
	# so Redhat is the last
	'Redhat Linux': '/etc/redhat-release'
}

#def getWindowsVersion():
	#if os.name == 'nt':
		#ver = os.sys.getwindowsversion()
		#ver_format = ver[3], ver[0], ver[1]
		#win_version = {
			#(1, 4, 0): '95',
			#(1, 4, 10): '98',
			#(1, 4, 90): 'me',
			#(2, 3, 51): 'NT 3.51',
			#(2, 4, 0): 'nt',
			#(2, 5, 0): '2000',
			#(2, 5, 1): 'xp',
			#(2, 5, 2): '2003',
			#(2, 6, 0): 'vista',
			#(2, 6, 1): '7'
		#}
		#if win_version.has_key(ver_format):
			#return win_version[ver_format]
		#else:
			#return 'unknown'
		
def get_os_info():
	if os.name == 'nt':
		ver = os.sys.getwindowsversion() #(5, 1, 2600, 2, 'Service Pack 2') = W XP profesional
		ver_format = ver[3], ver[0], ver[1]
		win_version = {
			#(type,major,minor)
			(1, 4, 0): '95',
			(1, 4, 10): '98',
			(1, 4, 90): 'ME',
			(2, 3, 51): 'NT 3.51',
			(2, 4, 0): 'NT 4',
			(2, 5, 0): '2000',
			(2, 5, 1): 'XP',
			(2, 5, 2): 'Server 2003',
			(2, 6, 0): 'Vista',
			(2, 6, 1): '7'
		}
		if win_version.has_key(ver_format):
			return 'Windows' + ' ' + win_version[ver_format]
		else:
			return 'Windows'
	elif os.name == 'posix':
		if platform.system() == 'Darwin' and platform.mac_ver()[0] != '':
			return 'Mac OS X' + ' ' + platform.mac_ver()[0]
		executable = 'lsb_release'
		params = ' --id --codename --release --short'
		full_path_to_executable = is_in_path(executable, return_abs_path = True)
		if full_path_to_executable:
			command = executable + params
			child_stdin, child_stdout = os.popen2(command)
			output = temp_failure_retry(child_stdout.readline).strip()
			child_stdout.close()
			child_stdin.close()
			os.wait()
			# some distros put n/a in places, so remove those
			output = output.replace('n/a', '').replace('N/A', '')
			return output

		# lsb_release executable not available, so parse files
		for distro_name in distro_info:
			path_to_file = distro_info[distro_name]
			if os.path.exists(path_to_file):
				if os.access(path_to_file, os.X_OK):
					# the file is executable (f.e. CRUX)
					# yes, then run it and get the first line of output.
					text = get_output_of_command(path_to_file)[0]
				else:
					fd = open(path_to_file)
					text = fd.readline().strip() # get only first line
					fd.close()
					if path_to_file.endswith('version'):
						# sourcemage_version and slackware-version files
						# have all the info we need (name and version of distro)
						if not os.path.basename(path_to_file).startswith(
						'sourcemage') or not\
						os.path.basename(path_to_file).startswith('slackware'):
							text = distro_name + ' ' + text
					elif path_to_file.endswith('aurox-release'):
						# file doesn't have version
						text = distro_name
					elif path_to_file.endswith('lfs-release'): # file just has version
						text = distro_name + ' ' + text
				return text

		# our last chance, ask uname and strip it
		uname_output = get_output_of_command('uname -a | cut -d" " -f1,3')
		if uname_output is not None:
			return uname_output[0] # only first line
	return 'N/A'

def is_in_path(name_of_command, return_abs_path = False):
	# if return_abs_path is True absolute path will be returned
	# for name_of_command
	# on failures False is returned
	is_in_dir = False
	found_in_which_dir = None
	path = os.getenv('PATH').split(':')
	for path_to_directory in path:
		try:
			contents = os.listdir(path_to_directory)
		except OSError: # user can have something in PATH that is not a dir
			pass
		else:
			is_in_dir = name_of_command in contents
		if is_in_dir:
			if return_abs_path:
				found_in_which_dir = path_to_directory
			break

	if found_in_which_dir:
		abs_path = os.path.join(path_to_directory, name_of_command)
		return abs_path
	else:
		return is_in_dir

def get_output_of_command(command):
	try:
		child_stdin, child_stdout = os.popen2(command)
	except ValueError:
		return None

	output = child_stdout.readlines()
	child_stdout.close()
	child_stdin.close()

	return output

def temp_failure_retry(func, *args, **kwargs):
	while True:
		try:
			return func(*args, **kwargs)
		except (os.error, IOError, select.error), ex:
			if ex.errno == errno.EINTR:
				continue
			else:
				raise

def replace_url(text,mainWindow,widget=None):
	#exp = re.compile("([A-Za-z][A-Za-z0-9+.-]{1,120}:[A-Za-z0-9/](([A-Za-z0-9$_.+!*,;/?:@&~=-])|%[A-Fa-f0-9]{2}){1,333}(#([a-zA-Z0-9][a-zA-Z0-9$_.+!*,;/?:@&~=%-]{0,1000}))?)")
	#exp=re.compile(unicode(r"((http|ftp)://)?(((([\d]+\.)+){3}[\d]+(/[\w./]+)?)|([a-z]\w*((\.\w+)+){2,})([/][\w.~]*)*)"))
	#for link in exp.findall(text):
		#fnt link
		#text = text.replace(link[0], '<a href="%s">%s</a>'%(link[0], link[0]))
	t=text
	t=t.replace("<br/>"," <br/>")
	text=""
	for word in t.split(" "):
		if word.find("://")!=-1:
			if word[-3:].lower() in ["png","jpg","gif","bmp","peg","iff"] and widget:
				widget.imageId+=1
				link = word
				if word.startswith('http://album.jabbim.cz'):
					print word
					jid, img = word.split('/')[-2:]
					link = 'http://album.jabbim.cz/embed/%s/%s'%(jid, img)
					print link
				text+='<div id="image%s"><a href="%s" title="%s">%s</a>'%(str(widget.imageId),word,word, word)+" "
				text+='<a href="javascript:;" title="%s" onclick="showImage(\'image%s\',\'%s\',\'%s\');")>['%(word,str(widget.imageId),link,word)+unicode(mainWindow.tr("Show Image"))+']</a></div>'+" "
# Youtube video title replacement is a nice feature to have, but this
# implementation reads the page synchronously, so it easily blocks Jabbim UI
# for a long time (several minutes in pathological cases like
# http://dev.jabbim.cz/jabbim/ticket/965 )
#			elif word.find("youtube.com/watch?")!=-1: #nahradi adresu z youtube za nazev videa
#				print 'processing youtube link: '+word
#				url=word
#				try:
#					stranka=urlopen(url).read(350)
#				except:
#					continue
#				title=re.findall('<title>(.*)</title>',stranka)
#				if title==[] or title[0].strip()=="": # pokud jsme nenasli zadny <title> tag, nebo byl prazdny
#					text+='<a href="'+url+'">'+url+'</a>'
#				else:
#					text+='<a href="'+url+'">'+title[0].decode('utf-8')+'</a>'
			else:
				text+='<a href="%s" title="%s">%s</a>'%(word, word, word)+" "
		elif word.startswith("www."):
			text+='<a href="http://%s" title="%s">%s</a>'%(word, word, word)+" "
		elif word.find('@') != -1:
			wellKnown = ['jabbim.cz', 'njs.netlab.cz', 'pyco.cz', 'jabbim.sk', 'jabbim.pl', 'jabber.cz', 'jabbim.com', 'gmail.com', 'jabber.org', 'jabster.pl', 'jabber.ru']
			wellKnownMuc = ['conf.netlab.cz', 'conference.jabber.org', 'chat.chrome.pl', 'conference.jabber.ru']
			user, server = word.split('@',1)
			server = server.split('/')[0]
			if word.count('@')>1 or not ('.' in server) or (widget != None and widget.main().getJid(word) is None and not(user.startswith('xmpp:') or user.startswith('mailto:'))):
				text += word+" "
				continue

			if user.startswith('xmpp:') or user.startswith('mailto:'):
				if server.endswith('?join'):
					server = server[:-5]
				text+='<a href="%s" title="%s"><img src="%s/images/16x16/categories/muc.png" />%s</a> '%(word, word, RESOURCEPATH, user.split(':')[1]+'@'+server)
			else:
				if (widget != None and widget.main().client.hasIdentity(server, 'server', 'im')) or server in wellKnown :
					text+='<a href="xmpp:%s" title="%s"><img src="%s/images/16x16/apps/jabbim.png" />%s</a> '%(user+'@'+server, word, RESOURCEPATH, word)
				elif (widget != None and widget.main().client.hasIdentity(server, 'conference', 'text')) or server in wellKnownMuc:
					text+='<a href="xmpp:%s?join" title="%s"><img src="%s/images/16x16/categories/muc.png" />%s</a> '%(user+'@'+server, word, RESOURCEPATH, word)
				else:
					text+='<a href="mailto:%s" title="%s"><img src="%s/images/16x16/actions/message.png" />%s</a> '%(word, word, RESOURCEPATH, word)
		else:
			text+=word+" "
	return text[:-1]
	
def getFilenameFromLnk(name):
	if sys.platform == 'win32' :

		from win32com.shell import shell
		import pythoncom

		class Win32Shortcut:
		    def __init__(self, lnkname):
		        self.shortcut = pythoncom.CoCreateInstance(
		            shell.CLSID_ShellLink, None,
		            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
		        self.shortcut.QueryInterface(pythoncom.IID_IPersistFile).Load(lnkname)

		    def __getattr__(self, name):
		        return getattr(self.shortcut, name)

		s = Win32Shortcut(name)
		return s.GetPath(0)[0]
	else:
		return name

def elapsed_time(mainWindow, seconds, separator=' '):
	"""
	Takes an amount of seconds and turns it into a human-readable amount of time.
	"""
	# the formatted time string to be returned
	tim = []
 
	# the pieces of time to iterate over (days, hours, minutes, etc)
	# - the first piece in each tuple is the suffix (d, h, w)
	# - the second piece is the length in seconds (a day is 60s * 60m * 24h)
	parts = [60 * 60 * 24 * 7 * 52,
		     60 * 60 * 24 * 7,
		     60 * 60 * 24,
		     60 * 60,
		     60,
		     1]
 
	# for each time piece, grab the value and remaining seconds, and add it to
	# the time string
	i=0
	for length in parts:
		value = seconds / length
		if value > 0:
			seconds = seconds % length
			tim.append(unicode([mainWindow.tr('%n year',"",value),mainWindow.tr('%n week',"",value),mainWindow.tr('%n day',"",value),mainWindow.tr('%n hour',"",value),mainWindow.tr('%n minute',"",value),mainWindow.tr('%n second',"",value)][i] ))
		i=i+1
		if seconds < 1:
			break
	return separator.join(tim)

def getRevisionFromSvn():
	try:
		f = open('.svn/entries')
		lines = f.readlines()
		f.close()
		return ' - rev. ' + lines[3].strip()
	except:
		return None

def getRevisionFromGit():
	commit = None
	svn_rev = None
	try:
		re_commit = re.compile(r'^\s*commit\s*(([a-zA-Z0-9])+)')
		re_svnrev = re.compile(r'^\s*git-svn-id: svn://dev\.jabbim\.cz/jabbim/trunk@(\d+)')
		for line in os.popen('git show'):
			if commit == None:
				m = re_commit.match(line)
				if m:
					commit = m.group(1)
			elif svn_rev == None:
				m = re_svnrev.match(line)
				if m:
					svn_rev = m.group(1)
					break
	except:
		pass
	if commit != None and svn_rev != None:
		return ' - rev. %s (git-svn %s)' % (svn_rev, commit[:7])
	if commit != None:
		return ' - git %s' % commit[:7]
	return None

def getRevisionFromIniFile():
	rev = None
	try:
		re_version = re.compile(r'^version\s*=\s*(\d+)')
		f = open('svn-version.ini')
		for line in f:
			m = re_version.match(line)
			if m:
				rev = ' - rev. ' + m.group(1)
				break
		f.close()
	except:
		pass
	return rev

def getSvnVersion():
	rev = getRevisionFromIniFile()
	if rev:
		return rev
	rev = getRevisionFromSvn()
	if rev:
		return rev
	rev = getRevisionFromGit()
	if rev:
		return rev
	return ''

def getNormalSize(byte, kmg = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB'], index = 0): 
	"""Convert Bytes to human readable form"""
	try:
		cislo = float(byte)
		while cislo >= 1024:
			cislo = cislo/1024
			index += 1
		return "%.1f %s" % (cislo, kmg[index])
	except:
		return 'N/A'
		
def getStampFromFormat(datetime, format): # format e.g. "%d.%m.%Y %H:%M"
	"""Conver datetime by format to time by xep-0082"""
	if format==None or datetime==None:
		(year, month, day, hour, minut, seconds, nic , nic , nic) = time.gmtime(time.mktime(time.localtime()))
	elif format == 'sec':
		try:
			datetime=float(datetime)
			(year, month, day, hour, minut, seconds, nic , nic , nic) = time.gmtime(time.mktime(time.localtime(datetime)))
		except Exception,ex:
			print ex
			(year, month, day, hour, minut, seconds, nic , nic , nic) = time.gmtime(time.mktime(time.localtime()))
	else:
		(year, month, day, hour, minut, seconds, nic , nic , nic) = time.gmtime(time.mktime(time.strptime(datetime, format)))
	
	if day<10:
		day="0%s" % day
	if month<10:
		month="0%s" % month
	if year<100:
		year="20%s" % year
	if hour<10:
		hour="0%s" % hour
	if minut<10:
		minut="0%s" % minut
	if seconds<10:
		seconds="0%s" % seconds
	return  "%s-%s-%sT%s:%s:%sZ" % (year, month, day, hour, minut, seconds)

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
	if not argv.startswith('xmpp:'):
		return 'wrong uri'
	uri = argv[5:]
	parts = uri.split('?', 1)
	if len (parts) == 1:
		return server.startChat(parts[0].replace('%40', '@'), porty[1])
	elif parts[1] == 'join':
		return server.joinMUC(parts[0].replace('%40', '@'), porty[1])

def regWindowsMenu(name, comm):
	if sys.platform == 'win32' :
		print os.getcwd()
		if sys.argv[0].find('jabbim.py') != -1:
			cesta = 'c:\Python25\python.exe "' + os.getcwd() + '\\jabbim.py" --plugin="'+comm+' %1"' #hack!
		else:
			cesta = '"' + os.getcwd() + '\\jabbim.exe" --plugin="'+comm+' %1"'
		import _winreg
		reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CLASSES_ROOT)
		command = _winreg.CreateKey(reg, 'AllFilesystemObjects\\shell\\%s\\command'%name)
		_winreg.CloseKey(command)
  		command = _winreg.OpenKey(reg, 'AllFilesystemObjects\\shell\\%s\\command'%name, 0, _winreg.KEY_WRITE)
		_winreg.SetValueEx(command,'', 0, _winreg.REG_SZ, cesta )
		_winreg.CloseKey(command)

def unregWindowsMenu(name):
	if sys.platform == 'win32' :
		import _winreg
		reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CLASSES_ROOT)
  		command = _winreg.OpenKey(reg, 'AllFilesystemObjects\\shell', 0, _winreg.KEY_WRITE)
		_winreg.DeleteKey(command, name + '\\command')
		_winreg.DeleteKey(command, name)
		_winreg.CloseKey(command)

def loadTranslator(path_prefix):
	native_lang = QtCore.QLocale.system().name()[:2]
	translator = QtCore.QTranslator()
	if native_lang == 'C':
		# if LANG=C was set, we must not attempt to load locales
		preferred_langs = []
	elif native_lang == 'sk':
		# in case Slovak translation is not available,
		# most Slovak people prefer reading Czech, not English
		preferred_langs = ['sk', 'cs', 'en']
	elif native_lang == 'en':
		preferred_langs = ['en']
	else:
		# 'en' is still better than the source pseudo-english,
		preferred_langs = [native_lang, 'en']
	for lang in preferred_langs:
		filename = path_prefix + lang + ".qm"
		if translator.load(filename):
			break
		print "failed to load locales from ", filename
	return translator
