# Hierarchy under which Jabbim can expect to be installed.
# Can be changed on the command line, eg.:
#   make PREFIX=/usr
PREFIX = /usr/local

# But you'd better leave these alone
bindir = $(PREFIX)/bin
datadir = $(PREFIX)/share
jabbimdata = $(datadir)/jabbim

# Builds generated files
build: qm ui_py jabbim .configured-prefix

ts_files := $(shell find . -name '*.ts')
qm_files := $(ts_files:.ts=.qm)
qm: $(qm_files)

ui_files := $(shell find . -name '*.ui')
ui_py_files := $(ui_files:.ui=_ui.py)
ui_py: $(ui_py_files)

.configured-prefix: jabbim
	echo $(PREFIX) > .configured-prefix

# Fills in the template for the starting script
jabbim: jabbim.in
	sed -e "s|@JABBIMDATA@|$(jabbimdata)|g" $< > $@

%.qm: %.ts
	lrelease-qt4 -compress $< -qm $@

%_ui.py: %.ui
	pyuic4 -o $@ $<

# Installs Jabbim into the system.
# DESTDIR is mainly useful for packagers.
# This variable can be overridden on the command line, eg.:
#    make install DESTDIR=/var/tmp/buildroot
DESTDIR =

configured_prefix = $(shell cat .configured-prefix)
inst_bindir = $(DESTDIR)$(configured_prefix)/bin
inst_datadir = $(DESTDIR)$(configured_prefix)/share
inst_jabbimdata = $(inst_datadir)/jabbim
.PHONY: install
install: build
	@echo "configured prefix is $(configured_prefix)"
	@[ -n "$(DESTDIR)" ] && echo "DESTDIR is $(DESTDIR)" ||:
	@echo "installation bindir is $(inst_bindir)"
	@echo "installation datadir is $(inst_datadir)"
	@echo "installation jabbimdata is $(inst_jabbimdata)"
	python install-files.py -v -b installation-blacklist . "$(inst_jabbimdata)"
	@#cp -dR --preserve=mode,timestamps,context,links . "$(DESTDIR)$(inst_jabbimdata)"
	install -D -p -m 755 jabbim "$(inst_bindir)/jabbim"
	install -D -p -m 644 jabbim.desktop "$(inst_datadir)/applications/jabbim.desktop"
	for i in 16 22 32 48 ; do \
		d="$(inst_datadir)/icons/hicolor/$${i}x$${i}/apps" ;\
		install -D -m 644 -p images/$${i}x$${i}/apps/jabbim.png "$$d/jabbim.png" ;\
	done
	d="$(inst_datadir)/icons/hicolor/scalable/apps" ;\
	install -D -m 644 -p images/scalable/apps/jabbim.svg "$$d/jabbim.svg"
	install -dm 755 $(inst_datadir)/pixmaps
	pushd $(inst_datadir)/pixmaps ;\
	ln -sf ../icons/hicolor/48x48/apps/jabbim.png . ;\
	ln -sf ../icons/hicolor/scalable/apps/jabbim.svg . ;\
	popd
	@echo Jabbim has been installed.


# Removes generated files
.PHONY: clean
clean:
	find . \( -name '*.py[co]' -o -name '*.qm' -o -name '*_ui.py' \) -print0 | xargs -0 --no-run-if-empty rm
	rm -f jabbim .configured-prefix
