# -*- coding: utf-8 -*-
"""
Copyright © 2009 Michal Schmidt <mschmidt AT redhat.com>

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

from include import plugins
from twisted.python import log

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'network-manager'
		self.installTranslator()
		self.description = self.tr('Detect network status using NetworkManager')
		self.author = "Michal 'Michich' Schmidt"
		self.name = self.tr('NetworkManager')
		self.version = '0.01'
		self.category = ['utils']
		self.url = 'http://dev.jabbim.cz/jabbim'

		self.sig_receivers = []

		if main:
			self.start_listening()
			self.check_state()

	def on_remove(self):
		self.stop_listening()

	def start_listening(self):
		dbus = self.main.system_dbus
		try:
			self.sig_receivers.append(dbus.add_signal_receiver(
				self.nm_state_change, 'StateChange',
				'org.freedesktop.NetworkManager',
				'org.freedesktop.NetworkManager',
				'/org/freedesktop/NetworkManager'))
		except:
			self.nm_error("start_listening")

	def stop_listening(self):
		for receiver in self.sig_receivers:
			receiver.remove()
		self.sig_receivers = []

	def nm_state_change(self, state):
		if 0 <= state <= 4:
			state_name =["unknown", "asleep", "connecting", "connected", "disconnected"][state]
		else:
			state_name = "???"
		log.msg("nm_state_change: state=%d (%s)" % (state, state_name))
		if state == 3:
			self.main.on_network_state_up()
		elif state == 4:
			self.main.on_network_state_down()

	def nm_error(self, err):
		# XXX
		log.err("NetworkManager error: %s" % err)

	def check_state(self):
		try:
			import dbus
			bus = self.main.system_dbus
			NM = bus.get_object('org.freedesktop.NetworkManager',
				'/org/freedesktop/NetworkManager')
			NM_props = dbus.Interface(NM, 'org.freedesktop.DBus.Properties')
			NM_props.Get('org.freedesktop.NetworkManager', 'State',
				reply_handler = self.nm_state_change,
				error_handler = self.nm_error)
		except:
			self.nm_error("check_state")
