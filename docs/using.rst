=============================================
 Using :mod:`persistent` in your application
=============================================


Inheriting from :class:`persistent.Persistent`
==============================================

The basic mechanism for making your application's objects persistent
is mix-in inheritance.  Instances whose classes derive from
:class:`persistent.Persistent` are automatically capable of being
created as :term:`ghost` instances, being associated with a database
connection (called the :term:`jar`), and notifying the connection when
they have been changed.


Relationship to a Data Manager and its Cache
============================================

Except immediately after their creation, persistent objects are normally
associated with a :term:`data manager` (also referred to as a :term:`jar`).
An object's data manager is stored in its ``_p_jar`` attribute.
The data manager is responsible for loading and saving the state of the
persistent object to some sort of backing store, including managing any
interactions with transaction machinery.

Each data manager maintains an :term:`object cache`, which keeps track of
the currently loaded objects, as well as any objects they reference which
have not yet been loaded:  such an object is called a :term:`ghost`.
The cache is stored on the data manager in its ``_cache`` attribute.

A persistent object remains in the ghost state until the application
attempts to access or mutate one of its attributes:  at that point, the
object requests that its data manager load its state.  The persistent
object also notifies the cache that it has been loaded, as well as on
each subsequent attribute access.  The cache keeps a "most-recently-used"
list of its objects, and removes objects in least-recently-used order
when it is asked to reduce its working set.

The examples below use a stub data manager class:

.. doctest::

   >>> from zope.interface import implementer
   >>> from persistent.interfaces import IPersistentDataManager
   >>> @implementer(IPersistentDataManager)
   ... class DM(object):
   ...     def __init__(self):
   ...         self.registered = 0
   ...     def register(self, ob):
   ...         self.registered += 1
   ...     def setstate(self, ob):
   ...         ob.__setstate__({'x': 42})

.. note::
   Notice that the ``DM`` class always sets the ``x`` attribute to the value
   ``42`` when activating an object.


Persistent objects without a Data Manager
=========================================

Before persistent instance has been associated with a a data manager (
i.e., its ``_p_jar`` is still ``None``).

The examples below use a class, ``P``, defined as:

.. doctest::

   >>> from persistent import Persistent
   >>> from persistent.interfaces import GHOST, UPTODATE, CHANGED
   >>> class P(Persistent):
   ...    def __init__(self):
   ...        self.x = 0
   ...    def inc(self):
   ...        self.x += 1

Instances of the derived ``P`` class which are not (yet) assigned to
a :term:`data manager` behave as other Python instances, except that
they have some extra attributes:

.. doctest::

   >>> p = P()
   >>> p.x
   0

The :attr:`_p_changed` attribute is a three-state flag:  it can be
one of ``None`` (the object is not loaded), ``False`` (the object has
not been changed since it was loaded) or ``True`` (the object has been
changed).  Until the object is assigned a :term:`jar`, this attribute
will always be ``False``.

.. doctest::

   >>> p._p_changed
   False

The :attr:`_p_state` attribute is an integer, representing which of the
"persistent lifecycle" states the object is in.  Until the object is assigned
a :term:`jar`, this attribute will always be ``0`` (the ``UPTODATE``
constant):

.. doctest::

   >>> p._p_state == UPTODATE
   True

The :attr:`_p_jar` attribute is the object's :term:`data manager`.  Since
it has not yet been assigned, its value is ``None``:

.. doctest::

   >>> print(p._p_jar)
   None

The :attr:`_p_oid` attribute is the :term:`object id`, a unique value
normally assigned by the object's :term:`data manager`.  Since the object
has not yet been associated with its :term:`jar`, its value is ``None``:

.. doctest::

   >>> print(p._p_oid)
   None

Without a data manager, modifying a persistent object has no effect on
its ``_p_state`` or ``_p_changed``.

.. doctest::

   >>> p.inc()
   >>> p.inc()
   >>> p.x
   2
   >>> p._p_changed
   False
   >>> p._p_state
   0

Try all sorts of different ways to change the object's state:

