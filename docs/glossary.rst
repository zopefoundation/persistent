.. _glossary:

Glossary
========

.. glossary::
   :sorted:

   data manager
     The object responsible for storing and loading an object's
     :term:`pickled data` in a backing store.  Also called a :term:`jar`.

   jar
     Alias for :term:`data manager`:  short for "pickle jar", because
     it traditionally holds the :term:`pickled data` of persistent objects.

   object cache
     An MRU cache for objects associated with a given :term:`data manager`.

   ghost
     An object whose :term:`pickled data` has not yet been loaded from its
     :term:`jar`.  Accessing or mutating any of its attributes causes
     that data to be loaded, which is referred to as :term:`activation`.

   volatile attribute
     Attributes of a persistent object which are *not* captured as part
     of its :term:`pickled data`.  These attributes thus disappear during
     :term:`deactivation` or :term:`invalidation`.

   pickled data
     The serialized data of a persistent object, stored in and retrieved
     from a backing store by a :term:`data manager`.

   activation
     Moving an object from the ``GHOST`` state to the ``UPTODATE`` state,
     load its :term:`pickled data` from its :term:`jar`.

   deactivation
     Moving an object from the ``UPTODATE`` state to the ``GHOST`` state,
     discarding its :term:`pickled data`.

   invalidation
     Moving an object from either the ``UPTODATE`` state or the ``CHANGED``
     state to the ``GHOST`` state, discarding its :term:`pickled data`.

   object id
     The stable identifier that uniquely names a particular object.
     This is analogous to Python's `id`, but unlike `id`, object
     ids remain the same for a given object across different
     processes.
