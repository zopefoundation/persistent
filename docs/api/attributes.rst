Customizing Attribute Access
============================

Hooking :meth:`__getattr__`
---------------------------
The __getattr__ method works pretty much the same for persistent
classes as it does for other classes.  No special handling is
needed.  If an object is a ghost, then it will be activated before
__getattr__ is called.

In this example, our objects returns a tuple with the attribute
name, converted to upper case and the value of _p_changed, for any
attribute that isn't handled by the default machinery.

.. doctest::

   >>> from persistent.tests.attrhooks import OverridesGetattr
   >>> o = OverridesGetattr()
   >>> o._p_changed
   False
   >>> o._p_oid
   >>> o._p_jar
   >>> o.spam
   ('SPAM', False)
   >>> o.spam = 1
   >>> o.spam
   1

We'll save the object, so it can be deactivated:

.. doctest::

   >>> from persistent.tests.attrhooks import _resettingJar
   >>> jar = _resettingJar()
   >>> jar.add(o)
   >>> o._p_deactivate()
   >>> o._p_changed

And now, if we ask for an attribute it doesn't have,

.. doctest::

  >>> o.eggs
  ('EGGS', False)

And we see that the object was activated before calling the
:meth:`__getattr__` method.

Hooking All Access
------------------

In this example, we'll provide an example that shows how to
override the :meth:`__getattribute__`, :meth:`__setattr__`, and
:meth:`__delattr__` methods.  We'll create a class that stores it's
attributes in a secret dictionary within the instance dictionary.

The class will have the policy that variables with names starting
with ``tmp_`` will be volatile.

Our sample class takes initial values as keyword arguments to the constructor:

.. doctest::

   >>> from persistent.tests.attrhooks import VeryPrivate
   >>> o = VeryPrivate(x=1)


Hooking :meth:`__getattribute__``
#################################

The :meth:`__getattribute__` method is called for all attribute
accesses.  It overrides the attribute access support inherited
from Persistent.

.. doctest::

   >>> o._p_changed
   False
   >>> o._p_oid
   >>> o._p_jar
   >>> o.x
   1
   >>> o.y
   Traceback (most recent call last):
   ...
   AttributeError: y

Next, we'll save the object in a database so that we can deactivate it:

.. doctest::

   >>> from persistent.tests.attrhooks import _rememberingJar
   >>> jar = _rememberingJar()
   >>> jar.add(o)
   >>> o._p_deactivate()
   >>> o._p_changed

And we'll get some data:

.. doctest::

   >>> o.x
   1

which activates the object:

.. doctest::

   >>> o._p_changed
   False

It works for missing attributes too:

.. doctest::

   >>> o._p_deactivate()
   >>> o._p_changed

   >>> o.y
   Traceback (most recent call last):
   ...
   AttributeError: y

   >>> o._p_changed
   False


Hooking :meth:`__setattr__``
############################

The :meth:`__setattr__` method is called for all attribute
assignments.  It overrides the attribute assignment support
inherited from Persistent.

Implementors of :meth:`__setattr__` methods:

1. Must call Persistent._p_setattr first to allow it
   to handle some attributes and to make sure that the object
   is activated if necessary, and

2. Must set _p_changed to mark objects as changed.

.. doctest::

   >>> o = VeryPrivate()
   >>> o._p_changed
   False
   >>> o._p_oid
   >>> o._p_jar
   >>> o.x
   Traceback (most recent call last):
   ...
   AttributeError: x

   >>> o.x = 1
   >>> o.x
   1

Because the implementation doesn't store attributes directly
in the instance dictionary, we don't have a key for the attribute:

.. doctest::

   >>> 'x' in o.__dict__
   False

Next, we'll give the object a "remembering" jar so we can
deactivate it:

.. doctest::

   >>> jar = _rememberingJar()
   >>> jar.add(o)
   >>> o._p_deactivate()
   >>> o._p_changed

We'll modify an attribute

.. doctest::

   >>> o.y = 2
   >>> o.y
   2

which reactivates it, and marks it as modified, because our
implementation marked it as modified:

.. doctest::

   >>> o._p_changed
   True

Now, if fake a commit:

.. doctest::

   >>> jar.fake_commit()
   >>> o._p_changed
   False

And deactivate the object:

.. doctest::

   >>> o._p_deactivate()
   >>> o._p_changed

and then set a variable with a name starting with ``tmp_``,
The object will be activated, but not marked as modified,
because our :meth:`__setattr__` implementation  doesn't mark the
object as changed if the name starts with ``tmp_``:

.. doctest::

   >>> o.tmp_foo = 3
   >>> o._p_changed
   False
   >>> o.tmp_foo
   3


Hooking :meth:`__delattr__``
############################

The __delattr__ method is called for all attribute
deletions.  It overrides the attribute deletion support
inherited from Persistent.

Implementors of :meth:`__delattr__` methods:

1. Must call Persistent._p_delattr first to allow it
   to handle some attributes and to make sure that the object
   is activated if necessary, and

2. Must set _p_changed to mark objects as changed.

.. doctest::

   >>> o = VeryPrivate(x=1, y=2, tmp_z=3)
   >>> o._p_changed
   False
   >>> o._p_oid
   >>> o._p_jar
   >>> o.x
   1
   >>> del o.x
   >>> o.x
   Traceback (most recent call last):
   ...
   AttributeError: x

Next, we'll save the object in a jar so that we can
deactivate it:

.. doctest::

   >>> jar = _rememberingJar()
   >>> jar.add(o)
   >>> o._p_deactivate()
   >>> o._p_changed

If we delete an attribute:

.. doctest::

   >>> del o.y

The object is activated.  It is also marked as changed because
our implementation marked it as changed.

.. doctest::

   >>> o._p_changed
   True
   >>> o.y
   Traceback (most recent call last):
   ...
   AttributeError: y

   >>> o.tmp_z
   3

Now, if fake a commit:

.. doctest::

   >>> jar.fake_commit()
   >>> o._p_changed
   False

And deactivate the object:

.. doctest::

   >>> o._p_deactivate()
   >>> o._p_changed

and then delete a variable with a name starting with ``tmp_``,
The object will be activated, but not marked as modified,
because our :meth:`__delattr__` implementation  doesn't mark the
object as changed if the name starts with ``tmp_``:

.. doctest::

   >>> del o.tmp_z
   >>> o._p_changed
   False
   >>> o.tmp_z
   Traceback (most recent call last):
   ...
   AttributeError: tmp_z

If we attempt to delete ``_p_oid``, we find that we can't, and the
object is also not activated or changed:

.. doctest::

   >>> del o._p_oid
   Traceback (most recent call last):
   ...
   ValueError: can't delete _p_oid of cached object
   >>> o._p_changed
   False

We are allowed to delete ``_p_changed``, which sets it to ``None``:

   >>> del o._p_changed
   >>> o._p_changed is None
   True
