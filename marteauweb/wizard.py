import os
import sys
import argparse

files_ = []


YML = '.marteau.yml', """\
name: %(name)s
wdir: loadtest
script: stress.py
test: StressTest.test_example
nodes: 4
cycles: '10:20:30'
duration: 60
"""

files_.append(YML)

Makefile = 'loadtest/Makefile',"""\
.PHONY: build test bench

# build virtualenv
build:
    virtualenv --no-site-packages .
    bin/pip install funkload

# run a single test, for sanity-checking
test:
    bin/fl-run-test stress.py

# run bench
bench:
    bin/fl-run-bench stress.py StressTest.test_simple

""".replace("    ", "\t")

files_.append(Makefile)

StressTest_conf = 'loadtest/StressTest.conf',"""\
[main]
title=%(name)s test
description=%(name)s Marteau test
url=%(url)s

[ftest]
log_to = console file
log_path = loadtest.log
result_path = loadtest.xml
ok_codes = 200
sleep_time_min = 0
sleep_time_max = 0

[bench]
cycles = 10:20:30
duration = 60
startup_delay = 0.05
sleep_time = 0.01
cycle_time = 0

log_to = file
log_path = loadtest.log
result_path = loadtest.xml
sleep_time_min = 0
sleep_time_max = 0.1
"""

files_.append(StressTest_conf)

stress_py = 'loadtest/stress.py', """\
import json
import random
from funkload.FunkLoadTestCase import FunkLoadTestCase
from funkload.utils import Data


class StressTest(FunkLoadTestCase):

    def setUp(self):
        self.server_url = self.conf_get("main", "url")
        if not self.server_url.endswith("/"):
            self.server_url += "/"

    def test_simple(self):
        self.setOkCodes([200])
        response = self.get(self.server_url + "/")
        self.assertTrue(response.body != '')

"""

files_.append(stress_py)


def main():
    parser = argparse.ArgumentParser(description='Generates a Marteau loadtest.')
    parser.add_argument('name', help='Name of the load test')
    parser.add_argument('url', help='Root url of the server to be tested.')
    args = parser.parse_args()

    args = {'name': args.name,
            'url': args.url}

    for path, content in files_:
        if os.path.exists(path):
            raise IOError('%r already exists' % path)

        dir = os.path.dirname(path)
        if dir != '' and not os.path.exists(dir):
            os.makedirs(os.path.dirname(path))

        print 'Writing %r' % path
        with open(path, 'w') as f:
            f.write(content % args)



if __name__ == '__main__':
    main()
