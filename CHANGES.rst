``persistent`` Changelog
========================

4.5.1 (unreleased)
------------------

- Add support for Python 3.8a3.

- Update documentation to Python 3.


4.5.0 (2019-05-09)
------------------

- Fully test the C implementation of the PickleCache, and fix
  discrepancies between it and the Python implementation:

  - The C implementation now raises ``ValueError`` instead of
    ``AssertionError`` for certain types of bad inputs.
  - The Python implementation uses the C wording for error messages.
  - The C implementation properly implements ``IPickleCache``; methods
    unique to the Python implementation were moved to
    ``IExtendedPickleCache``.
  - The Python implementation raises ``AttributeError`` if a
    persistent class doesn't have a ``p_jar`` attribute.

  See `issue 102
  <https://github.com/zopefoundation/persistent/issues/102>`_.

- Allow sweeping cache without ``cache_size``. ``cache_size_bytes``
  works with ``cache_size=0``, no need to set ``cache_size`` to a
  large value.

- Require ``CFFI`` on CPython for pure-Python operation. This drops
  support for Jython (which was untested). See `issue 77
  <https://github.com/zopefoundation/persistent/issues/77>`_.

- Fix DeprecationWarning about ``PY_SSIZE_T_CLEAN``.
  See `issue 108 <https://github.com/zopefoundation/persistent/issues/108>`_.

- Drop support for Python 3.4.


4.4.3 (2018-10-22)
------------------

- Fix the repr of the persistent objects to include the module name
  when using the C extension. This matches the pure-Python behaviour
  and the behaviour prior to 4.4.0. See `issue 92
  <https://github.com/zopefoundation/persistent/issues/92>`_.

- Change the repr of persistent objects to format the OID as in
  integer in hexadecimal notation if it is an 8-byte byte string, as
  ZODB does. This eliminates some issues in doctests. See `issue 95
  <https://github.com/zopefoundation/persistent/pull/95>`_.


4.4.2 (2018-08-28)
------------------

- Explicitly use unsigned constants for packing and unpacking C
  timestamps, fixing an arithmetic issue for GCC when optimizations
  are enabled and ``-fwrapv`` is *not* enabled. See `issue 86
  <https://github.com/zopefoundation/persistent/issues/86>`_.


4.4.1 (2018-08-23)
------------------

- Fix installation of source packages on PyPy. See `issue 88
  <https://github.com/zopefoundation/persistent/issues/88>`_.


4.4.0 (2018-08-22)
------------------

- Use unsigned constants when doing arithmetic on C timestamps,
  possibly avoiding some overflow issues with some compilers or
  compiler settings. See `issue 86
  <https://github.com/zopefoundation/persistent/issues/86>`_.

- Change the default representation of ``Persistent`` objects to
  include the representation of their OID and jar, if set. Also add
  the ability for subclasses to implement ``_p_repr()`` instead of
  overriding ``__repr__`` for better exception handling. See `issue 11
  <https://github.com/zopefoundation/persistent/issues/11>`_.

- Reach and maintain 100% test coverage.

- Simplify ``__init__.py``, including removal of an attempted legacy
  import of ``persistent.TimeStamp``. See `PR 80
  <https://github.com/zopefoundation/persistent/pull/80>`_.

- Add support for Python 3.7 and drop support for Python 3.3.

- Build the CFFI modules (used on PyPy or when PURE_PYTHON is set) `at
  installation or wheel building time
  <https://cffi.readthedocs.io/en/latest/cdef.html#ffibuilder-set-source-preparing-out-of-line-modules>`_
  when CFFI is available. This replaces `the deprecated way
  <https://cffi.readthedocs.io/en/latest/overview.html#abi-versus-api>`_
  of building them at import time. If binary wheels are distributed,
  it eliminates the need to have a functioning C compiler to use PyPy.
  See `issue 75
  <https://github.com/zopefoundation/persistent/issues/75>`_.

- Fix deleting the ``_p_oid`` of a pure-Python persistent object when
  it is in a cache.

- Fix deleting special (``_p``) attributes of a pure-Python persistent
  object that overrides ``__delattr__`` and correctly calls ``_p_delattr``.

- Remove some internal compatibility shims that are no longer
  necessary. See `PR 82 <https://github.com/zopefoundation/persistent/pull/82>`_.

- Make the return value of ``TimeStamp.second()`` consistent across C
  and Python implementations when the ``TimeStamp`` was created from 6
  arguments with floating point seconds. Also make it match across
  trips through ``TimeStamp.raw()``. Previously, the C version could
  initially have erroneous rounding and too much false precision,
  while the Python version could have too much precision. The raw/repr
  values have not changed. See `issue 41
  <https://github.com/zopefoundation/persistent/issues/41>`_.


