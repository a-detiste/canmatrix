#!/usr/bin/env python

# Copyright (c) 2013, Eduard Broecker
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that
# the following conditions are met:
#
#    Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#    Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,   PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR  OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# TODO: Definitions should be disassembled

from __future__ import division
import math
import attr

if attr.__version__ < '17.4.0':
    raise "need attrs >= 17.4.0"

from collections import OrderedDict

import logging
import fnmatch

import decimal
defaultFloatFactory = decimal.Decimal


logger = logging.getLogger('root')
import bitstruct

from past.builtins import basestring
import copy


@attr.s
class BoardUnit(object):
    """
    Contains one Boardunit/ECU
    """

    name = attr.ib(type=str)
    comment = attr.ib(default=None)
    attributes = attr.ib(factory=dict, repr=False)

    def attribute(self, attributeName, db=None, default=None):
        """Get Board unit attribute by its name.

        :param str attributeName: attribute name.
        :param CanMatrix db: Optional database parameter to get global default attribute value.
        :param default: Default value if attribute doesn't exist.
        :return: Return the attribute value if found, else `default` or None
        """
        if attributeName in self.attributes:
            return self.attributes[attributeName]
        elif db is not None:
            if attributeName in db.buDefines:
                define = db.buDefines[attributeName]
                return define.defaultValue
        return default

    def addAttribute(self, attribute, value):
        """
        Add the Attribute to current Boardunit/ECU. If the attribute already exists, update the value.

        :param str attribute: Attribute name
        :param any value: Attribute value
        """
        self.attributes[attribute] = value

    def addComment(self, comment):
        """
        Set Board unit comment.

        :param str comment: BU comment/description.
        """
        self.comment = comment


def normalizeValueTable(table):
    return {int(k): v for k, v in table.items()}


@attr.s(cmp=False)
class Signal(object):
    """
    Represents a Signal in CAN Matrix.

    Signal has following attributes:

    * name
    * startBit, size (in Bits)
    * is_little_endian (1: Intel, 0: Motorola)
    * is_signed (bool)
    * factor, offset, min, max
    * receiver  (Boarunit/ECU-Name)
    * attributes, _values, unit, comment
    * _multiplex ('Multiplexor' or Number of Multiplex)
    """

    name = attr.ib(default = "")
