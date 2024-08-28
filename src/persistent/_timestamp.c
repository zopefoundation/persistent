/*****************************************************************************

  Copyright (c) 2001, 2004 Zope Foundation and Contributors.
  All Rights Reserved.

  This software is subject to the provisions of the Zope Public License,
  Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
  THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
  WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
  WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
  FOR A PARTICULAR PURPOSE

 ****************************************************************************/

#define PY_SSIZE_T_CLEAN
#include "Python.h"
#include "bytesobject.h"
#include <time.h>

#if PY_VERSION_HEX < 0x030b0000
#define USE_HEAP_ALLOCATED_TYPE 0
#define USE_STATIC_TYPE 1
#define USE_STATIC_MODULE_INIT 1
#define USE_MULTIPHASE_MOD_INIT 0
#else
#define USE_HEAP_ALLOCATED_TYPE 1
#define USE_STATIC_TYPE 0
#define USE_STATIC_MODULE_INIT 0
#define USE_MULTIPHASE_MOD_INIT 1
#endif

static char timestamp_module_doc[] =
"A 64-bit TimeStamp used as a ZODB serial number.\n";

/*
 * Forward declarations
 */
static PyObject *TimeStamp_FromDate(PyObject*, int, int, int, int, int, double);
static PyObject *TimeStamp_FromString(PyObject*, const char *);
static PyObject* _get_module(PyTypeObject *typeobj);
static int _get_gmoff(PyObject* module, double* target);
static PyTypeObject* _get_timestamp_type(PyObject* module);


/* A magic constant having the value 0.000000013969839. When an
   number of seconds between 0 and 59 is *divided* by this number, we get
   a number between 0 (for 0), 71582786 (for 1) and 4223384393 (for 59),
   all of which can be represented in a 32-bit unsigned integer, suitable
   for packing into 4 bytes using `TS_PACK_UINT32_INTO_BYTES`.
   To get (close to) the original seconds back, use
   `TS_UNPACK_UINT32_FROM_BYTES` and *multiply* by this number.
 */
#define TS_SECOND_BYTES_BIAS ((double)((double)60) / ((double)(0x10000)) / ((double)(0x10000)))
#define TS_BASE_YEAR 1900
#define TS_MINUTES_PER_DAY 1440
/* We pretend there are always 31 days in a month; this has us using
   372 days in a year in some calculations */
#define TS_DAYS_PER_MONTH 31
#define TS_MONTHS_PER_YEAR 12
#define TS_MINUTES_PER_MONTH (TS_DAYS_PER_MONTH * TS_MINUTES_PER_DAY)
#define TS_MINUTES_PER_YEAR (TS_MINUTES_PER_MONTH * TS_MONTHS_PER_YEAR)

/* The U suffixes matter on these constants to be sure
   the compiler generates the appropriate instructions when
   optimizations are enabled. On x86_64 GCC, if -fno-wrapv is given
   and -O is used, the compiler might choose to treat these as 32 bit
   signed quantities otherwise, producing incorrect results on
   some corner cases. See
   https://github.com/zopefoundation/persistent/issues/86
*/

/**
 * Given an unsigned int *v*, pack it into the four
 * unsigned char bytes beginning at *bytes*. If *v* is larger
 * than 2^31 (i.e., it doesn't fit in 32 bits), the results will
 * be invalid (the first byte will be 0.)
 *
 * The inverse is `TS_UNPACK_UINT32_FROM_BYTES`. This is a
 * lossy operation and may lose some lower-order precision.
 *
 */
#define TS_PACK_UINT32_INTO_BYTES(v, bytes) do { \
    *(bytes) = v / 0x1000000U;                   \
    *(bytes + 1) = (v % 0x1000000U) / 0x10000U;  \
    *(bytes + 2) = (v % 0x10000U) / 0x100U;      \
    *(bytes + 3) = v % 0x100U;                   \
} while (0)

