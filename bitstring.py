#!/usr/bin/env python
"""
Module for bit-wise data manipulation.
http://python-bitstring.googlecode.com
"""

license = """
The MIT License

Copyright (c) 2006-2009 Scott Griffiths (scott@griffiths.name)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import array
import copy
import string
import os
import struct

os.SEEK_SET = 0 # For backward compatibility with Python 2.4

def _single_byte_from_hex_string(h):
    """Return a byte equal to the input hex string."""
    try:
        i = int(h, 16)
    except ValueError:
        raise ValueError("Can't convert hex string to a single byte")
    if len(h) > 2:
        raise ValueError("Hex string can't be more than one byte in size")
    if len(h) == 2:
        return struct.pack('B', i)  
    elif len(h) == 1:
        return struct.pack('B', i<<4)

def _single_byte_from_hex_string_unsafe(h):
    """Return a byte equal to the input 2 character hex string. No parameter checking done."""
    return struct.pack('B', int(h, 16))

def _hex_string_from_single_byte(b):
    """Return a two character hex string from a single byte value."""
    v = ord(b)
    if v > 15:
        return hex(v)[2:]
    elif v > 0:
        return '0'+hex(v)[2:]
    else:
        return '00'

def _tidyupinputstring(s):
    """Return string made lowercase and with all whitespace removed."""
    return string.join(s.split(), '').lower()


class BitStringError(Exception):
    """For errors in the bitstring module."""

class _FileArray(object):
    """A class that mimics the array.array type but gets data from a file object."""
    
    def __init__(self, filename, lengthinbits, offset):
        filelength = os.path.getsize(filename)
        self.source = file(filename, 'rb')
        if lengthinbits is None:
            length = filelength
        else:
            length = (lengthinbits + offset + 7)/8
        if length > filelength:
            raise ValueError("File is not long enough for specified BitString length")
        self._length = length # length in bytes
    
    def __len__(self):
        # This fails for > 4GB, so better to explictly disallow it!
        raise NotImplementedError

    def __copy__(self):
        raise BitStringError("_FileArray.copy() not allowed")
    
    def __getitem__(self, key):
        try:
            key.start
        except AttributeError:
            # single element
            if key >= self._length or key < -self._length:
                raise IndexError
            if key < 0:
                key = self._length + key
            self.source.seek(key, os.SEEK_SET)
            return ord(self.source.read(1))
        # A slice
        if key.step is not None:
            raise BitStringError("Step not supported for slicing BitStrings")
        if key.start is None:
            start = 0
        elif key.start < 0:
            start = self._length + key.start
        else:
            start = key.start
        if key.stop is None:
            stop = self._length
        elif key.stop < 0:
            stop = self._length + key.stop
        else:
            stop = key.stop
        if start < stop:
            self.source.seek(start, os.SEEK_SET)
            return self.source.read(stop-start)
        else:
            return ''
    
    def extend(self, data):
        raise NotImplementedError
    
    def append(self, data):
        raise NotImplementedError
    
    def length(self):
        return self._length
    
    def tostring(self):
        self.source.seek(0, os.SEEK_SET)
        return self.source.read(self._length)
    

class _MemArray(object):
    """A class that wraps the array.array functionality."""
    
    def __init__(self, data):
        self._data = array.array('B', data)
    
    def __len__(self):
        # Doesn't work for > 4GB.
        raise NotImplementedError

    def __copy__(self):
        return _MemArray(self._data)
    
    def __getitem__(self, key):
        return self._data.__getitem__(key)

    def __setitem__(self, key, item):
        self._data.__setitem__(key, item)
    
    def length(self):
        return len(self._data)
    
    def append(self, data):
        self._data.append(data)
        
    def extend(self, data):
        self._data.extend(data)
        
    def tostring(self):
        return self._data.tostring()


class BitString(object):
    """A class for general bit-wise manipulations and interpretations."""
    
    def __init__(self, auto = None, length = None, offset = 0, data = None,
                 filename = None, hex = None, bin = None, oct = None,
                 uint = None, int = None,  ue = None, se = None):
        """
        Initialise the BitString with one (and only one) of:
        auto -- string starting with '0x', '0o' or '0b' to be interpreted
                as hexadecimal, octal or binary respectively, or another BitString.
        data -- raw data as a string, for example read from binary file.
        bin -- binary string representation, e.g. '0b001010'.
        hex -- hexadecimal string representation, e.g. '0x2ef'
        oct -- octal string representation, e.g. '0o777'.
        uint -- an unsigned integer (length must be supplied).
        int -- a signed integer (length must be supplied).
        se -- a signed Exponential-Golomb code.
        ue -- an unsigned Exponential-Golomb code.
        filename -- a file which will be opened in binary read-only mode.
    
        Other keyword arguments:
        length -- length of the BitString in bits, if needed and appropriate.
        offset -- bit offset to the data (0 -> 7). These offset bits are ignored and
                  this is mainly intended for use when initialising using 'data'.
       
        e.g.
        a = BitString('0x123ab560')
        b = BitString(filename="movie.ts")
        c = BitString(int=10, length=6)
            
        """
        self._offset = offset
        self._pos = 0
        self._length = 0
        self._file = None
        if length is not None and length < 0:
            raise ValueError("length cannot be negative.")
        
        initialisers = [auto, data, filename, hex, bin, oct, int, uint, ue, se]
        initfuncs = [self._setauto, self._setdata, self._setfile,
                     self._sethexsafe, self._setbin, self._setoct,
                     self._setint, self._setuint, self._setue, self._setse]
        assert len(initialisers) == len(initfuncs)
        if initialisers.count(None) < len(initialisers) - 1:
            raise BitStringError("You must only specify one initialiser when initialising the BitString.")
        if (se is not None or ue is not None) and length is not None:
            raise BitStringError("A length cannot be specified for an Exponential-Golomb initialiser.")
        if (int or uint or ue or se) and offset != 0:
            raise BitStringError("offset cannot be specified when initialising from an integer.")
        if not 0 <= offset < 8:
            raise ValueError("offset must be between 0 and 7.")  
        if initialisers.count(None) == len(initialisers):
            # No initialisers, so initialise with nothing or zero bits
            if length is not None:
                data = '\x00'*((length+7)/8)
                self._setdata(data, length)
            else:
                self._setdata('')
        else:
            init = [(d, func) for (d, func) in zip(initialisers, initfuncs) if d is not None]
            assert len(init) == 1
            (d, func) = init[0]
            if length is not None:
                func(d, length)
            else:
                func(d)
        assert self._assertsanity()

    def __copy__(self):
        """Return a new copy of the BitString."""
        s_copy = BitString()
        s_copy._offset = self._offset
        s_copy._pos = self._pos
        s_copy._length = self._length
        if self._file is not None:
            raise BitStringError("Cannot copy file based BitStrings.")
        s_copy._datastore = copy.copy(self._datastore)
        return s_copy

    def __add__(self, bs):
        """Concatenate BitStrings and return new BitString.
        
        bs -- the BitString (or string for 'auto' initialiser) to append.
        
        """
        return self.__copy__().append(bs)
        
    def __iadd__(self, bs):
        """Append BitString to current BitString. Return self.
        
        bs -- the BitString (or string for 'auto' initialiser) to append.
        
        """
        return self.append(bs)

    def __setitem__(self, key, value):
        """Set item or range to new value.
        
        Indices are in bits.
        Stepping is not supported and use will raise a BitStringError.
        
        """
        if isinstance(value, str):
            value = BitString(value)
        if not isinstance(value, BitString):
            raise TypeError("BitString or string expected. Got %s." % type(value))
        try:
            key.start
        except AttributeError:
            # single element
            if key >= self._length or key < -self._length:
                raise IndexError
            oldpos = self._pos
            if key < 0:
                key = self._length + key
            self._pos = key
            if value._length == 1:
                self.overwrite(value)
            else:
                self.deletebits(1)
                self.insert(value)
            self._pos = oldpos
            return
        # A slice
        if key.step is not None:
            raise BitStringError("step not supported for slicing BitStrings.")
        if key.start is None:
            start = 0
        elif key.start < 0:
            start = self._length + key.start
        else:
            start = key.start
        if key.stop is None:
            stop = self._length
        elif key.stop < 0:
            stop = self._length + key.stop
        else:
            stop = key.stop
        oldpos = self._pos
        self._pos = start
        if start >= stop:
            raise IndexError
        if (stop - start) == value._length:
            self.overwrite(value)
        else:
            self.deletebits(stop - start)
            self.insert(value)
        return
    
    def __getitem__(self, key):
        """Return a new BitString representing a slice of the current BitString.
        
        Indices are in bits.
        Stepping is not supported and use will raise a BitStringError.
        
        """
        try:
            key.start
        except AttributeError:
            # single element
            if key >= self._length or key < -self._length:
                raise IndexError
            oldpos = self._pos
            if key < 0:
                key = self._length + key
            self._pos = key
            s = self.readbit()
            self._pos = oldpos
            return s
        # A slice
        if key.step is not None:
            raise BitStringError("step not supported for slicing BitStrings.")
        if key.start is None:
            start = 0
        elif key.start < 0:
            start = self._length + key.start
        else:
            start = key.start
        if key.stop is None:
            stop = self._length
        elif key.stop < 0:
            stop = self._length + key.stop
        else:
            stop = key.stop
        if start < stop:
            return self.slice(start, stop)
        else:
            return BitString()

    def __len__(self):
        """Return the length of the BitString in bits."""
        return self._getlength()

    def __str__(self):
        """Return approximate string representation of BitString for printing.
        
        If the BitString is an integer number of bytes then hexadecimal is used,
        otherwise binary is used. Long strings will be truncated with '...'.
        
        """
        if self._length == 0:
            return ''
        if self._length%8 == 0:
            if self._length <= 1024*8:
                return self._gethex()
            else:
                return self.slice(0, 1024*8)._gethex() + '...'
        else:
            if self._length <= 256*8:
                return self._getbin()
            else:
                return self.slice(0, 256*8)._getbin() + '...'
    
    def __eq__(self, bs):
        """Return True if and only if the two BitStrings have the same binary representation."""
        if not isinstance(bs, BitString):
            return False
        if self._length != bs._length:
            return False
        # Yes, I know how inefficient this could be in the worst case...
        if self._getbin() != bs._getbin():
            return False
        else:
            return True
    
    def __ne__(self, bs):
        """Return True if the two BitStrings do not have the same binary representation."""
        return not self.__eq__(bs)
    
    def __hex__(self):
        """Return the hexadecimal representation as a string prefixed with '0x'.
        
        Raises a ValueError if the BitString's length is not a multiple of 4.
        
        """
        return self._gethex()
    
    def __oct__(self):
        """Return the octal representation as a string prefixed with '0o'.
        
        Raises a ValueError if the BitString's length is not a multiple of 3.
        
        """
        return self._getoct()

    def __invert__(self):
        """Return BitString with every bit inverted.
        
        Raises BitStringError if the BitString is empty.
        
        """
        if self.empty():
            raise BitStringError("Cannot invert empty BitString.")
        s = BitString(int=~(self._getint()), length=self.length)
        return s

    def __lshift__(self, n):
        """Return BitString with bits shifted by n to the left.
        
        n -- the number of bits to shift. Must be >= 0.
        
        """
        if n < 0:
            raise ValueError("Cannot shift by a negative amount.")
        if self.empty():
            raise ValueError("Cannot shift an empty BitString.")
        s = self[n:].append(BitString(length = min(n, self._length)))
        return s
    
    def __ilshift__(self, n):
        """Shift bits by n to the left in place. Return self.
        
        n -- the number of bits to shift. Must be >= 0.
        
        """
        self._setbin(self.__lshift__(n)._getbin())
        return self

    def __rshift__(self, n):
        """Return BitString with bits shifted by n to the right.
        
        n -- the number of bits to shift. Must be >= 0.
        
        """
        if n < 0:
            raise ValueError("Cannot shift by a negative amount.")
        if self.empty():
            raise ValueError("Cannot shift an empty BitString.")
        s = BitString(length = min(n, self._length)).append(self[:-n])
        return s
    
    def __irshift__(self, n):
        """Shift bits by n to the right in place. Return self.
        
        n -- the number of bits to shift. Must be >= 0.
        
        """
        self._setbin(self.__rshift__(n)._getbin())
        return self
    
    def __mul__(self, n):
        """Return BitString consisting of n concatenations of self.
        
        Called for expression of the form 'a = b*3'.
        n -- The number of concatenations. Must be >= 0.
        
        """
        if not isinstance(n, int):
            raise TypeError("Can only multiply a BitString by an int, but %s was provided." % type(n))
        if n < 0:
            raise ValueError("Cannot multiply by a negative integer.")
        if n == 0:
            return BitString()
        s = BitString(self)
        for i in xrange(n-1):
            s.append(self)
        return s

    def __rmul__(self, n):
        """Return BitString consisting of n concatenations of self.
        
        Called for expressions of the form 'a = 3*b'.
        n -- The number of concatenations. Must be >= 0.
        
        """
        return self.__mul__(n)
    
    def __imul__(self, n):
        """Concatenate n copies of self in place. Return self.
        
        Called for expressions of the form 'a *= 3'.
        n -- The number of concatenations. Must be >= 0.
        
        """
        if not isinstance(n, int):
            raise TypeError("Can only multiply a BitString by an int, but %s was provided." % type(n))
        if n < 0:
            raise ValueError("Cannot multiply by a negative integer.")
        if n == 0:
            self._setdata('')
            return self
        s = BitString(self)
        for i in xrange(n-1):
            self.append(s)
        return self

    def _assertsanity(self):
        """Check internal self consistency as a debugging aid."""
        assert self._length >= 0
        assert 0 <= self._offset < 8
        if self._length == 0:
            assert self._datastore.length() <= 1
            assert self._pos == 0
        else:
            assert self._pos <= self._length
        assert (self._length + self._offset +7)/8 == self._datastore.length()
        if self._offset > 0:
            # initial unused bits should always be set to zero
            assert (self._datastore[0] >> (8-self._offset)) == 0
        bitsinfinalbyte = (self._offset + self._length)%8
        if bitsinfinalbyte > 0:
            # final unused bits should always be set to zero
            assert self._datastore[-1] & ((1 << (8-bitsinfinalbyte)) - 1) == 0
        return True
    
    def _setauto(self, s, length = None):
        """Set BitString from another BitString, or a binary, octal or hexadecimal string."""
        if isinstance(s, BitString):
            self.__init__(data=s._getdata(), length=s._length, offset=s._offset)
            return
        s = _tidyupinputstring(s)
        if not s:
            self._setdata('')
            return
        if s.startswith('0x'):
            s = s.replace('0x', '')
            self._sethexsafe(s, length)
            return
        if s.startswith('0b'):
            s = s.replace('0b', '')
            self._setbin(s, length)
            return
        if s.startswith('0o'):
            s = s.replace('0o', '')
            self._setoct(s, length)
            return
        raise ValueError("String '%s' cannot be interpreted as hexadecimal, binary or octal. "
                             "It must start with '0x', '0b' or '0o'." % s)

    def _setfile(self, filename, lengthinbits=None):
        "Use file as source of bits."
        # We disallow offsets as we would have to ensure that the initial and
        # final unused bits in the BitString are zeroed (which I haven't yet
        # worked out the best way of implementing)
        if self._offset > 0:
            raise ValueError("offset cannot be used for file-based BitStrings.")
        self._datastore = _FileArray(filename, lengthinbits, self._offset)
        if lengthinbits:
            self._length = lengthinbits
        else:
            self._length = self._datastore.length()*8 - self._offset

    def _setdata(self, data, length = None):
        """Set the data from a string."""
        self._datastore = _MemArray(data)
        if length is None:
            # Use to the end of the data
            self._length = self._datastore.length()*8 - self._offset
        else:
            self._length = length
            if self._length+self._offset < self._datastore.length()*8:
                # strip unused bytes from the end
                self._datastore = _MemArray(self._datastore[:(self._length+self._offset+7)/8])
            if self._length+self._offset > self._datastore.length()*8:
                raise ValueError("Not enough data present. Need %d bits, have %d." % \
                                     (self._length+self._offset, self._datastore.length()*8))
        self._setunusedbitstozero()
        assert self._assertsanity()

    def _getdata(self):
        """Return the data as an ordinary string."""
        self._setoffset(0)
        return self._datastore.tostring()

    def _setuint(self, uint, length=None):
        """Reset the BitString to have given unsigned int interpretation."""
        if length is None and self._length != 0:
            length = self._length
        if length is None or length == 0:
            raise ValueError("A non-zero length must be specified with a uint initialiser.")
        if uint >= (1 << length):
            raise ValueError("uint cannot be contained using BitString of that length.")
        if uint < 0:
            raise ValueError("uint cannot be initialsed by a negative number.")     
        hexstring = hex(uint)[2:]
        if hexstring[-1] == 'L':
            hexstring = hexstring[:-1]
        hexlengthneeded = (length+3)/4
        leadingzeros = hexlengthneeded - len(hexstring)
        if leadingzeros > 0:
            hexstring = '0'*leadingzeros + hexstring
        self._sethexunsafe(hexstring)
        self._offset = (4*hexlengthneeded) - length
        self._length = length

    def _getuint(self):
        """Return data as an unsigned int."""
        if self.empty():
            raise ValueError("An empty BitString cannot be interpreted as an unsigned integer")
        if self._datastore.length() == 1:
            mask = ((1<<self._length)-1)<<(8-self._length-self._offset)
            val = self._datastore[0] & mask
            val >>= 8 - self._offset - self._length
            return val
        firstbits = 8 - self._offset
        mask = (1<<firstbits) - 1
        val = self._datastore[0] & mask
        for j in xrange(1, self._datastore.length()-1):
            val <<= 8
            val += self._datastore[j]
        lastbyte = self._datastore[-1]
        bitsleft = (self._offset + self._length)%8
        if bitsleft == 0:
            bitsleft = 8
        val <<= bitsleft
        mask = 255 - ((1<<(8-bitsleft))-1)
        val += (lastbyte&mask)>>(8-bitsleft)
        return val

    def _setint(self, int, length=None):
        """Reset the BitString to have given signed int interpretation."""
        if length is None and self._length != 0:
            length = self._length
        if length is None or length == 0:
            raise ValueError("A non-zero length must be specified with an int initialiser.")
        if int >=  (1 << (length - 1)) or int < -(1 << (length - 1)):
            raise ValueError("int cannot be contained using BitString of that length.")   
        if int < 0:
            # the twos complement thing to get the equivalent +ive number
            int = (-int-1)^((1 << length) - 1)
        self._setuint(int, length)

    def _getint(self):
        """Return data as a two's complement signed int."""
        ui = self._getuint()
        if ui < (1 << (self._length - 1)):
            # Top bit not set - must be positive
            return ui
        tmp = (~(ui-1)) & ((1 << self._length)-1)
        return -tmp

    def _setue(self, i):
        """Initialise BitString with unsigned Exponential-Golomb code for i."""
        if i < 0:
            raise BitStringError("Cannot use negative initialiser for unsigned Exponential-Golomb.")
        if i == 0:
            self._setbin('1')
            return
        tmp = i + 1
        leadingzeros = -1
        while tmp > 0:
            tmp >>= 1
            leadingzeros += 1
        remainingpart = i + 1 - (1 << leadingzeros)
        binstring = '0'*leadingzeros + '1' + BitString(uint = remainingpart, length = leadingzeros).bin[2:]
        self._setbin(binstring)

    def _getue(self):
        """Return data as unsigned Exponential Golomb code."""
        oldpos = self._pos
        self._pos = 0
        try:
            value = self.readue()
            if self._pos != self._length:
                raise BitStringError
        except (BitStringError, ValueError):
            self._pos = oldpos
            raise BitStringError("BitString is not a single Exponential Golomb code.")
        self._pos = oldpos
        return value
    
    def _setse(self, i):
        """Initialise BitString with signed Exponential-Golomb code for i."""
        if i > 0:
            u = (i*2)-1
        else:
            u = -2*i
        self._setue(u)

    def _getse(self):
        """Read enough bits from current position to decode one Exponential Golomb code.
           Return the signed decoded value."""
        oldpos= self._pos
        self._pos = 0
        try:
            value = self.readse()
            if self._pos != self._length:
                raise BitStringError
        except (BitStringError, ValueError):
            self._pos = oldpos
            raise BitStringError("BitString is not a single Exponential Golomb code.")
        self._pos = oldpos
        return value
    
    def _setbin(self, binstring, length=None):
        """Reset the BitString to the value given in binstring."""
        binstring = _tidyupinputstring(binstring)
        # remove any 0b if present
        binstring = binstring.replace('0b', '')
        if length is None:
            length = len(binstring) - self._offset
        if length < 0 or length > (len(binstring) - self._offset):
            raise ValueError("Invalid length of binary string.")
        # Truncate the bin_string if needed
        binstring = binstring[self._offset:length+self._offset]
        self._length = length
        self._offset = 0
        if self._length == 0:
            self._datastore = _MemArray('')
            return
        # pad with zeros up to byte boundary if needed
        boundary = ((self._length + 7)/8)*8
        if len(binstring) < boundary:
            binstring += '0'*(boundary - self._length)
        try:
            bytes = [int(binstring[x:x+8], 2) for x in xrange(0, len(binstring), 8)]
        except ValueError:
            raise ValueError("Invalid character in binstring")
        self._datastore = _MemArray(bytes)
        self._setunusedbitstozero()
        assert self._assertsanity()

    def _getbin(self):
        """Return interpretation as a binary string."""
        if self._length == 0:
            return ''
        c = []
        if self._length != 0:
            # Horribly inefficient!
            i = self.uint
            for x in xrange(self._length):
                if i%2 == 1: c.append('1')
                else: c.append('0')
                i /= 2
        c.reverse()
        return '0b' + ''.join(c)
        
    def _setoct(self, octstring, length=None):
        """Reset the BitString to have the value given in octstring."""
        octstring = _tidyupinputstring(octstring)
        # remove any 0o if present
        octstring = octstring.replace('0o', '')
        if length is None:
            length = len(octstring)*3 - self._offset
        if length < 0 or length + self._offset > len(octstring)*3:
            raise ValueError("Invalid length %s, offset %d for oct initialiser %s" % (length, self._offset, octstring))
        octstring = octstring[0:(length + self._offset + 2)/3]
        self._length = length
        if self._length == 0:
            self._datastore = _MemArray('')
            return
        binlookup = ['000', '001', '010', '011', '100', '101', '110', '111']
        binlist = []
        for i in octstring:
            try:
                if not 0 <= int(i) < 8:
                    raise ValueError
                binlist.append(binlookup[int(i)])
            except ValueError:
                raise ValueError("Invalid symbol '%s' in oct initialiser." % i)
        self._setbin(''.join(binlist))
        
    def _getoct(self):
        """Return interpretation as an octal string."""
        if self._length%3 != 0:
            raise ValueError("Cannot convert to octal unambiguously - not multiple of 3 bits.")
        if self._length == 0:
            return ''
        oldbitpos = self._pos
        self._setbitpos(0)
        octlist = ['0o']
        for i in xrange(self._length/3):
            octlist.append(str(self.readbits(3).uint))
        self._pos = oldbitpos
        return ''.join(octlist)
    
    def _sethexsafe(self, hexstring, length=None):
        """Reset the BitString to have the value given in hexstring."""
        hexstring = _tidyupinputstring(hexstring)
        # remove any 0x if present
        hexstring = hexstring.replace('0x', '')
        if length is None:
            length = len(hexstring)*4 - self._offset
        if length < 0 or length + self._offset > len(hexstring)*4:
            raise ValueError("Invalid length %d, offset %d for hexstring %s." % (length, self._offset, hexstring))    
        hexstring = hexstring[0:(length + self._offset + 3)/4]
        self._length = length
        if self._length == 0:
            self._datastore = _MemArray('')
            return
        hexlist = []
        # First do the whole bytes
        for i in xrange(len(hexstring)/2):
            try:
                j = int(hexstring[i*2:i*2+2], 16) 
                if not 0 <= j < 256:
                    raise ValueError
                hexlist.append(_single_byte_from_hex_string(hexstring[i*2:i*2+2]))
            except ValueError:
                raise ValueError("Cannot convert to hexadecimal.")
        # then any remaining nibble
        if len(hexstring)%2 == 1:
            try:
                j = int(hexstring[-1], 16)
                if not 0 <= j < 16:
                    raise ValueError
                hexlist.append(_single_byte_from_hex_string(hexstring[-1]))
            except ValueError:
                raise ValueError("Cannot convert last digit to hexadecimal.")
        self._datastore = _MemArray(''.join(hexlist))
        self._setunusedbitstozero()
        assert self._assertsanity()
        
    def _sethexunsafe(self, hexstring, length=None):
        """Reset the BitString to have the value given in hexstring.
           Does not do parameter checking. Use _sethexsafe() unless you are sure of the input."""
        if length is None:
            length = len(hexstring)*4 - self._offset   
        self._length = length
        if self._length == 0:
            self._datastore = _MemArray('')
            return
        datastring = ""
        # First do the whole bytes
        for i in xrange(len(hexstring)/2):
            datastring += _single_byte_from_hex_string_unsafe(hexstring[i*2:i*2+2])
        # then any remaining nibble
        if len(hexstring)%2 == 1:
            datastring += _single_byte_from_hex_string(hexstring[-1])
        self._datastore = _MemArray(datastring)
        self._setunusedbitstozero()
        assert self._assertsanity()

    def _gethex(self):
        """Return the hexadecimal representation as a string prefixed with '0x'.
        
        Raises a ValueError if the BitString's length is not a multiple of 4.
        
        """        
        if self._length%4 != 0:
            raise ValueError("Cannot convert to hex unambiguously - not multiple of 4 bits.")
        if self._length == 0:
            return ''
        self._setoffset(0)
        s = self._datastore.tostring()
        hexstrings = [_hex_string_from_single_byte(i) for i in s]
        if (self._length/4)%2 == 1:
            # only a nibble left at the end
            hexstrings[-1] = hexstrings[-1][0]
        s = '0x'+''.join(hexstrings)
        return s  

    def _setbytepos(self, bytepos):
        """Move to absolute byte-aligned position in stream."""
        self._setbitpos(bytepos*8)

    def _getbytepos(self):
        """Return the current position in the stream in bytes. Must be byte aligned."""
        p = self._getbitpos()
        if p%8 != 0:
            raise BitStringError("Not byte aligned in _getbytepos().")
        return p/8

    def _setbitpos(self, bitpos):
        """Move to absolute postion bit in bitstream."""
        if bitpos < 0:
            raise ValueError("Bit position cannot be negative.")
        if bitpos > self._length:
            raise ValueError("Cannot seek past the end of the data.")
        self._pos = bitpos

    def _getbitpos(self):
        """Return the current position in the stream in bits."""
        assert 0 <= self._pos <= self._length
        return self._pos

    def _setoffset(self, offset):
        """Realign BitString with offset to first bit."""
        if offset == self._offset:
            return
        if not 0 <= offset < 8:
            raise ValueError("Can only align to an offset from 0 to 7.")
        assert 0 <= self._offset < 8
        if offset < self._offset:
            # We need to shift everything left
            shiftleft = self._offset - offset
            # First deal with everything except for the final byte
            for x in xrange(self._datastore.length() - 1):
                self._datastore[x] = ((self._datastore[x] << shiftleft)&255) + (self._datastore[x+1] >> (8 - shiftleft))
            # if we've shifted all of the data in the last byte then we need to truncate by 1
            bits_in_last_byte = (self._offset + self._length)%8
            if bits_in_last_byte == 0:
                bits_in_last_byte = 8
            if bits_in_last_byte <= shiftleft:
                self._datastore = _MemArray(self._datastore[:-1])
            # otherwise just shift the last byte
            else:
                self._datastore[-1] = (self._datastore[-1]<<shiftleft)&255
        else: # offset > self._offset
            shiftright = offset - self._offset
            # Give some overflow room for the last byte
            if (self._offset + self._length + shiftright + 7)/8 > (self._offset + self._length + 7)/8:
                self._datastore.append(0)
            for x in xrange(self._datastore.length()-1, 0, -1):
                self._datastore[x] = ((self._datastore[x-1] << (8 - shiftright))&255) + (self._datastore[x] >> shiftright)
            self._datastore[0] = self._datastore[0] >> shiftright
        self._offset = offset
        assert self._assertsanity()

    def _getoffset(self):
        """Return current offset."""
        return self._offset

    def _getlength(self):
        """Return the length of the BitString in bits."""
        assert self._length == 0 or 0 <= self._pos <= self._length
        return self._length
    
    def _setunusedbitstozero(self):
        """Set non data bits in first and last byte to zero."""
        # set unused bits in first byte to zero
        if self._offset > 0:
            self._datastore[0] &= (255 >> self._offset)
        # set unused bits at the end of the last byte to zero
        bits_used_in_final_byte = (self._offset + self._length)%8
        if bits_used_in_final_byte > 0:
            self._datastore[-1] &= 255 ^ (255 >> bits_used_in_final_byte)      
    
    def empty(self):
        """Return True if the BitString is empty (has zero length). Otherwise return False."""
        return self._length == 0
    
    def readbit(self):
        """Return next bit in BitString as new BitString and advance position.
        
        Raises ValueError if bitpos is at the end of the BitString.
        
        """
        return self.readbits(1)

    def readbits(self, bits):
        """Return next bits in BitString as a new BitString and advance position.
        
        bits -- The number of bits to read.
        
        Raises ValueError if there are not enough bits from bitpos to the end of the BitString.
        
        """
        if bits < 0:
            raise ValueError("Cannot read negative amount.")
        if self._pos+bits > self._length:
            raise ValueError("Reading off the end of the BitString.")
        newoffset = (self._pos+self._offset)%8
        startbyte = (self._pos+self._offset)/8
        endbyte = (self._pos+self._offset+bits-1)/8
        self._pos += bits
        assert self._assertsanity()
        return BitString(data = self._datastore[startbyte:endbyte+1], length = bits,
                         offset = newoffset) 
    
    def readbyte(self):
        """Return next 8 bits in BitString as a new BitString and advance position. Does not byte align.
        
        Raises ValueError if there are less than 8 bits from bitpos to the end of the BitString.
        
        """
        return self.readbits(8)
        
    def readbytes(self, bytes):
        """Return next bytes in BitString as a new BitString and advance position. Does not byte align.
        
        bytes -- The number of bytes to read.
        
        Raises ValueError if there are not enough bits from bitpos to the end of the BitString.
        
        """
        return self.readbits(bytes*8)

    def readue(self):
        """Return interpretation of next bits in stream as an unsigned Exponential Golomb code.
           
        Advances position to after the read code.
        Raises BitStringError if the end of the BitString is encountered while reading the code.
        
        """
        leadingzerobits = -1
        b = 0
        try:
            while b == 0:
                b = self.readbits(1).uint
                leadingzerobits += 1
        except ValueError:
            raise BitStringError("Read off end of BitString trying to read code.")
        codenum = (1 << leadingzerobits) - 1
        if leadingzerobits > 0:
            codenum += self.readbits(leadingzerobits).uint
        return codenum

    def readse(self):
        """Return interpretation of next bits in stream as a signed Exponential Golomb code.
        
        Advances position to after the read code.
        Raises BitStringError if the end of the BitString is encountered while reading the code.
        
        """
        codenum = self.readue()
        m = (codenum + 1)/2
        if codenum % 2 == 0:
            return -m
        else:
            return m

    def peekbit(self):
        """Return next bit in BitString as a new BitString without advancing position.
        
        Raises ValueError if bitpos is at the end of the BitString.
        
        """
        return self.peekbits(1)

    def peekbits(self, bits):
        """Return next bits in BitString as a new BitString without advancing position.
        
        bits -- The number of bits to read. Must be >= 0.
        
        Raises ValueError if there are not enough bits from bitpos to the end of the BitString.
        
        """
        bitpos = self._pos
        s = self.readbits(bits)
        self._pos = bitpos
        return s
    
    def peekbyte(self):
        """Return next byte in BitString as a new BitString without advancing position.
        
        Raises ValueError if there are not enough bits from bitpos to the end of the BitString.
        
        """
        return self.peekbits(8)
        
    def peekbytes(self, bytes):
        """Return next bytes in BitString as a new BitString without advancing position.
        
        bytes -- The number of bytes to read. Must be >= 0.
        
        Raises ValueError if there are not enough bits from bitpos to the end of the BitString.
        
        """
        return self.peekbits(bytes*8)

    def advancebit(self):
        """Advance position by one bit.
        
        Raises ValueError if bitpos is already past the last bit in the BitString.
        
        """
        self._setbitpos(self._pos + 1)

    def advancebits(self, bits):
        """Advance position by bits.
        
        bits -- Number of bits to increment bitpos by. Must be >= 0.
        
        Raises ValueError if bits negative or if bitpos goes past the end of the BitString.
        
        """
        if bits < 0:
            raise ValueError("Cannot advance by a negative amount.")
        self._setbitpos(self._pos + bits)

    def advancebyte(self):
        """Advance position by one byte. Does not byte align.
        
        Raises ValueError if there is less than one byte from bitpos to the end of the BitString.
        
        """
        self._setbitpos(self._pos + 8)

    def advancebytes(self, bytes):
        """Advance position by bytes. Does not byte align.
        
        bytes -- Number of bytes to increment bitpos by. Must be >= 0.
        
        Raises ValueError if there are not enough bytes from bitpos to the end of the BitString.
        
        """
        if bytes < 0:
            raise ValueError("Cannot advance by a negative amount.")
        self._setbitpos(self._pos + bytes*8)

    def retreatbit(self):
        """Retreat position by one bit.
        
        Raises ValueError if bitpos is already at the start of the BitString.
        
        """
        self._setbitpos(self._pos - 1)
 
    def retreatbits(self, bits):
        """Retreat position by bits.
        
        bits -- Number of bits to decrement bitpos by. Must be >= 0.
        
        Raises ValueError if bits negative or if bitpos goes past the start of the BitString.
        
        """
        if bits < 0:
            raise ValueError("Cannot retreat by a negative amount.")
        self._setbitpos(self._pos - bits)

    def retreatbyte(self):
        """Retreat position by one byte. Does not byte align.
        
        Raises ValueError if bitpos is less than 8.
        
        """
        self._setbitpos(self._pos - 8)

    def retreatbytes(self, bytes):
        """Retreat position by bytes. Does not byte align.
        
        bytes -- Number of bytes to decrement bitpos by. Must be >= 0.
        
        Raises ValueError if bytes negative or if bitpos goes past the start of the BitString.
        
        """
        if bytes < 0:
            raise ValueError("Cannot retreat by a negative amount.")
        self._setbitpos(self._pos - bytes*8)

    def find(self, bs):
        """Seek to start of next occurence of BitString. Return True if BitString is found.
        
        bs -- The BitString (or string for 'auto' initialiser) to find.
        
        """
        if isinstance(bs, str):
            bs = BitString(bs)         
        if bs.empty():
            raise ValueError("Can't find empty BitString.")
        oldpos = self._pos
        targetbin = bs.bin
        found = False
        for p in xrange(oldpos, self._length - bs._length + 1):
            if self[p:p+bs._length].bin == targetbin:
                found = True
                break
        if not found:
            self._pos = oldpos
            return False
        self._pos = p
        return True

    def findbytealigned(self, bs):
        """Seek to start of next occurence of byte-aligned BitString. Return True if string is found.
        
        bs -- The BitString (or string for 'auto' initialiser) to find.
        
        Raises ValueError if len(bs) is not a multiple of 8.
        
        """
        if isinstance(bs, str):
            bs = BitString(bs)
        if bs._length % 8 != 0:
            raise ValueError("Can only use find for whole-byte BitStrings.")
        # Extract data bytes from BitString to be found.
        bs._setoffset(0)
        d = bs.data
        if len(d) == 0:
            raise ValueError("Can't find empty BitString.")
        self._setoffset(0)
        oldpos = self._pos
        try:
            self.bytealign()
        except BitStringError:
            # Not even enough bits left to byte-align.
            self._pos = oldpos
            return False
        bytepos = self._pos/8
        found = False
        p = bytepos
        finalpos = self._length/8 - len(d) + 1
        while p < finalpos:
            if self[p*8:(p+len(d))*8].data == d:
                found = True
                break
            p += 1
        if not found:
            self._pos = oldpos
            return False
        self._setbytepos(p)
        assert self._assertsanity()
        return True

    def bytealign(self):
        """Align to next byte and return number of skipped bits.
        
        Raises ValueError if end of BitString reached before aligning to next byte.
        
        """
        skipped = (8 - ((self._pos)%8))%8
        self._setbitpos(self._pos + self._offset + skipped)
        assert self._assertsanity()
        return skipped

    def truncatestart(self, bits):
        """Truncate a number of bits from the start of the BitString. Return new BitString.
        
        bits -- Number of bits to remove from start of returned BitString.
        
        Raises ValueError if bits < 0 or bits > self.length.
        
        """
        if bits < 0 or bits > self._length:
            raise ValueError("Truncation length of %d not possible. Length = %d" % (bits, self._length))
        truncatedbytes = (bits+self._offset)/8
        self._offset = (self._offset + bits)%8
        self._setdata(self._datastore[bits/8:], length=self._length - bits)
        self._pos = max(0, self._pos - bits)
        assert self._assertsanity()
        return self

    def truncateend(self, bits):
        """Truncate a number of bits from the end of the BitString. Return new BitString.
        
        bits -- Number of bits to remove from end of returned BitString.
        
        Raises ValueError if bits < 0 or bits > self.length.
        
        """
        if bits < 0 or bits > self._length:
            raise ValueError("Truncation length of %d bits not possible. Length = %d." % (bits, self._length))
        new_length_in_bytes = (self._offset + self._length - bits + 7)/8
        # Ensure that the position is still valid
        self._pos = max(0, min(self._pos, self._length - bits))
        self._setdata(self._datastore[:new_length_in_bytes], length=self._length - bits)
        assert self._assertsanity()
        return self
    
    def slice(self, startbit, endbit):
        """Return a new BitString which is the slice [startbit, endbit).
        
        startbit -- Position of first bit in the new BitString.
        endbit -- One past the position of the last bit in the new BitString.
        
        Raises ValueError if endbit < startbit, if startbit < 0 or endbit > self.length.
        
        """
        if endbit < startbit:
            raise ValueError("Cannot slice - endbit is less than startbit.")
        if endbit == startbit:
            return BitString()
        if startbit < 0:
            raise ValueError("Cannot slice - startbit is less than zero.")
        if endbit > self._length:
            raise ValueError("Cannot slice - endbit is past the end of the BitString.")
        s = BitString()
        s._offset = (self._offset + startbit)%8
        startbyte = startbit/8
        new_length_in_bytes = (endbit - startbit + s._offset + 7)/8
        s._setdata(self._datastore[startbyte:startbyte+new_length_in_bytes])
        s._length = endbit - startbit
        s._pos = self._pos - startbit
        s._pos = max(0, min(s._pos, s._length-1))
        s._setunusedbitstozero()
        assert s._assertsanity()
        return s
    
    def insert(self, bs, bitpos=None):
        """Insert a BitString at current position, or bitpos if supplied. Return self.
        
        bs -- The BitString (or string for 'auto' initialiser) to insert.
        bitpos -- The bit position to insert the BitString.
        
        Raises ValueError if bitpos < 0 or bitpos > self.length.
        
        """
        if isinstance(bs, str):
            bs = BitString(bs)
        if bs.empty():
            return self
        if bs is self:
            bs = self.__copy__()
        if bitpos is None:
            bitpos = self._pos
        if bitpos < 0 or bitpos > self._length:
            raise ValueError("Invalid insert position.")
        end = self.slice(bitpos, self._length)
        self.truncateend(self._length - bitpos)
        self.append(bs)
        self.append(end)
        assert self._assertsanity()
        return self

    def overwrite(self, bs, bitpos=None):
        """Overwrite with new BitString at the current position, or bitpos if supplied. Return self.
        
        bs -- The BitString (or string for 'auto' initialiser) to overwrite with.
        bitpos -- The bit position to begin overwriting from.
        
        Raises ValueError if bitpos < 0 or bitpos + len(bs) > self.length
        
        """
        if isinstance(bs, str):
            bs = BitString(bs)
        if bs.empty():
            return self
        if bs is self:
            bs = self.__copy__()        
        if bitpos is None:
            bitpos = self._pos
        if bitpos < 0 or bitpos + bs._length > self._length:
            raise ValueError("Overwrite exceeds boundary of BitString.")
        end = self.slice(bitpos+bs._length, self._length)
        self.truncateend(self._length - bitpos)
        self.append(bs)
        self.append(end)
        self._pos = bitpos + bs._length
        assert self._assertsanity()
        return self
    
    def deletebits(self, bits, bitpos=None):
        """Delete number of bits at current position, or bitpos if supplied. Return self.
        
        bits -- Number of bits to delete.
        bitpos -- Bit position to delete from (default is self.bitpos).
        
        Raises ValueError if bits < 0 or if you try to delete past the end of the BitString.
        
        """
        if bitpos is None:
            bitpos = self._pos
        if bits < 0:
            raise ValueError("Cannott delete a negative number of bits.")
        if bits + bitpos > self.length:
            raise ValueError("Cannot delete past the end of the BitString.")
        end = self.slice(bitpos+bits, self._length)
        self.truncateend(self._length - bitpos)
        self.append(end)
        return self
    
    def deletebytes(self, bytes, bytepos=None):
        """Delete number of bytes at current position (must be byte-aligned), or bytepos if supplied. Return self.
        
        bytes -- Number of bytes to delete.
        bytepos -- Byte position to delete from (default is self.bytepos)
        
        Raises BitStringError if bytepos not specified and current position is not byte aligned.
        Raises ValueError if bytes < 0 or if you try to delete past the end of the BitString.
        
        """
        if bytepos is None and self._pos % 8 != 0:
            raise BitStringError("Must be byte-aligned for deletebytes().")
        if bytepos is None:
            bytepos = self._pos/8
        return self.deletebits(bytes*8, bytepos*8)

    def append(self, bs):
        """Append a BitString to the current BitString. Return self.
        
        bs -- The BitString (or string for 'auto' initialiser) to append.
        
        """
        if isinstance(bs, str):
            bs = BitString(bs)
        if bs.empty():
            return self
        if isinstance(self._datastore, _FileArray):
            # Can't modify file, so need to read it into memory.
            self._datastore = _MemArray(self._datastore[:])
        if bs is self:
            bs = self.__copy__()
        bits_in_final_byte = (self._offset + self._length)%8
        bs._setoffset(bits_in_final_byte)
        if bits_in_final_byte != 0:
            # first do the byte with the join.
            self._datastore[-1] = (self._datastore[-1] | bs._datastore[0])
        else:
            self._datastore.append(bs._datastore[0])
        self._datastore.extend(bs._datastore[1:bs._datastore.length()])
        self._length += bs._length
        assert self._assertsanity()
        return self
    
    def prepend(self, bs):
        """Prepend a BitString to the current BitString. Return self.
        
        bs -- The BitString (or string for 'auto' initialiser) to prepend.
        
        """
        if isinstance(bs, str):
            bs = BitString(bs)
        if bs.empty():
            return self
        if isinstance(self._datastore, _FileArray):
            # Can't modify file, so need to read it into memory.
            self._datastore = _MemArray(self._datastore[:])
        if bs is self:
            bs = self.__copy__()
        bits_in_final_byte = (bs._offset + bs._length)%8
        end = self.__copy__()
        end._setoffset(bits_in_final_byte)
        self._setdata(bs._getdata(), length=bs._length)
        if bits_in_final_byte != 0:
            self._datastore[-1] = (self._datastore[-1] | end._datastore[0])
        else:
            self._datastore.append(end._datastore[0])
        self._datastore.extend(end._datastore[1:end._datastore.length()])
        self._length += end._length
        assert self._assertsanity()
        return self
    
    def reversebits(self):
        """Reverse all bits in-place. Return self.
        
        Using on an empty BitString will have no effect.
        
        """
        self._setbin(self._getbin()[:1:-1])
        return self
    
    def split(self, delimiter):
        """Return a generator of BitStrings by splittling into substrings starting with a byte aligned delimiter.
        
        The first item returned is the initial bytes before the delimiter, which may be an empty BitString.
        
        delimiter -- The BitString (or string for 'auto' initialiser) used as the divider.
        
        Raises ValueError if the delimiter is not a whole number of bytes.
        
        """
        if isinstance(delimiter, str):
            delimiter = BitString(delimiter)
        if len(delimiter) == 0:
            raise ValueError("split delimiter cannot be null.")
        if len(delimiter)%8 != 0:
            raise ValueError("split delimiter must be whole number of bytes.")
        oldpos = self._pos
        self._pos = 0
        found = self.findbytealigned(delimiter)
        if not found:
            # Initial bits are the whole BitString
            self._pos = oldpos
            yield self.__copy__()
            return
        # yield the bytes before the first occurence of the delimiter, even if empty
        yield self[0:self._pos]
        startpos = self._pos
        while found:
            self._pos += len(delimiter)
            found = self.findbytealigned(delimiter)
            if not found:
                self._pos = oldpos
                yield self[startpos:]
                return
            yield self[startpos:self._pos]
            startpos = self._pos

    length = property(_getlength,
                      doc="The length of the BitString in bits.")
    offset = property(_getoffset,
                      doc="The offset of the BitString relative to the byte aligned underlying storage.")
    hex    = property(_gethex, _sethexsafe,
                      doc="The BitString as a hexadecimal string, prefixed with '0x' and including any leading zeros.")
    bin    = property(_getbin, _setbin,
                      doc="The BitString as a binary string, prefixed with '0b' and including any leading zeros.")
    oct    = property(_getoct, _setoct,
                      doc="The BitString as an octal string, prefixed with '0o' and including any leading zeros.")
    data   = property(_getdata, _setdata,
                      doc="The BitString as a ordinary string.")
    int    = property(_getint, _setint,
                      doc="The BitString as a two's complement signed int.")
    uint   = property(_getuint, _setuint,
                      doc="The BitString as an unsigned int.")
    ue     = property(_getue, _setue,
                      doc="The BitString as an unsigned Exponential-Golomb code.")
    se     = property(_getse, _setse,
                      doc="The BitString as a signed Exponential-Golomb code.")
    bitpos = property(_getbitpos, _setbitpos,
                      doc="The position in the BitString in bits.")
    bytepos= property(_getbytepos, _setbytepos,
                      doc="The position in the BitString in bytes.")


def join(bitstringlist):
    """Return the concatenation of the BitStrings in a list."""
    s = BitString()
    for bs in bitstringlist:
        s.append(bs)
    return s


if __name__=='__main__':
    print "Running bitsting module unit tests:"
    try:
        import test_bitstring
        test_bitstring.unittest.main(test_bitstring)
    except ImportError:
        print "Error: cannot find test_bitstring.py"
    