#    float_factory = attr.ib(default=defaultFloatFactory)
    float_factory = defaultFloatFactory
    startBit = attr.ib(type=int, default=0)
    size = attr.ib(type=int, default = 0)
    is_little_endian = attr.ib(type=bool, default = True)
    is_signed = attr.ib(type=bool, default = True)
    offset = attr.ib(converter = float_factory, default = float_factory(0.0))
    factor = attr.ib(converter = float_factory, default = float_factory(1.0))

    #    offset = attr.ib(converter = float_factory, default = 0.0)

    min  = attr.ib(converter=float_factory)
    @min.default
    def setDefaultMin(self):
        return  self.calcMin()

    max =  attr.ib(converter = float_factory)
    @max.default
    def setDefaultMax(self):
        return  self.calcMax()

    unit = attr.ib(type=str, default ="")
    receiver = attr.ib(default = attr.Factory(list))
    comment = attr.ib(default = None)
    multiplex  = attr.ib(default = None)

    mux_value = attr.ib(default = None)
    is_float = attr.ib(type=bool, default=False)
    enumeration = attr.ib(type=str, default = None)
    comments = attr.ib(type=dict, default = attr.Factory(dict))
    attributes = attr.ib(type=dict, default = attr.Factory(dict))
    values = attr.ib(type=dict, converter=normalizeValueTable, default = attr.Factory(dict))
    calc_min_for_none = attr.ib(type=bool, default = True)
    calc_max_for_none = attr.ib(type=bool, default = True)
    muxValMax = attr.ib(default = 0)
    muxValMin = attr.ib(default = 0)
    muxerForSignal= attr.ib(type=str, default = None)

    def __attrs_post_init__(self):
        self.multiplex = self.multiplexSetter(self.multiplex)


    @property
    def spn(self):
        """Get signal J1939 SPN or None if not defined."""
        return self.attributes.get("SPN", None)

    def multiplexSetter(self, value):
        self.mux_val = None
        self.is_multiplexer = False
        if value is not None and value != 'Multiplexor':
            ret_multiplex = int(value)
            self.mux_val = int(value)
        else:  # is it valid for None too?
            self.is_multiplexer = True
            ret_multiplex = value
        return ret_multiplex

    def attribute(self, attributeName, db=None, default=None):
        """Get any Signal attribute by its name.

        :param str attributeName: attribute name, can be mandatory (ex: startBit, size) or optional (customer) attribute.
        :param CanMatrix db: Optional database parameter to get global default attribute value.
        :param default: Default value if attribute doesn't exist.
        :return: Return the attribute value if found, else `default` or None
        """
        if attributeName in attr.fields_dict(type(self)):
            return getattr(self, attributeName)
        if attributeName in self.attributes:
            return self.attributes[attributeName]
        if db is not None:
            if attributeName in db.signalDefines:
                define = db.signalDefines[attributeName]
                return define.defaultValue
        return default

    def addComment(self, comment):
        """
        Set signal description.

        :param str comment: description
        """
        self.comment = comment

    def addReceiver(self, receiver):
        """Add signal receiver (ECU).

        :param str receiver: ECU name.
        """
        if receiver not in self.receiver:
            self.receiver.append(receiver)

    def delReceiver(self, receiver):
        """
        Remove receiver (ECU) from signal

        :param str receiver: ECU name.
        """
        if receiver in self.receiver:
            self.receiver.remove(receiver)

    def addAttribute(self, attribute, value):
        """
        Add user defined attribute to the Signal. Update the value if the attribute already exists.

        :param str attribute: attribute name
        :param value: attribute value
        """
        self.attributes[attribute] = value

    def delAttribute(self, attribute):
        """
        Remove user defined attribute from Signal.

        :param str attribute: attribute name
        """
        if attribute in self.attributes:
            del self.attributes[attribute]

    def addValues(self, value, valueName):
        """
        Add named Value Description to the Signal.

        :param int value: signal value (0xFF)
        :param str valueName: Human readable value description ("Init")
        """
        self.values[int(value)] = valueName

    def setStartbit(self, startBit, bitNumbering=None, startLittle=None):
        """
        Set startBit.

        bitNumbering is 1 for LSB0/LSBFirst, 0 for MSB0/MSBFirst.
        If bit numbering is consistent with byte order (little=LSB0, big=MSB0)
        (KCD, SYM), start bit unmodified.
        Otherwise reverse bit numbering. For DBC, ArXML (OSEK),
        both little endian and big endian use LSB0.
        If bitNumbering is None, assume consistent with byte order.
        If startLittle is set, given startBit is assumed start from lsb bit
        rather than the start of the signal data in the message data.
        """
        # bit numbering not consistent with byte order. reverse
        if bitNumbering is not None and bitNumbering != self.is_little_endian:
            startBit = startBit - (startBit % 8) + 7 - (startBit % 8)
        # if given startBit is for the end of signal data (lsbit),
        # convert to start of signal data (msbit)
        if startLittle is True and self.is_little_endian is False:
            startBit = startBit + 1 - self.size
        if startBit < 0:
            print("wrong startBit found Signal: %s Startbit: %d" %
                  (self.name, startBit))
            raise Exception("startBit lower zero")
        self.startBit = startBit

    def getStartbit(self, bitNumbering=None, startLittle=None):
        """Get signal start bit. Handle byte and bit order."""
        startBitInternal = self.startBit
        # convert from big endian start bit at
        # start bit(msbit) to end bit(lsbit)
        if startLittle is True and self.is_little_endian is False:
            startBitInternal = startBitInternal + self.size - 1
        # bit numbering not consistent with byte order. reverse
        if bitNumbering is not None and bitNumbering != self.is_little_endian:
            startBitInternal = startBitInternal - (startBitInternal % 8) + 7 - (startBitInternal % 8)
        return int(startBitInternal)

    def calculateRawRange(self):
        """Compute raw signal range based on Signal bit width and whether the Signal is signed or not.

        :return: Signal range, i.e. (0, 15) for unsigned 4 bit Signal or (-8, 7) for signed one.
        :rtype: tuple
        """
        rawRange = 2 ** (self.size - (1 if self.is_signed else 0))
        return (self.float_factory(-rawRange if self.is_signed else 0),
                self.float_factory(rawRange - 1))

    def setMin(self, min=None):
        """Set minimal physical Signal value.

        :param float min: minimal physical value. If None, compute using `calcMin`
        """
        self.min = min
        if self.calc_min_for_none and self.min is None:
            self.min = self.calcMin()

        return self.min

    def calcMin(self):
        """Compute minimal physical Signal value based on offset and factor and `calculateRawRange`."""
        rawMin = self.calculateRawRange()[0]

        return self.offset + (rawMin * self.factor)

    def setMax(self, max=None):
        """Set maximal signal value.

        :param float max: minimal physical value. If None, compute using `calcMax`
        """
        self.max = max

        if self.calc_max_for_none and self.max is None:
            self.max = self.calcMax()

        return self.max

    def calcMax(self):
        """Compute maximal physical Signal value based on offset, factor and `calculateRawRange`."""
        rawMax = self.calculateRawRange()[1]

        return self.offset + (rawMax * self.factor)

    def bitstruct_format(self):
        """Get the bit struct format for this signal.

        :return: bitstruct representation of the Signal
        :rtype: str
        """
        endian = '<' if self.is_little_endian else '>'
        if self.is_float:
            bit_type = 'f'
        else:
            bit_type = 's' if self.is_signed else 'u'

        return endian + bit_type + str(self.size)

    def phys2raw(self, value=None):
        """Return the raw value (= as is on CAN).

        :param value: (scaled) value compatible with `decimal` or value choice to encode
        :return: raw unscaled value as it appears on the bus
        :rtype: int or decimal.Decimal
        """
        if value is None:
            return int(self.attributes.get('GenSigStartValue', 0))

        if isinstance(value, basestring):
            for value_key, value_string in self.values.items():
                if value_string == value:
                    value = value_key
                    break
            else:
                raise ValueError(
                        "{} is invalid value choice for {}".format(value, self)
                )

        if not (self.min <= value <= self.max):
            logger.info(
                "Value {} is not valid for {}. Min={} and Max={}".format(
                    value, self, self.min, self.max)
                )
        raw_value = (value - self.offset) / self.factor

        if not self.is_float:
            raw_value = int(raw_value)
        return raw_value

    def raw2phys(self, value, decodeToStr=False):
        """Decode the given raw value (= as is on CAN).

        :param value: raw value compatible with `decimal`.
        :param bool decodeToStr: If True, try to get value representation as *string* ('Init' etc.)
        :return: physical value (scaled)
        """

        if self.is_float:
            value = self.float_factory(value)
        value = value * self.factor + self.offset
        if decodeToStr:
            for value_key, value_string in self.values.items():
                if value_key == value:
                    value = value_string
                    break

        return value

    def __str__(self):
        return self.name


@attr.s(cmp=False)
class SignalGroup(object):
    """
    Represents signal-group, containing multiple Signals.
    """
    name = attr.ib(type=str)
    id = attr.ib(type=int)
    signals = attr.ib(factory=list, repr=False)

    def addSignal(self, signal):
        """Add a Signal to SignalGroup.

        :param Signal signal: signal to add
        """
        if signal not in self.signals:
            self.signals.append(signal)

    def delSignal(self, signal):
        """Remove Signal from SignalGroup.

        :param Signal signal: signal to remove
        """
        if signal in self.signals:
            self.signals.remove(signal)

    def byName(self, name):
        """
        Find a Signal in the group by Signal name.

        :param str name: Signal name to find
        :return: signal contained in the group identified by name
        :rtype: Signal
        """
        for test in self.signals:
            if test.name == name:
                return test
        return None

    def __iter__(self):
        """Iterate over all contained signals."""
        return iter(self.signals)

    def __getitem__(self, name):
        signal = self.byName(name)
        if signal:
            return signal
        raise KeyError("Signal '{}' doesn't exist".format(name))


