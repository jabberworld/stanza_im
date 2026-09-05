
class Enums(object):


	def __init__(self, main):
		self.main = main
		self.shows={u"online":u"1",
					u"available":u"1",
					u"chat":u"0",
					u"away":u"3",
					u"xa":u"4",
					u"dnd":u"5",
					u"None":u"1",
					u"":u"1",
					u"offline":u"9",
					u"unavailable":u"9"
					}
		#: {ID:icon_text}
		self.icons={u"1":u"online",
					u"0":u"chat",
					u"3":u"away",
					u"4":u"xa",
					u"5":u"dnd",
					u"9":u"offline"
					}
		#: {show:translated_text}
		self.status={"online":self.tr("Online"),
					"available":self.tr("Online"),
					"chat":self.tr("Chatty"),
					"away":self.tr("Away"),
					"xa":self.tr("Extended away"),
					"dnd":self.tr("DND"),
					"None":self.tr("Online"),
					"offline":self.tr("Offline"),
					"invisible":self.tr("Invisible")
					}
		#mood:translation
		self.moods = {
					"none":self.tr("None"),
					"afraid":self.tr("afraid"),
					"amazed":self.tr("amazed"),
					"angry":self.tr("angry"),
					"annoyed":self.tr("annoyed"),
					"anxious":self.tr("anxious"),
					"aroused":self.tr("aroused"),
					"ashamed":self.tr("ashamed"),
					"bored":self.tr("bored"),
					"brave":self.tr("brave"),
					"calm":self.tr("calm"),
					"cold":self.tr("cold"),
					"confused":self.tr("confused"),
					"contented":self.tr("contented"),
					"cranky":self.tr("cranky"),
					"curious":self.tr("curious"),
					"depressed":self.tr("depressed"),
					"disappointed":self.tr("disappointed"),
					"disgusted":self.tr("disgusted"),
					"distracted":self.tr("distracted"),
					"embarrassed":self.tr("embarrassed"),
					"excited":self.tr("excited"),
					"flirtatious":self.tr("flirtatious"),
					"frustrated":self.tr("frustrated"),
					"grumpy":self.tr("grumpy"),
					"guilty":self.tr("guilty"),
					"happy":self.tr("happy"),
					"hot":self.tr("hot"),
					"humbled":self.tr("humbled"),
					"humiliated":self.tr("humiliated"),
					"hungry":self.tr("hungry"),
					"hurt":self.tr("hurt"),
					"impressed":self.tr("impressed"),
					"in_awe":self.tr("in_awe"),
					"in_love":self.tr("in_love"),
					"indignant":self.tr("indignant"),
					"interested":self.tr("interested"),
					"intoxicated":self.tr("intoxicated"),
					"invincible":self.tr("invincible"),
					"jealous":self.tr("jealous"),
					"lonely":self.tr("lonely"),
					"mean":self.tr("mean"),
					"moody":self.tr("moody"),
					"nervous":self.tr("nervous"),
					"neutral":self.tr("neutral"),
					"offended":self.tr("offended"),
					"playful":self.tr("playful"),
					"proud":self.tr("proud"),
					"relieved":self.tr("relieved"),
					"remorseful":self.tr("remorseful"),
					"restless":self.tr("restless"),
					"sad":self.tr("sad"),
					"sarcastic":self.tr("sarcastic"),
					"serious":self.tr("serious"),
					"shocked":self.tr("shocked"),
					"shy":self.tr("shy"),
					"sick":self.tr("sick"),
					"sleepy":self.tr("sleepy"),
					"stressed":self.tr("stressed"),
					"surprised":self.tr("surprised"),
					"thirsty":self.tr("thirsty"),
					"worried":self.tr("worried")
		}
		self.moodActions = {}
		self.activities = {
					"none":self.tr("None"),
					"buying_groceries":self.tr("buying_groceries"),
					"cleaning":self.tr("cleaning"),
					"cooking":self.tr("cooking"),
					"doing_maintenance":self.tr("doing_maintenance"),
					"doing_the_dishes":self.tr("doing_the_dishes"),
					"doing_the_laundry":self.tr("doing_the_laundry"),
					"gardening":self.tr("gardening"),
					"running_an_errand":self.tr("running_an_errand"),
					"walking_the_dog":self.tr("walking_the_dog"),
					"having_a_beer":self.tr("having_a_beer"),
					"having_coffee":self.tr("having_coffee"),
					"having_tea":self.tr("having_tea"),
					"having_a_snack":self.tr("having_a_snack"),
					"having_breakfast":self.tr("having_breakfast"),
					"having_dinner":self.tr("having_dinner"),
					"having_lunch":self.tr("having_lunch"),
					"cycling":self.tr("cycling"),
					"hiking":self.tr("hiking"),
					"jogging":self.tr("jogging"),
					"playing_sports":self.tr("playing_sports"),
					"running":self.tr("running"),
					"skiing":self.tr("skiing"),
					"swimming":self.tr("swimming"),
					"working_out":self.tr("working_out"),
					"at_the_spa":self.tr("at_the_spa"),
					"brushing_teeth":self.tr("brushing_teeth"),
					"getting_a_haircut":self.tr("getting_a_haircut"),
					"shaving":self.tr("shaving"),
					"taking_a_bath":self.tr("taking_a_bath"),
					"taking_a_shower":self.tr("taking_a_shower"),
					"day_off":self.tr("day_off"),
					"hanging_out":self.tr("hanging_out"),
					"on_vacation":self.tr("on_vacation"),
					"scheduled_holiday":self.tr("scheduled_holiday"),
					"sleeping":self.tr("sleeping"),
					"gaming":self.tr("gaming"),
					"going_out":self.tr("going_out"),
					"partying":self.tr("partying"),
					"reading":self.tr("reading"),
					"rehearsing":self.tr("rehearsing"),
					"shopping":self.tr("shopping"),
					"socializing":self.tr("socializing"),
					"sunbathing":self.tr("sunbathing"),
					"watching_tv":self.tr("watching_tv"),
					"watching_a_movie":self.tr("watching_a_movie"),
					"in_real_life":self.tr("in_real_life"),
					"on_the_phone":self.tr("on_the_phone"),
					"on_video_phone":self.tr("on_video_phone"),
					"commuting":self.tr("commuting"),
					"cycling":self.tr("cycling"),
					"driving":self.tr("driving"),
					"in_a_car":self.tr("in_a_car"),
					"on_a_bus":self.tr("on_a_bus"),
					"on_a_plane":self.tr("on_a_plane"),
					"on_a_train":self.tr("on_a_train"),
					"on_a_trip":self.tr("on_a_trip"),
					"walking":self.tr("walking"),
					"coding":self.tr("coding"),
					"in_a_meeting":self.tr("in_a_meeting"),
					"studying":self.tr("studying"),
					"writing":self.tr("writing")}

		self.activityGroups = {"doing_chores":[self.tr("doing_chores"),"buying_groceries","cleaning","cooking","doing_maintenance","doing_the_dishes","doing_the_laundry","gardening","running_an_errand","walking_the_dog"],
					"drinking":[self.tr("drinking"),"having_a_beer","having_coffee","having_tea"],
					"eating":[self.tr("eating"),"having_a_snack","having_breakfast","having_dinner","having_lunch"],
					"exercising":[self.tr("exercising"),"cycling","hiking","jogging","playing_sports","running","skiing","swimming","working_out"],
					"grooming":[self.tr("grooming"),"at_the_spa","brushing_teeth","getting_a_haircut","shaving","taking_a_bath","taking_a_shower"],
					# no substate... we don't allow it<= "having_appointment":self.tr("having_appointment"),
					"inactive":[self.tr("inactive"),"day_off","hanging_out","on_vacation","scheduled_holiday","sleeping"],
					"relaxing":[self.tr("relaxing"),"gaming","going_out","partying","reading","rehearsing","shopping","socializing","sunbathing","watching_tv","watching_a_movie"],
					"talking":[self.tr("talking"),"in_real_life","on_the_phone","on_video_phone"],
					"traveling":[self.tr("traveling"),"commuting","cycling","driving","in_a_car","on_a_bus","on_a_plane","on_a_train","on_a_trip","walking"],
					"working":[self.tr("working"),"coding","in_a_meeting","studying","writing"]}
	def tr(self, string):
		return self.main.tr(string)
	
	def GetShows(self):
		return self.__shows


	def GetIcons(self):
		return self.__icons


	def GetStatus(self):
		return self.__status


	def GetMoods(self):
		return self.__moods


	def GetMoodActions(self):
		return self.__moodActions


	def GetActivities(self):
		return self.__activities


	def GetActivityGroups(self):
		return self.__activityGroups


	def SetShows(self, value):
		self.__shows = value


	def SetIcons(self, value):
		self.__icons = value


	def SetStatus(self, value):
		self.__status = value


	def SetMoods(self, value):
		self.__moods = value


	def SetMoodActions(self, value):
		self.__moodActions = value


	def SetActivities(self, value):
		self.__activities = value


	def SetActivityGroups(self, value):
		self.__activityGroups = value


	def DelShows(self):
		del self.__shows


	def DelIcons(self):
		del self.__icons


	def DelStatus(self):
		del self.__status


	def DelMoods(self):
		del self.__moods


	def DelMoodActions(self):
		del self.__moodActions


	def DelActivities(self):
		del self.__activities


	def DelActivityGroups(self):
		del self.__activityGroups
	shows = property(GetShows, SetShows, DelShows, "shows's docstring")
	icons = property(GetIcons, SetIcons, DelIcons, "icons's docstring")
	status = property(GetStatus, SetStatus, DelStatus, "status's docstring")
	moods = property(GetMoods, SetMoods, DelMoods, "moods's docstring")
	moodActions = property(GetMoodActions, SetMoodActions, DelMoodActions, "moodActions's docstring")
	activities = property(GetActivities, SetActivities, DelActivities, "activities's docstring")
	activityGroups = property(GetActivityGroups, SetActivityGroups, DelActivityGroups, "activityGroups's docstring")