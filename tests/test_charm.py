# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock

from ops.testing import Harness
from charm import GraylogCharm


class TestCharm(unittest.TestCase):
    def setUp(self) -> None:
        harness = Harness(GraylogOperatorCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