/**
 * Given a sequence of four unsigned chars beginning at *bytes*
 * as produced by `TS_PACK_UINT32_INTO_BYTES`, return the
 * original unsigned int.
 *
 * Remember this is a lossy operation, and the value you get back
 * may not exactly match the original value. If the original value
 * was greater than 2^31 it will definitely not match.
 */
#define TS_UNPACK_UINT32_FROM_BYTES(bytes) (*(bytes) * 0x1000000U + *(bytes + 1) * 0x10000U + *(bytes + 2) * 0x100U + *(bytes + 3))

/* The first dimension of the arrays below is non-leapyear / leapyear */

static char month_len[2][12] =
{
    {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31},
    {31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}
};

static short joff[2][12] =
{
    {0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334},
    {0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335}
};


static int
leap(int year)
{
    return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
}

static int
days_in_month(int year, int month)
{
    return month_len[leap(year)][month];
}

static double
_yad(int y)
{
    double d, s;

    y -= TS_BASE_YEAR;

    d = (y - 1) * 365;
    if (y > 0) {
        s = 1.0;
        y -= 1;
    } else {
        s = -1.0;
        y = -y;
    }
    return d + s * (y / 4 - y / 100 + (y + 300) / 400);
}

static double
_abst(int y, int mo, int d, int m, int s)
{
    return (_yad(y) + joff[leap(y)][mo] + d) * 86400 + m * 60 + s;
}


static int
_init_gmoff(double *p_gmoff)
{
    struct tm *t;
    time_t z=0;

    t = gmtime(&z);
    if (t == NULL)
    {
        PyErr_SetString(PyExc_SystemError, "gmtime failed");
        return -1;
    }

    *p_gmoff = _abst(
        t->tm_year + TS_BASE_YEAR,
        t->tm_mon,
        t->tm_mday - 1,
        t->tm_hour * 60 + t->tm_min,
        t->tm_sec
    );

    return 0;
}

/*
 *  TimeStamp type
 */

typedef struct
{
    PyObject_HEAD
    /*
      The first four bytes of data store the year, month, day, hour, and
      minute as the number of minutes since Jan 1 00:00.

      The final four bytes store the seconds since 00:00 as
      the number of microseconds.

      Both are normalized into those four bytes the same way with
      TS_[UN]PACK_UINT32_INTO|FROM_BYTES.
    */

    unsigned char data[8];
} TimeStamp;

#if USE_HEAP_ALLOCATED_TYPE
static int
TimeStamp_traverse(PyObject *self, visitproc visit, void *arg)
{
    Py_VISIT(Py_TYPE(self));
    return 0;
}

static int
TimeStamp_clear(PyObject *self)
{
    return 0;
}
#endif

static void
TimeStamp_dealloc(PyObject *self)
{
    PyTypeObject *type = Py_TYPE(self);

#if USE_HEAP_ALLOCATED_TYPE
    PyObject_GC_UnTrack(self);
#endif

    type->tp_free(self);

#if USE_HEAP_ALLOCATED_TYPE
    Py_DECREF(type);
#endif
}

static PyObject*
TimeStamp_richcompare(TimeStamp *self, TimeStamp *other, int op)
{
    PyObject *result = NULL;
    int cmp;

    if (Py_TYPE(other) != Py_TYPE(self))
    {
        result = Py_NotImplemented;
    }
    else
    {
        cmp = memcmp(self->data, other->data, 8);
        switch (op) {
        case Py_LT:
            result = (cmp < 0) ? Py_True : Py_False;
            break;
        case Py_LE:
            result = (cmp <= 0) ? Py_True : Py_False;
            break;
        case Py_EQ:
            result = (cmp == 0) ? Py_True : Py_False;
            break;
        case Py_NE:
            result = (cmp != 0) ? Py_True : Py_False;
            break;
        case Py_GT:
            result = (cmp > 0) ? Py_True : Py_False;
            break;
        case Py_GE:
            result = (cmp >= 0) ? Py_True : Py_False;
            break;
        }
    }

    Py_XINCREF(result);
    return result;
}


