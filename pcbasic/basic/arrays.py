"""
PC-BASIC - arrays.py
Array variable management

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import struct

from . import error
from . import values
from .scalars import get_name_in_memory


class Arrays(object):

    def __init__(self, memory, values):
        """Initialise arrays."""
        self._memory = memory
        self._values = values
        self.clear()
        # OPTION BASE is unset
        self._base = None

    def __contains__(self, varname):
        """Check if a scalar has been defined."""
        return varname in self._dims

    def __iter__(self):
        """Return an iterable over all scalar names."""
        return self._dims.iterkeys()

    def __str__(self):
        """Debugging representation of variable dictionary."""
        return '\n'.join('%s%s: %s' % (n, v, str(self._buffers[n]).encode('hex')) for n, v in self._dims.iteritems())

    def clear(self):
        """Clear arrays."""
        self._dims = {}
        self._buffers = {}
        self._cache = {}
        self._array_memory = {}
        self.current = 0

    def erase(self, name):
        """Remove an array from memory."""
        if name not in self._dims:
            # IFC if array does not exist
            raise error.RunError(error.IFC)
        dimensions = self._dims[name]
        record_len = 1 + max(3, len(name)) + 3 + 2*len(dimensions)
        freed_bytes = self.array_len(dimensions) * values.size_bytes(name) + record_len
        erased_name_ptr, _ = self._array_memory[name]
        # delete buffers
        del self._dims[name]
        del self._buffers[name]
        del self._cache[name]
        del self._array_memory[name]
        # update memory model
        for name in self._array_memory:
            name_ptr, array_ptr = self._array_memory[name]
            if name_ptr > erased_name_ptr:
                self._array_memory[name] = name_ptr - freed_bytes, array_ptr - freed_bytes
        self.current -= freed_bytes

    def index(self, index, dimensions):
        """Return the flat index for a given dimensioned index."""
        bigindex = 0
        area = 1
        for i in range(len(index)):
            # dimensions is the *maximum index number*, regardless of self._base
            bigindex += area * (index[i] - self._base)
            area *= dimensions[i] + 1 - self._base
        return bigindex

    def array_len(self, dimensions):
        """Return the flat length for given dimensioned size."""
        return self.index(dimensions, dimensions) + 1

    def array_size_bytes(self, name):
        """Return the byte size of an array, if it exists. Return 0 otherwise."""
        try:
            dimensions = self._dims[name]
        except KeyError:
            return 0
        return self.array_len(dimensions) * values.size_bytes(name)

    def view_full_buffer(self, name):
        """Return a memoryview to a full array."""
        return memoryview(self._buffers[name])

    def dimensions(self, name):
        """Return the dimensions of an array."""
        return self._dims[name]

    def get_cache(self, name):
        """Retrieve the sprite cache for the given array."""
        return self._cache[name]

    def set_cache(self, name, item):
        """Store a sprite in the cache for a given array."""
        self._cache[name] = item

    def dim(self, name, dimensions):
        """Allocate array space for an array of given dimensioned size. Raise errors if duplicate name or illegal index value."""
        if self._base is None:
            self._base = 0
        if name in self._dims:
            raise error.RunError(error.DUPLICATE_DEFINITION)
        for d in dimensions:
            if d < 0:
                raise error.RunError(error.IFC)
            elif d < self._base:
                raise error.RunError(error.SUBSCRIPT_OUT_OF_RANGE)
        size = self.array_len(dimensions)
        # update memory model
        # first two bytes: chars of name or 0 if name is one byte long
        name_ptr = self.current
        record_len = 1 + max(3, len(name)) + 3 + 2*len(dimensions)
        array_ptr = name_ptr + record_len
        array_bytes = size * values.size_bytes(name)
        self._memory.check_free(record_len + array_bytes, error.OUT_OF_MEMORY)
        self.current += record_len + array_bytes
        self._array_memory[name] = (name_ptr, array_ptr)
        self._buffers[name] = bytearray(array_bytes)
        self._dims[name] = dimensions
        self._cache[name] = None

    def check_dim(self, name, index):
        """Check if an array has been allocated. If not, auto-allocate if indices are <= 10; raise error otherwise."""
        try:
            dimensions = self._dims[name]
        except KeyError:
            # auto-dimension - 0..10 or 1..10
            # this even fixes the dimensions if the index turns out to be out of range
            dimensions = [10] * len(index)
            self.dim(name, dimensions)
        lst = self._buffers[name]
        if len(index) != len(dimensions):
            raise error.RunError(error.SUBSCRIPT_OUT_OF_RANGE)
        for i, d in zip(index, dimensions):
            if i < 0:
                raise error.RunError(error.IFC)
            elif i < self._base or i > d:
                # dimensions is the *maximum index number*, regardless of self._base
                raise error.RunError(error.SUBSCRIPT_OUT_OF_RANGE)
        return dimensions, lst

    def clear_base(self):
        """Unset the array base."""
        self._base = None

    def base(self, base):
        """Set the array base to 0 or 1 (OPTION BASE). Raise error if already set."""
        if base not in (1, 0):
            # syntax error
            raise error.RunError(error.STX)
        if self._base is not None and base != self._base:
            # duplicate definition
            raise error.RunError(error.DUPLICATE_DEFINITION)
        self._base = base

    def view_buffer(self, name, index):
        """Return a memoryview to an array element."""
        dimensions, lst = self.check_dim(name, index)
        bigindex = self.index(index, dimensions)
        bytesize = values.size_bytes(name)
        return memoryview(lst)[bigindex*bytesize:(bigindex+1)*bytesize]

    def get(self, name, index):
        """Retrieve a view of the value of an array element."""
        # do not make a copy - we may end up with stale string pointers
        # due to garbage collection
        return self._values.create(self.view_buffer(name, index))

    def set(self, name, index, value):
        """Assign a value to an array element."""
        # copy value into array
        self.view_buffer(name, index)[:] = values.to_type(name[-1], value).to_bytes()
        # drop cache
        self._cache[name] = None

    def varptr(self, name, indices):
        """Retrieve the address of an array."""
        dimensions = self._dims[name]
        _, array_ptr = self._array_memory[name]
        # arrays are kept at the end of the var list
        return self._memory.var_current() + array_ptr + values.size_bytes(name) * self.index(indices, dimensions)

    def dereference(self, address):
        """Get a value for an array given its pointer address."""
        found_addr = -1
        found_name = None
        for name, data in self._array_memory.iteritems():
            addr = self._memory.var_current() + data[1]
            if addr > found_addr and addr <= address:
                found_addr = addr
                found_name = name
        if not found_name:
            return None
        lst = self._buffers[name]
        offset = address - found_addr
        return self._values.from_bytes(lst[offset : offset+values.size_bytes(name)])

    def get_memory(self, address):
        """Retrieve data from data memory: array space """
        name_addr = -1
        arr_addr = -1
        the_arr = None
        for name in self._array_memory:
            name_try, arr_try = self._array_memory[name]
            if name_try <= address and name_try > name_addr:
                name_addr, arr_addr = name_try, arr_try
                the_arr = name
        if the_arr is None:
            return -1
        var_current = self._memory.var_current()
        if address >= var_current + arr_addr:
            offset = address - arr_addr - var_current
            if offset >= self.array_size_bytes(the_arr):
                return -1
            byte_array = self._buffers[the_arr]
            return byte_array[offset]
        else:
            offset = address - name_addr - var_current
            if offset < max(3, len(the_arr))+1:
                return get_name_in_memory(the_arr, offset)
            else:
                offset -= max(3, len(the_arr))+1
                dimensions = self._dims[the_arr]
                data_rep = struct.pack('<HB', self.array_size_bytes(the_arr) + 1 + 2*len(dimensions), len(dimensions))
                for d in dimensions:
                    data_rep += struct.pack('<H', d + 1 - self._base)
                return data_rep[offset]

    def get_strings(self):
        """Return a list of views of string array elements."""
        return [memoryview(buf)[i:i+3]
                    for name, buf in self._buffers.iteritems()
                        if name[-1] == '$'
                            for i in range(0, len(buf), 3)]


    ###########################################################################
    # helper functions for Python interface

    def from_list(self, python_list, name):
        """Convert Python list to BASIC array."""
        self._from_list(python_list, name, [])

    def _from_list(self, python_list, name, index):
        """Convert Python list to BASIC array."""
        if not python_list:
            return
        if isinstance(python_list[0], list):
            for i, v in enumerate(python_list):
                self._from_list(v, name, index+[i+(self._base or 0)])
        else:
            for i, v in enumerate(python_list):
                self.set(name, index+[i+(self._base or 0)], self._values.from_value(v, name[-1]))

    def to_list(self, name):
        """Convert BASIC array to Python list."""
        if name in self._dims:
            indices = self._dims[name]
            return self._to_list(name, [], indices)
        else:
            return []

    def _to_list(self, name, index, remaining_dimensions):
        """Convert BASIC array to Python list."""
        if not remaining_dimensions:
            return []
        elif len(remaining_dimensions) == 1:
            return [self.get(name, index+[i+(self._base or 0)]).to_value() for i in xrange(remaining_dimensions[0])]
        else:
            return [self._to_list(name, index+[i+(self._base or 0)], remaining_dimensions[1:]) for i in xrange(remaining_dimensions[0])]
