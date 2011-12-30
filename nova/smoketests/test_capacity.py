# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import random
import sys
import time
import tempfile
import shutil
import commands
import re
import math

# If ../nova/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir))
sys.path.insert(0, possible_topdir)

from smoketests import flags
from smoketests import base

FLAGS = flags.FLAGS

TEST_PREFIX = 'test%s' % int(random.random() * 1000000)
TEST_BUCKET = '%s_bucket' % TEST_PREFIX
TEST_KEY = '%s_key' % TEST_PREFIX
TEST_GROUP = '%s_group' % TEST_PREFIX


class CapacityTests(base.UserSmokeTestCase):
    def __estimate_water_mark(self):
        low = 0
        high = 1
        status, meminfo = commands.getstatusoutput('cat /proc/meminfo')

        p = re.compile(r'MemTotal:\s+(\d+)\s+kB\n'
                        'MemFree:\s+(\d+)\s+kB\n'
                        'Buffers:\s+(\d+)\s+kB\n'
                        'Cached:\s+(\d+)\s+kB\n')
        m = re.match(p, meminfo)
        (memtotal, memfree, buffers, cached) = m.groups()
        memtotal = float(memtotal)
        memfree = float(memfree) + float(buffers) + float(cached)
        self.no_capture_write('\n')
        status, flavorinfo = commands.getstatusoutput('sudo -p ' + r'"        [sudo] password for %p: "' +
                                                        (' nova-manage flavor list %s' % FLAGS.test_flavor))
        p = re.compile(r'Memory: (\d+)MB,')
        m = re.search(p, flavorinfo)
        (mem_per_instance, ) = m.groups()
        mem_per_instance = float(mem_per_instance) * 1024

        low = math.pi * memfree/mem_per_instance
        high = math.pi * memtotal/mem_per_instance
        return low, high

    def test_000_setUp(self):
        key = self.create_key_pair(self.conn, TEST_KEY)
        self.data['instance_list'] = []
        self.data['low_water_mark'], self.data['high_water_mark'] = self.__estimate_water_mark()
        capacity = round((self.data['low_water_mark'] + self.data['high_water_mark'])/2)
        plural = capacity != 1 and "s" or ""
        self.no_capture_write(('        Estimated capacity: %s instance%s' % (capacity, plural)).ljust(64))
        self.assertEqual(key.name, TEST_KEY)

    def test_001_can_launch_how_many_instances(self):
        count = 0
        while True:
            if not FLAGS.dryrun:
                reservation = self.conn.run_instances(FLAGS.test_image,
                                                      key_name=TEST_KEY,
                                                      instance_type=FLAGS.test_flavor)
    
                instance = reservation.instances[0]
                self.data['instance_list'].append(instance)
                if not self.wait_for_running(instance):
                    break
                instance.update()
                if not self.wait_for_ping(instance.private_dns_name):
                    break
                if not self.wait_for_ssh(instance.private_dns_name,
                                         TEST_KEY):
                    break
            count += 1
            if count > (2 * self.data['high_water_mark']):
                break
        plural = count != 1 and "s" or ""
        self.no_capture_write(('\n        Launced %s instance%s with flavor %s' % (count, plural, FLAGS.test_flavor)).ljust(65))
        self.assertTrue(True)

    def test_999_tearDown(self):
        self.conn.delete_key_pair(TEST_KEY)
        for instance in self.data['instance_list']:
            self.conn.terminate_instances([instance.id])
