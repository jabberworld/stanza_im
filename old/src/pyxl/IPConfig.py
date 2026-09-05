"""
IPConfig - finds out about DNS servers configured in Windows
Copyright (C) 2007  Michal "michich" Schmidt <mschmidt@redhat.com>

The registry keys were found in James Macfarlane's Win32::IPConfig CPAN module.

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
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import _winreg

def getProxy():
	hkcu = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
	settings=_winreg.OpenKey(hkcu, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')
	try:
		(proxy, typ) = _winreg.QueryValueEx(settings, "ProxyServer")
		print "Proxy according to IE:",[proxy]
	except WindowsError:
		print "no proxy in IE settings"
		proxy=None
	return proxy

class Adapter:
	def __init__(self, interfaces_key, nic_uuid):
		try:
			print "Adapter: __init__"
			tcpip_params_key = _winreg.OpenKey(interfaces_key, nic_uuid)
			print "Adapter: key opened"
			(dhcp_enabled, type) = _winreg.QueryValueEx(tcpip_params_key, "EnableDHCP")
			print "Adapter: EnableDHCP=%s" % unicode(dhcp_enabled)
			(nameserver, type) = _winreg.QueryValueEx(tcpip_params_key, "NameServer")
			print "Adapter: NameServer=%s" % unicode(nameserver)

			if nameserver == '' and dhcp_enabled:
				print "Adapter: alternative branch"
				(nameserver, type) = _winreg.QueryValueEx(tcpip_params_key, "DhcpNameServer")
				print "Adapter: DhcpNameServer=%s" % unicode(nameserver)

			if nameserver == '':
				print "Adapter: no nameserver on this iface"
				self.nameservers = []
			else:
				self.nameservers = nameserver.replace(',',' ').split(' ')
		except WindowsError:
			print "Adapter: a key is not present"
			self.nameservers = []

	def get_dns(self):
		return self.nameservers

class IPConfig:
	def __init__(self):
		self.cards = []
		hklm = _winreg.ConnectRegistry(None, _winreg.HKEY_LOCAL_MACHINE)
		print "IPConfig: registry connected"
		interfaces_key = _winreg.OpenKey(hklm, r'SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces')
		print "IPConfig: Interfaces key opened"
		i = 0
		try:
			while True:
				nic_uuid = _winreg.EnumKey(interfaces_key, i)
				print "IPConfig: found uuid %s" % unicode(nic_uuid)
				i = i + 1
				card = Adapter(interfaces_key, nic_uuid)
				self.cards.append(card)
				print "IPConfig: adapter added"
		except EnvironmentError:
			print "IPConfig: no more uuids"
			pass

	def get_dns(self):
		all_dns = []
		for c in self.cards:
			all_dns = all_dns + c.get_dns()
		print "IPConfig: get_dns gives %s" % unicode(all_dns)
		return all_dns