@attr.s(cmp=False)
class Frame(object):
    """
    Contains one CAN Frame.

    The Frame has  following mandatory attributes

    * id,
    * name,
    * transmitters (list of boardunits/ECU-names),
    * size (= DLC),
    * signals (list of signal-objects),
    * attributes (list of attributes),
    * receiver (list of boardunits/ECU-names),
    * extended (Extended Frame = 1),
    * comment

    and any *custom* attributes in `attributes` dict.

    Frame signals can be accessed using the iterator.
    """

    name = attr.ib(default="")
    id = attr.ib(type=int, default = 0)
    size = attr.ib(default = 0)
    transmitters = attr.ib(default = attr.Factory(list))
    extended = attr.ib(type=bool, default = False)
    is_complex_multiplexed = attr.ib(type=bool, default = False)
    is_fd = attr.ib(type=bool, default = False)
    comment = attr.ib(default="")
    signals = attr.ib(default = attr.Factory(list))
    mux_names = attr.ib(type=dict, default = attr.Factory(dict))
    attributes = attr.ib(type=dict, default = attr.Factory(dict))
    receiver = attr.ib(default = attr.Factory(list))
    signalGroups = attr.ib(default = attr.Factory(list))

    j1939_pgn = attr.ib(default = None)
    j1939_source = attr.ib(default = 0)
    j1939_prio  = attr.ib(default = 0)
    is_j1939  = attr.ib(type=bool, default = False)
            #            ('cycleTime', '_cycleTime', int, None),
            #            ('sendType', '_sendType', str, None),

    @property
    def is_multiplexed(self):
        """Frame is multiplexed if at least one of its signals is a multiplexer."""
        for sig in self.signals:
            if sig.is_multiplexer:
                return True
        return False

    @property
    def pgn(self):
        return CanId(self.id).pgn

    @pgn.setter
    def pgn(self, value):
        self.j1939_pgn = value
        self.recalcJ1939Id()

    @property
    def priority(self):
        """Get J1939 priority."""
        return self._j1939_prio

    @priority.setter
    def priority(self, value):
        """Set J1939 priority."""
        self._j1939_prio = value
        self.recalcJ1939Id()

    @property
    def source(self):
        """Get J1939 source."""
        return self._j1939_source

    @source.setter
    def source(self, value):
        """Set J1939 source."""
        self._j1939_source = value
        self.recalcJ1939Id()

    def recalcJ1939Id(self):
        """Recompute J1939 ID"""
        self.id = (self.j1939_source & 0xff) + ((self.j1939_pgn & 0xffff) << 8) + ((self.j1939_prio & 0x7) << 26)
        self.extended = True
        self.is_j1939 = True

    #    @property
#    def cycleTime(self):
#        if self._cycleTime is None:
#            self._cycleTime = self.attribute("GenMsgCycleTime")
#        return self._cycleTime

#    @property
#    def sendType(self, db = None):
#        if self._sendType is None:
#            self._sendType = self.attribute("GenMsgSendType")
 #       return self._sendType

#    @cycleTime.setter
#    def cycleTime(self, value):
#        self._cycleTime = value
#        self.attributes["GenMsgCycleTime"] = value

#    @sendType.setter
#    def sendType(self, value):
 #       self._sendType = value
 #       self.attributes["GenMsgCycleTime"] = value



    def attribute(self, attributeName, db=None, default=None):
        """Get any Frame attribute by its name.

        :param str attributeName: attribute name, can be mandatory (ex: id) or optional (customer) attribute.
        :param CanMatrix db: Optional database parameter to get global default attribute value.
        :param default: Default value if attribute doesn't exist.
        :return: Return the attribute value if found, else `default` or None
        """
        if attributeName in attr.fields_dict(type(self)):
            return getattr(self, attributeName)
        if attributeName in self.attributes:
            return self.attributes[attributeName]
        elif db is not None:
            if attributeName in db.frameDefines:
                define = db.frameDefines[attributeName]
                return define.defaultValue
        else:
            return default

    def __iter__(self):
        """Iterator over all signals."""
        return iter(self.signals)

    def addSignalGroup(self, Name, Id, signalNames):
        """Add new SignalGroup to the Frame. Add given signals to the group.

        :param str Name: Group name
        :param int Id: Group id
        :param list of str signalNames: list of Signal names to add. Non existing names are ignored.
        """
        newGroup = SignalGroup(Name, Id)
        self.signalGroups.append(newGroup)
        for signal in signalNames:
            signal = signal.strip()
            if signal.__len__() == 0:
                continue
            signalId = self.signalByName(signal)
            if signalId is not None:
                newGroup.addSignal(signalId)

    def signalGroupByName(self, name):
        """Get signal group.

        :param str name: group name
        :return: SignalGroup by name or None if not found.
        :rtype: SignalGroup
        """
        for signalGroup in self.signalGroups:
            if signalGroup.name == name:
                return signalGroup
        return None

    def addSignal(self, signal):
        """
        Add Signal to Frame.

        :param Signal signal: Signal to be added.
        :return: the signal added.
        """
        self.signals.append(signal)
        return self.signals[len(self.signals) - 1]

    def addTransmitter(self, transmitter):
        """Add transmitter ECU Name to Frame.

        :param str transmitter: transmitter name
        """
        if transmitter not in self.transmitters:
            self.transmitters.append(transmitter)

    def delTransmitter(self, transmitter):
        """Delete transmitter ECU Name from Frame.

        :param str transmitter: transmitter name
        """
        if transmitter in self.transmitters:
            self.transmitters.remove(transmitter)

    def addReceiver(self, receiver):
        """Add receiver ECU Name to Frame.

        :param str receiver: receiver name
        """
        if receiver not in self.receiver:
            self.receiver.append(receiver)

    def signalByName(self, name):
        """
        Get signal by name.

        :param str name: signal name to be found.
        :return: signal with given name or None if not found
        """
        for signal in self.signals:
            if signal.name == name:
                return signal
        return None

    def globSignals(self, globStr):
        """Find Frame Signals by a name pattern.

        :param str globStr: pattern for signal name. See `fnmatch.fnmatchcase`
        :return: list of Signals by name pattern.
        :rtype: list of Signal
        """
        returnArray = []
        for signal in self.signals:
            if fnmatch.fnmatchcase(signal.name, globStr):
                returnArray.append(signal)
        return returnArray

    def addAttribute(self, attribute, value):
        """
        Add the attribute with value to customer Frame attribute-list. If Attribute already exits, modify its value.
        :param str attribute: Attribute name
        :param any value: attribute value
        """
        try:
            self.attributes[attribute] = str(value)
        except UnicodeDecodeError:
            self.attributes[attribute] = value

    def delAttribute(self, attribute):
        """
        Remove attribute from customer Frame attribute-list.

        :param str attribute: Attribute name
        """
        if attribute in self.attributes:
            del self.attributes[attribute]

    def addComment(self, comment):
        """
        Set Frame comment.

        :param str comment: Frame comment
        """
        self.comment = comment

    def calcDLC(self):
        """
        Compute minimal Frame DLC (length) based on its Signals

        :return: Message DLC
        """
        maxBit = 0
        for sig in self.signals:
            if sig.getStartbit() + int(sig.size) > maxBit:
                maxBit = sig.getStartbit() + int(sig.size)
        self.size = max(self.size, int(math.ceil(maxBit / 8)))

    def findNotUsedBits(self):
        """
        Find unused bits in frame

        :return: dict with position and length-tuples
        """
        bitfield = []
        bitfieldLe = []
        bitfieldBe = []

        for i in range(0,64):
            bitfieldBe.append(0)
            bitfieldLe.append(0)
            bitfield.append(0)
        i = 0

        for sig in self.signals:
            i += 1
            for bit in range(sig.getStartbit(),  sig.getStartbit() + int(sig.size)):
                if sig.is_little_endian:
                    bitfieldLe[bit] = i
                else:
                    bitfieldBe[bit] = i

        for i in range(0,8):
            for j in range(0,8):
                bitfield[i*8+j] = bitfieldLe[i*8+(7-j)]

        for i in range(0,8):
            for j in range(0,8):
                if bitfield[i*8+j] == 0:
                    bitfield[i*8+j] = bitfieldBe[i*8+j]


        return bitfield

    def createDummySignals(self):
        """Create dummy signals for unused bits.

        Names of dummy signals are *_Dummy_<frame.name>_<index>*
        """
        bitfield = self.findNotUsedBits()
