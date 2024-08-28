/*****************************************************************************

  Copyright (c) 2001, 2002 Zope Foundation and Contributors.
  All Rights Reserved.

  This software is subject to the provisions of the Zope Public License,
  Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
  THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
  WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
  WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
  FOR A PARTICULAR PURPOSE

****************************************************************************/

/*

  Objects are stored under three different regimes:

  Regime 1: Persistent Classes

  Persistent Classes are part of ZClasses. They are stored in the
  self->data dictionary, and are never garbage collected.

  The klass_items() method returns a sequence of (oid,object) tuples for
  every Persistent Class, which should make it possible to implement
  garbage collection in Python if necessary.

  Regime 2: Ghost Objects

  There is no benefit to keeping a ghost object which has no external
  references, therefore a weak reference scheme is used to ensure that
  ghost objects are removed from memory as soon as possible, when the
  last external reference is lost.

  Ghost objects are stored in the self->data dictionary. Normally a
  dictionary keeps a strong reference on its values, however this
  reference count is 'stolen'.

  This weak reference scheme leaves a dangling reference, in the
  dictionary, when the last external reference is lost. To clean up this
  dangling reference the persistent object dealloc function calls
  self->cache->_oid_unreferenced(self->oid). The cache looks up the oid
  in the dictionary, ensures it points to an object whose reference
  count is zero, then removes it from the dictionary. Before removing
  the object from the dictionary it must temporarily resurrect the
  object in much the same way that class instances are resurrected
  before their __del__ is called.

  Since ghost objects are stored under a different regime to non-ghost
  objects, an extra ghostify function in cPersistenceAPI replaces
  self->state=GHOST_STATE assignments that were common in other
  persistent classes (such as BTrees).

  Regime 3: Non-Ghost Objects

  Non-ghost objects are stored in two data structures: the dictionary
  mapping oids to objects and a doubly-linked list that encodes the
  order in which the objects were accessed.  The dictionary reference is
  borrowed, as it is for ghosts.  The list reference is a new reference;
  the list stores recently used objects, even if they are otherwise
  unreferenced, to avoid loading the object from the database again.

  The doubly-link-list nodes contain next and previous pointers linking
  together the cache and all non-ghost persistent objects.

  The node embedded in the cache is the home position. On every
  attribute access a non-ghost object will relink itself just behind the
  home position in the ring. Objects accessed least recently will
  eventually find themselves positioned after the home position.

  Occasionally other nodes are temporarily inserted in the ring as
  position markers. The cache contains a ring_lock flag which must be
  set and unset before and after doing so. Only if the flag is unset can
  the cache assume that all nodes are either his own home node, or nodes
  from persistent objects. This assumption is useful during the garbage
  collection process.

  The number of non-ghost objects is counted in self->non_ghost_count.
  The garbage collection process consists of traversing the ring, and
  deactivating (that is, turning into a ghost) every object until
  self->non_ghost_count is down to the target size, or until it
  reaches the home position again.

  Note that objects in the sticky or changed states are still kept in
  the ring, however they can not be deactivated. The garbage collection
  process must skip such objects, rather than deactivating them.

*/

static char cPickleCache_doc_string[] =
  "Defines the PickleCache used by ZODB Connection objects.\n"
  "\n"
  "$Id$\n";

#include "cPersistence.h"
#include "structmember.h"
#include <time.h>
#include <stddef.h>
#undef Py_FindMethod

#if PY_VERSION_HEX < 0x030b0000
#define USE_HEAP_ALLOCATED_TYPE 0
#define USE_STATIC_MODULE_INIT 1
#define USE_MULTIPHASE_MODULE_INIT 0
#else
#define USE_HEAP_ALLOCATED_TYPE 1
#define USE_STATIC_MODULE_INIT 0
#define USE_MULTIPHASE_MODULE_INIT 1
#endif


/* Python string objects to speed lookups; set by module init. */
static PyObject *py__p_changed;
static PyObject *py__p_deactivate;
static PyObject *py__p_invalidate;
static PyObject *py__p_jar;
static PyObject *py__p_oid;

