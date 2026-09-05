import sys,os
print "###########################"
print "# USE IT ONLY FOR PLUGINS #"
print "###########################"
try:
	if os.path.exists(sys.argv[1]) and sys.argv[2]:
		os.system('/usr/bin/pyuic4 '+sys.argv[1]+' -o '+sys.argv[2])
	else:
		print 'usage:',sys.argv[0]," file.ui file.py"
		exit()
except:
	print 'usage:',sys.argv[0]," file.ui file.py"
	exit()
try:
	f=open(sys.argv[2],'r')
except:
	print "can't open file"
	print 'usage:',sys.argv[0]," file.ui file.py"
	exit()
data=f.read()
f.close()
c=None
for line in data.split('\n'):
	if line.find("self.retranslateUi")!=-1:
		# self.retranslateUi(MainWindow)
		try:
			line=line.split("(")[1]
			c=line[:-1]
			print "class name:",c
		except:
			print "can't find class name"
			exit()
		break
print "replacing QtGui.QApplication.translate to "+c+".translate"
data=data.replace("QtGui.QApplication.translate",c+".translate")
f=open(sys.argv[2],'w')
f.write(data)
f.close()
print "done"