#        for i in range(0,8):
#            print (bitfield[(i)*8:(i+1)*8])
        startBit = -1
        sigCount = 0
        for i in range(0,64):
            if bitfield[i] == 0 and startBit == -1:
                startBit = i
            if (i == 63 or bitfield[i] != 0) and startBit != -1:
                if i == 63:
                    i = 64
                self.addSignal(Signal("_Dummy_%s_%d" % (self.name,sigCount),size=i-startBit, startBit=startBit, is_little_endian = False))
                startBit = -1
                sigCount +=1

#        bitfield = self.findNotUsedBits()
#        for i in range(0,8):
#            print (bitfield[(i)*8:(i+1)*8])




    def updateReceiver(self):
        """
        Collect Frame receivers out of receiver given in each signal. Add them to `self.receiver` list.
        """
        for sig in self.signals:
            for receiver in sig.receiver:
                self.addReceiver(receiver)

    def bitstruct_format(self, signalsToDecode = None):
        """Returns the Bitstruct format string of this frame

        :return: Bitstruct format string.
        :rtype: str
        """
        fmt = []
        frame_size = self.size * 8
        end = frame_size
        if signalsToDecode is None:
            signals = sorted(self.signals, key=lambda s: s.getStartbit())
        else:
            signals = sorted(signalsToDecode, key=lambda s: s.getStartbit())

        for signal in signals:
            start = frame_size - signal.getStartbit() - signal.size
            padding = end - (start + signal.size)
            if padding > 0:
                fmt.append('p' + str(padding))
            fmt.append(signal.bitstruct_format())
            end = start
        if end != 0:
            fmt.append('p' + str(end))
        # assert bitstruct.calcsize(''.join(fmt)) == frame_size
        return ''.join(fmt)

    def encode(self, data=None):
        """Return a byte string containing the values from data packed
        according to the frame format.

        :param dict data: data dictionary
        :return: A byte string of the packed values.
        :rtype: bitstruct
        """
        data = dict() if data is None else data

        if self.is_complex_multiplexed:
            # TODO
            pass
        elif self.is_multiplexed:
            # search for mulitplexer-signal
            muxSignal = None
            for signal in self.signals:
                if signal.is_multiplexer:
                    muxSignal = signal
                    muxVal = data.get(signal.name)
            # create list of signals which belong to muxgroup
            encodeSignals = [muxSignal]
            for signal in self.signals:
                if signal.mux_val == muxVal or signal.mux_val is None:
                    encodeSignals.append(signal)
            fmt = self.bitstruct_format(encodeSignals)
            signals = sorted(encodeSignals, key=lambda s: s.getStartbit())
        else:
            fmt = self.bitstruct_format()
            signals = sorted(self.signals, key=lambda s: s.getStartbit())
        signal_value = []
        for signal in signals:
            signal_value.append(
                signal.phys2raw(data.get(signal.name))
            )

        return bitstruct.pack(fmt, *signal_value)

    def decode(self, data, decodeToStr=False):
        """Return OrderedDictionary with Signal Name: Signal Value

        :param data: Iterable or bytes.
            i.e. (0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8)
        :param bool decodeToStr: If True, try to get value representation as *string* ('Init' etc.)
        :return: OrderedDictionary
        """
        if self.is_complex_multiplexed:
            # TODO
            pass
        elif self.is_multiplexed:
            # find multiplexer and decode only its value:
            for signal in self.signals:
                if signal.is_multiplexer:
                    fmt = self.bitstruct_format([signal])
                    signals = sorted(self.signals, key=lambda s: s.getStartbit())
                    signals_values = OrderedDict()
                    for signal, value in zip(signals, bitstruct.unpack(fmt, data)):
                        signals_values[signal.name] = signal.raw2phys(value, decodeToStr)
                muxVal = int(list(signals_values.values())[0])
            # find all signals with the identified multiplexer-value
            muxedSignals = []
            for signal in self.signals:
                if signal.mux_val == muxVal or signal.mux_val is None:
                    muxedSignals.append(signal)
            fmt = self.bitstruct_format(muxedSignals)
            signals = sorted(muxedSignals, key=lambda s: s.getStartbit())
        else:
            fmt = self.bitstruct_format()
            signals = sorted(self.signals, key=lambda s: s.getStartbit())

        #decode
        signals_values = OrderedDict()
        for signal, value in zip(signals, bitstruct.unpack(fmt, data)):
            signals_values[signal.name] = signal.raw2phys(value, decodeToStr)

        return signals_values


    def __str__(self):
        """Represent the frame by its name only."""
        return self.name  # add more details than the name only?