static int
define_static_strings(void)
{
#define INIT_STRING(S)                              \
  if (!(py_ ## S = PyUnicode_InternFromString(#S))) \
    return -1;
    INIT_STRING(_p_changed);
    INIT_STRING(_p_deactivate);
    INIT_STRING(_p_invalidate);
    INIT_STRING(_p_jar);
    INIT_STRING(_p_oid);
#undef INIT_STRING
    return 0;
}
static cPersistenceCAPIstruct* _get_capi_struct(PyTypeObject* type);

/* This object is the pickle cache.  The CACHE_HEAD macro guarantees
   that layout of this struct is the same as the start of
   ccobject_head in cPersistence.c */
typedef struct
{
    CACHE_HEAD
    int klass_count;                     /* count of persistent classes */
    PyObject *data;                      /* oid -> object dict */
    PyObject *jar;                       /* Connection object */
    int cache_size;                      /* target number of items in cache */
    Py_ssize_t cache_size_bytes;       /* target total estimated size of
                                            items in cache */

    /* Most of the time the ring contains only:
    * many nodes corresponding to persistent objects
    * one 'home' node from the cache.
    In some cases it is handy to temporarily add other types
    of node into the ring as placeholders. 'ring_lock' is a boolean
    indicating that someone has already done this. Currently this
    is only used by the garbage collection code. */

    int ring_lock;

    /* 'cache_drain_resistance' controls how quickly the cache size will drop
        when it is smaller than the configured size. A value of zero means it
        will not drop below the configured size (suitable for most caches).
        Otherwise, it will remove cache_non_ghost_count/cache_drain_resistance
        items from the cache every time (suitable for rarely used caches, such
        as those associated with Zope versions. */

    int cache_drain_resistance;

} ccobject;

static int cc_ass_sub(ccobject *self, PyObject *key, PyObject *v);

/* ---------------------------------------------------------------- */

#define OBJECT_FROM_RING(SELF, HERE)                                    \
  ((cPersistentObject *)(((char *)here) - offsetof(cPersistentObject, ring)))

/* Insert self into the ring, following after. */
static void
insert_after(CPersistentRing *self, CPersistentRing *after)
{
    assert(self != NULL);
    assert(after != NULL);
    self->r_prev = after;
    self->r_next = after->r_next;
    after->r_next->r_prev = self;
    after->r_next = self;
}

/* Remove self from the ring. */
static void
unlink_from_ring(CPersistentRing *self)
{
    assert(self != NULL);
    self->r_prev->r_next = self->r_next;
    self->r_next->r_prev = self->r_prev;
}

static int
scan_gc_items(ccobject *self, int target, Py_ssize_t target_bytes)
{
    /* This function must only be called with the ring lock held,
        because it places non-object placeholders in the ring.
    */
    cPersistentObject *object;
    CPersistentRing *here;
    CPersistentRing before_original_home;
    int result = -1;   /* guilty until proved innocent */

    /* Scan the ring, from least to most recently used, deactivating
    * up-to-date objects, until we either find the ring_home again or
    * or we've ghosted enough objects to reach the target size.
    * Tricky:  __getattr__ and __del__ methods can do anything, and in
    * particular if we ghostify an object with a __del__ method, that method
    * can load the object again, putting it back into the MRU part of the
    * ring.  Waiting to find ring_home again can thus cause an infinite
    * loop (Collector #1208).  So before_original_home records the MRU
    * position we start with, and we stop the scan when we reach that.
    */
    insert_after(&before_original_home, self->ring_home.r_prev);
    here = self->ring_home.r_next;   /* least recently used object */
    /* All objects should be deactivated when the objects count parameter
     * (target) is zero and the size limit parameter in bytes(target_bytes)
     * is also zero.
     *
     * Otherwise the objects should be collect while one of the following
     * conditions are True:
     *  - the ghost count is bigger than the number of objects limit(target).
     *  - the estimated size in bytes is bigger than the size limit in
     *    bytes(target_bytes).
     */
    while (here != &before_original_home &&
            (
             (!target && !target_bytes) ||
             (
              (target && self->non_ghost_count > target) ||
              (target_bytes && self->total_estimated_size > target_bytes)
             )
            )
          )
    {
        assert(self->ring_lock);
        assert(here != &self->ring_home);

        /* At this point we know that the ring only contains nodes
            from persistent objects, plus our own home node.  We know
            this because the ring lock is held.  We can safely assume
            the current ring node is a persistent object now we know it
            is not the home */
        object = OBJECT_FROM_RING(self, here);

        if (object->state == cPersistent_UPTODATE_STATE)
        {
            CPersistentRing placeholder;
            PyObject *method;
            PyObject *temp;
            int error_occurred = 0;
            /* deactivate it. This is the main memory saver. */

            /* Add a placeholder, a dummy node in the ring.  We need
                to do this to mark our position in the ring.  It is
                possible that the PyObject_GetAttr() call below will
                invoke a __getattr__() hook in Python.  Also possible
                that deactivation will lead to a __del__ method call.
                So another thread might run, and mutate the ring as a side
                effect of object accesses.  There's no predicting then where
                in the ring here->next will point after that.  The
                placeholder won't move as a side effect of calling Python
                code.
            */
            insert_after(&placeholder, here);
            method = PyObject_GetAttr((PyObject *)object, py__p_deactivate);
            if (method == NULL)
                error_occurred = 1;
            else
            {
                temp = PyObject_CallObject(method, NULL);
                Py_DECREF(method);
                if (temp == NULL)
                    error_occurred = 1;
                else
                    Py_DECREF(temp);
            }

            here = placeholder.r_next;
            unlink_from_ring(&placeholder);
            if (error_occurred)
                goto Done;
        }
        else
            here = here->r_next;
    }
    result = 0;
Done:
    unlink_from_ring(&before_original_home);
    return result;
}

static PyObject *
lockgc(ccobject *self, int target_size, Py_ssize_t target_size_bytes)
{
    /* This is thread-safe because of the GIL, and there's nothing
    * in between checking the ring_lock and acquiring it that calls back
    * into Python.
    */
    if (self->ring_lock)
    {
        Py_INCREF(Py_None);
        return Py_None;
    }

    self->ring_lock = 1;
    if (scan_gc_items(self, target_size, target_size_bytes) < 0)
    {
        self->ring_lock = 0;
        return NULL;
    }
    self->ring_lock = 0;

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
cc_incrgc(ccobject *self, PyObject *args)
{
    int obsolete_arg = -999;
    int starting_size = self->non_ghost_count;
    int target_size = self->cache_size;
    Py_ssize_t target_size_bytes = self->cache_size_bytes;

    if (self->cache_drain_resistance >= 1)
    {
        /* This cache will gradually drain down to a small size. Check
            a (small) number of objects proportional to the current size */

        int target_size_2 = (starting_size - 1
                            - starting_size / self->cache_drain_resistance);
        if (target_size_2 < target_size)
            target_size = target_size_2;
    }


    if (!PyArg_ParseTuple(args, "|i:incrgc", &obsolete_arg))
        return NULL;

    if (obsolete_arg != -999
        &&
        (PyErr_Warn(PyExc_DeprecationWarning,
                    "No argument expected")
        < 0))
        return NULL;

    return lockgc(self, target_size, target_size_bytes);
}

static PyObject *
cc_full_sweep(ccobject *self, PyObject *args)
{
    int dt = -999;

    /* TODO:  This should be deprecated;  */

    if (!PyArg_ParseTuple(args, "|i:full_sweep", &dt))
        return NULL;
    if (dt == -999)
        return lockgc(self, 0, 0);
    else
        return cc_incrgc(self, args);
}

static PyObject *
cc_minimize(ccobject *self, PyObject *args)
{
    int ignored = -999;

    if (!PyArg_ParseTuple(args, "|i:minimize", &ignored))
        return NULL;

    if (ignored != -999
        &&
        (PyErr_Warn(PyExc_DeprecationWarning,
                    "No argument expected")
        < 0))
        return NULL;

    return lockgc(self, 0, 0);
}

static int
_invalidate(ccobject *self, PyObject *key)
{
    PyObject *meth, *v;

    v = PyDict_GetItem(self->data, key);
    if (v == NULL)
        return 0;

    if (v->ob_refcnt <= 1 && PyType_Check(v))
    {
        /* This looks wrong, but it isn't. We use strong references to types
            because they don't have the ring members.

            The result is that we *never* remove classes unless
            they are modified.  We can fix this by using wekrefs uniformly.
        */
        self->klass_count--;
        return PyDict_DelItem(self->data, key);
    }

    meth = PyObject_GetAttr(v, py__p_invalidate);
    if (meth == NULL)
        return -1;

    v = PyObject_CallObject(meth, NULL);
    Py_DECREF(meth);
    if (v == NULL)
        return -1;
    Py_DECREF(v);
    return 0;
}

static PyObject *
cc_invalidate(ccobject *self, PyObject *inv)
{
    PyObject *key, *v;
    Py_ssize_t i = 0;

    if (PyDict_Check(inv))
    {
        while (PyDict_Next(inv, &i, &key, &v))
        {
            if (_invalidate(self, key) < 0)
                return NULL;
        }
        PyDict_Clear(inv);
    }
    else
    {
        if (PyBytes_Check(inv))
        {
            if (_invalidate(self, inv) < 0)
                return NULL;
        }
        else
        {
            int l, r;

            l = PyObject_Length(inv);
            if (l < 0)
                return NULL;
            for (i=l; --i >= 0; )
            {
                key = PySequence_GetItem(inv, i);
                if (!key)
                    return NULL;
                r = _invalidate(self, key);
                Py_DECREF(key);
                if (r < 0)
                    return NULL;
            }
            /* Dubious:  modifying the input may be an unexpected side effect. */
            PySequence_DelSlice(inv, 0, l);
        }
    }

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
cc_get(ccobject *self, PyObject *args)
{
    PyObject *r, *key, *d = NULL;

    if (!PyArg_ParseTuple(args, "O|O:get", &key, &d))
        return NULL;

    r = PyDict_GetItem(self->data, key);
    if (!r)
    {
        if (d)
            r = d;
        else
            r = Py_None;
    }
    Py_INCREF(r);
    return r;
}

static PyObject *
cc_items(ccobject *self)
{
    return PyObject_CallMethod(self->data, "items", "");
}

static PyObject *
cc_klass_items(ccobject *self)
{
    PyObject *l,*k,*v;
    Py_ssize_t p = 0;

    l = PyList_New(0);
    if (l == NULL)
        return NULL;

    while (PyDict_Next(self->data, &p, &k, &v))
    {
        if(PyType_Check(v))
        {
            v = Py_BuildValue("OO", k, v);
            if (v == NULL)
            {
                Py_DECREF(l);
                return NULL;
            }
            if (PyList_Append(l, v) < 0)
            {
                Py_DECREF(v);
                Py_DECREF(l);
                return NULL;
            }
            Py_DECREF(v);
        }
    }

    return l;
}

static PyObject *
cc_debug_info(ccobject *self)
{
    PyObject* obj_self = (PyObject*)self;
    cPersistenceCAPIstruct* cPersistenceCAPI =
                _get_capi_struct(Py_TYPE(obj_self));
    PyObject *l;
    PyObject *k;
    PyObject *v;
    Py_ssize_t p = 0;

    l = PyList_New(0);
    if (l == NULL)
        return NULL;

    while (PyDict_Next(self->data, &p, &k, &v))
    {
        if (v->ob_refcnt <= 0)
            v = Py_BuildValue("Oi", k, v->ob_refcnt);

        else if (! PyType_Check(v) &&
                PyObject_TypeCheck(v, cPersistenceCAPI->pertype)
                )
            v = Py_BuildValue("Oisi",
                            k, v->ob_refcnt, v->ob_type->tp_name,
                            ((cPersistentObject*)v)->state);
        else
            v = Py_BuildValue("Ois", k, v->ob_refcnt, v->ob_type->tp_name);

        if (v == NULL)
            goto err;

        if (PyList_Append(l, v) < 0)
            goto err;
    }

    return l;

err:
    Py_DECREF(l);
    return NULL;
}

static PyObject *
cc_lru_items(ccobject *self)
{
    PyObject *l;
    CPersistentRing *here;

    if (self->ring_lock)
    {
        /* When the ring lock is held, we have no way of know which
            ring nodes belong to persistent objects, and which a
            placeholders. */
        PyErr_SetString(PyExc_ValueError,
                        ".lru_items() is unavailable during garbage collection");
        return NULL;
    }

    l = PyList_New(0);
    if (l == NULL)
        return NULL;

    here = self->ring_home.r_next;
    while (here != &self->ring_home)
    {
        PyObject *v;
        cPersistentObject *object = OBJECT_FROM_RING(self, here);

        if (object == NULL)
        {
            Py_DECREF(l);
            return NULL;
        }
        v = Py_BuildValue("OO", object->oid, object);
        if (v == NULL)
        {
            Py_DECREF(l);
            return NULL;
        }
        if (PyList_Append(l, v) < 0)
        {
            Py_DECREF(v);
            Py_DECREF(l);
            return NULL;
        }
        Py_DECREF(v);
        here = here->r_next;
    }

    return l;
}

static void
cc_oid_unreferenced(ccobject *self, PyObject *oid)
{
    /* This is called by the persistent object deallocation function
        when the reference count on a persistent object reaches
        zero. We need to fix up our dictionary; its reference is now
        dangling because we stole its reference count. Be careful to
        not release the global interpreter lock until this is
        complete. */

    cPersistentObject *dead_pers_obj;
    ccobject* dead_pers_obj_ref_to_self;

    /* If the cache has been cleared by GC, data will be NULL. */
    if (!self->data)
        return;

    dead_pers_obj = (cPersistentObject*)PyDict_GetItem(self->data, oid);
    assert(dead_pers_obj);
    assert(Py_REFCNT(dead_pers_obj) == 0);

    dead_pers_obj_ref_to_self = (ccobject*)dead_pers_obj->cache;
    assert(dead_pers_obj_ref_to_self == self);

    /* Need to be very hairy here because a dictionary is about
        to decref an already deleted object.
    */

    Py_INCREF(dead_pers_obj);
    assert(Py_REFCNT(dead_pers_obj) == 1);
    /* Incremement the refcount again, because delitem is going to
        DECREF it.  If its refcount reached zero again, we'd call back to
        the dealloc function that called us.
    */
    Py_INCREF(dead_pers_obj);

    if (PyDict_DelItem(self->data, oid) < 0)
    {
        /* Almost ignore errors if it wasn't already present (somehow;
           that shouldn't be possible since we literally just got it out
           of this dict and we're holding the GIL and not making any
           calls that could cause a greenlet switch so the state of the
           dictionary should not change). We still need to finish the cleanup.

           Just write an unraisable error (like an exception from __del__,
           because that's basically what this is).
        */
        PyErr_WriteUnraisable((PyObject*)dead_pers_obj);
        PyErr_Clear();
        /* Have the same side effect of clearing a ref count as the dict would have.*/
        Py_DECREF(dead_pers_obj);
    }
    /* Now remove the dead object's reference to self. Note that this could
       cause self to be dealloced.
    */
    Py_DECREF(dead_pers_obj_ref_to_self);
    dead_pers_obj->cache = NULL;

    assert(Py_REFCNT(dead_pers_obj) == 1);

    /* Don't DECREF the object, because this function is called from
        the object's dealloc function. If the refcnt reaches zero (again), it
        will all be invoked recursively.
    */
}

static PyObject *
cc_ringlen(ccobject *self)
{
    CPersistentRing *here;
    int c = 0;

    for (here = self->ring_home.r_next; here != &self->ring_home;
        here = here->r_next)
        c++;
    return PyLong_FromLong(c);
}

static PyObject *
cc_update_object_size_estimation(ccobject *self, PyObject *args)
{
    PyObject *oid;
    cPersistentObject *v;
    unsigned int new_size;
    if (!PyArg_ParseTuple(args, "OI:updateObjectSizeEstimation",
                            &oid, &new_size))
        return NULL;
    /* Note: reference borrowed */
    v = (cPersistentObject *)PyDict_GetItem(self->data, oid);
    if (v)
    {
        /* we know this object -- update our "total_size_estimation"
            we must only update when the object is in the ring
        */
        if (v->ring.r_next)
        {
            self->total_estimated_size += _estimated_size_in_bytes(
                (int)(_estimated_size_in_24_bits(new_size))
                    - (int)(v->estimated_size)
                );
            /* we do this in "Connection" as we need it even when the
                object is not in the cache (or not the ring)
            */
            /* v->estimated_size = new_size; */
        }
    }
    Py_RETURN_NONE;
}

static PyObject*
cc_new_ghost(ccobject *self, PyObject *args)
{
    PyObject* obj_self = (PyObject*)self;
    cPersistenceCAPIstruct* cPersistenceCAPI =
                _get_capi_struct(Py_TYPE(obj_self));
    PyObject *tmp;
    PyObject *key;
    PyObject *v;

    if (!PyArg_ParseTuple(args, "OO:new_ghost", &key, &v))
        return NULL;

    /* Sanity check the value given to make sure it is allowed in the cache */
    if (PyType_Check(v))
    {
        /* Its a persistent class, such as a ZClass. Thats ok. */
    }
    else if (! PyObject_TypeCheck(v, cPersistenceCAPI->pertype))
    {
        /* If it's not an instance of a persistent class, (ie Python
            classes that derive from persistent.Persistent, BTrees,
            etc), report an error.

        */
        PyErr_SetString(PyExc_TypeError,
                        "Cache values must be persistent objects.");
        return NULL;
    }

    /* Can't access v->oid directly because the object might be a
    *  persistent class.
    */
    tmp = PyObject_GetAttr(v, py__p_oid);
    if (tmp == NULL)
        return NULL;
    Py_DECREF(tmp);
    if (tmp != Py_None)
    {
        PyErr_SetString(PyExc_ValueError,
                        "New ghost object must not have an oid");
        return NULL;
    }

    /* useful sanity check, but not strictly an invariant of this class */
    tmp = PyObject_GetAttr(v, py__p_jar);
    if (tmp == NULL)
        return NULL;
    Py_DECREF(tmp);
    if (tmp != Py_None)
    {
        PyErr_SetString(PyExc_ValueError,
                        "New ghost object must not have a jar");
        return NULL;
    }

    tmp = PyDict_GetItem(self->data, key);
    if (tmp)
    {
        Py_DECREF(tmp);
        PyErr_SetString(PyExc_ValueError,
                        "The given oid is already in the cache");
        return NULL;
    }

    if (PyType_Check(v))
    {
        if (PyObject_SetAttr(v, py__p_jar, self->jar) < 0)
            return NULL;
        if (PyObject_SetAttr(v, py__p_oid, key) < 0)
            return NULL;
        if (PyDict_SetItem(self->data, key, v) < 0)
            return NULL;
        PyObject_GC_UnTrack((void *)self->data);
        self->klass_count++;
    }
    else
    {
        cPersistentObject *p = (cPersistentObject *)v;

        if(p->cache != NULL)
        {
            PyErr_SetString(PyExc_AssertionError, "Already in a cache");
            return NULL;
        }

        if (PyDict_SetItem(self->data, key, v) < 0)
            return NULL;
        /* the dict should have a borrowed reference */
        PyObject_GC_UnTrack((void *)self->data);
        Py_DECREF(v);

        Py_INCREF(self);
        p->cache = (PerCache *)self;
        Py_INCREF(self->jar);
        p->jar = self->jar;
        Py_INCREF(key);
        p->oid = key;
        p->state = cPersistent_GHOST_STATE;
    }

    Py_RETURN_NONE;
}

static struct PyMethodDef cc_methods[] = {
    {"items", (PyCFunction)cc_items, METH_NOARGS,
     "Return list of oid, object pairs for all items in cache."},

    {"lru_items", (PyCFunction)cc_lru_items, METH_NOARGS,
     "List (oid, object) pairs from the lru list, as 2-tuples."},

    {"klass_items", (PyCFunction)cc_klass_items, METH_NOARGS,
     "List (oid, object) pairs of cached persistent classes."},

    {"full_sweep", (PyCFunction)cc_full_sweep, METH_VARARGS,
     "full_sweep() -- Perform a full sweep of the cache."},

    {"minimize",    (PyCFunction)cc_minimize, METH_VARARGS,
     "minimize([ignored]) -- Remove as many objects as possible\n\n"
     "Ghostify all objects that are not modified.  Takes an optional\n"
     "argument, but ignores it."},

    {"incrgc", (PyCFunction)cc_incrgc, METH_VARARGS,
     "incrgc() -- Perform incremental garbage collection\n\n"
     "This method had been depricated!"
     "Some other implementations support an optional parameter 'n' which\n"
     "indicates a repetition count; this value is ignored."},

    {"invalidate", (PyCFunction)cc_invalidate, METH_O,
     "invalidate(oids) -- invalidate one, many, or all ids"},

    {"get", (PyCFunction)cc_get, METH_VARARGS,
     "get(key [, default]) -- get an item, or a default"},

    {"ringlen", (PyCFunction)cc_ringlen, METH_NOARGS,
     "ringlen() -- Returns number of non-ghost items in cache."},

    {"debug_info", (PyCFunction)cc_debug_info, METH_NOARGS,
     "debug_info() -- Returns debugging data about objects in the cache."},

    {"update_object_size_estimation",
     (PyCFunction)cc_update_object_size_estimation, METH_VARARGS,
     "update_object_size_estimation(oid, new_size) -- "
     "update the caches size estimation for *oid* "
     "(if this is known to the cache)."},

    {"new_ghost", (PyCFunction)cc_new_ghost, METH_VARARGS,
     "new_ghost() -- Initialize a ghost and add it to the cache."},

    {NULL, NULL}        /* sentinel */
};

static int
cc_init(ccobject *self, PyObject *args, PyObject *kwds)
{
    int cache_size = 100;
    Py_ssize_t cache_size_bytes = 0;
    PyObject *jar;

    if (!PyArg_ParseTuple(args, "O|in", &jar, &cache_size, &cache_size_bytes))
        return -1;

    self->jar = NULL;
    self->data = PyDict_New();
    if (self->data == NULL)
    {
        Py_DECREF(self);
        return -1;
    }
    /* Untrack the dict mapping oids to objects.

        The dict contains uncounted references to ghost objects, so it
        isn't safe for GC to visit it.  If GC finds an object with more
        referents that refcounts, it will die with an assertion failure.

        When the cache participates in GC, it will need to traverse the
        objects in the doubly-linked list, which will account for all the
        non-ghost objects.
    */
    PyObject_GC_UnTrack((void *)self->data);
    self->jar = jar;
    Py_INCREF(jar);
    self->cache_size = cache_size;
    self->cache_size_bytes = cache_size_bytes;
    self->non_ghost_count = 0;
    self->total_estimated_size = 0;
    self->klass_count = 0;
    self->cache_drain_resistance = 0;
    self->ring_lock = 0;
    self->ring_home.r_next = &self->ring_home;
    self->ring_home.r_prev = &self->ring_home;
    return 0;
}

static void
cc_dealloc(ccobject *self)
{
    PyObject_GC_UnTrack((PyObject *)self);
    Py_XDECREF(self->data);
    Py_XDECREF(self->jar);
    PyObject_GC_Del(self);
}

static int
cc_clear(ccobject *self)
{
    Py_ssize_t pos = 0;
    PyObject *k, *v;
    /* Clearing the cache is delicate.

        A non-ghost object will show up in the ring and in the dict.  If
        we deallocating the dict before clearing the ring, the GC will
        decref each object in the dict.  Since the dict references are
        uncounted, this will lead to objects having negative refcounts.

        Freeing the non-ghost objects should eliminate many objects from
        the cache, but there may still be ghost objects left.  It's
        not safe to decref the dict until it's empty, so we need to manually
        clear those out of the dict, too.  We accomplish that by replacing
        all the ghost objects with None.
    */

    /* We don't need to lock the ring, because the cache is unreachable.
        It should be impossible for anyone to be modifying the cache.
    */
    assert(! self->ring_lock);

    while (self->ring_home.r_next != &self->ring_home)
    {
        CPersistentRing *here = self->ring_home.r_next;
        cPersistentObject *o = OBJECT_FROM_RING(self, here);

        if (o->cache)
        {
            Py_INCREF(o); /* account for uncounted reference */
            if (PyDict_DelItem(self->data, o->oid) < 0)
                return -1;
        }
        o->cache = NULL;
        Py_DECREF(self);
        self->ring_home.r_next = here->r_next;
        o->ring.r_prev = NULL;
        o->ring.r_next = NULL;
        Py_DECREF(o);
        here = here->r_next;
    }

    Py_XDECREF(self->jar);

    while (PyDict_Next(self->data, &pos, &k, &v))
    {
        Py_INCREF(v);
        if (PyDict_SetItem(self->data, k, Py_None) < 0)
            return -1;
    }
    Py_XDECREF(self->data);
    self->data = NULL;
    self->jar = NULL;
    return 0;
}

static int
cc_traverse(ccobject *self, visitproc visit, void *arg)
{
    int err;
    CPersistentRing *here;

    /* If we're in the midst of cleaning up old objects, the ring contains
    * assorted junk we must not pass on to the visit() callback.  This
    * should be rare (our cleanup code would need to have called back
    * into Python, which in turn triggered Python's gc).  When it happens,
    * simply don't chase any pointers.  The cache will appear to be a
    * source of external references then, and at worst we miss cleaning
    * up a dead cycle until the next time Python's gc runs.
    */
    if (self->ring_lock)
        return 0;

#define VISIT(SLOT)                             \
    if (SLOT) {                                   \
        err = visit((PyObject *)(SLOT), arg);       \
        if (err)                                    \
        return err;                               \
    }

    VISIT(self->jar);

    here = self->ring_home.r_next;

    /* It is possible that an object is traversed after it is cleared.
        In that case, there is no ring.
    */
    if (!here)
        return 0;

    while (here != &self->ring_home)
    {
        cPersistentObject *o = OBJECT_FROM_RING(self, here);
        VISIT(o);
        here = here->r_next;
    }
#undef VISIT

    return 0;
}

static Py_ssize_t
cc_length(ccobject *self)
{
    return PyObject_Length(self->data);
}

static PyObject *
cc_subscript(ccobject *self, PyObject *key)
{
    PyObject *r;

    r = PyDict_GetItem(self->data, key);
    if (r == NULL)
    {
        PyErr_SetObject(PyExc_KeyError, key);
        return NULL;
    }
    Py_INCREF(r);

    return r;
}

static int
cc_add_item(ccobject *self, PyObject *key, PyObject *v)
{
    PyObject* obj_self = (PyObject*)self;
    cPersistenceCAPIstruct* cPersistenceCAPI =
                _get_capi_struct(Py_TYPE(obj_self));
    int result;
    PyObject *oid, *object_again, *jar;
    cPersistentObject *p;

    /* Sanity check the value given to make sure it is allowed in the cache */
    if (PyType_Check(v))
    {
        /* Its a persistent class, such as a ZClass. Thats ok. */
    }
    else if (! PyObject_TypeCheck(v, cPersistenceCAPI->pertype))
    {
        /* If it's not an instance of a persistent class, (ie Python
            classes that derive from persistent.Persistent, BTrees,
            etc), report an error.
        */
        PyErr_SetString(PyExc_TypeError,
                        "Cache values must be persistent objects.");
        return -1;
    }

    /* Can't access v->oid directly because the object might be a
    *  persistent class.
    */
    oid = PyObject_GetAttr(v, py__p_oid);
    if (oid == NULL)
        return -1;
    if (! PyBytes_Check(oid))
    {
        Py_DECREF(oid);
        PyErr_Format(PyExc_TypeError,
                    "Cached object oid must be bytes, not a %s",
                    oid->ob_type->tp_name);

        return -1;
    }

    /*  we know they are both strings.
    *  now check if they are the same string.
    */
    result = PyObject_RichCompareBool(key, oid, Py_NE);
    Py_DECREF(oid);
    if (result < 0)
    {
        return -1;
    }
    if (result)
    {
        PyErr_SetString(PyExc_ValueError, "Cache key does not match oid");
        return -1;
    }

    /* useful sanity check, but not strictly an invariant of this class */
    jar = PyObject_GetAttr(v, py__p_jar);
    if (jar == NULL)
        return -1;
    if (jar==Py_None)
    {
        Py_DECREF(jar);
        PyErr_SetString(PyExc_ValueError,
                        "Cached object jar missing");
        return -1;
    }
    Py_DECREF(jar);

    object_again = PyDict_GetItem(self->data, key);
    if (object_again)
    {
        if (object_again != v)
        {
            PyErr_SetString(PyExc_ValueError,
                            "A different object already has the same oid");
            return -1;
        }
        else
        {
            /* re-register under the same oid - no work needed */
            return 0;
        }
    }

    if (PyType_Check(v))
    {
        if (PyDict_SetItem(self->data, key, v) < 0)
            return -1;
        PyObject_GC_UnTrack((void *)self->data);
        self->klass_count++;
        return 0;
    }
    else
    {
        PerCache *cache = ((cPersistentObject *)v)->cache;
        if (cache)
        {
            if (cache != (PerCache *)self)
                /* This object is already in a different cache. */
                PyErr_SetString(PyExc_ValueError,
                                "Cache values may only be in one cache.");
            return -1;
        }
        /* else:

            This object is already one of ours, which is ok.  It
            would be very strange if someone was trying to register
            the same object under a different key.
        */
    }

    if (PyDict_SetItem(self->data, key, v) < 0)
        return -1;
    /* the dict should have a borrowed reference */
    PyObject_GC_UnTrack((void *)self->data);
    Py_DECREF(v);

    p = (cPersistentObject *)v;
    Py_INCREF(self);
    p->cache = (PerCache *)self;
    if (p->state >= 0)
    {
        /* insert this non-ghost object into the ring just
            behind the home position. */
        self->non_ghost_count++;
        ring_add(&self->ring_home, &p->ring);
        /* this list should have a new reference to the object */
        Py_INCREF(v);
    }
    return 0;
}

static int
cc_del_item(ccobject *self, PyObject *key)
{
    PyObject *v;
    cPersistentObject *p;

    /* unlink this item from the ring */
    v = PyDict_GetItem(self->data, key);
    if (v == NULL)
    {
        PyErr_SetObject(PyExc_KeyError, key);
        return -1;
    }

    if (PyType_Check(v))
    {
        self->klass_count--;
    }
    else
    {
        p = (cPersistentObject *)v;
        if (p->state >= 0)
        {
            self->non_ghost_count--;
            ring_del(&p->ring);
            /* The DelItem below will account for the reference
                held by the list. */
        }
        else
        {
            /* This is a ghost object, so we haven't kept a reference
                count on it.  For it have stayed alive this long
                someone else must be keeping a reference to
                it. Therefore we need to temporarily give it back a
                reference count before calling DelItem below */
            Py_INCREF(v);
        }

        Py_DECREF((PyObject *)p->cache);
        p->cache = NULL;
    }

    if (PyDict_DelItem(self->data, key) < 0)
    {
        PyErr_SetString(PyExc_RuntimeError,
                        "unexpectedly couldn't remove key in cc_ass_sub");
        return -1;
    }

    return 0;
}

static int
cc_ass_sub(ccobject *self, PyObject *key, PyObject *v)
{
    if (!PyBytes_Check(key))
    {
        PyErr_Format(PyExc_TypeError,
                    "cPickleCache key must be bytes, not a %s",
                    key->ob_type->tp_name);
        return -1;
    }
    if (v)
        return cc_add_item(self, key, v);
    else
        return cc_del_item(self, key);
}

static PyObject *
cc_cache_data(ccobject *self, void *context)
{
    return PyDict_Copy(self->data);
}

static PyGetSetDef cc_getsets[] =
{
    {"cache_data", (getter)cc_cache_data},
    {NULL}
};


static PyMemberDef cc_members[] =
{
    {"cache_size", T_INT, offsetof(ccobject, cache_size)},
    {"cache_size_bytes", T_PYSSIZET, offsetof(ccobject, cache_size_bytes)},
    {"total_estimated_size", T_PYSSIZET,
     offsetof(ccobject, total_estimated_size), READONLY},
    {"cache_drain_resistance", T_INT,
      offsetof(ccobject, cache_drain_resistance)},
    {"cache_non_ghost_count", T_INT, offsetof(ccobject, non_ghost_count),
      READONLY},
    {"cache_klass_count", T_INT, offsetof(ccobject, klass_count), READONLY},
    {NULL}
};

static char cc__name__[] = "persistent.PickleCache";
static char cc__doc__[] = "Cache holding pickles";

/* This module is compiled as a shared library.  Some compilers don't
   allow addresses of Python objects defined in other libraries to be
   used in static initializers here.  The DEFERRED_ADDRESS macro is
   used to tag the slots where such addresses appear; the module init
   function must fill in the tagged slots at runtime.  The argument is
   for documentation -- the macro ignores it.
*/
#define DEFERRED_ADDRESS(ADDR) 0

#if USE_HEAP_ALLOCATED_TYPE

/*
 *  Heap type: PickleCache
 */

static PyType_Slot CC_type_slots[] = {
    {Py_tp_doc,             cc__doc__},
    {Py_tp_init,            cc_init},
    {Py_mp_length,          (lenfunc)cc_length},
    {Py_mp_subscript,       (binaryfunc)cc_subscript},
    {Py_mp_ass_subscript,   (objobjargproc)cc_ass_sub},
    {Py_tp_traverse,        cc_traverse},
    {Py_tp_clear,           cc_clear},
    {Py_tp_dealloc,         cc_dealloc},
    {Py_tp_methods,         cc_methods},
    {Py_tp_members,         cc_members},
    {Py_tp_getset,          cc_getsets},
    {0,                     NULL}
};

static PyType_Spec CC_type_spec = {
    .name       = cc__name__,
    .basicsize  = sizeof(ccobject),
    .flags      = Py_TPFLAGS_DEFAULT |
                  Py_TPFLAGS_BASETYPE |
                  Py_TPFLAGS_HAVE_GC,
    .slots      = CC_type_slots
};

#else

/*
 *  Static type: PickleCache
 */
static PyMappingMethods cc_as_mapping =
{
    (lenfunc)cc_length,             /* mp_length */
    (binaryfunc)cc_subscript,       /* mp_subscript */
    (objobjargproc)cc_ass_sub,      /* mp_ass_subscript */
};

static PyTypeObject CC_type_def =
{
    PyVarObject_HEAD_INIT(DEFERRED_ADDRESS(&PyType_Type), 0)
    .tp_name                = cc__name__,
    .tp_doc                 = cc__doc__,
    .tp_basicsize           = sizeof(ccobject),
    .tp_flags               = Py_TPFLAGS_DEFAULT |
                              Py_TPFLAGS_BASETYPE |
                              Py_TPFLAGS_HAVE_GC,
    .tp_new                 = DEFERRED_ADDRESS(&PyType_GenericNew),
    .tp_init                = (initproc)cc_init,
    .tp_as_mapping          = &cc_as_mapping,
    .tp_traverse            = (traverseproc)cc_traverse,
    .tp_clear               = (inquiry)cc_clear,
    .tp_dealloc             = (destructor)cc_dealloc,
    .tp_methods             = cc_methods,
    .tp_members             = cc_members,
    .tp_getset              = cc_getsets,
};

#endif


/*
 *  Module initialization
 */
static struct PyModuleDef CC_module_def;

typedef struct {
    PyTypeObject* cc_type;
    cPersistenceCAPIstruct* capi_struct;
} CC_module_state;

static int
CC_module_traverse(PyObject *module, visitproc visit, void *arg)
{
    CC_module_state* state = PyModule_GetState(module);
    Py_VISIT(state->cc_type);
    Py_VISIT(state->capi_struct->pertype);
    return 0;
}

static int
CC_module_clear(PyObject *module)
{
    CC_module_state* state = PyModule_GetState(module);
    Py_CLEAR(state->cc_type);
    Py_CLEAR(state->capi_struct->pertype);
    return 0;
}

static int
init_cpersistence_capi(PyObject* module, percachedelfunc func)
{
    CC_module_state* state = PyModule_GetState(module);
    state->capi_struct = (cPersistenceCAPIstruct *)PyCapsule_Import(
        CAPI_CAPSULE_NAME, 0
    );
    if (state->capi_struct == NULL)
        return -1;

    state->capi_struct->percachedel = func;
    Py_INCREF(state->capi_struct->pertype);
    return 0;
}

static PyObject*
_get_module(PyTypeObject *typeobj)
{
#if USE_STATIC_MODULE_INIT
    return PyState_FindModule(&CC_module_def);
#else
    if (PyType_Check(typeobj)) {
        /* Only added in Python 3.9 */
        return PyType_GetModule(typeobj);
    }

    PyErr_SetString(PyExc_TypeError, "_get_module: called w/ non-type");
    return NULL;
#endif
}

static cPersistenceCAPIstruct*
_get_capi_struct(PyTypeObject* type)
{
    PyObject* module = _get_module(type);
    if (module == NULL)
        return NULL;

    CC_module_state* state = PyModule_GetState(module);
    if (state == NULL)
        return NULL;

    return state->capi_struct;
}

static int
CC_module_exec(PyObject* module)
{
    CC_module_state* state = PyModule_GetState(module);

    if (init_cpersistence_capi(
            module, (percachedelfunc)cc_oid_unreferenced) < 0)
        return -1;

    if (PyModule_AddStringConstant(module, "cache_variant", "stiff/c") < 0)
        return -1;

#if USE_HEAP_ALLOCATED_TYPE

    state->cc_type = (PyTypeObject*) PyType_FromModuleAndSpec(
            module, &CC_type_spec, NULL);

#else

    ((PyObject*)&CC_type_def)->ob_type = &PyType_Type;
    CC_type_def.tp_new = &PyType_GenericNew;

    if (PyType_Ready(&CC_type_def) < 0)
        return -1;

    state->cc_type = &CC_type_def;
#endif

    /* We hold one ref to the type in module state;  the module dict
     * holds another.
     */
    if (PyModule_AddObject(
            module, "PickleCache", (PyObject*)state->cc_type) < 0)
        return -1;

    Py_INCREF(state->cc_type);  /* restore stolen ref */

    return 0;
}

#if USE_MULTIPHASE_MODULE_INIT
/* Slot definitions for multi-phase initialization
 *
 * See: https://docs.python.org/3/c-api/module.html#multi-phase-initialization
 * and: https://peps.python.org/pep-0489
 */
static PyModuleDef_Slot CC_module_slots[] = {
    {Py_mod_exec,       CC_module_exec},
    {0,                 NULL}
};
#endif

static struct PyModuleDef CC_module_def =
{
    PyModuleDef_HEAD_INIT,
    .m_name                 = "cPickleCache",
    .m_doc                  = cPickleCache_doc_string,
    .m_size                 = sizeof(CC_module_state),
    .m_traverse             = CC_module_traverse,
    .m_clear                = CC_module_clear,
#if USE_MULTIPHASE_MODULE_INIT
    .m_slots                = CC_module_slots,
#endif
};

static PyObject*
CC_module_init(void)
{
    if (define_static_strings() < 0)
        return NULL;

#if USE_STATIC_MODULE_INIT

    PyObject* module = PyModule_Create(&CC_module_def);
    if (module == NULL)
        return NULL;

    if (CC_module_exec(module) < 0)
        return NULL;

    return module;

#else
    return PyModuleDef_Init(&CC_module_def);
#endif
}

PyMODINIT_FUNC
PyInit_cPickleCache(void)
{
    return CC_module_init();
}
