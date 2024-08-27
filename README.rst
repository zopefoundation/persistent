===========================================================
 ``persistent``:  automatic persistence for Python objects
===========================================================

.. image:: https://github.com/zopefoundation/persistent/actions/workflows/tests.yml/badge.svg
        :target: https://github.com/zopefoundation/persistent/actions/workflows/tests.yml

.. image:: https://coveralls.io/repos/github/zopefoundation/persistent/badge.svg?branch=master
        :target: https://coveralls.io/github/zopefoundation/persistent?branch=master

.. image:: https://readthedocs.org/projects/persistent/badge/?version=latest
        :target: https://persistent.readthedocs.io/en/latest/
        :alt: Documentation Status

.. image:: https://img.shields.io/pypi/v/persistent.svg
        :target: https://pypi.org/project/persistent/
        :alt: Latest release

.. image:: https://img.shields.io/pypi/pyversions/persistent.svg
        :target: https://pypi.org/project/persistent/
        :alt: Python versions

This package contains a generic persistence implementation for Python. It
forms the core protocol for making objects interact "transparently" with
a database such as the ZODB.

Please see the Sphinx documentation (``docs/index.rst``) for further
information, or view the documentation at Read The Docs, for either
the latest (``https://persistent.readthedocs.io/en/latest/``) or stable
release (``https://persistent.readthedocs.io/en/stable/``).

.. note::

   Use of this standalone ``persistent`` release is not recommended or
   supported with ZODB < 3.11.  ZODB 3.10 and earlier bundle their own
   version of  the ``persistent`` package.