static Py_hash_t
TimeStamp_hash(TimeStamp* self)
{
    register unsigned char *p = (unsigned char *)self->data;
    register int len = 8;
    register long x = *p << 7;
    while (--len >= 0)
        x = (1000003*x) ^ *p++;
    x ^= 8;
    if (x == -1)
        x = -2;
    return x;
}

typedef struct
{
    /* TODO:  reverse-engineer what's in these things and comment them */
    int y;
    int m;
    int d;
    int mi;
} TimeStampParts;


static void
TimeStamp_unpack(TimeStamp *self, TimeStampParts *p)
{
    unsigned int minutes_since_base;

    minutes_since_base = TS_UNPACK_UINT32_FROM_BYTES(self->data);
    p->y = minutes_since_base / TS_MINUTES_PER_YEAR + TS_BASE_YEAR;
    p->m = (minutes_since_base % TS_MINUTES_PER_YEAR) / TS_MINUTES_PER_MONTH + 1;
    p->d = (minutes_since_base % TS_MINUTES_PER_MONTH) / TS_MINUTES_PER_DAY + 1;
    p->mi = minutes_since_base % TS_MINUTES_PER_DAY;
}

static double
TimeStamp_sec(TimeStamp *self)
{
    unsigned int v;

    v = TS_UNPACK_UINT32_FROM_BYTES(self->data +4);
    return TS_SECOND_BYTES_BIAS * v;
}

static PyObject *
TimeStamp_year(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return PyLong_FromLong(p.y);
}

static PyObject *
TimeStamp_month(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return PyLong_FromLong(p.m);
}

static PyObject *
TimeStamp_day(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return PyLong_FromLong(p.d);
}

static PyObject *
TimeStamp_hour(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return PyLong_FromLong(p.mi / 60);
}

static PyObject *
TimeStamp_minute(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return PyLong_FromLong(p.mi % 60);
}

static PyObject *
TimeStamp_second(TimeStamp *self)
{
    return PyFloat_FromDouble(TimeStamp_sec(self));
}

static PyObject *
TimeStamp_timeTime(TimeStamp *self)
{
    PyObject* obj_self = (PyObject*)self;
    PyObject* module;
    double gmoff;

    module = _get_module(Py_TYPE(obj_self));
    if (module == NULL)
        return NULL;

    if (_get_gmoff(module, &gmoff) < 0)
        return NULL;

    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return PyFloat_FromDouble(
        _abst(p.y, p.m - 1, p.d - 1, p.mi, 0) + TimeStamp_sec(self) - gmoff
    );
}

static PyObject *
TimeStamp_raw(TimeStamp *self)
{
    return PyBytes_FromStringAndSize((const char*)self->data, 8);
}

static PyObject *
TimeStamp_repr(TimeStamp* self)
{
    PyObject *raw, *result;
    raw = TimeStamp_raw(self);
    result = PyObject_Repr(raw);
    Py_DECREF(raw);
    return result;
}

static PyObject *
TimeStamp_str(TimeStamp* self)
{
    char buf[128];
    TimeStampParts p;
    int len;

    TimeStamp_unpack(self, &p);
    len = snprintf(buf, 128, "%4.4d-%2.2d-%2.2d %2.2d:%2.2d:%09.6f",
             p.y, p.m, p.d, p.mi / 60, p.mi % 60,
             TimeStamp_sec(self));

    return PyUnicode_FromStringAndSize(buf, len);
}


