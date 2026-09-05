# Test of RatingAssigner.
# We'll probably want to call the 'reward' method either:
#  - on sending a message to a contact, or
#  - on initiating a conversation with a contact.
import weakref

class User:
	def __init__(self, jid):
		self.jid = jid
		self.rating = 0.0
		self.messages = 0

# Before trying to understand this algorithm, make yourself familiar with
# OldRatingAssigner first. They really produce equivalent results.
# While the values of 'rating' are not the same at all times for the two algorithms,
# the sorting order is - and that's what's important.
class RatingAssigner:
	# For aging of the ratings. Must be: 0 < q < 1. Usually close to 1.
	QUOTIENT = 0.999999

	# To prevent unlimited exponential growth of rating values, they must
	# be all scaled back (renormalized) into reasonable magnitudes once in
	# a while.
	RENORMALIZE_THRESH = 10.0

	def __init__(self,main):
		self.users = {}
		self.last_reward = 1.0
		self.counter=0
		self.main=weakref.proxy(main)
		self.changed=[]

	def reward(self, jid):
		# we have to create new user because reward can be called for user which
		# is not in roster, so he is not created by default.
		if not self.users.has_key(jid):
			self.users[jid]=User(jid)
		self.last_reward /= self.QUOTIENT
		self.users[jid].rating = self.users[jid].rating / self.QUOTIENT + self.last_reward
		self.users[jid].messages+=1
		self.counter+=1
		self.main.ui.roster.repaint()
		if self.counter>10:
			self.counter=0
			for j in self.changed:
				self.main.client.sendUserRating(j)
			self.changed=[]
		else:
			if jid not in self.changed:
				self.changed.append(jid)

		if self.last_reward > self.RENORMALIZE_THRESH:
			self.renormalize()

	def renormalize(self):
		for k in self.users.keys():
			self.users[k].rating /= self.last_reward
		self.main.client.sendUserRating()
		self.changed=[]
		self.last_reward = 1.0

# This algorithm produces equivalent results, but it is inefficient as it
# recalculates _everyone_'s rating every time.
# However, the algorithms' principle (additive reviving and exponential aging)
# is more obviously visible here.
class OldRatingAssigner(RatingAssigner):
	def __init__(self, users):
		RatingAssigner.__init__(self, users)

	def reward(self, jid):
		for k in self.users.keys():
			if k == jid:
				self.users[k].rating += 1.0
			else:
				self.users[k].rating *= self.QUOTIENT


if __name__ == "__main__":
	# Let's test how the two RatingAssigners work.
	# They must always produce the same ordering of users.

	import sys
	import operator

	users_1 = {}
	users_2 = {}
	for i in xrange(9):
		jid = 'user%d@jabbim.cz' % (i+1)
		users_1[jid] = User(jid)
		users_2[jid] = User(jid)

	ra1 = RatingAssigner(users_1)
	ra2 = OldRatingAssigner(users_2)

	while True:
		print 'Zadej cislo uzivatele: '
		line = sys.stdin.readline()
		if line.strip() == '':
			break
		try:
			v = int(line)
			jid = 'user%d@jabbim.cz' % v
			ra1.reward(jid)
			ra2.reward(jid)
		except:
			continue

		# verify the algorithms give equivalent results
		sorted_1 = sorted(users_1.values(), key=operator.attrgetter('rating'), reverse=True)
		sorted_2 = sorted(users_2.values(), key=operator.attrgetter('rating'), reverse=True)
		jids_1 = [u.jid for u in sorted_1 ]
		jids_2 = [u.jid for u in sorted_2 ]
		if jids_1 != jids_2:
			print "ERROR: sort orders do not match"
			sys.exit(1)

		print "%15s |%11s |%11s |%9s" % ('JID','Rating','R.algor.#2','ratio')
		for jid in jids_1:
			try:
				ratio = users_1[jid].rating / users_2[jid].rating
				ratio = "%9.6f" % ratio
			except:
				ratio = "%9s" % 'N/A'
			print "%15s |%11.6f |%11.6f |%s" % (jid, users_1[jid].rating, users_2[jid].rating, ratio)

