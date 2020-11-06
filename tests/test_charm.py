# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock

from ops.testing import Harness
from charm import GraylogCharm

BASE_CONFIG = {
    'port': 9000
}


class TestCharm(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness(GraylogCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_pod_spec_for_leader(self):
        self.harness.set_leader(True)
        self.harness.update_config(BASE_CONFIG)
        spec = self.harness.charm._build_pod_spec()
        expected_port = 9000
        actual_port = spec['containers'][0]['ports'][0]['containerPort']
        self.assertEqual(expected_port, actual_port)


    def test_pod_spec_for_non_leader(self):
        self.harness.set_leader(False)