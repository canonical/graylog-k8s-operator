#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import textwrap

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
        # TODO: test whether we can just pass the {ingress-address}:{port} string
        #       from Elasticsearch to Graylog or if we need to send multiple hosts
        #       Hypothesis: just the ingress is fine
        self._stored.set_default(elasticsearch_uri=str)  # connection str for elasticsearch

    @property
    def has_elasticsearch(self):
        if self._stored.elasticsearch_uri:
            return True
        else:
            return False

    def _on_config_changed(self, _):
        self._configure_pod()

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
        self._configure_pod()

    def _on_elasticsearch_relation_broken(self, _):
        """If the relation no longer exists, reconfigure pod after removing the es URI"""
        self._stored.elasticsearch_uri = str()
        self._configure_pod()

    def _on_mongodb_relation_changed(self, event):
        """Get the relation data from the relation and save to stored variable."""
        # skip if unit is not leader
        if not self.unit.is_leader():
            return

        data = event.relation.data[event.unit]
        mongodb_uri = data.get("standalone_uri")
        port = data.get("port")
        if mongodb_uri is None or port is None:
            logger.warning("No port or mongodb_uri in MondoDB relation data")
            return

        # if we have the data we need, get the information
        self._stored.mongodb_uri = "{}:{}".format(mongodb_uri, port,)

        # configure the pod spec
        self._configure_pod()

    def _on_mongodb_relation_broken(self, _):
        """If the relation no longer exists, reconfigure pod after removing the es URI"""
        self._stored.mongodb_uri = str()
        self._configure_pod()

    def _build_pod_spec(self):
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
                'volumeConfig': [{
                    'name': 'config',
                    'mountPath': '/etc/graylog/server',
                    'files': [{
                        'path': 'server.conf',
                        'content': textwrap.dedent("""\
                            is_master = true
                            password_secret = {}
                            elasticsearch_hosts = {}
                            """.format(
                                config['admin-password'],
                                self._stored.elasticsearch_uri,
                        ))
                    }],
                }],
            }]
        }

        return spec

    def _configure_pod(self):
        """Configure the K8s pod spec for Graylog."""
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus()
            return

        spec = self._build_pod_spec()
        if not spec:
            return
        self.model.pod.set_spec(spec)
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(GraylogCharm)
