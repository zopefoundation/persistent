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
static char cPersistence_doc_string[] =
  "Defines Persistent mixin class for persistent objects.\n"
  "\n"
  "$Id$\n";

#define PY_SSIZE_T_CLEAN
#include "cPersistence.h"
#include "structmember.h"

struct ccobject_head_struct
{
    CACHE_HEAD
};

/*
  The compiler on Windows used for Python 2.7 doesn't include
  stdint.h.
*/
#if !defined(PY3K) && defined(_WIN32)
typedef unsigned long long uint64_t;
#  define PRIx64 "llx"
#else
#  include <stdint.h>
#  include <inttypes.h>
#endif

/* These objects are initialized when the module is loaded */
static PyObject *py_simple_new;

/* Strings initialized by init_strings() below. */
static PyObject *py_keys, *py_setstate, *py___dict__, *py_timeTime;
static PyObject *py__p_changed, *py__p_deactivate;
static PyObject *py___getattr__, *py___setattr__, *py___delattr__;
static PyObject *py___slotnames__, *copy_reg_slotnames, *__newobj__;
static PyObject *py___getnewargs__, *py___getstate__;
static PyObject *py_unsaved, *py_ghost, *py_saved, *py_changed, *py_sticky;


static int
init_strings(void)
{
#define INIT_STRING(S)                              \
  if (!(py_ ## S = INTERN(#S)))  \
    return -1;
  INIT_STRING(keys);
  INIT_STRING(setstate);
  INIT_STRING(timeTime);
  INIT_STRING(__dict__);
  INIT_STRING(_p_changed);
  INIT_STRING(_p_deactivate);
  INIT_STRING(__getattr__);
  INIT_STRING(__setattr__);
  INIT_STRING(__delattr__);
  INIT_STRING(__slotnames__);
  INIT_STRING(__getnewargs__);
  INIT_STRING(__getstate__);
  INIT_STRING(unsaved);
  INIT_STRING(ghost);
  INIT_STRING(saved);
  INIT_STRING(changed);
  INIT_STRING(sticky);
#undef INIT_STRING
  return 0;
}

#ifdef Py_DEBUG
static void
fatal_1350(cPersistentObject *self, const char *caller, const char *detail)
{
    char buf[1000];

    PyOS_snprintf(buf, sizeof(buf),
                "cPersistence.c %s(): object at %p with type %.200s\n"
                "%s.\n"
                "The only known cause is multiple threads trying to ghost and\n"
                "unghost the object simultaneously.\n"
                "That's not legal, but ZODB can't stop it.\n"
                "See Collector #1350.\n",
                caller, self, Py_TYPE(self)->tp_name, detail);
    Py_FatalError(buf);
}
#endif

static void ghostify(cPersistentObject*);
static PyObject * pickle_slotnames(PyTypeObject *cls);

static PyObject * convert_name(PyObject *name);

/* Load the state of the object, unghostifying it.  Upon success, return 1.
 * If an error occurred, re-ghostify the object and return -1.
 */
static int
unghostify(cPersistentObject *self)
{
    if (self->state < 0 && self->jar)
    {
        PyObject *r;

        /* Is it ever possible to not have a cache? */
        if (self->cache)
        {
            /* Create a node in the ring for this unghostified object. */
            self->cache->non_ghost_count++;
            self->cache->total_estimated_size +=
                _estimated_size_in_bytes(self->estimated_size);
            ring_add(&self->cache->ring_home, &self->ring);
            Py_INCREF(self);
        }
        /* set state to CHANGED while setstate() call is in progress
            to prevent a recursive call to _PyPersist_Load().
        */
        self->state = cPersistent_CHANGED_STATE;
        /* Call the object's __setstate__() */
        r = PyObject_CallMethod(self->jar, "setstate", "O", (PyObject *)self);
        if (r == NULL)
        {
            ghostify(self);
            return -1;
        }
        self->state = cPersistent_UPTODATE_STATE;
        Py_DECREF(r);
        if (self->cache && self->ring.r_next == NULL)
        {
#ifdef Py_DEBUG
            fatal_1350(self, "unghostify",
                     "is not in the cache despite that we just "
                     "unghostified it");
#else
            PyErr_Format(PyExc_SystemError, "object at %p with type "
                       "%.200s not in the cache despite that we just "
                       "unghostified it", self, Py_TYPE(self)->tp_name);
            return -1;
#endif
        }
    }
    return 1;
}

/****************************************************************************/

static PyTypeObject Pertype;

static void
accessed(cPersistentObject *self)
{
    /* Do nothing unless the object is in a cache and not a ghost. */
    if (self->cache && self->state >= 0 && self->ring.r_next)
        ring_move_to_head(&self->cache->ring_home, &self->ring);
}

static void
ghostify(cPersistentObject *self)
{
    PyObject **dictptr, *slotnames;
    PyObject *errtype, *errvalue, *errtb;

    /* are we already a ghost? */
    if (self->state == cPersistent_GHOST_STATE)
        return;

    /* Is it ever possible to not have a cache? */
    if (self->cache == NULL)
    {
        self->state = cPersistent_GHOST_STATE;
        return;
    }

    if (self->ring.r_next == NULL)
    {
        /* There's no way to raise an error in this routine. */
#ifdef Py_DEBUG
        fatal_1350(self, "ghostify", "claims to be in a cache but isn't");
#else
        return;
#endif
    }

    /* If we're ghostifying an object, we better have some non-ghosts. */
    assert(self->cache->non_ghost_count > 0);
    self->cache->non_ghost_count--;
    self->cache->total_estimated_size -=
        _estimated_size_in_bytes(self->estimated_size);
    ring_del(&self->ring);
    self->state = cPersistent_GHOST_STATE;

    /* clear __dict__ */
    dictptr = _PyObject_GetDictPtr((PyObject *)self);
    if (dictptr && *dictptr)
    {
        Py_DECREF(*dictptr);
        *dictptr = NULL;
    }

    /* clear all slots besides _p_*
     * ( for backward-compatibility reason we do this only if class does not
     *   override __new__ ) */
    if (Py_TYPE(self)->tp_new == Pertype.tp_new)
    {
        /* later we might clear an AttributeError but
         * if we have a pending exception that still needs to be
         * raised so that we don't generate a SystemError.
         */
        PyErr_Fetch(&errtype, &errvalue, &errtb);

        slotnames = pickle_slotnames(Py_TYPE(self));
        if (slotnames && slotnames != Py_None)
        {
            int i;

            for (i = 0; i < PyList_GET_SIZE(slotnames); i++)
            {
                PyObject *name;
                char *cname;
                int is_special;

                name = PyList_GET_ITEM(slotnames, i);
#ifdef PY3K
                if (PyUnicode_Check(name))
                {
                    PyObject *converted = convert_name(name);
                    cname = PyBytes_AS_STRING(converted);
#else
                if (PyBytes_Check(name))
                {
                    cname = PyBytes_AS_STRING(name);
#endif
                    is_special = !strncmp(cname, "_p_", 3);
#ifdef PY3K
                    Py_DECREF(converted);
#endif
                    if (is_special) /* skip persistent */
                    {
                        continue;
                    }
                }

                /* NOTE: this skips our delattr hook */
                if (PyObject_GenericSetAttr((PyObject *)self, name, NULL) < 0)
                    /* delattr of non-set slot will raise AttributeError - we
                     * simply ignore. */
                    PyErr_Clear();
            }
        }
        Py_XDECREF(slotnames);
        PyErr_Restore(errtype, errvalue, errtb);
    }

    /* We remove the reference to the just ghosted object that the ring
    * holds.  Note that the dictionary of oids->objects has an uncounted
    * reference, so if the ring's reference was the only one, this frees
    * the ghost object.  Note further that the object's dealloc knows to
    * inform the dictionary that it is going away.
    */
    Py_DECREF(self);
}

static int
changed(cPersistentObject *self)
{
    if ((self->state == cPersistent_UPTODATE_STATE ||
        self->state == cPersistent_STICKY_STATE)
        && self->jar)
    {
        PyObject *meth, *arg, *result;
        static PyObject *s_register;

        if (s_register == NULL)
            s_register = INTERN("register");
        meth = PyObject_GetAttr((PyObject *)self->jar, s_register);
        if (meth == NULL)
            return -1;
        arg = PyTuple_New(1);
        if (arg == NULL)
        {
            Py_DECREF(meth);
            return -1;
        }
        Py_INCREF(self);
        PyTuple_SET_ITEM(arg, 0, (PyObject *)self);
        result = PyObject_CallObject(meth, arg);
        Py_DECREF(arg);
        Py_DECREF(meth);
        if (result == NULL)
            return -1;
        Py_DECREF(result);

        self->state = cPersistent_CHANGED_STATE;
    }

    return 0;
}

static int
readCurrent(cPersistentObject *self)
{
    if ((self->state == cPersistent_UPTODATE_STATE ||
        self->state == cPersistent_STICKY_STATE)
        && self->jar && self->oid)
    {
        static PyObject *s_readCurrent=NULL;
        PyObject *r;

        if (s_readCurrent == NULL)
            s_readCurrent = INTERN("readCurrent");

        r = PyObject_CallMethodObjArgs(self->jar, s_readCurrent, self, NULL);
        if (r == NULL)
            return -1;

        Py_DECREF(r);
    }

    return 0;
}

static PyObject *
Per__p_deactivate(cPersistentObject *self)
{
    if (self->state == cPersistent_UPTODATE_STATE && self->jar)
    {
        PyObject **dictptr = _PyObject_GetDictPtr((PyObject *)self);
        if (dictptr && *dictptr)
        {
            Py_DECREF(*dictptr);
            *dictptr = NULL;
        }
        /* Note that we need to set to ghost state unless we are
            called directly. Methods that override this need to
            do the same! */
        ghostify(self);
        if (PyErr_Occurred())
            return NULL;
    }

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
Per__p_activate(cPersistentObject *self)
{
    if (unghostify(self) < 0)
        return NULL;

    Py_INCREF(Py_None);
    return Py_None;
}

static int Per_set_changed(cPersistentObject *self, PyObject *v);

static PyObject *
Per__p_invalidate(cPersistentObject *self)
{
    signed char old_state = self->state;

    if (old_state != cPersistent_GHOST_STATE)
    {
        if (Per_set_changed(self, NULL) < 0)
            return NULL;
        ghostify(self);
        if (PyErr_Occurred())
            return NULL;
    }
    Py_INCREF(Py_None);
    return Py_None;
}


static PyObject *
pickle_slotnames(PyTypeObject *cls)
{
    PyObject *slotnames;

    slotnames = PyDict_GetItem(cls->tp_dict, py___slotnames__);
    if (slotnames)
    {
        int n = PyObject_Not(slotnames);
        if (n < 0)
            return NULL;
        if (n)
            slotnames = Py_None;

        Py_INCREF(slotnames);
        return slotnames;
    }

    slotnames = PyObject_CallFunctionObjArgs(copy_reg_slotnames,
                                            (PyObject*)cls, NULL);
    if (slotnames && !(slotnames == Py_None || PyList_Check(slotnames)))
    {
        PyErr_SetString(PyExc_TypeError,
                        "copy_reg._slotnames didn't return a list or None");
        Py_DECREF(slotnames);
        return NULL;
    }

    return slotnames;
}

static PyObject *
pickle_copy_dict(PyObject *state)
{
    PyObject *copy, *key, *value;
    char *ckey;
    Py_ssize_t pos = 0;

    copy = PyDict_New();
    if (!copy)
        return NULL;

    if (!state)
        return copy;

    while (PyDict_Next(state, &pos, &key, &value))
    {
        int is_special;
#ifdef PY3K
        if (key && PyUnicode_Check(key))
        {
            PyObject *converted = convert_name(key);
            ckey = PyBytes_AS_STRING(converted);
#else
        if (key && PyBytes_Check(key))
        {
            ckey = PyBytes_AS_STRING(key);
#endif
            is_special = (*ckey == '_' &&
                          (ckey[1] == 'v' || ckey[1] == 'p') &&
                           ckey[2] == '_');
#ifdef PY3K
            Py_DECREF(converted);
#endif
            if (is_special) /* skip volatile and persistent */
                continue;
        }

        if (PyObject_SetItem(copy, key, value) < 0)
            goto err;
    }

    return copy;
err:
    Py_DECREF(copy);
    return NULL;
}


static char pickle___getstate__doc[] =
  "Get the object serialization state\n"
  "\n"
  "If the object has no assigned slots and has no instance dictionary, then \n"
  "None is returned.\n"
  "\n"
  "If the object has no assigned slots and has an instance dictionary, then \n"
  "the a copy of the instance dictionary is returned. The copy has any items \n"
  "with names starting with '_v_' or '_p_' ommitted.\n"
  "\n"
  "If the object has assigned slots, then a two-element tuple is returned.  \n"
  "The first element is either None or a copy of the instance dictionary, \n"
  "as described above. The second element is a dictionary with items \n"
  "for each of the assigned slots.\n"
  ;

static PyObject *
pickle___getstate__(PyObject *self)
{
    PyObject *slotnames=NULL, *slots=NULL, *state=NULL;
    PyObject **dictp;
    int n=0;

    slotnames = pickle_slotnames(Py_TYPE(self));
    if (!slotnames)
        return NULL;

    dictp = _PyObject_GetDictPtr(self);
    if (dictp)
        state = pickle_copy_dict(*dictp);
    else
    {
        state = Py_None;
        Py_INCREF(state);
    }

    if (slotnames != Py_None)
    {
        int i;

        slots = PyDict_New();
        if (!slots)
            goto end;

        for (i = 0; i < PyList_GET_SIZE(slotnames); i++)
        {
            PyObject *name, *value;
            char *cname;
            int is_special;

            name = PyList_GET_ITEM(slotnames, i);
#ifdef PY3K
            if (PyUnicode_Check(name))
            {
                PyObject *converted = convert_name(name);
                cname = PyBytes_AS_STRING(converted);
#else
            if (PyBytes_Check(name))
            {
                cname = PyBytes_AS_STRING(name);
#endif
                is_special = (*cname == '_' &&
                              (cname[1] == 'v' || cname[1] == 'p') &&
                               cname[2] == '_');
#ifdef PY3K
                Py_DECREF(converted);
#endif
                if (is_special) /* skip volatile and persistent */
                {
                    continue;
                }
            }

            /* Unclear:  Will this go through our getattr hook? */
            value = PyObject_GetAttr(self, name);
            if (value == NULL)
                PyErr_Clear();
            else
            {
                int err = PyDict_SetItem(slots, name, value);
                Py_DECREF(value);
                if (err < 0)
                    goto end;
                n++;
            }
        }
    }

    if (n)
        state = Py_BuildValue("(NO)", state, slots);

end:
    Py_XDECREF(slotnames);
    Py_XDECREF(slots);

    return state;
}

static int
pickle_setattrs_from_dict(PyObject *self, PyObject *dict)
{
    PyObject *key, *value;
    Py_ssize_t pos = 0;

    if (!PyDict_Check(dict))
    {
        PyErr_SetString(PyExc_TypeError, "Expected dictionary");
        return -1;
    }

    while (PyDict_Next(dict, &pos, &key, &value))
    {
        if (PyObject_SetAttr(self, key, value) < 0)
            return -1;
    }
    return 0;
}

static char pickle___setstate__doc[] =
  "Set the object serialization state\n\n"
  "The state should be in one of 3 forms:\n\n"
  "- None\n\n"
  "  Ignored\n\n"
  "- A dictionary\n\n"
  "  In this case, the object's instance dictionary will be cleared and \n"
  "  updated with the new state.\n\n"
  "- A two-tuple with a string as the first element. \n\n"
  "  In this case, the method named by the string in the first element will\n"
  "  be called with the second element.\n\n"
  "  This form supports migration of data formats.\n\n"
  "- A two-tuple with None or a Dictionary as the first element and\n"
  "  with a dictionary as the second element.\n\n"
  "  If the first element is not None, then the object's instance dictionary \n"
  "  will be cleared and updated with the value.\n\n"
  "  The items in the second element will be assigned as attributes.\n"
  ;

static PyObject *
pickle___setstate__(PyObject *self, PyObject *state)
{
    PyObject *slots=NULL;

    if (PyTuple_Check(state))
    {
        if (!PyArg_ParseTuple(state, "OO:__setstate__", &state, &slots))
            return NULL;
    }

    if (state != Py_None)
    {
        PyObject **dict;
        PyObject *items;
        PyObject *d_key, *d_value;
        Py_ssize_t i;
        int len;

        dict = _PyObject_GetDictPtr(self);

        if (!dict)
        {
            PyErr_SetString(PyExc_TypeError,
                            "this object has no instance dictionary");
            return NULL;
        }

        if (!*dict)
        {
            *dict = PyDict_New();
            if (!*dict)
                return NULL;
        }

        PyDict_Clear(*dict);

        if (PyDict_CheckExact(state))
        {
            i = 0;
            while (PyDict_Next(state, &i, &d_key, &d_value)) {
                /* normally the keys for instance attributes are
                   interned.  we should try to do that here. */
                if (NATIVE_CHECK_EXACT(d_key)) {
                    Py_INCREF(d_key);
                    INTERN_INPLACE(&d_key);
                    Py_DECREF(d_key);
                }
                if (PyObject_SetItem(*dict, d_key, d_value) < 0)
                    return NULL;
            }
        }
        else
        {
            /* can happen that not a built-in dict is passed as state
               fall back to iterating over items, instead of silently
               failing with PyDict_Next */
            items = PyMapping_Items(state);
            if (items == NULL)
                return NULL;
            len = PySequence_Size(items);
            if (len < 0)
            {
                Py_DECREF(items);
                return NULL;
            }
            for ( i=0; i<len; ++i ) {
                PyObject *item = PySequence_GetItem(items, i);
                if (item == NULL)
                {
                    Py_DECREF(items);
                    return NULL;
                }
                d_key = PyTuple_GetItem(item, 0);
                if (d_key == NULL)
                {
                    Py_DECREF(item);
                    Py_DECREF(items);
                    return NULL;
                }
                d_value = PyTuple_GetItem(item, 1);
                if (d_value == NULL)
                {
                    Py_DECREF(item);
                    Py_DECREF(items);
                    return NULL;
                }

                if (NATIVE_CHECK_EXACT(d_key)) {
                    Py_INCREF(d_key);
                    INTERN_INPLACE(&d_key);
                    Py_DECREF(d_key);
                }
                Py_DECREF(item);
                if (PyObject_SetItem(*dict, d_key, d_value) < 0)
                {
                    Py_DECREF(items);
                    return NULL;
                }
            }
            Py_DECREF(items);
        }
    }

    if (slots && pickle_setattrs_from_dict(self, slots) < 0)
        return NULL;

    Py_INCREF(Py_None);
    return Py_None;
}

static char pickle___reduce__doc[] =
  "Reduce an object to contituent parts for serialization\n"
  ;

static PyObject *
pickle___reduce__(PyObject *self)
{
    PyObject *args=NULL, *bargs=NULL, *state=NULL, *getnewargs=NULL;
    int l, i;

    getnewargs = PyObject_GetAttr(self, py___getnewargs__);
    if (getnewargs)
    {
        bargs = PyObject_CallFunctionObjArgs(getnewargs, NULL);
        Py_DECREF(getnewargs);
        if (!bargs)
            return NULL;
        l = PyTuple_Size(bargs);
        if (l < 0)
            goto end;
    }
    else
    {
        PyErr_Clear();
        l = 0;
    }

    args = PyTuple_New(l+1);
    if (args == NULL)
        goto end;

    Py_INCREF(Py_TYPE(self));
    PyTuple_SET_ITEM(args, 0, (PyObject*)(Py_TYPE(self)));
    for (i = 0; i < l; i++)
    {
        Py_INCREF(PyTuple_GET_ITEM(bargs, i));
        PyTuple_SET_ITEM(args, i+1, PyTuple_GET_ITEM(bargs, i));
    }

    state = PyObject_CallMethodObjArgs(self, py___getstate__, NULL);
    if (!state)
        goto end;

    state = Py_BuildValue("(OON)", __newobj__, args, state);

end:
    Py_XDECREF(bargs);
    Py_XDECREF(args);

    return state;
}


/* Return the object's state, a dict or None.

   If the object has no dict, it's state is None.
   Otherwise, return a dict containing all the attributes that
   don't start with "_v_".

   The caller should not modify this dict, as it may be a reference to
   the object's __dict__.
*/

static PyObject *
Per__getstate__(cPersistentObject *self)
{
    /* TODO:  Should it be an error to call __getstate__() on a ghost? */
    if (unghostify(self) < 0)
        return NULL;

    /* TODO:  should we increment stickyness?  Tim doesn't understand that
        question. S*/
    return pickle___getstate__((PyObject*)self);
}

/* The Persistent base type provides a traverse function, but not a
   clear function.  An instance of a Persistent subclass will have
   its dict cleared through subtype_clear().

   There is always a cycle between a persistent object and its cache.
   When the cycle becomes unreachable, the clear function for the
   cache will break the cycle.  Thus, the persistent object need not
   have a clear function.  It would be complex to write a clear function
   for the objects, if we needed one, because of the reference count
   tricks done by the cache.
*/

static void
Per_dealloc(cPersistentObject *self)
{
    PyObject_GC_UnTrack((PyObject *)self);
    if (self->state >= 0)
    {
        /* If the cache has been cleared, then a non-ghost object
            isn't in the ring any longer.
        */
        if (self->ring.r_next != NULL)
        {
            /* if we're ghostifying an object, we better have some non-ghosts */
            assert(self->cache->non_ghost_count > 0);
            self->cache->non_ghost_count--;
            self->cache->total_estimated_size -=
                _estimated_size_in_bytes(self->estimated_size);
            ring_del(&self->ring);
        }
    }

    if (self->cache)
        cPersistenceCAPI->percachedel(self->cache, self->oid);
    Py_XDECREF(self->cache);
    Py_XDECREF(self->jar);
    Py_XDECREF(self->oid);
    Py_TYPE(self)->tp_free(self);
}

static int
Per_traverse(cPersistentObject *self, visitproc visit, void *arg)
{
    int err;

#define VISIT(SLOT)                             \
    if (SLOT) {                                   \
        err = visit((PyObject *)(SLOT), arg);       \
        if (err)                                    \
        return err;                               \
    }

    VISIT(self->jar);
    VISIT(self->oid);
    VISIT(self->cache);

#undef VISIT
    return 0;
}

/* convert_name() returns a new reference to a string name
   or sets an exception and returns NULL.
*/

static PyObject *
convert_name(PyObject *name)
{
#ifdef Py_USING_UNICODE
  /* The Unicode to string conversion is done here because the
     existing tp_setattro slots expect a string object as name
     and we wouldn't want to break those. */
    if (PyUnicode_Check(name))
    {
        name = PyUnicode_AsEncodedString(name, NULL, NULL);
    }
    else
#endif
        if (!PyBytes_Check(name))
        {
            PyErr_SetString(PyExc_TypeError, "attribute name must be a string");
            return NULL;
        }
        else
            Py_INCREF(name);
    return name;
}

/* Returns true if the object requires unghostification.

   There are several special attributes that we allow access to without
   requiring that the object be unghostified:
   __class__
   __del__
   __dict__
   __of__
   __setstate__
*/

static int
unghost_getattr(const char *s)
{
    if (*s++ != '_')
        return 1;
    if (*s == 'p')
    {
        s++;
        if (*s == '_')
            return 0; /* _p_ */
        else
            return 1;
    }
    else if (*s == '_')
    {
        s++;
        switch (*s)
        {
            case 'c':
                return strcmp(s, "class__");
            case 'd':
                s++;
                if (!strcmp(s, "el__"))
                    return 0; /* __del__ */
                if (!strcmp(s, "ict__"))
                    return 0; /* __dict__ */
                return 1;
            case 'o':
                return strcmp(s, "of__");
            case 's':
                return strcmp(s, "setstate__");
            default:
                return 1;
        }
    }
    return 1;
}

static PyObject*
Per_getattro(cPersistentObject *self, PyObject *name)
{
    PyObject *result = NULL;    /* guilty until proved innocent */
    PyObject *converted;
    char *s;

    converted = convert_name(name);
    if (!converted)
        goto Done;
    s = PyBytes_AS_STRING(converted);

    if (unghost_getattr(s))
    {
        if (unghostify(self) < 0)
            goto Done;
        accessed(self);
    }
    result = PyObject_GenericGetAttr((PyObject *)self, name);

Done:
    Py_XDECREF(converted);
    return result;
}

/* Exposed as _p_getattr method.  Test whether base getattr should be used */
static PyObject *
Per__p_getattr(cPersistentObject *self, PyObject *name)
{
    PyObject *result = NULL;    /* guilty until proved innocent */
    PyObject *converted;
    char *s;

    converted = convert_name(name);
    if (!converted)
        goto Done;
    s = PyBytes_AS_STRING(converted);

    if (*s != '_' || unghost_getattr(s))
    {
        if (unghostify(self) < 0)
            goto Done;
        accessed(self);
        result = Py_False;
    }
    else
        result = Py_True;

    Py_INCREF(result);

Done:
    Py_XDECREF(converted);
    return result;
}

/*
 * TODO:  we should probably not allow assignment of __class__ and __dict__.
 * But we do, and have for a long time. Code in the wild is known to rely on
 * assigning __class__.
*/

static int
Per_setattro(cPersistentObject *self, PyObject *name, PyObject *v)
{
    int result = -1;    /* guilty until proved innocent */
    PyObject *converted;
    char *s;

    converted = convert_name(name);
    if (!converted)
        goto Done;
    s = PyBytes_AS_STRING(converted);

    if (strncmp(s, "_p_", 3) != 0)
    {
        if (unghostify(self) < 0)
            goto Done;
        accessed(self);
        if (strncmp(s, "_v_", 3) != 0
            && self->state != cPersistent_CHANGED_STATE)
            {
            if (changed(self) < 0)
                goto Done;
            }
    }
    result = PyObject_GenericSetAttr((PyObject *)self, name, v);

Done:
    Py_XDECREF(converted);
    return result;
}


static int
Per_p_set_or_delattro(cPersistentObject *self, PyObject *name, PyObject *v)
{
    int result = -1;    /* guilty until proved innocent */
    PyObject *converted;
    char *s;

    converted = convert_name(name);
    if (!converted)
        goto Done;
    s = PyBytes_AS_STRING(converted);

    if (strncmp(s, "_p_", 3))
    {
        if (unghostify(self) < 0)
            goto Done;
        accessed(self);

        result = 0;
    }
    else
    {
        if (PyObject_GenericSetAttr((PyObject *)self, name, v) < 0)
            goto Done;
        result = 1;
    }

Done:
  Py_XDECREF(converted);
  return result;
}

static PyObject *
Per__p_setattr(cPersistentObject *self, PyObject *args)
{
    PyObject *name, *v, *result;
    int r;

    if (!PyArg_ParseTuple(args, "OO:_p_setattr", &name, &v))
        return NULL;

    r = Per_p_set_or_delattro(self, name, v);
    if (r < 0)
        return NULL;

    result = r ? Py_True : Py_False;
    Py_INCREF(result);
    return result;
}

static PyObject *
Per__p_delattr(cPersistentObject *self, PyObject *name)
{
    int r;
    PyObject *result;

    r = Per_p_set_or_delattro(self, name, NULL);
    if (r < 0)
        return NULL;

    result = r ? Py_True : Py_False;
    Py_INCREF(result);
    return result;
}


static PyObject *
Per_get_changed(cPersistentObject *self)
{
    if (self->state < 0)
    {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return PyBool_FromLong(self->state == cPersistent_CHANGED_STATE);
}

static int
Per_set_changed(cPersistentObject *self, PyObject *v)
{
    int deactivate = 0;
    int istrue;

    if (!v)
    {
        /* delattr is used to invalidate an object even if it has changed. */
        if (self->state != cPersistent_GHOST_STATE)
            self->state = cPersistent_UPTODATE_STATE;
        deactivate = 1;
    }
    else if (v == Py_None)
        deactivate = 1;

    if (deactivate)
    {
        PyObject *res, *meth;
        meth = PyObject_GetAttr((PyObject *)self, py__p_deactivate);
        if (meth == NULL)
            return -1;
        res = PyObject_CallObject(meth, NULL);
        if (res)
            Py_DECREF(res);
        else
        {
            /* an error occurred in _p_deactivate().

                It's not clear what we should do here.  The code is
                obviously ignoring the exception, but it shouldn't return
                0 for a getattr and set an exception.  The simplest change
                is to clear the exception, but that simply masks the
                error.

                This prints an error to stderr just like exceptions in
                __del__().  It would probably be better to log it but that
                would be painful from C.
            */
            PyErr_WriteUnraisable(meth);
        }
        Py_DECREF(meth);
        return 0;
    }
    /* !deactivate.  If passed a true argument, mark self as changed (starting
    * with ZODB 3.6, that includes activating the object if it's a ghost).
    * If passed a false argument, and the object isn't a ghost, set the
    * state as up-to-date.
    */
    istrue = PyObject_IsTrue(v);
    if (istrue == -1)
        return -1;
    if (istrue)
    {
        if (self->state < 0)
        {
            if (unghostify(self) < 0)
                return -1;
        }
        return changed(self);
    }

    /* We were passed a false, non-None argument.  If we're not a ghost,
    * mark self as up-to-date.
    */
    if (self->state >= 0)
        self->state = cPersistent_UPTODATE_STATE;
    return 0;
}

static PyObject *
Per_get_oid(cPersistentObject *self)
{
    PyObject *oid = self->oid ? self->oid : Py_None;
    Py_INCREF(oid);
    return oid;
}

static int
Per_set_oid(cPersistentObject *self, PyObject *v)
{
    if (self->cache)
    {
        int result;

        if (v == NULL)
        {
            PyErr_SetString(PyExc_ValueError,
                            "can't delete _p_oid of cached object");
            return -1;
        }
        result = PyObject_RichCompareBool(self->oid, v, Py_NE);
        if (result < 0)
            return -1;
        if (result)
        {
            PyErr_SetString(PyExc_ValueError,
                            "can not change _p_oid of cached object");
            return -1;
        }
    }
    Py_XDECREF(self->oid);
    Py_XINCREF(v);
    self->oid = v;
    return 0;
}

static PyObject *
Per_get_jar(cPersistentObject *self)
{
    PyObject *jar = self->jar ? self->jar : Py_None;
    Py_INCREF(jar);
    return jar;
}

static int
Per_set_jar(cPersistentObject *self, PyObject *v)
{
    if (self->cache)
    {
        int result;

        if (v == NULL)
        {
            PyErr_SetString(PyExc_ValueError,
                            "can't delete _p_jar of cached object");
            return -1;
        }
        result = PyObject_RichCompareBool(self->jar, v, Py_NE);
        if (result < 0)
            return -1;
        if (result)
        {
            PyErr_SetString(PyExc_ValueError,
                            "can not change _p_jar of cached object");
            return -1;
        }
    }
    Py_XDECREF(self->jar);
    Py_XINCREF(v);
    self->jar = v;
    return 0;
}

static PyObject *
Per_get_serial(cPersistentObject *self)
{
    return PyBytes_FromStringAndSize(self->serial, 8);
}

static int
Per_set_serial(cPersistentObject *self, PyObject *v)
{
    if (v)
    {
        if (PyBytes_Check(v) && PyBytes_GET_SIZE(v) == 8)
            memcpy(self->serial, PyBytes_AS_STRING(v), 8);
        else
        {
            PyErr_SetString(PyExc_ValueError,
                            "_p_serial must be an 8-character bytes array");
            return -1;
        }
    }
    else
        memset(self->serial, 0, 8);
    return 0;
}

static PyObject *
Per_get_mtime(cPersistentObject *self)
{
    static PyObject* TimeStamp;
    PyObject *t, *v;

    if (unghostify(self) < 0)
        return NULL;

    accessed(self);

    if (memcmp(self->serial, "\0\0\0\0\0\0\0\0", 8) == 0)
    {
        Py_INCREF(Py_None);
        return Py_None;
    }

    if (!TimeStamp)
    {
        PyObject* ts_module;
        ts_module = PyImport_ImportModule("persistent._timestamp");
        if (!ts_module)
            return NULL;
        TimeStamp = PyObject_GetAttrString(ts_module, "TimeStamp");
        Py_DECREF(ts_module);
        if (!TimeStamp)
          return NULL;
    }

#ifdef PY3K
    t = PyObject_CallFunction(TimeStamp, "y#", self->serial, (Py_ssize_t)8);
#else
    t = PyObject_CallFunction(TimeStamp, "s#", self->serial, (Py_ssize_t)8);
#endif
    if (!t)
    {
        return NULL;
    }
    v = PyObject_CallMethod(t, "timeTime", "");
    Py_DECREF(t);
    return v;
}

static PyObject *
Per_get_state(cPersistentObject *self)
{
    return INT_FROM_LONG(self->state);
}

static PyObject *
Per_get_estimated_size(cPersistentObject *self)
{
    return INT_FROM_LONG(_estimated_size_in_bytes(self->estimated_size));
}

static int
Per_set_estimated_size(cPersistentObject *self, PyObject *v)
{
    if (v)
    {
        if (INT_CHECK(v))
        {
            long lv = INT_AS_LONG(v);
            if (lv < 0)
            {
                PyErr_SetString(PyExc_ValueError,
                                "_p_estimated_size must not be negative");
                return -1;
            }
            self->estimated_size = _estimated_size_in_24_bits(lv);
        }
        else
        {
            PyErr_SetString(PyExc_TypeError,
                            "_p_estimated_size must be an integer");
            return -1;
        }
    }
    else
        self->estimated_size = 0;
    return 0;
}

static PyObject *
Per_get_status(cPersistentObject *self)
{
    PyObject *result = NULL;

    if (!self->jar)
    {
        result = py_unsaved;
    } else
    {
        switch (self->state)
        {
            case cPersistent_GHOST_STATE:
                result = py_ghost;
                break;
            case cPersistent_STICKY_STATE:
                result = py_sticky;
                break;
            case cPersistent_UPTODATE_STATE:
                result = py_saved;
                break;
            case cPersistent_CHANGED_STATE:
                result = py_changed;
                break;
        }
    }

    if (result)
    {
        Py_INCREF(result);
    }
    return result;
}

static PyObject*
Per_get_sticky(cPersistentObject *self)
{
    return PyBool_FromLong(self->state == cPersistent_STICKY_STATE);
}

static int
Per_set_sticky(cPersistentObject *self, PyObject* value)
{
    if (self->state < 0)
    {
        PyErr_SetString(PyExc_ValueError,
                            "can't set sticky flag on a ghost");
        return -1;
    }
    if (self->jar)
    {
        if (PyObject_IsTrue(value))
        {
            self->state = cPersistent_STICKY_STATE;
        } else {
            self->state = cPersistent_UPTODATE_STATE;
        }
    }
    return 0;
}

static PyObject*
repr_format_exception(char* format)
{
    /* If an exception we should catch occurred, return a new
       string of its repr. Otherwise, return NULL. */
    PyObject *exc_t;
    PyObject *exc_v;
    PyObject *exc_tb;
    PyObject *result = NULL;

    if (PyErr_Occurred() && PyErr_ExceptionMatches(PyExc_Exception))
    {
        PyErr_Fetch(&exc_t, &exc_v, &exc_tb);
        PyErr_NormalizeException(&exc_t, &exc_v, &exc_tb);
        PyErr_Clear();

        result = PyUnicode_FromFormat(format, exc_v);
        Py_DECREF(exc_t);
        Py_DECREF(exc_v);
        Py_DECREF(exc_tb);
    }
    return result;
}

static PyObject*
repr_helper(PyObject *o, char* format)
{
    /* Returns a new reference, or NULL on error */
    PyObject *result;

    if (o)
    {
        result = PyUnicode_FromFormat(format, o);
        if (!result)
            result = repr_format_exception(format);
    }
    else
    {
        result = PyUnicode_FromString("");
    }

    return result;

}

static PyObject*
Per_repr(cPersistentObject *self)
{
    PyObject *prepr = NULL;
    PyObject *prepr_exc_str = NULL;

    PyObject *module = NULL;
    PyObject *name = NULL;
    PyObject *oid_str = NULL;
    PyObject *jar_str = NULL;
    PyObject *result = NULL;

    unsigned char* oid_bytes;
    char buf[20];
    uint64_t oid_value;

    prepr = PyObject_GetAttrString((PyObject*)Py_TYPE(self), "_p_repr");
    if (prepr)
    {
        result = PyObject_CallFunctionObjArgs(prepr, self, NULL);
        if (result)
            goto cleanup;
        else
        {
            prepr_exc_str = repr_format_exception(" _p_repr %R");
            if (!prepr_exc_str)
                goto cleanup;
        }
    }
    else
    {
        PyErr_Clear();
        prepr_exc_str = PyUnicode_FromString("");
    }

    if (self->oid && PyBytes_Check(self->oid) && PyBytes_GET_SIZE(self->oid) == 8) {
        oid_bytes = (unsigned char*)PyBytes_AS_STRING(self->oid);
        oid_value = ((uint64_t)oid_bytes[0] << 56)
            | ((uint64_t)oid_bytes[1] << 48)
            | ((uint64_t)oid_bytes[2] << 40)
            | ((uint64_t)oid_bytes[3] << 32)
            | ((uint64_t)oid_bytes[4] << 24)
            | ((uint64_t)oid_bytes[5] << 16)
            | ((uint64_t)oid_bytes[6] << 8)
            | ((uint64_t)oid_bytes[7]);
        /*
          Python's PyUnicode_FromFormat doesn't understand the ll
          length modifier for %x, so to format a 64-bit value we need to
          use stdio.
        */
        snprintf(buf, sizeof(buf) - 1, "%" PRIx64, oid_value);
        oid_str = PyUnicode_FromFormat(" oid 0x%s", buf);
    }

    if (!oid_str) {
        oid_str = repr_helper(self->oid, " oid %R");
        if (!oid_str)
            goto cleanup;
    }

    jar_str = repr_helper(self->jar, " in %R");
    if (!jar_str)
        goto cleanup;

    module = PyObject_GetAttrString((PyObject*)Py_TYPE(self), "__module__");
    name = PyObject_GetAttrString((PyObject*)Py_TYPE(self), "__name__");

    if (!module || !name) {
        /*
          Some error retrieving __module__ or __name__. Ignore it, use the
          C data.
        */
        PyErr_Clear();
        result = PyUnicode_FromFormat("<%s object at %p%S%S%S>",
                                      Py_TYPE(self)->tp_name, self,
                                      oid_str, jar_str, prepr_exc_str);
    }
    else {
        result = PyUnicode_FromFormat("<%S.%S object at %p%S%S%S>",
                                      module, name, self,
                                      oid_str, jar_str, prepr_exc_str);
    }

cleanup:
    Py_XDECREF(prepr);
    Py_XDECREF(prepr_exc_str);
    Py_XDECREF(oid_str);
    Py_XDECREF(jar_str);
    Py_XDECREF(name);
    Py_XDECREF(module);

    return result;
}

static PyGetSetDef Per_getsets[] = {
  {"_p_changed", (getter)Per_get_changed, (setter)Per_set_changed},
  {"_p_jar", (getter)Per_get_jar, (setter)Per_set_jar},
  {"_p_mtime", (getter)Per_get_mtime},
  {"_p_oid", (getter)Per_get_oid, (setter)Per_set_oid},
  {"_p_serial", (getter)Per_get_serial, (setter)Per_set_serial},
  {"_p_state", (getter)Per_get_state},
  {"_p_estimated_size",
   (getter)Per_get_estimated_size, (setter)Per_set_estimated_size
  },
  {"_p_status", (getter)Per_get_status},
  {"_p_sticky", (getter)Per_get_sticky, (setter)Per_set_sticky},
  {NULL}
};

static struct PyMethodDef Per_methods[] = {
  {"_p_deactivate", (PyCFunction)Per__p_deactivate, METH_NOARGS,
   "_p_deactivate() -- Deactivate the object"},
  {"_p_activate", (PyCFunction)Per__p_activate, METH_NOARGS,
   "_p_activate() -- Activate the object"},
  {"_p_invalidate", (PyCFunction)Per__p_invalidate, METH_NOARGS,
   "_p_invalidate() -- Invalidate the object"},
  {"_p_getattr", (PyCFunction)Per__p_getattr, METH_O,
   "_p_getattr(name) -- Test whether the base class must handle the name\n"
   "\n"
   "The method unghostifies the object, if necessary.\n"
   "The method records the object access, if necessary.\n"
   "\n"
   "This method should be called by subclass __getattribute__\n"
   "implementations before doing anything else. If the method\n"
   "returns True, then __getattribute__ implementations must delegate\n"
   "to the base class, Persistent.\n"
  },
  {"_p_setattr", (PyCFunction)Per__p_setattr, METH_VARARGS,
   "_p_setattr(name, value) -- Save persistent meta data\n"
   "\n"
   "This method should be called by subclass __setattr__ implementations\n"
   "before doing anything else.  If it returns true, then the attribute\n"
   "was handled by the base class.\n"
   "\n"
   "The method unghostifies the object, if necessary.\n"
   "The method records the object access, if necessary.\n"
  },
  {"_p_delattr", (PyCFunction)Per__p_delattr, METH_O,
   "_p_delattr(name) -- Delete persistent meta data\n"
   "\n"
   "This method should be called by subclass __delattr__ implementations\n"
   "before doing anything else.  If it returns true, then the attribute\n"
   "was handled by the base class.\n"
   "\n"
   "The method unghostifies the object, if necessary.\n"
   "The method records the object access, if necessary.\n"
  },
  {"__getstate__", (PyCFunction)Per__getstate__, METH_NOARGS,
   pickle___getstate__doc },
  {"__setstate__", (PyCFunction)pickle___setstate__, METH_O,
   pickle___setstate__doc},
  {"__reduce__", (PyCFunction)pickle___reduce__, METH_NOARGS,
   pickle___reduce__doc},

  {NULL,        NULL}        /* sentinel */
};

/* This module is compiled as a shared library.  Some compilers don't
   allow addresses of Python objects defined in other libraries to be
   used in static initializers here.  The DEFERRED_ADDRESS macro is
   used to tag the slots where such addresses appear; the module init
   function must fill in the tagged slots at runtime.  The argument is
   for documentation -- the macro ignores it.
*/
#define DEFERRED_ADDRESS(ADDR) 0

static PyTypeObject Pertype = {
  PyVarObject_HEAD_INIT(DEFERRED_ADDRESS(&PyType_Type), 0)
  "persistent.Persistent",          /* tp_name */
  sizeof(cPersistentObject),        /* tp_basicsize */
  0,                                /* tp_itemsize */
  (destructor)Per_dealloc,          /* tp_dealloc */
  0,                                /* tp_print */
  0,                                /* tp_getattr */
  0,                                /* tp_setattr */
  0,                                /* tp_compare */
  (reprfunc)Per_repr,               /* tp_repr */
  0,                                /* tp_as_number */
  0,                                /* tp_as_sequence */
  0,                                /* tp_as_mapping */
  0,                                /* tp_hash */
  0,                                /* tp_call */
  0,                                /* tp_str */
  (getattrofunc)Per_getattro,       /* tp_getattro */
  (setattrofunc)Per_setattro,       /* tp_setattro */
  0,                                /* tp_as_buffer */
  Py_TPFLAGS_DEFAULT |
  Py_TPFLAGS_BASETYPE |
  Py_TPFLAGS_HAVE_GC,               /* tp_flags */
  0,                                /* tp_doc */
  (traverseproc)Per_traverse,       /* tp_traverse */
  0,                                /* tp_clear */
  0,                                /* tp_richcompare */
  0,                                /* tp_weaklistoffset */
  0,                                /* tp_iter */
  0,                                /* tp_iternext */
  Per_methods,                      /* tp_methods */
  0,                                /* tp_members */
  Per_getsets,                      /* tp_getset */
};

/* End of code for Persistent objects */
/* -------------------------------------------------------- */

typedef int (*intfunctionwithpythonarg)(PyObject*);

/* Load the object's state if necessary and become sticky */
static int
Per_setstate(cPersistentObject *self)
{
    if (unghostify(self) < 0)
        return -1;
    self->state = cPersistent_STICKY_STATE;
    return 0;
}

static PyObject *
simple_new(PyObject *self, PyObject *type_object)
{
    if (!PyType_Check(type_object))
    {
        PyErr_SetString(PyExc_TypeError,
                        "simple_new argument must be a type object.");
        return NULL;
    }
    return PyType_GenericNew((PyTypeObject *)type_object, NULL, NULL);
}

static PyMethodDef cPersistence_methods[] =
{
    {"simple_new", simple_new, METH_O,
     "Create an object by simply calling a class's __new__ method without "
     "arguments."},
    {NULL, NULL}
};


static cPersistenceCAPIstruct
truecPersistenceCAPI = {
    &Pertype,
    (getattrofunc)Per_getattro,         /*tp_getattr with object key*/
    (setattrofunc)Per_setattro,         /*tp_setattr with object key*/
    changed,
    accessed,
    ghostify,
    (intfunctionwithpythonarg)Per_setstate,
    NULL, /* The percachedel slot is initialized in cPickleCache.c when
            the module is loaded.  It uses a function in a different
            shared library. */
    readCurrent
};

#ifdef PY3K
static struct PyModuleDef moduledef =
{
    PyModuleDef_HEAD_INIT,
    "cPersistence",                     /* m_name */
    cPersistence_doc_string,            /* m_doc */
    -1,                                 /* m_size */
    cPersistence_methods,               /* m_methods */
    NULL,                               /* m_reload */
    NULL,                               /* m_traverse */
    NULL,                               /* m_clear */
    NULL,                               /* m_free */
};

#endif

static PyObject*
module_init(void)
{
    PyObject *module, *capi;
    PyObject *copy_reg;

    if (init_strings() < 0)
        return NULL;

#ifdef PY3K
    module = PyModule_Create(&moduledef);
#else
    module = Py_InitModule3("cPersistence", cPersistence_methods,
                            cPersistence_doc_string);
#endif

#ifdef PY3K
    ((PyObject*)&Pertype)->ob_type = &PyType_Type;
#else
    Pertype.ob_type = &PyType_Type;
#endif
    Pertype.tp_new = PyType_GenericNew;
    if (PyType_Ready(&Pertype) < 0)
        return NULL;
    if (PyModule_AddObject(module, "Persistent", (PyObject *)&Pertype) < 0)
        return NULL;

    cPersistenceCAPI = &truecPersistenceCAPI;
#ifdef PY3K
    capi = PyCapsule_New(cPersistenceCAPI, CAPI_CAPSULE_NAME, NULL);
#else
    capi = PyCObject_FromVoidPtr(cPersistenceCAPI, NULL);
#endif
    if (!capi)
        return NULL;
    if (PyModule_AddObject(module, "CAPI", capi) < 0)
        return NULL;

    if (PyModule_AddIntConstant(module, "GHOST", cPersistent_GHOST_STATE) < 0)
        return NULL;

    if (PyModule_AddIntConstant(module, "UPTODATE",
                                cPersistent_UPTODATE_STATE) < 0)
        return NULL;

    if (PyModule_AddIntConstant(module, "CHANGED",
                                cPersistent_CHANGED_STATE) < 0)
        return NULL;

    if (PyModule_AddIntConstant(module, "STICKY",
                                cPersistent_STICKY_STATE) < 0)
        return NULL;

    py_simple_new = PyObject_GetAttrString(module, "simple_new");
    if (!py_simple_new)
        return NULL;

#ifdef PY3K
    copy_reg = PyImport_ImportModule("copyreg");
#else
    copy_reg = PyImport_ImportModule("copy_reg");
#endif
    if (!copy_reg)
        return NULL;

    copy_reg_slotnames = PyObject_GetAttrString(copy_reg, "_slotnames");
    if (!copy_reg_slotnames)
    {
      Py_DECREF(copy_reg);
      return NULL;
    }

    __newobj__ = PyObject_GetAttrString(copy_reg, "__newobj__");
    if (!__newobj__)
    {
      Py_DECREF(copy_reg);
      return NULL;
    }

    return module;
}

#ifdef PY3K
PyMODINIT_FUNC PyInit_cPersistence(void)
{
    return module_init();
}
#else
PyMODINIT_FUNC initcPersistence(void)
{
    module_init();
}
#endif
