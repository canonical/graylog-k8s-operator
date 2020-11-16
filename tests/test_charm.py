# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest import mock

from ops.testing import Harness
from charm import GraylogCharm

BASE_CONFIG = {
    'port': 9000,
    'admin-password': 'admin',
}


class TestCharm(unittest.TestCase):
    def setUp(self) -> None:
        # charm setup
        self.harness = Harness(GraylogCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.harness.add_oci_resource('graylog-image')

        # patches
        self.mock_bind_address = \
            mock.patch('charm.GraylogCharm.bind_address', new_callable=mock.PropertyMock)
        self.mock_external_uri = \
            mock.patch('charm.GraylogCharm.external_uri', new_callable=mock.PropertyMock)

        self.mock_bind_address.start()
        self.mock_external_uri.start()

        # cleanup
        self.addCleanup(self.mock_bind_address.stop)
        self.addCleanup(self.mock_external_uri.stop)

    def test_pod_specs(self):
        self.harness.set_leader(True)
        # pretend to have mongo and elasticsearch
        self.harness.charm._stored.mongodb_uri = 'mongo://test_uri/'
        self.harness.charm._stored.elasticsearch_uri = 'http://test_es_uri'

        self.harness.update_config(BASE_CONFIG)
        self.harness.charm.on.config_changed.emit()

        spec, _ = self.harness.get_pod_spec()
        expected_port = 9000
        actual_port = spec['containers'][0]['ports'][0]['containerPort']
        self.assertEqual(expected_port, actual_port)

        expected_spec_version = 3
        actual_spec_version = spec["version"]
        self.assertEqual(actual_spec_version, expected_spec_version)

        expected_rediness_path = "/api/system/lbstatus"
        actual_rediness_path = spec["containers"][0]["kubernetes"]["readinessProbe"][
            "httpGet"]["path"]
        self.assertEqual(actual_rediness_path, expected_rediness_path)

        actual_rediness_port = spec["containers"][0]["kubernetes"]["readinessProbe"][
            "httpGet"]["port"]
        self.assertEqual(actual_rediness_port, expected_port)

    def test_elasticsearch_and_mongodb_conn_strings(self):
        self.harness.set_leader(True)
        self.harness.update_config(BASE_CONFIG)

        # add the elasticsearch relation
        es_rel_id = self.harness.add_relation('elasticsearch', 'elasticsearch')
        mongo_rel_id = self.harness.add_relation('mongodb', 'mongodb')
        self.harness.add_relation_unit(es_rel_id, 'elasticsearch/0')
        self.harness.add_relation_unit(mongo_rel_id, 'mongodb/0')

        # add elasticsearch relation data
        es_rel_data = {
            'ingress-address': '10.183.1.2',
            'port': 9200,
        }
        self.harness.update_relation_data(es_rel_id, 'elasticsearch/0', es_rel_data)
        self.assertTrue(self.harness.charm.has_elasticsearch)

        # add mongodb relation data
        mongo_rel_data = {
            'replica_set_uri': 'mongo://10.0.0.2:14001,10.0.0.3:14002',
            'replicated': 'True',
            'replica_set_name': 'rs0',
        }
        self.harness.update_relation_data(mongo_rel_id, 'mongodb/0', mongo_rel_data)
        self.assertTrue(self.harness.charm.has_mongodb)

        # test that elasticsearch-uri properly made it to the _stored variable
        expected_uri = 'http://10.183.1.2:9200'
        self.assertEqual(expected_uri, self.harness.charm._stored.elasticsearch_uri)

        # now emit the relation broken events and make sure the _stored variables are cleared
        es_rel = self.harness.model.get_relation('elasticsearch')
        mongo_rel = self.harness.model.get_relation('mongodb')
        self.harness.charm.on.elasticsearch_relation_broken.emit(es_rel)
        self.harness.charm.on.mongodb_relation_broken.emit(mongo_rel)
        self.assertEqual(str(), self.harness.charm._stored.elasticsearch_uri)
        self.assertEqual(str(), self.harness.charm._stored.mongodb_uri)

    def test_blocking_without_mongodb_and_elasticsearch(self):
        self.harness.set_leader(True)
        with self.assertLogs(level='WARNING') as logger:
            self.harness.update_config(BASE_CONFIG)
            msg = 'WARNING:charm:Need both mongodb and Elasticsearch ' \
                  'relation for Graylog to function properly. Blocking.'
            self.assertEqual(sorted(logger.output), [msg])
