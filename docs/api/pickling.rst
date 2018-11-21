Pickling Persistent Objects
===========================

Persistent objects are designed to make the standard Python pickling
machinery happy:

.. doctest::

   >>> import pickle
   >>> from persistent.tests.cucumbers import Simple
   >>> from persistent.tests.cucumbers import print_dict

   >>> x = Simple('x', aaa=1, bbb='foo')

   >>> print_dict(x.__getstate__())
   {'__name__': 'x', 'aaa': 1, 'bbb': 'foo'}

   >>> f, (c,), state = x.__reduce__()
   >>> f.__name__
   '__newobj__'
   >>> f.__module__.replace('_', '') # Normalize Python2/3
   'copyreg'
   >>> c.__name__
   'Simple'

   >>> print_dict(state)
   {'__name__': 'x', 'aaa': 1, 'bbb': 'foo'}

   >>> import pickle
   >>> pickle.loads(pickle.dumps(x)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 0)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 1)) == x
   True

   >>> pickle.loads(pickle.dumps(x, 2)) == x
   True

   >>> x.__setstate__({'z': 1})
   >>> x.__dict__
   {'z': 1}

This support even works well for derived classes which customize pickling
by overriding :meth:`__getnewargs__`, :meth:`__getstate__` and
:meth:`__setstate__`.

.. doctest::

   >>> from persistent.tests.cucumbers import Custom

   >>> x = Custom('x', 'y')
   >>> x.__getnewargs__()
   ('x', 'y')
   >>> x.a = 99

   >>> (f, (c, ax, ay), a) = x.__reduce__()
   >>> f.__name__
   '__newobj__'
   >>> f.__module__.replace('_', '') # Normalize Python2/3
   'copyreg'
   >>> c.__name__
   'Custom'
   >>> ax, ay, a
   ('x', 'y', 99)

   >>> pickle.loads(pickle.dumps(x)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 0)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 1)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 2)) == x
   True

The support works for derived classes which define :attr:`__slots__`.  It
ignores any slots which map onto the "persistent" namespace (prefixed with
``_p_``) or the "volatile" namespace (prefixed with ``_v_``):

.. doctest::

   >>> from persistent.tests.cucumbers import SubSlotted
   >>> x = SubSlotted('x', 'y', 'z')

Note that we haven't yet assigned a value to the ``s4`` attribute:

.. doctest::

   >>> d, s = x.__getstate__()
   >>> d
   >>> print_dict(s)
   {'s1': 'x', 's2': 'y', 's3': 'z'}

   >>> import pickle
   >>> pickle.loads(pickle.dumps(x)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 0)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 1)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 2)) == x
   True


After assigning it:

.. doctest::

   >>> x.s4 = 'spam'

   >>> d, s = x.__getstate__()
   >>> d
   >>> print_dict(s)
   {'s1': 'x', 's2': 'y', 's3': 'z', 's4': 'spam'}

   >>> pickle.loads(pickle.dumps(x)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 0)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 1)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 2)) == x
   True

:class:`persistent.Persistent` supports derived classes which have base
classes defining :attr:`__slots`, but which do not define attr:`__slots__`
themselves:

.. doctest::

   >>> from persistent.tests.cucumbers import SubSubSlotted
   >>> x = SubSubSlotted('x', 'y', 'z')

   >>> d, s = x.__getstate__()
   >>> print_dict(d)
   {}
   >>> print_dict(s)
   {'s1': 'x', 's2': 'y', 's3': 'z'}

   >>> import pickle
   >>> pickle.loads(pickle.dumps(x)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 0)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 1)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 2)) == x
   True

   >>> x.s4 = 'spam'
   >>> x.foo = 'bar'
   >>> x.baz = 'bam'

   >>> d, s = x.__getstate__()
   >>> print_dict(d)
   {'baz': 'bam', 'foo': 'bar'}
   >>> print_dict(s)
   {'s1': 'x', 's2': 'y', 's3': 'z', 's4': 'spam'}

   >>> pickle.loads(pickle.dumps(x)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 0)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 1)) == x
   True
   >>> pickle.loads(pickle.dumps(x, 2)) == x
   True
