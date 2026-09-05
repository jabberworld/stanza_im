import re, os
import shutil
from optparse import OptionParser

parser = OptionParser(usage="usage: %prog [options] srcdir destdir")
parser.add_option("-b", "--blacklist", dest="blacklist",
	help="skip files matching a regexp from FILE", metavar="FILE")
parser.add_option("-v", "--verbose", dest="verbose", action="store_true",
	default=False, help="print messages about files being copied")
(options, args) = parser.parse_args()

if len(args) != 2:
	parser.error("Incorrect number of arguments")

(srcdir, destdir) = args

black_re = None
if options.blacklist != None:
	blacklist = []
	f = open(options.blacklist, 'r')
	for l in f.readlines():
		if l.startswith('#'):
			continue
		blacklist.append('(' + l.rstrip() + ')')
	f.close()
	black_re = re.compile('\./(' + '|'.join(blacklist) + ')$')

def mk_filter(regex):
	if not regex:
		def does_not_match(p):
			return True
	else:
		def does_not_match(p):
			return not regex.match(p)
	return does_not_match

passes_blacklist = mk_filter(black_re)

def errwalk(err):
	raise err

os.chdir(srcdir)

for root, dirs, files in os.walk('.', topdown=True, onerror=errwalk):
	destroot = os.path.join(destdir, root)
	if options.verbose:
		print "Creating %s" % destroot
	try:
		os.makedirs(destroot, 0755)
	except OSError, e:
		# only "file exists" is ok
		if e.errno != 17:
			raise e

	# prevent descending into blacklisted dirs
	fullpaths = [os.path.join(root,d) for d in dirs]
	fullpaths = filter(passes_blacklist, fullpaths)
	del dirs[:]    # dirs must be edited in-place
	dirs.extend([ p[p.rindex('/')+1:] for p in fullpaths ])

	# copy files
	fullpaths = [os.path.join(root,f) for f in files]
	fullpaths = filter(passes_blacklist, fullpaths)
	for f in fullpaths:
		destfile = os.path.join(destroot, f[f.rindex('/')+1:])
		if options.verbose:
			print "Installing %s" % destfile
		shutil.copy2(f, destfile)
		os.chmod(destfile, 0644)
