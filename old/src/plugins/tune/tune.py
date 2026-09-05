# -*-coding: utf-8 -*-

import sys, os, locale
sys.path.append('.')
if sys.platform == 'win32':
	import win32gui
from include import plugins
from twisted.python import log
from twisted.internet.task import LoopingCall
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessDone
from twisted.internet import reactor

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		if sys.platform == 'win32':
			self.config['player']={'type':'list-single','label':self.main.tr("Player"), 'items':{'Winamp':'winamp', 'Foobar 2000':'fb2k' }, 'value':'winamp'}
		else:
			self.config['player']={'type':'list-single','label':self.main.tr("Player"), 'items':{'MPD':'mpd', 'Amarok':'amarok', 'Amarok 2':'amarok2', 'Exaile':'exaile', 'Banshee':'banshee', 'Rhythmbox':'rhythmbox', 'Audacious':'audacious', 'Qmmp':'qmmp'}, 'value':'amarok'}

class Player:
	def __init__(self, plugin):
		self.plugin = plugin
		self.main = plugin.main
	def clear_PEP(self, reason=None):
		self.plugin.sendPEP({})
	def check(self):
		pass

class Winamp(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
	def check(self):
		out = {}
		try:
			hWinamp = win32gui.FindWindow('Winamp v1.x', None)
			text = win32gui.GetWindowText(hWinamp).decode(locale.getpreferredencoding())
		except Exception, ex:
			text = ''
		if len(text) > 0:
			parts = text.split(' - ')
			if len(parts) > 1:
				out['artist'] = parts[0].split(' ', 1)[1]
				out['title'] = parts[1]
			else:
				out = {}
			if text.find('[Stopped]')!= -1:
				out = {}
		self.plugin.sendPEP(out)

class Foobar2000(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
	def check(self):
		out = {}
		try:
			hfb2k = win32gui.FindWindow('{97E27FAA-C0B3-4b8e-A693-ED7881E99FC1}', None)
			text = win32gui.GetWindowText(hfb2k).decode(locale.getpreferredencoding())
		except Exception, ex:
			text = ''
		if len(text) > 0:
			parts = text.split(' - ')
			if len(parts) > 1:
				out['artist'] = parts[0]
				out['title'] = parts[1].split('[foobar2000 v', 1)[0].strip()
			else:
				out = {}
		self.plugin.sendPEP(out)

class MPDProtocol(ProcessProtocol):
	def __init__(self, plugin):
		self.plugin = plugin
		self.output = ''
	def outReceived(self, output):
		self.output += output
	def processEnded(self, reason):
		out = {}
		if isinstance(reason.value, ProcessDone) and self.output.find('\n[playing]') != -1:
			text = self.output.split('\n')[0]
			text = unicode(text, 'utf8')
			text = text.split(' - ', 2)
			if len(text)>1:
				out['artist'] = text[0]
				out['title'] = text[1]
				if len(text)>2:
					out['source'] = text[2]
			else:
				out['title'] = self.output.split('\n')[0].split('/')[-1]
			out['length'] = self.output.split('\n')[1].split('/')[-1].split('(')[0].strip()
		self.plugin.sendPEP(out)

class MPD(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
	def check(self):
		reactor.spawnProcess(
			MPDProtocol(self.plugin),
			'mpc', ['mpc', 'status','--format', '%artist% - %title% - %album%'],
			env=os.environ)

class AmarokProtocol(ProcessProtocol):
	def __init__(self, plugin, out, field):
		self.plugin = plugin
		self.out = out
		if field == 'album':
			field = 'source'
		self.field = field
	def outReceived(self, data):
		self.out[self.field] = unicode(data, "utf-8").strip()
	def processEnded(self, reason):
		if not isinstance(reason.value, ProcessDone):
			self.out = {}
		if len(self.out) == 3 or self.out == {}:
			self.plugin.sendPEP(self.out)

class Amarok(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
	def check(self):
		out = {}
		for field in ['artist', 'title', 'album']:
			reactor.spawnProcess(
				AmarokProtocol(self.plugin, out, field),
				'dcop', ['dcop', 'amarok', 'player', field],
				env=os.environ)

class MPRISPlayer(Player):
	def __init__(self, plugin, mpris_name):
		Player.__init__(self, plugin)
		self.sig_receivers = []
		self.dbus_name = "org.mpris." + mpris_name
	def got_metadata(self, song_info):
		out = {}
		try:
			out['artist'] = unicode(song_info['artist'])
			out['title'] = unicode(song_info['title'])
			if out['artist'] == "" and out['title'] == "":
				out = {}
		except:
			out = {}
		self.plugin.sendPEP(out)
	def check(self, dummy=None):
		# I ignore the data supplied in DBus signals {Track,Status}Change,
		# because I couldn't make it work reliably. Instead I just always ask
		# Amarok again what the current song is. It's slower, but works.
		try:
			bus = self.main.session_dbus
			amarok_player = bus.get_object(self.dbus_name, "/Player")
			amarok_player.GetMetadata(reply_handler=self.got_metadata, error_handler=self.clear_PEP)
		except:
			self.clear_PEP()
	def start_listening(self):
		bus = self.main.session_dbus
		self.sig_receivers.append(bus.add_signal_receiver(self.check,
			'TrackChange',  "org.freedesktop.MediaPlayer", self.dbus_name, "/Player"))
		self.sig_receivers.append(bus.add_signal_receiver(self.check,
			'StatusChange', "org.freedesktop.MediaPlayer", self.dbus_name, "/Player"))
	def stop_listening(self):
		for receiver in self.sig_receivers:
			receiver.remove()
		self.sig_receivers = []

class Amarok2(MPRISPlayer):
	def __init__(self, plugin):
		MPRISPlayer.__init__(self, plugin, "amarok")

class Qmmp(MPRISPlayer):
	def __init__(self, plugin):
		MPRISPlayer.__init__(self, plugin, "qmmp")

class Exaile(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
		self.song_info = {}
	def maybe_send(self):
		if len(self.song_info) == 2:
			out = self.song_info.copy()
			self.plugin.sendPEP(out)
	# the possible race when the song changes right between the two dbus
	# messages is hardly worth fixing
	def got_artist(self, artist):
		self.song_info['artist'] = artist
		self.maybe_send()
	def got_title(self, title):
		self.song_info['title'] = title
		self.maybe_send()
	def check(self):
		self.song_info = {}
		try:
			bus = self.main.session_dbus
			exa = bus.get_object("org.exaile.DBusInterface","/DBusInterfaceObject")
			exa.get_artist(reply_handler=self.got_artist, error_handler=self.clear_PEP)
			exa.get_title (reply_handler=self.got_title , error_handler=self.clear_PEP)
		except:
			self.clear_PEP()

class Banshee(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
		self.sig_receivers = []
	def got_metadata(self, song_info):
		out = {}
		try:
			out['artist'] = song_info['artist']
			out['title'] = song_info['name']
		except:
			out = {}
		self.plugin.sendPEP(out)
	def check(self):
		try:
			bus = self.main.session_dbus
			banshee = bus.get_object("org.bansheeproject.Banshee", "/org/bansheeproject/Banshee/PlayerEngine")
			banshee.GetLastState(reply_handler=self.on_state_changed, error_handler=self.clear_PEP)
		except:
			self.clear_PEP()
	def recheck(self):
		try:
			bus = self.main.session_dbus
			banshee = bus.get_object("org.bansheeproject.Banshee", "/org/bansheeproject/Banshee/PlayerEngine")
			banshee.GetCurrentTrack(reply_handler=self.got_metadata, error_handler=self.clear_PEP)
		except:
			self.clear_PEP()
#	def on_event_changed(self, *args, **kwargs):
#		log.msg("MMM: on_event_changed, args=%s kwargs=%s" % (args, kwargs))
	def on_state_changed(self, state):
#		log.msg("MMM: on_state_changed, new state=%s" % state)
		if state == 'playing':
			self.recheck()
		else:
			self.clear_PEP()
	def start_listening(self):
		bus = self.main.session_dbus
#		self.sig_receivers.append(bus.add_signal_receiver(self.on_event_changed,
#			'EventChanged', "org.bansheeproject.Banshee.PlayerEngine",
#			"org.bansheeproject.Banshee", "/org/bansheeproject/Banshee/PlayerEngine"))
		self.sig_receivers.append(bus.add_signal_receiver(self.on_state_changed,
			'StateChanged', "org.bansheeproject.Banshee.PlayerEngine",
			"org.bansheeproject.Banshee", "/org/bansheeproject/Banshee/PlayerEngine"))
	def stop_listening(self):
		for receiver in self.sig_receivers:
			receiver.remove()
		self.sig_receivers = []

class Rhythmbox(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
		self.sig_receivers = []
		self.playing = False
		self.song_info = {}
	def send(self):
		if self.playing:
			out = self.song_info.copy()
		else:
			out = {}
		self.plugin.sendPEP(out)
	def check(self):
		try:
			bus = self.main.session_dbus
			rhythmboxplayer = bus.get_object("org.gnome.Rhythmbox", "/org/gnome/Rhythmbox/Player")
			rhythmboxplayer.getPlaying(reply_handler=self.on_playing_changed, error_handler=self.clear_PEP)
			rhythmboxplayer.getPlayingUri(reply_handler=self.on_playing_uri_changed, error_handler=self.clear_PEP)
		except:
			self.clear_PEP()
	def on_playing_changed(self, playing):
		self.playing = bool(playing)
		self.send()
	def on_playing_uri_changed(self, uri):
		try:
			bus = self.main.session_dbus
			rhythmboxshell = bus.get_object("org.gnome.Rhythmbox", "/org/gnome/Rhythmbox/Shell")
			rhythmboxshell.getSongProperties(uri, reply_handler=self.on_song_properties, error_handler=self.clear_PEP)
		except:
			self.song_info = {}
			self.send()
	def on_song_properties(self, song_info):
		self.song_info['title']  = song_info['title']
		self.song_info['artist'] = song_info['artist']
		self.send()
	def start_listening(self):
		bus = self.main.session_dbus
		self.sig_receivers.append(bus.add_signal_receiver(self.on_playing_changed,
			'playingChanged', "org.gnome.Rhythmbox.Player", "org.gnome.Rhythmbox", "/org/gnome/Rhythmbox/Player"))
		self.sig_receivers.append(bus.add_signal_receiver(self.on_playing_uri_changed,
			'playingUriChanged', "org.gnome.Rhythmbox.Player", "org.gnome.Rhythmbox", "/org/gnome/Rhythmbox/Player"))
	def stop_listening(self):
		for receiver in self.sig_receivers:
			receiver.remove()
		self.sig_receivers = []

class Audacious(Player):
	def __init__(self, plugin):
		Player.__init__(self, plugin)
		self.sig_receivers = []
		self.song_info = {}
		self.status = 2
	def send(self):
		if self.status == 0:
			out = self.song_info.copy()
		else:
			out = {}
		self.plugin.sendPEP(out)
	def check(self):
		try:
			bus = self.main.session_dbus
			audacious_player = bus.get_object("org.mpris.audacious", "/Player")
			audacious_player.GetStatus(reply_handler=self.on_status_changed, error_handler=self.clear_PEP)
			audacious_player.GetMetadata(reply_handler=self.on_track_changed, error_handler=self.clear_PEP)
		except:
			self.clear_PEP()
	def on_track_changed(self, info):
		# Audacious sends author/title only if it knows them from
		# the music file metadata
		title  = unicode(info.get('title',  ""))
		artist = unicode(info.get('artist', ""))
		if title == u"" and artist == u"":
			# non-tagged music file, fallback to base filename
			title = info.get('URI', "")
			last_slash_pos = title.rfind('/')
			title = title[last_slash_pos + 1 : ]
		self.song_info['title'] = title
		self.song_info['artist'] = artist
		self.send()
	def on_status_changed(self, status):
		# Audacious's GetStatus() does not comply exactly with
		# MPRIS spec, it returns a single Int32
		self.status = int(status)
		self.send()
	def start_listening(self):
		bus = self.main.session_dbus
		self.sig_receivers.append(bus.add_signal_receiver(self.on_track_changed,
			'TrackChange',  "org.freedesktop.MediaPlayer", "org.mpris.audacious", "/Player"))
		self.sig_receivers.append(bus.add_signal_receiver(self.on_status_changed,
			'StatusChange', "org.freedesktop.MediaPlayer", "org.mpris.audacious", "/Player"))
	def stop_listening(self):
		for receiver in self.sig_receivers:
			receiver.remove()
		self.sig_receivers = []

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'tune'
		self.installTranslator()
		self.description = self.tr('Plugin for User Tune')
		self.author = "Jiri 'Sef' Gabrys + Josef 'PepeQ' Halicek + Krzysztof 'Grom' K. + Pinky + Michal 'Michich' Schmidt"
		self.name = self.tr('tune')
		self.version = '0.264'
		self.category = ['utils']
		self.configDialog=config(self)
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.player_installed = False
		if main:
			self.loadConfig()
			self.registerHandler('on_authd', self.on_authd)
			if self.main.isConnected() and self.main.client.xmlstream:
				self.on_authd()
		else:
			self.loadConfig(homedir)

	def on_authd(self):
		self.last = None
		self.loop = None
		player_map = {
			'winamp':    Winamp,
			'fb2k':      Foobar2000,
			'mpd':       MPD,
			'amarok':    Amarok,
			'amarok2':   Amarok2,
			'exaile':    Exaile,
			'banshee':   Banshee,
			'rhythmbox': Rhythmbox,
			'audacious': Audacious,
			'qmmp': Qmmp
		}
		# create the chosen Player instance
		self.player = player_map[self.config['player']](self)
		try:
			# if it can listen for events from the music player,
			# it will implement start_listening()
			self.player.start_listening()
			self.player.check()
		except AttributeError:
			# it is polling-based
			self.loop = LoopingCall(self.player.check)
			self.loop.start(30)
		self.player_installed = True

	def on_remove(self):
		if self.player_installed:
			if self.loop:
				self.loop.stop()
			else:
				self.player.stop_listening()
		if self.main.isConnected():
			self.sendPEP({})

	def on_configChanged(self):
		self.on_remove()
		self.on_authd()

	def sendPEP(self, out):
		if not self.main.isConnected():
			return
		if self.main.client.xmlstream == None:
			log.err("tune: Can't sendPEP yet, no xmlstream!")
			return
		if out != self.last:
			self.main.client.sendPEP('http://jabber.org/protocol/tune', self.main.client.getTunePayload(out))
			self.last = out
