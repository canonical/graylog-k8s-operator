#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import logging
import random
import string

from oci_image import OCIImageResource, OCIImageResourceError
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, BlockedStatus
from ops.framework import StoredState

logger = logging.getLogger(__name__)


class GraylogCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        # initialize image resource
        self.image = OCIImageResource(self, 'graylog-image')

        # event observations
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(
            self.on['elasticsearch'].relation_changed,
            self._on_elasticsearch_relation_changed
        )
        self.framework.observe(
            self.on['elasticsearch'].relation_broken,
            self._on_elasticsearch_relation_broken
        )
        self.framework.observe(
            self.on["mongodb"].relation_changed, self._on_mongodb_relation_changed
        )
        self.framework.observe(
            self.on["mongodb"].relation_broken, self._on_mongodb_relation_broken
        )
        # initialized stored variables
        self._stored.set_default(elasticsearch_uri=str())  # connection str for elasticsearch
        self._stored.set_default(mongodb_uri=str())  # connection info for mongodb
        self._stored.set_default(password_secret=str())

    @property
    def bind_address(self):
        """Bind address used for http_bind_address config option"""
        port = self.model.config['port']
        return '0.0.0.0:{}'.format(port)

    def external_uri(self, event):
        """Public URI used in http_publish_uri and http_external_uri config options"""
        try:
            ingress = str(self.model.get_binding('graylog').network.ingress_address)
            port = self.model.config['port']
            return 'http://{}:{}/'.format(ingress, port)
        except TypeError:
            event.defer()
            return "http://"

    @property
    def has_elasticsearch(self):
        if self._stored.elasticsearch_uri:
            return True
        else:
            return False

    @property
    def has_mongodb(self):
        if self._stored.mongodb_uri:
            return True
        else:
            return False

    def _on_config_changed(self, event):
        self._configure_pod(event)

    def _on_update_status(self, event):
        self._configure_pod(event)

    def _on_stop(self, _):
        self.unit.status = MaintenanceStatus('Pod is terminating.')

    def _on_elasticsearch_relation_changed(self, event):
        """Get the relation data from the relation and save to stored variable."""
        # skip if unit is not leader
        if not self.unit.is_leader():
            return

        data = event.relation.data[event.unit]
        ingress_address = data.get('ingress-address')
        port = data.get('port')
        if ingress_address is None or port is None:
            logger.warning('No port or ingress-address in Elasticsearch relation data')
            return

        # if we have the data we need, get the information
        self._stored.elasticsearch_uri = 'http://{}:{}'.format(
            ingress_address,
            port,
        )

        # configure the pod spec
        self._configure_pod(event)

    def _on_elasticsearch_relation_broken(self, event):
        """If the relation no longer exists, reconfigure pod after removing the es URI"""
        logger.warning('Removing elasticsearch_uri from _stored')
        self._stored.elasticsearch_uri = str()
        self._configure_pod(event)

    def _on_mongodb_relation_changed(self, event):
        """Get the relation data from the relation and save to stored variable."""
        # skip if unit is not leader
        if not self.unit.is_leader():
            return

        data = event.relation.data[event.unit]
        mongodb_uri = data.get("replica_set_uri")
        mongodb_rs_name = data.get('replica_set_name')
        if mongodb_uri is None or mongodb_rs_name is None:
            logger.warning("No replica_set_uri or replica_set_name in MongoDB relation data")
            return
        # if we have the data we need, get the information
        self._stored.mongodb_uri = '{}graylog?replicaSet={}'.format(mongodb_uri, mongodb_rs_name)

        # configure the pod spec
        self._configure_pod(event)

    def _on_mongodb_relation_broken(self, event):
        """If the relation no longer exists, reconfigure pod after removing the es URI"""
        logger.warning('Removing mongodb_uri from _stored')
        self._stored.mongodb_uri = str()
        self._configure_pod(event)

    def _password_secret(self, n=96):
        """The secret of size n used to encrypt/salt the Graylog password

        Returns the already existing secret if it exists, otherwise, generate one
        """
        if self._stored.password_secret:
            return self._stored.password_secret

        # TODO: is this how we want to generate random strings?
        # generate a random secret that will be used for the life of this charm
        chars = string.ascii_letters + string.digits
        secret = ''.join(random.choice(chars) for _ in range(n))
        self._stored.password_secret = secret

        return secret

    def _password_hash(self):
        """SHA256 hash of the root password"""
        return hashlib.sha256(self.model.config['admin-password'].encode()).hexdigest()

    def _check_config(self) -> bool:
        """Check the required configuration options

        Returns a boolean indicating whether the check passed or not.
        """
        config = self.model.config

        # check for admin password
        if not config['admin-password']:
            logger.error('Need admin-password config option before setting pod spec.')
            self.unit.status = BlockedStatus("Need 'admin-password' config option.")
            return False

        return True

    def _build_pod_spec(self, event):
        config = self.model.config

        # fetch OCI image resource
        try:
            image_info = self.image.fetch()
        except OCIImageResourceError:
            logging.exception('An error occurred while fetching the image info')
            self.unit.status = BlockedStatus('Error fetching image information')
            return {}

        # baseline pod spec
        spec = {
            'version': 3,
            'containers': [{
                'name': self.app.name,  # self.app.name is defined in metadata.yaml
                'imageDetails': image_info,
                'ports': [{
                    'containerPort': config['port'],
                    'protocol': 'TCP'
                }],
                'envConfig': {
                    'GRAYLOG_IS_MASTER': True,
                    'GRAYLOG_PASSWORD_SECRET': self._password_secret(),
                    'GRAYLOG_ROOT_PASSWORD_SHA2': self._password_hash(),
                    'GRAYLOG_HTTP_BIND_ADDRESS': self.bind_address,
                    'GRAYLOG_HTTP_PUBLISH_URI': self.external_uri(event),
                    'GRAYLOG_HTTP_EXTERNAL_URI': self.external_uri(event),
                    'GRAYLOG_ELASTICSEARCH_HOSTS': self._stored.elasticsearch_uri,
                    'GRAYLOG_ELASTICSEARCH_DISCOVERY_ENABLED': True,
                    'GRAYLOG_MONGODB_URI': self._stored.mongodb_uri,
                },
                'kubernetes': {
                    'livenessProbe': {
                        'httpGet': {
                            'path': '/api/system/lbstatus',
                            'port': config['port'],
                        },
                        'initialDelaySeconds': 60,
                        'timeoutSeconds': 5,
                    },
                    'readinessProbe': {
                        'httpGet': {
                            'path': '/api/system/lbstatus',
                            'port': config['port'],
                        },
                        'initialDelaySeconds': 60,
                        'timeoutSeconds': 5,
                    }
                }
            }]
        }

        return spec

    def _configure_pod(self, event):
        """Configure the K8s pod spec for Graylog."""

        if not self.unit.is_leader():
            self.unit.status = ActiveStatus()
            return

        if not self._check_config():
            return

        # make sure we have a valid mongo and elasticsearch relation
        if not self.has_mongodb or not self.has_elasticsearch:
            logger.warning('Need both mongodb and Elasticsearch relation for '
                           'Graylog to function properly. Blocking.')
            self.unit.status = BlockedStatus('Need mongodb and Elasticsearch relations.')
            return

        spec = self._build_pod_spec(event)
        if not spec:
            return
        self.model.pod.set_spec(spec)
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(GraylogCharm)
