``persistent``:  automatic persistence for Python objects
=========================================================

.. image:: https://travis-ci.org/zopefoundation/persistent.svg?branch=master
        :target: https://travis-ci.org/zopefoundation/persistent

.. image:: https://coveralls.io/repos/github/zopefoundation/persistent/badge.svg?branch=master
        :target: https://coveralls.io/github/zopefoundation/persistent?branch=master

.. image:: https://readthedocs.org/projects/persistent/badge/?version=latest
        :target: http://persistent.readthedocs.org/en/latest/
        :alt: Documentation Status

.. image:: https://img.shields.io/pypi/v/persistent.svg
        :target: https://pypi.org/project/persistent
        :alt: Latest release

.. image:: https://img.shields.io/pypi/pyversions/persistent.svg
        :target: https://pypi.org/project/persistent
        :alt: Python versions

This package contains a generic persistence implementation for Python. It
forms the core protocol for making objects interact "transparently" with
a database such as the ZODB.

Please see the Sphinx documentation (``docs/index.rst``) for further
information, or view the documentation at Read The Docs, for either
the latest (``http://persistent.readthedocs.io/en/latest/``) or stable
release (``http://persistent.readthedocs.io/en/stable/``).

.. note::

   Use of this standalone ``persistent`` release is not recommended or
   supported with ZODB < 3.11.  ZODB 3.10 and earlier bundle their own
   version of  the ``persistent`` package.
