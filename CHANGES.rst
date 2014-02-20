``persistent`` Changelog
========================


4.0.7 (2014-02-20)
------------------

- Avoid a KeyError from ``_p_accessed()`` on newly-created objects under
  pure-Python:  these objects may be assigned to a jar, but not yet added
  to its cache.  (PR #6)

- Avoid a failure in ``Persistent.__setstate__`` when the state dict
  contains exactly two keys.  (PR #5)

- Fix a hang in ``picklecache`` invalidation if OIDs are manually passed
  out-of-order. (PR #4)

- Add ``PURE_PYTHON`` environment variable support:  if set, the C
  extensions will not be built, imported, or tested.


4.0.6 (2013-01-03)
------------------

- Updated Trove classifiers.


4.0.5 (2012-12-14)
------------------

- Fixed the C-extensions under Py3k (previously they compiled but were
  not importable).


4.0.4 (2012-12-11)
------------------

- Added support for Python 3.3.

- C extenstions now build under Python 3.2, passing the same tests as
  the pure-Python reference implementation.

4.0.3 (2012-11-19)
------------------

- Fixed: In the C implimentation, an integer was compared with a
  pointer, with undefined results and a compiler warning.

- Fixed: the Python implementation of the ``_p_estimated_size`` propety
  didn't support deletion.

- Simplified implementation of the ``_p_estimated_size`` property to
  only accept integers.  A TypeError is raised if an incorrect type is
  provided.


4.0.2 (2012-08-27)
------------------

- Correct initialization functions in renamed ``_timestamp`` extension.


4.0.1 (2012-08-26)
------------------

- Worked around test failure due to overflow to long on 32-bit systems.

- Renamed ``TimeStamp`` extension module to avoid clash with pure-Python
  ``timestamp`` module on case-insensitive filesystems.

  N.B:  the canonical way to import the ``TimeStamp`` class is now::

    from persistent.timestamp import TimeStamp

  which will yield the class from the extension module (if available),
  falling back to the pure-Python reference implementation.


4.0.0 (2012-08-11)
------------------

Platform Changes
################

- Added explicit support for Python 3.2 and PyPy.

  - Note that the C implementations of Persistent, PickleCache, and Timestamp
    are not built (yet) on these platforms.

- Dropped support for Python < 2.6.

Testing Changes
###############

- 100% unit test coverage.

- Removed all ``ZODB``-dependent tests:

  - Rewrote some to avoid the dependency

  - Cloned the remainder into new ``ZODB.tests`` modules.

- Refactored some doctests refactored as unittests.

- Completed pure-Python reference implementations of 'Persistent',
  'PickleCache', and 'TimeStamp'.

- All covered platforms tested under ``tox``.

- Added support for continuous integration using ``tox`` and ``jenkins``.

- Added ``setup.py dev`` alias (installs ``nose`` and ``coverage``).

- Dropped dependency on ``zope.testing`` / ``zope.testrunner``:  tests now
  run with ``setup.py test``.

Documentation Changes
#####################

- Refactored many Doctests as Sphinx documentation (snippets are exercised
  via 'tox').

- Added ``setup.py docs`` alias (installs ``Sphinx`` and
  ``repoze.sphinx.autointerface``).
