#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import textwrap

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus
from ops.framework import StoredState

logger = logging.getLogger(__name__)
DOCKER_IMAGE = 'graylog/graylog:3.3.8-1'


class GraylogCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.stop, self._on_stop)

    def _on_config_changed(self, _):
        self._configure_pod()

    def _on_stop(self, event):
        self.unit.status = MaintenanceStatus('Pod is terminating')

    def _build_pod_spec(self):
        config = self.model.config
        spec = {
            'version': 3,
            'containers': [{
                'name': self.app.name,  # self.app.name is defined in metadata.yaml
                'imageDetails': {
                    'imagePath': DOCKER_IMAGE
                },
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
                            password_secret = admin
                            """)
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
        self.model.pod.set_spec(spec)
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(GraylogCharm)