class Define(object):
    """
    Hold the defines and default-values.
    """

    def __init__(self, definition):
        """Initialize Define object.

        :param str definition: definition string. Ex: "INT -5 10"
        """
        definition = definition.strip()
        self.definition = definition
        self.type = None
        self.defaultValue = None

        def safeConvertStrToInt(inStr):
            """Convert string to int safely. Check that it isn't float.

            :param str inStr: integer represented as string.
            :rtype: int
            """
            out = int(defaultFloatFactory(inStr))
            if out != defaultFloatFactory(inStr):
                logger.warning("Warning, integer was expected but got float: got: {0} using {1}\n".format(inStr, str(out)))
            return out

        # for any known type:
        if definition[0:3] == 'INT':
            self.type = 'INT'
            min, max = definition[4:].split(' ', 2)
            self.min = safeConvertStrToInt(min)
            self.max = safeConvertStrToInt(max)

        elif definition[0:6] == 'STRING':
            self.type = 'STRING'
            self.min = None
            self.max = None

        elif definition[0:4] == 'ENUM':
            self.type = 'ENUM'
            tempValues = definition[5:].split(',')
            self.values = []
            for value in tempValues:
                value = value.strip()
                if value[0] == '"':
                    value = value[1:]
                if value[-1] == '"':
                    value = value[:-1]
                self.values.append(value)

        elif definition[0:3] == 'HEX':
            self.type = 'HEX'
            min, max = definition[4:].split(' ', 2)
            self.min = safeConvertStrToInt(min)  # TODO check: the same for INT and HEX?
            self.max = safeConvertStrToInt(max)

        elif definition[0:5] == 'FLOAT':
            self.type = 'FLOAT'
            min, max = definition[6:].split(' ', 2)
            self.min = defaultFloatFactory(min)
            self.max = defaultFloatFactory(max)


    def setDefault(self, default):
        """Set Definition default value.

        :param default: default value; number, str or quoted str ("value")
        """
        if default is not None and len(default) > 1 and default[0] == '"' and default[-1] =='"':
            default = default[1:-1]
        self.defaultValue = default

    def update(self):
        """Update definition string for type ENUM.

        For type ENUM rebuild the definition string from current values. Otherwise do nothing.
        """
        if self.type != 'ENUM':
            return
        self.definition = 'ENUM "' + '","' .join(self.values) +'"'