.. doctest::

   >>> p._p_deactivate()
   >>> p._p_state
   0
   >>> p._p_changed
   False
   >>> p._p_changed = True
   >>> p._p_changed
   False
   >>> p._p_state
   0
   >>> del p._p_changed
   >>> p._p_changed
   False
   >>> p._p_state
   0
   >>> p.x
   2


Associating an Object with a Data Manager
=========================================

Once associated with a data manager, a persistent object's behavior changes:

.. doctest::

   >>> p = P()
   >>> dm = DM()
   >>> p._p_oid = "00000012"
   >>> p._p_jar = dm
   >>> p._p_changed
   False
   >>> p._p_state
   0
   >>> p.__dict__
   {'x': 0}
   >>> dm.registered
   0

Modifying the object marks it as changed and registers it with the data
manager.  Subsequent modifications don't have additional side-effects.

.. doctest::

   >>> p.inc()
   >>> p.x
   1
   >>> p.__dict__
   {'x': 1}
   >>> p._p_changed
   True
   >>> p._p_state
   1
   >>> dm.registered
   1
   >>> p.inc()
   >>> p._p_changed
   True
   >>> p._p_state
   1
   >>> dm.registered
   1

Object which register themselves with the data manager are candidates
for storage to the backing store at a later point in time.

Note that mutating a non-persistent attribute of a persistent object
such as a :class:`dict` or :class:`list` will *not* cause the
containing object to be changed. Instead you can either explicitly
control the state as described below, or use a
:class:`~.PersistentList` or :class:`~.PersistentMapping`.

Explicitly controlling ``_p_state``
===================================

Persistent objects expose three methods for moving an object into and out
of the "ghost" state::  :meth:`persistent.Persistent._p_activate`,
:meth:`persistent.Persistent._p_deactivate`, and
:meth:`persistent.Persistent._p_invalidate`:

.. doctest::

   >>> p = P()
   >>> p._p_oid = '00000012'
   >>> p._p_jar = DM()

After being assigned a jar, the object is initially in the ``UPTODATE``
state:

.. doctest::

   >>> p._p_state
   0

From that state, ``_p_deactivate`` rests the object to the ``GHOST`` state:

.. doctest::

   >>> p._p_deactivate()
   >>> p._p_state
   -1

From the ``GHOST`` state, ``_p_activate`` reloads the object's data and
moves it to the ``UPTODATE`` state:

.. doctest::

   >>> p._p_activate()
   >>> p._p_state
   0
   >>> p.x
   42

Changing the object puts it in the ``CHANGED`` state:

.. doctest::

   >>> p.inc()
   >>> p.x
   43
   >>> p._p_state
   1

Attempting to deactivate in the ``CHANGED`` state is a no-op:

.. doctest::

   >>> p._p_deactivate()
   >>> p.__dict__
   {'x': 43}
   >>> p._p_changed
   True
   >>> p._p_state
   1

``_p_invalidate`` forces objects into the ``GHOST`` state;  it works even on
objects in the ``CHANGED`` state, which is the key difference between
deactivation and invalidation:

.. doctest::

   >>> p._p_invalidate()
   >>> p.__dict__
   {}
   >>> p._p_state
   -1

You can manually reset the ``_p_changed`` field to ``False``:  in this case,
the object changes to the ``UPTODATE`` state but retains its modifications:

.. doctest::

   >>> p.inc()
   >>> p.x
   43
   >>> p._p_changed = False
   >>> p._p_state
   0
   >>> p._p_changed
   False
   >>> p.x
   43

For an object in the "ghost" state, assigning ``True`` (or any value which is
coercible to ``True``) to its ``_p_changed`` attributes activates the object,
which is exactly the same as calling ``_p_activate``:

.. doctest::

   >>> p._p_invalidate()
   >>> p._p_state
   -1
   >>> p._p_changed = True
   >>> p._p_changed
   True
   >>> p._p_state
   1
   >>> p.x
   42


The pickling protocol
=====================

Because persistent objects need to control how they are pickled and
unpickled, the :class:`persistent.Persistent` base class overrides
the implementations of ``__getstate__()`` and ``__setstate__()``:

