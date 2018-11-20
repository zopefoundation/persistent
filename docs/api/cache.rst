Caching Persistent Objects
==========================

Creating Objects ``de novo``
----------------------------

Creating ghosts from scratch, as opposed to ghostifying a non-ghost
is rather tricky. :class:`~persistent.interfaces.IPeristent` doesn't
really provide the right interface given that:

- :meth:`_p_deactivate` and :meth:`_p_invalidate` are overridable, and
  could assume that the object's state is properly initialized.

- Assigning :attr:`_p_changed` to None just calls :meth:`_p_deactivate`.

- Deleting :attr:`_p_changed` just calls :meth:`_p_invalidate`.

.. note::

   The current cache implementation is intimately tied up with the
   persistence implementation and has internal access to the persistence
   state.  The cache implementation can update the persistence state for
   newly created and uninitialized objects directly.

   The future persistence and cache implementations will be far more
   decoupled. The persistence implementation will only manage object
   state and generate object-usage events.  The cache implementation(s)
   will be responsible for managing persistence-related (meta-)state,
   such as _p_state, _p_changed, _p_oid, etc.  So in that future
   implementation, the cache will be more central to managing object
   persistence information.

Caches have a :meth:`new_ghost` method that:

- adds an object to the cache, and

- initializes its persistence data.

.. doctest::

   >>> import persistent
   >>> from persistent.tests.utils import ResettingJar

   >>> class C(persistent.Persistent):
   ...     pass

   >>> jar = ResettingJar()
   >>> cache = persistent.PickleCache(jar, 10, 100)
   >>> ob = C.__new__(C)
   >>> cache.new_ghost(b'1', ob)

   >>> ob._p_changed
   >>> ob._p_jar is jar
   True
   >>> ob._p_oid == b'1'
   True

   >>> cache.cache_non_ghost_count
   0