@attr.s(cmp=False)
class CanMatrix(object):
    """
    The Can-Matrix-Object
    attributes (global canmatrix-attributes),
    boardUnits (list of boardunits/ECUs),
    frames (list of Frames)
    signalDefines (list of signal-attribute types)
    frameDefines (list of frame-attribute types)
    buDefines (list of BoardUnit-attribute types)
    globalDefines (list of global attribute types)
    valueTables (global defined values)
    """

    attributes = attr.ib(type=dict, default= attr.Factory(dict))
    boardUnits = attr.ib(default = attr.Factory(list))
    frames = attr.ib(default = attr.Factory(list))

    signalDefines = attr.ib(default = attr.Factory(dict))
    frameDefines = attr.ib(default = attr.Factory(dict))
    globalDefines = attr.ib(default = attr.Factory(dict))
    buDefines = attr.ib(default = attr.Factory(dict))
    valueTables = attr.ib(default = attr.Factory(dict))
    envVars = attr.ib(default = attr.Factory(dict))

    load_errors = attr.ib(factory=list)

    def __iter__(self):
        """Matrix iterates over Frames (Messages)."""
        return iter(self.frames)

    def addEnvVar(self, name, envVarDict):
        self.envVars[name] = envVarDict

    @property
    def contains_fd(self):
        for frame in self.frames:
            if frame.is_fd:
                return True
        return False

    @property
    def contains_j1939(self):
        """Check whether the Matrix contains any J1939 Frame."""
        for frame in self.frames:
            if frame.is_j1939:
                return True
        return False


    def attribute(self, attributeName, default=None):
        """Return custom Matrix attribute by name.

        :param str attributeName: attribute name
        :param default: default value if given attribute doesn't exist
        :return: attribute value or default or None if no such attribute found.
        """
        if attributeName in self.attributes:
            return self.attributes[attributeName]
        else:
            if attributeName in self.globalDefines:
                define = self.globalDefines[attributeName]
                return define.defaultValue

    def addValueTable(self, name, valueTable):
        """Add named value table.

        :param str name: value table name
        :param valueTable: value table itself
        """
        self.valueTables[name] = normalizeValueTable(valueTable)

    def addAttribute(self, attribute, value):
        """
        Add attribute to Matrix attribute-list.

        :param str attribute: attribute name
        :param value: attribute value
        """
        self.attributes[attribute] = value

    def addSignalDefines(self, type, definition):
        """
        Add signal-attribute definition to canmatrix.

        :param str type: signal type
        :param str definition: signal-attribute string definition, see class Define
        """
        if type not in self.signalDefines:
            self.signalDefines[type] = Define(definition)

    def addFrameDefines(self, type, definition):
        """
        Add frame-attribute definition to canmatrix.

        :param str type: frame type
        :param str definition: frame definition as string
        """
        if type not in self.frameDefines:
            self.frameDefines[type] = Define(definition)

    def addBUDefines(self, type, definition):
        """
        Add Boardunit-attribute definition to canmatrix.

        :param str type: Boardunit type
        :param str definition: BU definition as string
        """
        if type not in self.buDefines:
            self.buDefines[type] = Define(definition)

    def addGlobalDefines(self, type, definition):
        """
        Add global-attribute definition to canmatrix.

        :param str type: attribute type
        :param str definition: attribute definition as string
        """
        if type not in self.globalDefines:
            self.globalDefines[type] = Define(definition)

    def addDefineDefault(self, name, value):
        if name in self.signalDefines:
            self.signalDefines[name].setDefault(value)
        if name in self.frameDefines:
            self.frameDefines[name].setDefault(value)
        if name in self.buDefines:
            self.buDefines[name].setDefault(value)
        if name in self.globalDefines:
            self.globalDefines[name].setDefault(value)

    def deleteObsoleteDefines(self):
        """Delete all unused Defines.

        Delete them from frameDefines, buDefines and signalDefines.
        """
        toBeDeleted = []
        for frameDef in self.frameDefines:
            found = False
            for frame in self.frames:
                if frameDef in frame.attributes:
                    found = True
                    break
            if found is False and found not in toBeDeleted:
                toBeDeleted.append(frameDef)
        for element in toBeDeleted:
            del self.frameDefines[element]
        toBeDeleted = []
        for buDef in self.buDefines:
            found = False
            for ecu in self.boardUnits:
                if buDef in ecu.attributes:
                    found = True
                    break
            if found is False and found not in toBeDeleted:
                toBeDeleted.append(buDef)
        for element in toBeDeleted:
            del self.buDefines[element]

        toBeDeleted = []
        for signalDef in self.signalDefines:
            found = False
            for frame in self.frames:
                for signal in frame.signals:
                    if signalDef in signal.attributes:
                        found = True
                        break
            if found is False and found not in toBeDeleted:
                toBeDeleted.append(signalDef)
        for element in toBeDeleted:
            del self.signalDefines[element]

    def frameById(self, Id, extended=None):
        """Get Frame by its arbitration id.

        :param Id: Frame id as str or int
        :param extended: is it an extended id? None means "doesn't matter"
        :rtype: Frame or None
        """
        Id = int(Id)
        extendedMarker = 0x80000000
        for test in self.frames:
            if test.id == Id:
                if extended is None:
                    # found ID while ignoring extended or standard
                    return test
                elif test.extended == extended:
                    # found ID while checking extended or standard
                    return test
            else:
                if extended is not None:
                    # what to do if Id is not equal and extended is also provided ???
                    pass
                else:
                    if test.extended and Id & extendedMarker:
                        # check regarding common used extended Bit 31
                        if test.id == Id - extendedMarker:
                            return test
        return None

    def frameByName(self, name):
        """Get Frame by name.

        :param str name: Frame name to search for
        :rtype: Frame or None
        """
        for test in self.frames:
            if test.name == name:
                return test
        return None

    def globFrames(self, globStr):
        """Find Frames by given name pattern.

        :param str globStr: Frame name pattern to be filtered. See `fnmatch.fnmatchcase`.
        :rtype: list of Frame
        """
        returnArray = []
        for test in self.frames:
            if fnmatch.fnmatchcase(test.name, globStr):
                returnArray.append(test)
        return returnArray

    def boardUnitByName(self, name):
        """
        Returns Boardunit by Name.

        :param str name: BoardUnit name
        :rtype: BoardUnit or None
        """
        for test in self.boardUnits:
            if test.name == name:
                return test
        return None

    def globBoardUnits(self, globStr):
        """
        Find ECUs by given name pattern.

        :param globStr: BoardUnit name pattern to be filtered. See `fnmatch.fnmatchcase`.
        :rtype: list of BoardUnit
        """
        returnArray = []
        for test in self.boardUnits:
            if fnmatch.fnmatchcase(test.name, globStr):
                returnArray.append(test)
        return returnArray

    def addFrame(self, frame):
        """Add the Frame to the Matrix.

        :param Frame frame: Frame to add
        :return: the inserted Frame
        """
        self.frames.append(frame)
        return self.frames[len(self.frames) - 1]

    def removeFrame(self, frame):
        """Remove the Frame from Matrix.

        :param Frame frame: frame to remove from CAN Matrix
        """
        self.frames.remove(frame)

    def deleteZeroSignals(self):
        """Delete all signals with zero bit width from all Frames."""
        for frame in self.frames:
            for signal in frame.signals:
                if 0 == signal.size:
                    frame.signals.remove(signal)

    def delSignalAttributes(self, unwantedAttributes):
        """Delete Signal attributes from all Signals of all Frames.

        :param list of str unwantedAttributes: List of attributes to remove
        """
        for frame in self.frames:
            for signal in frame.signals:
                for attrib in unwantedAttributes:
                    signal.delAttribute(attrib)

    def delFrameAttributes(self, unwantedAttributes):
        """Delete Frame attributes from all Frames.

        :param list of str unwantedAttributes: List of attributes to remove
        """
        for frame in self.frames:
            for attrib in unwantedAttributes:
                frame.delAttribute(attrib)

    def recalcDLC(self, strategy):
        """Recompute DLC of all Frames.

        :param str strategy: selected strategy, "max" or "force".
        """
        for frame in self.frames:
            originalDlc = frame.size  # unused, remove?
            if "max" == strategy:
                frame.calcDLC()
            if "force" == strategy:
                maxBit = 0
                for sig in frame.signals:
                    if sig.getStartbit() + int(sig.size) > maxBit:
                        maxBit = sig.getStartbit() + int(sig.size)
                frame.size = math.ceil(maxBit / 8)

    def renameEcu(self, old, newName):
        """Rename ECU in the Matrix. Update references in all Frames.

        :param str or BoardUnit old: old name or ECU instance
        :param str newName: new name
        """
        if type(old).__name__ == 'instance':
            pass
        else:
            old = self.boardUnitByName(old)
        if old is None:
            return
        oldName = old.name
        old.name = newName
        for frame in self.frames:
            if oldName in frame.transmitters:
                frame.transmitters.remove(oldName)
                frame.addTransmitter(newName)
            for signal in frame.signals:
                if oldName in signal.receiver:
                    signal.receiver.remove(oldName)
                    signal.addReceiver(newName)
            frame.updateReceiver()

    def addEcu(self, ecu):
        """Add new ECU to the Matrix. Do nothing if ecu with the same name already exists.

        :param BoardUnit ecu: ECU name to add
        """
        for bu in self.boardUnits:
            if bu.name.strip() == ecu.name:
                return
        self.boardUnits.append(ecu)

    def delEcu(self, ecu):
        """Remove ECU from Matrix and all Frames.

        :param str or BoardUnit ecu: ECU name pattern or instance to remove from list
        """
        if type(ecu).__name__ == 'instance':
            ecuList = [ecu]
        else:
            ecuList = self.globBoardUnits(ecu)

        for ecu in ecuList:
            if ecu in self.boardUnits:
                self.boardUnits.remove(ecu)
                for frame in self.frames:
                    if ecu.name in frame.transmitters:
                        frame.transmitters.remove(ecu.name)
                    for signal in frame.signals:
                        if ecu.name in signal.receiver:
                            signal.receiver.remove(ecu.name)
                    frame.updateReceiver()

    def updateEcuList(self):
        """Check all Frames and add unknown ECUs to the Matrix ECU list."""
        for frame in self.frames:
            for ecu in frame.transmitters:
                self.addEcu(BoardUnit(ecu))
            frame.updateReceiver()
            for signal in frame.signals:
                for ecu in signal.receiver:
                    self.addEcu(BoardUnit(ecu))

    def renameFrame(self, old, newName):
        """Rename Frame.

        :param Frame or str old: Old Frame instance or name or part of the name with '*' at the beginning or the end.
        :param str newName: new Frame name, suffix or prefix
        """
        if type(old).__name__ == 'instance':
            old = old.name
        for frame in self.frames:
            if old[-1] == '*':
                oldPrefixLen = len(old)-1
                if frame.name[:oldPrefixLen] == old[:-1]:
                    frame.name = newName + frame.name[oldPrefixLen:]
            if old[0] == '*':
                oldSuffixLen = len(old)-1
                if frame.name[-oldSuffixLen:] == old[1:]:
                    frame.name = frame.name[:-oldSuffixLen] + newName
            elif frame.name == old:
                frame.name = newName

    def delFrame(self, frame):
        """Delete Frame from Matrix.

        :param Frame or str frame: Frame or name to delete"""
        if type(frame).__name__ == 'instance' or type(frame).__name__ == 'Frame':
            pass
        else:
            frame = self.frameByName(frame)
        self.frames.remove(frame)

    def renameSignal(self, old, newName):
        """Rename Signal.

        :param Signal or str old: Old Signal instance or name or part of the name with '*' at the beginning or the end.
        :param str newName: new Signal name, suffix or prefix
        """
        if type(old).__name__ == 'instance' or type(old).__name__ == 'Signal':
            old.name = newName
        else:
            for frame in self.frames:
                if old[-1] == '*':
                    oldPrefixLen = len(old) - 1
                    for signal in frame.signals:
                        if signal.name[:oldPrefixLen] == old[:-1]:
                            signal.name = newName + signal.name[oldPrefixLen:]
                if old[0] == '*':
                    oldSuffixLen = len(old) - 1
                    for signal in frame.signals:
                        if signal.name[-oldSuffixLen:] == old[1:]:
                            signal.name = signal.name[:-oldSuffixLen] + newName

                else:
                    signal = frame.signalByName(old)
                    if signal is not None:
                        signal.name = newName

    def delSignal(self, signal):
        """Delete Signal from Matrix and all Frames.

        :param Signal or str signal: Signal instance or signal name to be deleted"""
        if type(signal).__name__ == 'instance' or type(signal).__name__ == 'Signal':
            for frame in self.frames:
                if signal in frame.signals:
                    frame.signals.remove(signal)
        else:
            for frame in self.frames:
                signalList = frame.globSignals(signal)
                for sig in signalList:
                    frame.signals.remove(sig)

    def addSignalReceiver(self, framePattern, signalName, ecu):
        """Add Receiver to all Frames by name pattern.

        :param str framePattern: Frame name pattern
        :param str signalName: signal name
        :param str ecu: Receiver ECU name
        """
        frames = self.globFrames(framePattern)
        for frame in frames:
            for signal in frame.globSignals(signalName):
                signal.addReceiver(ecu)
            frame.updateReceiver()

    def delSignalReceiver(self, framePattern, signalName, ecu):
        """Delete Receiver from all Frames by name pattern.

        :param str framePattern: Frame name pattern
        :param str signalName: signal name
        :param str ecu: Receiver ECU name
        """
        frames = self.globFrames(framePattern)
        for frame in frames:
            for signal in frame.globSignals(signalName):
                signal.delReceiver(ecu)
            frame.updateReceiver()

    def addFrameTransmitter(self, framePattern, ecu):
        """Add Transmitter to all Frames by name pattern.

        :param str framePattern: Frame name pattern
        :param str ecu: Receiver ECU name
        """
        frames = self.globFrames(framePattern)
        for frame in frames:
            frame.addTransmitter(ecu)

    def addFrameReceiver(self, framePattern, ecu):
        """Add Receiver to all Frames by name pattern.

        :param str framePattern: Frame name pattern
        :param str ecu: Receiver ECU name
        """
        frames = self.globFrames(framePattern)
        for frame in frames:
            for signal in frame.signals:
                signal.addReceiver(ecu)

    def delFrameTransmitter(self, framePattern, ecu):
        """Delete Transmitter from all Frames by name pattern.

        :param str framePattern: Frame name pattern
        :param str ecu: Receiver ECU name
        """
        frames = self.globFrames(framePattern)
        for frame in frames:
            frame.delTransmitter(ecu)

    def merge(self, mergeArray):
        """Merge multiple Matrices to this Matrix.

        Try to copy all Frames and all environment variables from source Matrices. Don't make duplicates.
        Log collisions.

        :param list of Matrix mergeArray: list of source CAN Matrices to be merged to to self.
        """
        for dbTemp in mergeArray:
            for frame in dbTemp.frames:
                copyResult = copy.copyFrame(frame.id, dbTemp, self)
                if copyResult == False:
                    logger.error(
                        "ID Conflict, could not copy/merge frame " + frame.name + "  %xh " % frame.id + self.frameById(frame.id).name)
            for envVar in dbTemp.envVars:
                if envVar not in self.envVars:
                    self.addEnvVar(envVar, dbTemp.envVars[envVar])
                else:
                    logger.error(
                        "Name Conflict, could not copy/merge EnvVar " + envVar)

    def setFdType(self):
        """Try to guess and set the CAN type for every frame.

        If a Frame is longer than 8 bytes, it must be Flexible Data Rate frame (CAN-FD).
        If not, the Frame type stays unchanged.
        """
        for frame in self.frames:
            if frame.size > 8:
                frame.is_fd = True

    def encode(self, frame_id, data):
        """Return a byte string containing the values from data packed
        according to the frame format.

        :param frame_id: frame id
        :param data: data dictionary
        :return: A byte string of the packed values.
        """
        return self.frameById(frame_id).encode(data)

    def decode(self, frame_id, data, decodeToStr=False):
        """Return OrderedDictionary with Signal Name: Signal Value

        :param frame_id: frame id
        :param data: Iterable or bytes.
            i.e. (0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8)
        :return: OrderedDictionary
        """
        return self.frameById(frame_id).decode(data, decodeToStr)

    def EnumAttribs2Values(self):
        for define in self.buDefines:
            if self.buDefines[define].type == "ENUM":
                for bu in self.boardUnits:
                    if define in bu.attributes:
                        bu.attributes[define] = self.buDefines[define].values[int(bu.attributes[define])]

        for define in self.frameDefines:
            if self.frameDefines[define].type == "ENUM":
                for frame in self.frames:
                    if define in frame.attributes:
                        frame.attributes[define] = self.frameDefines[define].values[int(frame.attributes[define])]

        for define in self.signalDefines:
            if self.signalDefines[define].type == "ENUM":
                for frame in self.frames:
                    for signal in frame.signals:
                        if define in signal.attributes:
                            signal.attributes[define] = self.signalDefines[define].values[int(signal.attributes[define])]

    def EnumAttribs2Keys(self):
        for define in self.buDefines:
            if self.buDefines[define].type == "ENUM":
                for bu in self.boardUnits:
                    if define in bu.attributes:
                        if len(bu.attributes[define]) > 0:
                            bu.attributes[define] = self.buDefines[define].values.index(bu.attributes[define])
                            bu.attributes[define] = str(bu.attributes[define])
        for define in self.frameDefines:
            if self.frameDefines[define].type == "ENUM":
                for frame in self.frames:
                    if define in frame.attributes:
                        if len(frame.attributes[define]) > 0:
                            frame.attributes[define] = self.frameDefines[define].values.index(frame.attributes[define])
                            frame.attributes[define] = str(frame.attributes[define])
        for define in self.signalDefines:
            if self.signalDefines[define].type == "ENUM":
                for frame in self.frames:
                    for signal in frame.signals:
                        if define in signal.attributes:
                            signal.attributes[define] = self.signalDefines[define].values.index(signal.attributes[define])
                            signal.attributes[define] = str(signal.attributes[define])
