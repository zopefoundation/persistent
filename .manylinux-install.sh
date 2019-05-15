#!/usr/bin/env bash

set -e -x

# Compile wheels
for PYBIN in /opt/python/*/bin; do
    if [[ "${PYBIN}" == *"cp27"* ]] || \
       [[ "${PYBIN}" == *"cp35"* ]] || \
       [[ "${PYBIN}" == *"cp36"* ]] || \
       [[ "${PYBIN}" == *"cp37"* ]]; then
        "${PYBIN}/pip" install -U pip setuptools wheel cffi
        "${PYBIN}/pip" install -e /io/
        "${PYBIN}/pip" wheel /io/ -w wheelhouse/
	rm -rf /io/build /io/*.egg-info
    fi
done

# Bundle external shared libraries into the wheels
for whl in wheelhouse/persistent*.whl; do
    auditwheel repair "$whl" -w /io/wheelhouse/
done
