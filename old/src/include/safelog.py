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
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
from twisted.python import log

class SafeFileLogObserver(log.FileLogObserver):
	"""
	Workaround for t.p.log's FileLogObserver insistence to encode Unicode
	messages as ascii (which is of course often impossible).
	This encodes Unicode messages into UTF-8 instead.
	"""
	def __init__(self, logfile):
		log.FileLogObserver.__init__(self, logfile)
	def emit(self, eventDict):
		def encode_if_unicode(input):
			if type(input) == type(u''):
				return input.encode('utf-8')
			else:
				return input
		edm = eventDict['message']
		eventDict['message'] = tuple(map(encode_if_unicode, edm))
		log.FileLogObserver.emit(self, eventDict)

if __name__ == "__main__":
	logfile = open('/tmp/test_SafeFileLogObserver.txt', 'w')
	log_obs = SafeFileLogObserver(logfile)
	log_obs.timeFormat = '%Y-%m-%d %H:%M:%S'
	log.startLoggingWithObserver(log_obs.emit)

	log.msg('ahoj')
	log.msg(u'ahoj')
	log.msg('žluťoučký kůň')
	log.msg(u'žluťoučký kůň')
