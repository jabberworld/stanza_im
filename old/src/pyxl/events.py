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
from twisted.python import log
import traceback, time
import StringIO



class EventDispatcher:
	def __init__(self, prefix="event_"):
		self.prefix = prefix
		self.callbacks = {}
		self.sorted = {}

	def registerHandler(self, name, meth, hname = 'nic', priority = 5):
		self.callbacks.setdefault(name, {})[hname] = {'method':meth, 'prio':priority}
		seznam = self.callbacks[name].itervalues()
		serazeno = sorted(seznam, key = self.k)
		self.sorted[name] = serazeno

	def unregisterHandler(self, name, hname):
		try:
			del self.callbacks[name][hname]
		except:
			pass
		seznam = self.callbacks[name].itervalues()
		serazeno = sorted(seznam, key = self.k)
		self.sorted[name] = serazeno

	def publishEvent(self, name, *args, **kwargs):
		if self.callbacks.has_key(name) and self.sorted.has_key(name):
			t1 = time.time()
			for cb in self.sorted[name]:
				try:
					t2 = time.time()
					vysl = cb['method'](*args, **kwargs)
					#log.msg('handler %s executed in %i'%(unicode(cb), time.time()-t2))
					if vysl == False:
						log.msg('event %s consumed by %s'%(name, unicode(cb['method'])))
						return False

				except Exception, ex:
					#log.msg('Plugin error: ' +unicode(ex, 'utf8'))
					log.err('In function:'+unicode(name, 'utf8'))
					message = traceback.format_exc()
					log.err(message)
			#log.msg('%s event executed in %i s'%(name, time.time()-t1))
		else:
			#log.msg('no handler for %s'%name)
			pass
		return True

	def k(self, key):
		return key['prio']
