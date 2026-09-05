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

from twisted.enterprise import adbapi
from twisted.python import log
from twisted.internet.defer import DeferredList

class Cache:
	def __init__(self, DB_DRIVER = 'sqlite3', db='cache.db'):#,isolation_level = "IMMEDIATE"):
		if DB_DRIVER == 'sqlite3':
			try:
				self.db = adbapi.ConnectionPool(DB_DRIVER, db, cp_min=1, cp_max=1)
			except ImportError:
				self.db = adbapi.ConnectionPool('pysqlite2.dbapi2', db, cp_min=1, cp_max=1)
			except:
				log.msg('Unknown DB error')

	def drop_caps(self, res):
		return self.db.runQuery('drop table caps')

	def check_caps_table(self):
		# if the caps table does not have the identity column, it was
		# created with an old version of Jabbim, so let's drop it.
		return self.db.runQuery('select typeof(identity) from caps').addErrback(self.drop_caps)

	def _create_tables(self, res):
		t1 = self.db.runQuery('create table caps2 (node text primary key, feature text, identity text);').addCallback(self.table_created, 'caps').addErrback(self.table_present, 'caps')
		t2 = self.db.runQuery('create table status (show text, desc text, id integer primary key);').addCallback(self.table_created, 'status').addErrback(self.table_present, 'status')
		t3 = self.db.runQuery('create table avatars (file text, hash text, jid text);').addCallback(self.table_created, 'avatars').addErrback(self.table_present, 'avatars')
		return DeferredList([t1,t2,t3], consumeErrors = False)

	def create_tables(self):
		return self.check_caps_table().addBoth(self._create_tables)
		
	def table_created(self, result, table):
		log.msg( 'created '+table)
		return { 'created': True, 'table_name': table }

	def table_present(self, result, table):
		log.msg( 'table "%s" already here' % table)
		return { 'created': False, 'table_name': table }
	
	def get_avatar(self, jid, handler):
		self.db.runQuery('select file, hash, jid from avatars where jid = "%s"'%(adbapi.safe(jid),)).addCallback(self.got_avatar, handler)

	
	def got_avatar(self, result, handler):
		for x in result:
			handler(x[0], x[1], x[2])

	def set_avatar(self, jid, avatar): #avatar = (file,hash)
		log.msg('ukladam ' + jid)
		self.db.runQuery('select jid from avatars where jid = "%s"'%(adbapi.safe(jid),)).addCallback(self._has_avatar, jid, avatar)

	
	def _has_avatar(self, result, jid, avatar):
		if len(result)==0:
			self.db.runOperation('insert into avatars (jid, file, hash) values("%s","%s","%s")'%(adbapi.safe(jid), adbapi.safe(avatar[0]), avatar[1]))
		else:
			self.db.runOperation('update avatars set file="%s", hash="%s" where jid="%s"'%(adbapi.safe(avatar[0]), avatar[1], adbapi.safe(jid)))
	
	def set_caps(self, node, features, identity):
		fstr = ''
		for feature in features:
			fstr += feature+'\n'
		self.db.runOperation('insert into caps2 (node, feature, identity) values ("%s", "%s", "%s" )'%(node, fstr, identity))
	
	def get_caps(self):
		return self.db.runQuery('select * from caps2;').addCallback(self._getCaps)
	
	def _getCaps(self, result):
		out = []
		for radek in result:
			h = radek[0]
			i = radek[2]
			f = radek[1].split()
			for feature in f:
				out.append((h,feature, i))
		return out
	
	def get_status(self):
		return self.db.runQuery('select * from status;')
	
	def get_status_by_id(self,id):
		return self.db.runQuery('select * from status where id = %s'%id)
	
	def del_status(self, id):
		return self.db.runOperation('delete from status where id = %s'%id)

	def set_status(self, show, message):
		#message=message.replace("'","''")
		return self.db.runQuery('insert into status (show, desc,id) values (?, ?,NULL)',(unicode(show), unicode(message)))
	
	def update_status(self,show,message,ID):
		return self.db.runOperation('update status set show=?, desc=? where id=?',(unicode(show), unicode(message), int(ID)))

	def close(self):
		self.db.close()

		
