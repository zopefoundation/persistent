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
#include "_compat.h"


PyObject *TimeStamp_FromDate(int, int, int, int, int, double);
PyObject *TimeStamp_FromString(const char *);

static char TimeStampModule_doc[] =
"A 64-bit TimeStamp used as a ZODB serial number.\n"
"\n"
"$Id$\n";


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

static double gmoff=0;


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
TimeStamp_yad(int y)
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
TimeStamp_abst(int y, int mo, int d, int m, int s)
{
    return (TimeStamp_yad(y) + joff[leap(y)][mo] + d) * 86400 + m * 60 + s;
}

static int
TimeStamp_init_gmoff(void)
{
    struct tm *t;
    time_t z=0;

    t = gmtime(&z);
    if (t == NULL)
    {
        PyErr_SetString(PyExc_SystemError, "gmtime failed");
        return -1;
    }

    gmoff = TimeStamp_abst(t->tm_year + TS_BASE_YEAR, t->tm_mon, t->tm_mday - 1,
               t->tm_hour * 60 + t->tm_min, t->tm_sec);

    return 0;
}

static void
TimeStamp_dealloc(TimeStamp *ts)
{
    PyObject_Del(ts);
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
TimeStamp_hash(TimeStamp *self)
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
    return INT_FROM_LONG(p.y);
}

static PyObject *
TimeStamp_month(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return INT_FROM_LONG(p.m);
}

static PyObject *
TimeStamp_day(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return INT_FROM_LONG(p.d);
}

static PyObject *
TimeStamp_hour(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return INT_FROM_LONG(p.mi / 60);
}

static PyObject *
TimeStamp_minute(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return INT_FROM_LONG(p.mi % 60);
}

static PyObject *
TimeStamp_second(TimeStamp *self)
{
    return PyFloat_FromDouble(TimeStamp_sec(self));
}

static PyObject *
TimeStamp_timeTime(TimeStamp *self)
{
    TimeStampParts p;
    TimeStamp_unpack(self, &p);
    return PyFloat_FromDouble(TimeStamp_abst(p.y, p.m - 1, p.d - 1, p.mi, 0)
                  + TimeStamp_sec(self) - gmoff);
}

static PyObject *
TimeStamp_raw(TimeStamp *self)
{
    return PyBytes_FromStringAndSize((const char*)self->data, 8);
}

static PyObject *
TimeStamp_repr(TimeStamp *self)
{
    PyObject *raw, *result;
    raw = TimeStamp_raw(self);
    result = PyObject_Repr(raw);
    Py_DECREF(raw);
    return result;
}

static PyObject *
TimeStamp_str(TimeStamp *self)
{
    char buf[128];
    TimeStampParts p;
    int len;

    TimeStamp_unpack(self, &p);
    len =sprintf(buf, "%4.4d-%2.2d-%2.2d %2.2d:%2.2d:%09.6f",
             p.y, p.m, p.d, p.mi / 60, p.mi % 60,
             TimeStamp_sec(self));

    return NATIVE_FROM_STRING_AND_SIZE(buf, len);
}


