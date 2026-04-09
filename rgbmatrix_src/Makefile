# The *.cpp files are included in the distribution; this is only needed when
# working on the pyx files.
#
# Please check in modified *.cpp files with distribution to not require cython
# to be installed on the users' machine.
CYTHON ?= cython

all : core.cpp graphics.cpp

core.cpp : core.pyx core.pxd cppinc.pxd
	$(CYTHON) --cplus -o $@ $<

graphics.cpp : graphics.pyx graphics.pxd cppinc.pxd core.pxd
	$(CYTHON) --cplus -o $@ $<

clean:
	rm -rf core.cpp graphics.cpp
