.PHONY: build

ifndef VTENV_OPTS
VTENV_OPTS = "--no-site-packages"
endif

bin/python:
	virtualenv $(VTENV_OPTS) .
	bin/python setup.py develop

build: bin/python

docs: 
	bin/python setup.py build_sphinx