.. doctest::

   >>> p = P()
   >>> dm = DM()
   >>> p._p_oid = "00000012"
   >>> p._p_jar = dm
   >>> p.__getstate__()
   {'x': 0}
   >>> p._p_state
   0

Calling ``__setstate__`` always leaves the object in the uptodate state.

.. doctest::

   >>> p.__setstate__({'x': 5})
   >>> p._p_state
   0

A :term:`volatile attribute` is an attribute those whose name begins with a
special prefix (``_v__``).  Unlike normal attributes, volatile attributes do
not get stored in the object's :term:`pickled data`.

.. doctest::

   >>> p._v_foo = 2
   >>> p.__getstate__()
   {'x': 5}

Assigning to volatile attributes doesn't cause the object to be marked as
changed:

.. doctest::

   >>> p._p_state
   0

The ``_p_serial`` attribute is not affected by calling setstate.

.. doctest::

   >>> p._p_serial = b"00000012"
   >>> p.__setstate__(p.__getstate__())
   >>> p._p_serial
   b'00000012'


Estimated Object Size
=====================

We can store a size estimation in ``_p_estimated_size``. Its default is 0.
The size estimation can be used by a cache associated with the data manager
to help in the implementation of its replacement strategy or its size bounds.

.. doctest::

   >>> p._p_estimated_size
   0
   >>> p._p_estimated_size = 1000
   >>> p._p_estimated_size
   1024

Huh?  Why is the estimated size coming out different than what we put
in? The reason is that the size isn't stored exactly.  For backward
compatibility reasons, the size needs to fit in 24 bits, so,
internally, it is adjusted somewhat.

Of course, the estimated size must not be negative.

.. doctest::

   >>> p._p_estimated_size = -1
   Traceback (most recent call last):
   ...
   ValueError: _p_estimated_size must not be negative


Overriding the attribute protocol
=================================

Subclasses which override the attribute-management methods provided by
:class:`persistent.Persistent`, but must obey some constraints:


:meth:`__getattribute__`
  When overriding ``__getattribute__``, the derived class implementation
  **must** first call :meth:`persistent.IPersistent._p_getattr`, passing the
  name being accessed.  This method ensures that the object is activated,
  if needed, and handles the "special" attributes which do not require
  activation (e.g., ``_p_oid``, ``__class__``, ``__dict__``, etc.)
  If ``_p_getattr`` returns ``True``, the derived class implementation
  **must** delegate to the base class implementation for the attribute.

:meth:`__setattr__`
  When overriding ``__setattr__``, the derived class implementation
  **must** first call :meth:`persistent.IPersistent._p_setattr`, passing the
  name being accessed and the value.  This method ensures that the object is
  activated, if needed, and handles the "special" attributes which do not
  require activation (``_p_*``).  If ``_p_setattr`` returns ``True``, the
  derived implementation must assume that the attribute value has been set by
  the base class.

:meth:`__delattr__`
  When overriding ``__delattr__``, the derived class implementation
  **must** first call :meth:`persistent.IPersistent._p_delattr`, passing the
  name being accessed.  This method ensures that the object is
  activated, if needed, and handles the "special" attributes which do not
  require activation (``_p_*``).  If ``_p_delattr`` returns ``True``, the
  derived implementation must assume that the attribute has been deleted
  base class.

:meth:`__getattr__`
  For the ``__getattr__`` method, the behavior is like that for regular Python
  classes and for earlier versions of ZODB 3.


Implementing ``_p_repr``
========================

Subclasses can implement ``_p_repr`` to provide a custom
representation. If this method raises an exception, the default
representation will be used. The benefit of implementing ``_p_repr``
instead of overriding ``__repr__`` is that it provides safer handling
for objects that can't be activated because their persistent data is
missing or their jar is closed.

.. doctest::

   >>> class P(Persistent):
   ...    def _p_repr(self):
   ...        return "Custom repr"

   >>> p = P()
   >>> print(repr(p))
   Custom repr
