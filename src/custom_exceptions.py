#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

"""
This module has custom exceptions for garylog-operator
Perhaps in the future we can generalise these exceptions to other charms.

Exception: IngressAddressUnavailableError
"""


class IngressAddressUnavailableError(Exception):
    """Exception raised when Ingress Adreess is not yet availability"""
    def __init__(self, message="Ingress address unavailable"):
        self.message = message
        super().__init__(self.message)