static PyObject *
TimeStamp_laterThan(TimeStamp *self, PyObject *obj)
{
    PyObject* obj_self = (PyObject*)self;
    PyObject* module;
    TimeStamp *o = NULL;
    TimeStampParts p;
    unsigned char new[8];
    int i;

    if (Py_TYPE(obj) != Py_TYPE(self))
    {
        PyErr_SetString(PyExc_TypeError, "expected TimeStamp object");
        return NULL;
    }

    o = (TimeStamp *)obj;
    if (memcmp(self->data, o->data, 8) > 0)
    {
        Py_INCREF(self);
        return (PyObject *)self;
    }

    module = _get_module(Py_TYPE(obj_self));
    if (module == NULL)
        return NULL;

    memcpy(new, o->data, 8);
    for (i = 7; i > 3; i--)
    {
        if (new[i] == 255)
            new[i] = 0;
        else
        {
            new[i]++;
            return TimeStamp_FromString(module, (const char*)new);
        }
    }

    /* All but the first two bytes are the same.  Need to increment
       the year, month, and day explicitly. */
    TimeStamp_unpack(o, &p);
    if (p.mi >= 1439)
    {
        p.mi = 0;
        if (p.d == month_len[leap(p.y)][p.m - 1])
        {
            p.d = 1;
            if (p.m == 12)
            {
                p.m = 1;
                p.y++;
            }
            else
                p.m++;
        }
        else
            p.d++;
    }
    else
        p.mi++;

    return TimeStamp_FromDate(module, p.y, p.m, p.d, p.mi / 60, p.mi % 60, 0);
}

static struct PyMethodDef TimeStamp_methods[] =
{
    {"year", (PyCFunction)TimeStamp_year, METH_NOARGS},
    {"minute", (PyCFunction)TimeStamp_minute, METH_NOARGS},
    {"month", (PyCFunction)TimeStamp_month, METH_NOARGS},
    {"day", (PyCFunction)TimeStamp_day, METH_NOARGS},
    {"hour", (PyCFunction)TimeStamp_hour, METH_NOARGS},
    {"second", (PyCFunction)TimeStamp_second, METH_NOARGS},
    {"timeTime", (PyCFunction)TimeStamp_timeTime, METH_NOARGS},
    {"laterThan", (PyCFunction)TimeStamp_laterThan, METH_O},
    {"raw", (PyCFunction)TimeStamp_raw, METH_NOARGS},
    {NULL, NULL},
};

static char TimeStamp__name__[] = "persistent.TimeStamp";
static char TimeStamp__doc__[] = "Timestamp object used as object ID";

#if USE_STATIC_TYPE

/*
 *  Static type: TimeStamp
 */

static PyTypeObject TimeStamp_type_def =
{
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name            = TimeStamp__name__,
    .tp_doc             = TimeStamp__doc__,
    .tp_basicsize       = sizeof(TimeStamp),
    .tp_flags           = Py_TPFLAGS_DEFAULT |
                          Py_TPFLAGS_BASETYPE,
    .tp_str             = (reprfunc)TimeStamp_str,
    .tp_repr            = (reprfunc)TimeStamp_repr,
    .tp_hash            = (hashfunc)TimeStamp_hash,
    .tp_richcompare     = (richcmpfunc)TimeStamp_richcompare,
    .tp_dealloc         = TimeStamp_dealloc,
    .tp_methods         = TimeStamp_methods,
};

#else

/*
 *  Heap type: TimeStamp
 */

static PyType_Slot TimeStamp_type_slots[] = {
    {Py_tp_doc,         TimeStamp__doc__},
    {Py_tp_str,         TimeStamp_str},
    {Py_tp_repr,        TimeStamp_repr},
    {Py_tp_hash,        TimeStamp_hash},
    {Py_tp_richcompare, TimeStamp_richcompare},
    {Py_tp_traverse,    TimeStamp_traverse},
    {Py_tp_clear,       TimeStamp_clear},
    {Py_tp_dealloc,     TimeStamp_dealloc},
    {Py_tp_methods,     TimeStamp_methods},
    {0,                 NULL}
};