#
#
#
def computeSignalValueInFrame(startBit, ln, fmt, value):
    """
    Compute the Signal value in the Frame.

    :param int startBit: signal start bit
    :param int ln: signal length
    :param int fmt: byte order, 1 for Little Endian (Intel), else Big Endian (Motorola)
    :param int value: signal value
    :return: data frame with signal set to value
    :rtype: int
    """

    frame = 0
    if fmt == 1:  # Intel
    # using "sawtooth bit counting policy" here
        pos = ((7 - (startBit % 8)) + 8*(int(startBit/8)))
        while ln > 0:
            # How many bits can we stuff in current byte?
            #  (Should be 8 for anything but the first loop)
            availbitsInByte = 1 + (pos % 8)
            # extract relevant bits from value
            valueInByte = value & ((1<<availbitsInByte)-1)
            # stuff relevant bits into frame at the "corresponding inverted bit"
            posInFrame = ((7 - (pos % 8)) + 8*(int(pos/8)))
            frame |= valueInByte << posInFrame
            # move to the next byte
            pos += 0xf
            # discard used bytes
            value = value >> availbitsInByte
            # reduce length by how many bits we consumed
            ln -= availbitsInByte

    else:  # Motorola
        # Work this out in "sequential bit counting policy"
        # Compute the LSB position in "sequential"
        lsbpos = ((7 - (startBit % 8)) + 8*(int(startBit/8)))
        # deduce the MSB position
        msbpos = 1 + lsbpos - ln
        # "reverse" the value
        cvalue = int(format(value, 'b')[::-1],2)
        # shift the value to the proper position in the frame
        frame = cvalue << msbpos

    # Return frame, to be accumulated by caller
    return frame


class CanId(object):
    """
    Split Id into Global source addresses (source, destination) off ECU and PGN (SAE J1939).
    """
    # TODO link to BoardUnit/ECU
    source = None  # Source Address
    destination = None  # Destination Address
    pgn = None  # PGN

    def __init__(self, id, extended=True):
        if extended:
            self.source = id & int('0xFF', 16)
            self.pgn = (id >> 8) & int('0xFFFF', 16)
            self.destination = id >> 8 * 3 & int('0xFF', 16)
        else:
            # TODO implement for standard Id
            pass

    def tuples(self):
        """Get tuple (destination, PGN, source)

        :rtype: tuple"""
        return self.destination, self.pgn, self.source

    def __str__(self):
        return "DA:{da:#02X} PGN:{pgn:#04X} SA:{sa:#02X}".format(
            da=self.destination, pgn=self.pgn, sa=self.source)
