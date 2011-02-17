Using :mod:`persistent` in your application
===========================================

.. note::
    This document is under construction. More basic documentation will
    eventually appear here.


Inheriting from :class:`persistent.Persistent`
----------------------------------------------

The basic mechanism for making your application's objects persistent
is mix-in interitance.  Instances whose classes derive from
:class:`persistent.Persistent` are automatically capable of being
created as :term:`ghost` instances, being associated with a database
connection (called :term:`jar`), and notifying the connection when they
have been changed.


Overriding the attribute protocol
---------------------------------

Subclasses can override the attribute-management methods provided by
:class:`persistent.Persistent`.  For the `__getattr__` method, the behavior
is like that for regular Python classes and for earlier versions of ZODB 3.

When overriding `__getattribute__`, the derived class implementation
**must** first call :meth:`persistent.Persistent._p_getattr`, passing the
name being accessed.  This method ensures that the object is activated,
if needed, and handles the "special" attributes which do not require
activation (e.g., ``_p_oid``, ``__class__``, ``__dict__``, etc.) 
If ``_p_getattr`` returns ``True``, the derived class implementation
**must** delegate to the base class implementation for the attribute.

When overriding `__setattr__`, the derived class implementation
**must** first call :meth:`persistent.Persistent._p_setattr`, passing the
name being accessed and the value.  This method ensures that the object is
activated, if needed, and handles the "special" attributes which do not
require activation (``_p_*``).  If ``_p_setattr`` returns ``True``, the
derived implementation must assume that the attribute value has been set by
the base class.

When overriding `__detattr__`, the derived class implementation
**must** first call :meth:`persistent.Persistent._p_detattr`, passing the
name being accessed.  This method ensures that the object is
activated, if needed, and handles the "special" attributes which do not
require activation (``_p_*``).  If ``_p_delattr`` returns ``True``, the
derived implementation must assume that the attribute has been deleted
base class.



More Examples
-------------

Detailed examples are provided in the test module,
`persistent.tests.test_overriding_attrs`.