static PyType_Spec TimeStamp_type_spec = {
    .name       = TimeStamp__name__,
    .basicsize  = sizeof(TimeStamp),
    .flags      = Py_TPFLAGS_DEFAULT |
                  Py_TPFLAGS_BASETYPE |
                  Py_TPFLAGS_HAVE_GC,
    .slots      = TimeStamp_type_slots
};

#endif


/*
 *  Module functions
 */

PyObject *
TimeStamp_FromString(PyObject* module, const char *buf)
{
    /* buf must be exactly 8 characters */
    PyTypeObject* timestamp_type;
    TimeStamp *ts;

    timestamp_type = _get_timestamp_type(module);
    if (timestamp_type == NULL)
        return NULL;

    ts = (TimeStamp *)PyObject_New(TimeStamp, timestamp_type);
    memcpy(ts->data, buf, 8);
    return (PyObject *)ts;
}

#define CHECK_RANGE(VAR, LO, HI) if ((VAR) < (LO) || (VAR) > (HI)) { \
     return PyErr_Format(PyExc_ValueError, \
             # VAR " must be between %d and %d: %d", \
             (LO), (HI), (VAR)); \
    }

PyObject *
TimeStamp_FromDate(
    PyObject* module,
    int year,
    int month,
    int day,
    int hour,
    int min,
    double sec)
{

    PyTypeObject* timestamp_type;
    TimeStamp *ts = NULL;
    unsigned int years_since_base;
    unsigned int months_since_base;
    unsigned int days_since_base;
    unsigned int hours_since_base;
    unsigned int minutes_since_base;
    unsigned int v;

    if (year < TS_BASE_YEAR)
        return PyErr_Format(PyExc_ValueError,
                    "year must be greater than %d: %d", TS_BASE_YEAR, year);
    CHECK_RANGE(month, 1, 12);
    CHECK_RANGE(day, 1, days_in_month(year, month - 1));
    CHECK_RANGE(hour, 0, 23);
    CHECK_RANGE(min, 0, 59);
    /* Seconds are allowed to be anything, so chill
       If we did want to be pickly, 60 would be a better choice.
    if (sec < 0 || sec > 59)
    return PyErr_Format(PyExc_ValueError,
                "second must be between 0 and 59: %f", sec);
    */
    timestamp_type = _get_timestamp_type(module);
    if (timestamp_type == NULL)
        return NULL;

    ts = (TimeStamp *)PyObject_New(TimeStamp, timestamp_type);

    /* months come in 1-based, hours and minutes come in 0-based */
    /* The base time is Jan 1, 00:00 of TS_BASE_YEAR */
    years_since_base = year - TS_BASE_YEAR;
    months_since_base = years_since_base * TS_MONTHS_PER_YEAR + (month - 1);
    days_since_base = months_since_base * TS_DAYS_PER_MONTH + (day - 1);
    hours_since_base = days_since_base * 24 + hour;
    minutes_since_base = hours_since_base * 60 + min;

    TS_PACK_UINT32_INTO_BYTES(minutes_since_base, ts->data);

    sec /= TS_SECOND_BYTES_BIAS;
    v = (unsigned int)sec;
    TS_PACK_UINT32_INTO_BYTES(v, ts->data + 4);
    return (PyObject *)ts;
}

PyObject *
TimeStamp_TimeStamp(PyObject *module, PyObject *args)
{
    char *buf = NULL;
    Py_ssize_t len = 0;
    int y, mo, d, h = 0, m = 0;
    double sec = 0;

    if (PyArg_ParseTuple(args, "y#", &buf, &len))
    {
        if (len != 8)
        {
            PyErr_SetString(PyExc_ValueError,
                            "8-byte array expected");
            return NULL;
        }
        return TimeStamp_FromString(module, buf);
    }
    PyErr_Clear();

    if (!PyArg_ParseTuple(args, "iii|iid", &y, &mo, &d, &h, &m, &sec))
        return NULL;
    return TimeStamp_FromDate(module, y, mo, d, h, m, sec);
}


/*
 *  Module initialization
 */

