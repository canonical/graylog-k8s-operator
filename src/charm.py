#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import logging
import random
import string

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, BlockedStatus
from ops.framework import StoredState

logger = logging.getLogger(__name__)

class GraylogCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.container = self.unit.get_container("graylog")

        # event observations
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.stop, self._on_stop)

        self.framework.observer(
            self.on["graylog-peers"].relation_joined, self._on_peer_relation_joined
        )

        self.provider = GraylogProvider(self, "graylog", "graylog", "3.2")

        self.mongodb = MongoDbProvider(self, "mongodb")
        self.framework.observe(self.mongodb.on["ready"], self._requirement_ready)

        self.elastic = ElasticSearchProvider(self, "elasticsearch", ">=5.0 <7")
        self.framework.observe(self.elastic.on["ready"], self._requirement_ready)

        #self.model.get_binding(PEER).network.ingress_address,

    def _on_config_changed(self, event):
        self._update_peers()
        self._configure_pod()

    def _on_stop(self, _):
        self.unit.status = MaintenanceStatus('Pod is terminating.')


    def _requirement_ready(self, event):
        self._configure_pod()

    def _update_peers(self):
        peers_data = self.model.get_relation("graylog-peers").data[self.app]
        if self.unit.is_leader():
            if not peers_data["graylog_master"]:
                peers_data["graylog_master"] = self.unit.name

            if not peers_data["password_secret"]:
                peers_data["password_secret"] = self._generate_secret()

            if not peers_data["admin_password"]:
                peers_data["admin_password"] = self._generate_password()

    def _on_peer_relation_joined(self, event):
        event.relation.data[self.unit].private_address = str(
            self.model.get_binding(event.relation).network.ingress_address
        )

    def _generate_secret(self, n=96):
        """The secret of size n used to encrypt/salt the Graylog password

        Returns the already existing secret if it exists, otherwise, generate one
        """
        # TODO: is this how we want to generate random strings?
        # generate a random secret that will be used for the life of this charm
        chars = string.ascii_letters + string.digits
        secret = ''.join(random.choice(chars) for _ in range(n))

        return secret

    def _generate_password(self):
        return "strong_password"

    def _hash_password(self, password):
        """SHA256 hash of the root password"""
        return hashlib.sha256(password).hexdigest()


    def _build_pebble_layer(self):
        elastic_addrs = self.elastic.getClusterInfo()
        mongodb_addrs = self.mongodb.getClusterInfo()
        peers_data = self.model.get_relation("graylog-peers").data[self.app]

        layer = {
            "summary" : "Graylog Layer",
            "description" : "Pebble layer configuration for Graylog",
            "services" : {
                "graylog" : {
                    "override" : "replace",
                    "summary" : "graylog service",
                    "command" : "graylog",
                    "startup" : "enabled",
                    "environment" : {
                        'GRAYLOG_IS_MASTER': True,
                        'GRAYLOG_PASSWORD_SECRET': peers_data["password_secret"],
                        'GRAYLOG_ROOT_PASSWORD_SHA2': self._hash_password(peers_data["admin_password"]),
                        'GRAYLOG_HTTP_BIND_ADDRESS': self.bind_address,
                        'GRAYLOG_HTTP_PUBLISH_URI': self.external_uri,
                        'GRAYLOG_HTTP_EXTERNAL_URI': self.external_uri,
                        'GRAYLOG_ELASTICSEARCH_HOSTS': elastic_addrs,
                        'GRAYLOG_ELASTICSEARCH_DISCOVERY_ENABLED': True,
                        'GRAYLOG_MONGODB_URI': mongodb_addrs,
                    },
                },
            },
        }

        return layer

    def _configure_pod(self):
        """Configure the Pebble layer for Graylog."""

        if not self.mongodb.is_valid():
            logger.warning('Need both MongoDB and Elasticsearch relation for '
                           'Graylog to function properly. Blocking.')
            self.unit.status = BlockedStatus('Missing MongoDB relation')
            return False

        if not self.elastic.is_valid():
            logger.warning('Need both MongoDB and Elasticsearch relation for '
                           'Graylog to function properly. Blocking.')
            self.unit.status = BlockedStatus('Missing ElasticSearch relation')
            return False

        layer = self._build_pebble_layer()
        if not layer.services.graylog.environment.GRAYLOG_PASSWORD_SECRET:
            self.unit.status = MaintenanceStatus("Awaiting leader node to set password")
            return False

        if not layer.service.graylog.environment.GRAYLOG_ELASTICSEARCH_HOSTS:
            self.unit.status = MaintenanceStatus('Related ElasticSearch not yet ready.')
            return False

        if not layer.service.graylog.environment.GRAYLOG_MONGODB_URI:
            self.unit.status = MaintenanceStatus('Related MongoDb not yet ready.')
            return False

        self.container.add_layer("graylog", layer, combine=True)
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(GraylogCharm)
