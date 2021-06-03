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

        self._stored.set_default("pebble_ready", False)

        # event observations
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pebble_ready, self._on_pebble_ready)
        # self.framework.observe(self.on.stop, self._on_stop)

        self.framework.observer(
            self.on["graylog-peers"].relation_joined, self._on_peer_relation_joined
        )

        self.provider = GraylogProvider(self, "graylog", "graylog", "3.3.8")

        self.mongodb_lib = MongoDbConsumer(self, "mongodb")
        self.framework.observe(
            self.mongodb_lib.on["available"], self._requirement_ready
        )

        self.elastic_lib = ElasticSearchConsumer(self, "elasticsearch", ">=5.0 <7")
        self.framework.observe(
            self.elastic_lib.on["available"], self._requirement_ready
        )

        # self.model.get_binding(PEER).network.ingress_address,

    @property
    def port(self):
        return str(9000)
        # return self.config.get("port", 9000)

    @property
    def is_primary(self):
        return (
            self.model.get_relation("graylog-peers")
            .data[self.app]
            .get("graylog-primary", "")
            == self.unit.name
        )

    def _on_config_changed(self, event):
        self._update_peers()
        self.provider.set_port(self.port)
        self._configure_pod()

    def _on_pebble_ready(self, event):
        self._stored.pebble_ready = True
        self._configure_pod()

    def _on_stop(self, _):
        self.unit.status = MaintenanceStatus("Pod is terminating.")

    def _requirement_ready(self, event):
        self._configure_pod()

    def _update_peers(self):
        if self.unit.is_leader():
            peers_data = self.model.get_relation("graylog-peers").data[self.app]
            if not peers_data["graylog_primary"]:
                peers_data["graylog_primary"] = self.unit.name

            if not peers_data["password_secret"]:
                peers_data["password_secret"] = self._generate_secret()

            if not peers_data["admin_password"]:
                peers_data["admin_password"] = self._generate_password()

    def _on_peer_relation_joined(self, event):
        event.relation.data[self.unit].private_address = str(
            self.model.get_binding(event.relation).network.ingress_address
        )

    def _get_cluster_info(self):
        relation = self.framework.model.get_relation("graylog-peers")
        addrs = []
        for unit in relation.units:
            if relation.data[unit].private_address:
                addrs.append(
                    "http://{}:{}/".format(
                        relation.data[unit].private_address, self.port
                    )
                )

        return addrs

    def _generate_secret(self, n=96):
        """The secret of size n used to encrypt/salt the Graylog password

        Returns the already existing secret if it exists, otherwise, generate one
        """
        # TODO: is this how we want to generate random strings?
        # generate a random secret that will be used for the life of this charm
        chars = string.ascii_letters + string.digits
        secret = "".join(random.choice(chars) for _ in range(n))

        return secret

    def _generate_password(self):
        return "strong_password"

    def _hash_password(self, password):
        """SHA256 hash of the root password"""
        return hashlib.sha256(password).hexdigest()

    def _build_pebble_layer(self):
        elastic_addrs = self.elastic.get_cluster_info()
        mongodb_addrs = self.mongodb.get_cluster_info()
        peers_data = self.model.get_relation("graylog-peers").data[self.app]

        layer = {
            "summary": "Graylog Layer",
            "description": "Pebble layer configuration for Graylog",
            "services": {
                "graylog": {
                    "override": "replace",
                    "summary": "graylog service",
                    "command": "graylog",
                    "startup": "enabled",
                    "environment": {
                        "GRAYLOG_IS_MASTER": self.is_primary,
                        "GRAYLOG_PASSWORD_SECRET": peers_data["password_secret"],
                        "GRAYLOG_ROOT_PASSWORD_SHA2": self._hash_password(
                            peers_data["admin_password"]
                        ),
                        "GRAYLOG_HTTP_BIND_ADDRESS": "0.0.0.0:{}".format(self.port),
                        "GRAYLOG_ELASTICSEARCH_HOSTS": elastic_addrs,
                        "GRAYLOG_ELASTICSEARCH_DISCOVERY_ENABLED": True,
                        "GRAYLOG_MONGODB_URI": mongodb_addrs,
                    },
                },
            },
        }

        return layer

    def _configure_pod(self):
        """Configure the Pebble layer for Graylog."""

        if not self.mongodb.is_valid():
            logger.warning(
                "Need both MongoDB and Elasticsearch relation for "
                "Graylog to function properly. Blocking."
            )
            self.unit.status = BlockedStatus("Missing MongoDB relation")
            return False

        if not self.elastic.is_valid():
            logger.warning(
                "Need both MongoDB and Elasticsearch relation for "
                "Graylog to function properly. Blocking."
            )
            self.unit.status = BlockedStatus("Missing ElasticSearch relation")
            return False

        if not self._stored.pebble_ready:
            self.unit.status = MaintenanceStatus("Waiting for Pod startup to complete")
            return False

        layer = self._build_pebble_layer()
        if not layer.services.graylog.environment.GRAYLOG_PASSWORD_SECRET:
            self.unit.status = MaintenanceStatus("Awaiting leader node to set password")
            return False

        if not layer.service.graylog.environment.GRAYLOG_ELASTICSEARCH_HOSTS:
            self.unit.status = MaintenanceStatus("Related ElasticSearch not yet ready.")
            return False

        if not layer.service.graylog.environment.GRAYLOG_MONGODB_URI:
            self.unit.status = MaintenanceStatus("Related MongoDb not yet ready.")
            return False

        self.container.add_layer("graylog", layer, combine=True)
        self.container.autostart()
        self.provider.ready()
        self.unit.status = ActiveStatus()
        return True


if __name__ == "__main__":
    main(GraylogCharm)
