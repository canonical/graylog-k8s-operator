# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
import textwrap

from ops.testing import Harness
from charm import GraylogCharm

BASE_CONFIG = {
    'port': 9000,
    'admin-password': 'admin',
}


class TestCharm(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness(GraylogCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.harness.add_oci_resource('graylog-image')

    def test_pod_spec_port(self):
        self.harness.set_leader(True)
        self.harness.update_config(BASE_CONFIG)
        self.harness.charm.on.config_changed.emit()
        spec, _ = self.harness.get_pod_spec()
        expected_port = 9000
        actual_port = spec['containers'][0]['ports'][0]['containerPort']
        self.assertEqual(expected_port, actual_port)

    def test_elasticsearch_uri(self):
        self.harness.set_leader(True)
        self.harness.update_config(BASE_CONFIG)

        # add the elasticsearch relation
        rel_id = self.harness.add_relation('elasticsearch', 'elasticsearch')
        self.harness.add_relation_unit(rel_id, 'elasticsearch/0')

        # add data to the unit
        rel_data = {
            'ingress-address': '10.183.1.2',
            'port': 9200,
        }
        self.harness.update_relation_data(rel_id, 'elasticsearch/0', rel_data)

        # test that elasticsearch-uri properly made it to the _stored variable
        expected_uri = 'http://10.183.1.2:9200'
        self.assertEqual(expected_uri, self.harness.charm._stored.elasticsearch_uri)

    def test_mounted_server_conf_contents(self):
        self.harness.set_leader(True)
        self.harness.update_config(BASE_CONFIG)

        # add the elasticsearch relation
        # TODO: add mongodb when the relation is added
        es_rel_id = self.harness.add_relation('elasticsearch', 'elasticsearch')
        self.harness.add_relation_unit(es_rel_id, 'elasticsearch/0')

        # add data to the unit
        es_rel_data = {
            'ingress-address': '10.183.9.8',
            'port': 9200,
        }
        self.harness.update_relation_data(es_rel_id, 'elasticsearch/0', es_rel_data)

        # test that the server.conf file contains the correct information
        expected_server_conf = textwrap.dedent("""\
            is_master = true
            password_secret = admin
            elasticsearch_hosts = http://10.183.9.8:9200
            """)
        spec, _ = self.harness.get_pod_spec()
        actual_server_conf = spec['containers'][0]['volumeConfig'][0]['files'][0]['content']
        self.assertEqual(expected_server_conf, actual_server_conf)