static struct PyModuleDef timestamp_module_def;

typedef struct {
    PyTypeObject* timestamp_type;
    double gmoff;
} timestamp_module_state;

static int
timestamp_module_traverse(PyObject *module, visitproc visit, void *arg)
{
    timestamp_module_state* state = PyModule_GetState(module);
    Py_VISIT(state->timestamp_type);
    return 0;
}

static int
timestamp_module_clear(PyObject *module)
{
    timestamp_module_state* state = PyModule_GetState(module);
    Py_CLEAR(state->timestamp_type);
    return 0;
}

static PyObject*
_get_module(PyTypeObject *typeobj)
{
#if USE_STATIC_MODULE_INIT
    return PyState_FindModule(&timestamp_module_def);
#else
    if (PyType_Check(typeobj)) {
        /* Only added in Python 3.9 */
        return PyType_GetModule(typeobj);
    }

    PyErr_SetString(PyExc_TypeError, "_get_module: called w/ non-type");
    return NULL;
#endif
}

static int
_get_gmoff(PyObject* module, double* target)
{
    timestamp_module_state* state = PyModule_GetState(module);
    if (state == NULL)
        return -1;

    *target = state->gmoff;
    return 0;
}

static PyTypeObject*
_get_timestamp_type(PyObject* module)
{
    timestamp_module_state* state = PyModule_GetState(module);
    if (state == NULL)
        return NULL;

    return state->timestamp_type;
}

static PyMethodDef timestamp_module_functions[] =
{
    {"TimeStamp", TimeStamp_TimeStamp, METH_VARARGS},
    {NULL, NULL},
};

static int
timestamp_module_exec(PyObject* module)
{
    PyTypeObject* timestamp_type;
    timestamp_module_state* state;
    double my_gmoff;

    if (_init_gmoff(&my_gmoff) < 0)
        return -1;

    state = (timestamp_module_state*)PyModule_GetState(module);
    if (state == NULL) {
        return -1;
    }
    state->gmoff = my_gmoff;

#if USE_STATIC_MODULE_INIT
    if (PyType_Ready(&TimeStamp_type_def) < 0)
        return -1;

    timestamp_type = &TimeStamp_type_def;
#else
    timestamp_type = (PyTypeObject*)PyType_FromModuleAndSpec(
        module, &TimeStamp_type_spec, NULL);

    if (timestamp_type == NULL)
        return -1;
#endif

    state->timestamp_type = timestamp_type;
    return 0;
}

#if USE_MULTIPHASE_MOD_INIT
/* Slot definitions for multi-phase initialization
 *
 * See: https://docs.python.org/3/c-api/module.html#multi-phase-initialization
 * and: https://peps.python.org/pep-0489
 */
static PyModuleDef_Slot timestamp_module_slots[] = {
    {Py_mod_exec,       timestamp_module_exec},
    {0,                 NULL}
};
#endif

static struct PyModuleDef timestamp_module_def =
{
    PyModuleDef_HEAD_INIT,
    .m_name                     = "_timestamp",
    .m_doc                      = timestamp_module_doc,
    .m_size                     = sizeof(timestamp_module_state),
    .m_traverse                 = timestamp_module_traverse,
    .m_clear                    = timestamp_module_clear,
    .m_methods                  = timestamp_module_functions,
#if USE_MULTIPHASE_MOD_INIT
    .m_slots                    = timestamp_module_slots,
#endif
};


static PyObject*
timestamp_module_init(void)
{

#if USE_STATIC_MODULE_INIT
    PyObject *module;

    module = PyModule_Create(&timestamp_module_def);

    if (module == NULL)
        return NULL;

    if (timestamp_module_exec(module) < 0)
        return NULL;

    return module;

#else
    return PyModuleDef_Init(&timestamp_module_def);
#endif

}

PyMODINIT_FUNC
PyInit__timestamp(void)
{
    return timestamp_module_init();
}