4.3.0 (2018-07-30)
------------------

- Fix the possibility of a rare crash in the C extension when
  deallocating items. See https://github.com/zopefoundation/persistent/issues/66

- Change cPickleCache's comparison of object sizes to determine
  whether an object can go in the cache to use ``PyObject_TypeCheck()``.
  This matches what the pure Python implementation does and is a
  stronger test that the object really is compatible with the cache.
  Previously, an object could potentially include ``cPersistent_HEAD``
  and *not* set ``tp_base`` to ``cPersistenceCAPI->pertype`` and still
  be eligible for the pickle cache; that is no longer the case. See
  `issue 69 <https://github.com/zopefoundation/persistent/issues/69>`_.


4.2.4.2 (2017-04-23)
--------------------

- Packaging-only release: fix Python 2.7 ``manylinux`` wheels.


4.2.4.1 (2017-04-21)
--------------------

- Packaging-only release:  get ``manylinux`` wheel built automatically.


4.2.4 (2017-03-20)
------------------

- Avoid raising a ``SystemError: error return without exception set``
  when loading an object with slots whose jar generates an exception
  (such as a ZODB ``POSKeyError``) in ``setstate``.


4.2.3 (2017-03-08)
------------------

- Fix the hashcode of Python ``TimeStamp`` objects on 64-bit Python on
  Windows. See https://github.com/zopefoundation/persistent/pull/55

- Stop calling ``gc.collect`` every time ``PickleCache.incrgc`` is called (every
  transaction boundary) in pure-Python mode (PyPy). This means that
  the reported size of the cache may be wrong (until the next GC), but
  it is much faster. This should not have any observable effects for
  user code.

- Stop clearing the dict and slots of objects added to
  ``PickleCache.new_ghost`` (typically these values are passed to
  ``__new__`` from the pickle data) in pure-Python mode (PyPy). This
  matches the behaviour of the C code.

- Add support for Python 3.6.

- Fix ``__setstate__`` interning when ``state`` parameter is not a built-in dict


4.2.2 (2016-11-29)
------------------

- Drop use of ``ctypes`` for determining maximum integer size, to increase
  pure-Python compatibility. See https://github.com/zopefoundation/persistent/pull/31

- Ensure that ``__slots__`` attributes are cleared when a persistent
  object is ghostified.  (This excluses classes that override
  ``__new__``.  See
  https://github.com/zopefoundation/persistent/wiki/Notes_on_state_new_and_slots
  if you're curious.)


4.2.1 (2016-05-26)
------------------

- Fix the hashcode of C ``TimeStamp`` objects on 64-bit Python 3 on
  Windows.


4.2.0 (2016-05-05)
------------------

- Fixed the Python(/PYPY) implementation ``TimeStamp.timeTime`` method
  to have subsecond precision.

- When testing ``PURE_PYTHON`` environments under ``tox``, avoid poisoning
  the user's global wheel cache.

- Add support for Python 3.5.

- Drop support for Python 2.6 and 3.2.


4.1.1 (2015-06-02)
------------------

- Fix manifest and re-upload to fix stray files included in 4.1.0.


4.1.0 (2015-05-19)
------------------

- Make the Python implementation of ``Persistent`` and ``PickleCache``
  behave more similarly to the C implementation. In particular, the
  Python version can now run the complete ZODB and ZEO test suites.

- Fix the hashcode of the Python ``TimeStamp`` on 32-bit platforms.


4.0.9 (2015-04-08)
------------------

- Make the C and Python ``TimeStamp`` objects behave more alike. The
  Python version now produces the same ``repr`` and ``.raw()`` output as
  the C version, and has the same hashcode. In addition, the Python
  version is now supports ordering and equality like the C version.

- Intern keys of object state in ``__setstate__`` to reduce memory usage
  when unpickling multiple objects with the same attributes.

- Add support for PyPy3.

- 100% branch coverage.


4.0.8 (2014-03-20)
------------------

- Add support for Python 3.4.

- In pure-Python ``Persistent``, avoid loading state in ``_p_activate``
  for non-ghost objects (which could corrupt their state).  (PR #9)

- In pure-Python, and don't throw ``POSKeyError`` if ``_p_activate`` is
  called on an object that has never been committed.  (PR #9)

- In pure-Python ``Persistent``, avoid calling a subclass's ``__setattr__``
  at instance creation time. (PR #8)

- Make it possible to delete ``_p_jar`` / ``_p_oid`` of a pure-Python
  ``Persistent`` object which has been removed from the jar's cache
  (fixes aborting a ZODB Connection that has added objects). (PR #7)


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