static PyObject *
TimeStamp_laterThan(TimeStamp *self, PyObject *obj)
{
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

    memcpy(new, o->data, 8);
    for (i = 7; i > 3; i--)
    {
        if (new[i] == 255)
            new[i] = 0;
        else
        {
            new[i]++;
            return TimeStamp_FromString((const char*)new);
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

    return TimeStamp_FromDate(p.y, p.m, p.d, p.mi / 60, p.mi % 60, 0);
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

#define DEFERRED_ADDRESS(ADDR) 0

static PyTypeObject TimeStamp_type =
{
    PyVarObject_HEAD_INIT(DEFERRED_ADDRESS(NULL), 0)
    "persistent.TimeStamp",
    sizeof(TimeStamp),                      /* tp_basicsize */
    0,                                      /* tp_itemsize */
    (destructor)TimeStamp_dealloc,          /* tp_dealloc */
    0,                                      /* tp_print */
    0,                                      /* tp_getattr */
    0,                                      /* tp_setattr */
    0,                                      /* tp_compare */
    (reprfunc)TimeStamp_repr,               /* tp_repr */
    0,                                      /* tp_as_number */
    0,                                      /* tp_as_sequence */
    0,                                      /* tp_as_mapping */
    (hashfunc)TimeStamp_hash,               /* tp_hash */
    0,                                      /* tp_call */
    (reprfunc)TimeStamp_str,                /* tp_str */
    0,                                      /* tp_getattro */
    0,                                      /* tp_setattro */
    0,                                      /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT |
    Py_TPFLAGS_BASETYPE |
    Py_TPFLAGS_HAVE_RICHCOMPARE,            /* tp_flags */
    0,                                      /* tp_doc */
    0,                                      /* tp_traverse */
    0,                                      /* tp_clear */
    (richcmpfunc)&TimeStamp_richcompare,    /* tp_richcompare */
    0,                                      /* tp_weaklistoffset */
    0,                                      /* tp_iter */
    0,                                      /* tp_iternext */
    TimeStamp_methods,                      /* tp_methods */
    0,                                      /* tp_members */
    0,                                      /* tp_getset */
    0,                                      /* tp_base */
    0,                                      /* tp_dict */
    0,                                      /* tp_descr_get */
    0,                                      /* tp_descr_set */
};

PyObject *
TimeStamp_FromString(const char *buf)
{
    /* buf must be exactly 8 characters */
    TimeStamp *ts = (TimeStamp *)PyObject_New(TimeStamp, &TimeStamp_type);
    memcpy(ts->data, buf, 8);
    return (PyObject *)ts;
}

#define CHECK_RANGE(VAR, LO, HI) if ((VAR) < (LO) || (VAR) > (HI)) { \
     return PyErr_Format(PyExc_ValueError, \
             # VAR " must be between %d and %d: %d", \
             (LO), (HI), (VAR)); \
    }

PyObject *
TimeStamp_FromDate(int year, int month, int day, int hour, int min,
           double sec)
{

    TimeStamp *ts = NULL;
    int d;
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
    d = days_in_month(year, month - 1);
    if (day < 1 || day > d)
        return PyErr_Format(PyExc_ValueError,
                    "day must be between 1 and %d: %d", d, day);
    CHECK_RANGE(hour, 0, 23);
    CHECK_RANGE(min, 0, 59);
    /* Seconds are allowed to be anything, so chill
       If we did want to be pickly, 60 would be a better choice.
    if (sec < 0 || sec > 59)
    return PyErr_Format(PyExc_ValueError,
                "second must be between 0 and 59: %f", sec);
    */
    ts = (TimeStamp *)PyObject_New(TimeStamp, &TimeStamp_type);
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
TimeStamp_TimeStamp(PyObject *obj, PyObject *args)
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
        return TimeStamp_FromString(buf);
    }
    PyErr_Clear();

    if (!PyArg_ParseTuple(args, "iii|iid", &y, &mo, &d, &h, &m, &sec))
        return NULL;
    return TimeStamp_FromDate(y, mo, d, h, m, sec);
}

static PyMethodDef TimeStampModule_functions[] =
{
    {"TimeStamp", TimeStamp_TimeStamp, METH_VARARGS},
    {NULL, NULL},
};

static struct PyModuleDef moduledef =
{
    PyModuleDef_HEAD_INIT,
    "_timestamp",               /* m_name */
    TimeStampModule_doc,        /* m_doc */
    -1,                         /* m_size */
    TimeStampModule_functions,  /* m_methods */
    NULL,                       /* m_reload */
    NULL,                       /* m_traverse */
    NULL,                       /* m_clear */
    NULL,                       /* m_free */
};


static PyObject*
module_init(void)
{
    PyObject *module;

    if (TimeStamp_init_gmoff() < 0)
        return NULL;

    module = PyModule_Create(&moduledef);
    if (module == NULL)
        return NULL;

    ((PyObject*)&TimeStamp_type)->ob_type = &PyType_Type;
    TimeStamp_type.tp_getattro = PyObject_GenericGetAttr;

    return module;
}

PyMODINIT_FUNC PyInit__timestamp(void)
{
    return module_init();
}
