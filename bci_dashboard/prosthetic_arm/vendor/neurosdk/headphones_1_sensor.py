from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.amp_sensor import AmpSensor
from neurosdk.cmn_types import *
from neurosdk.neuro_smart_sensor import NeuroSmartSensor
from neurosdk.resist_sensor import ResistSensor
from neurosdk.sensor import Sensor, _neuro_lib
from neurosdk.signal_sensor import SignalSensor


class Headphones1Sensor(SignalSensor, ResistSensor, AmpSensor, NeuroSmartSensor):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.readAmplifierParamHeadphones.argtypes = [SensorPointer, POINTER(NativeHeadphonesAmplifierParam),
                                                            POINTER(OpStatus)]
        _neuro_lib.readAmplifierParamHeadphones.restype = c_uint8
        _neuro_lib.writeAmplifierParamHeadphones.argtypes = [SensorPointer, NativeHeadphonesAmplifierParam,
                                                             POINTER(OpStatus)]
        _neuro_lib.writeAmplifierParamHeadphones.restype = c_uint8
        _neuro_lib.addResistCallbackHeadphones.argtypes = [SensorPointer, ResistCallbackHeadphones, c_void_p,
                                                           ctypes.py_object, POINTER(OpStatus)]
        _neuro_lib.addResistCallbackHeadphones.restype = c_uint8
        _neuro_lib.removeResistCallbackHeadphones.argtypes = [HeadphonesResistDataListenerHandle]
        _neuro_lib.removeResistCallbackHeadphones.restype = c_void_p
        _neuro_lib.addSignalDataCallbackHeadphones.argtypes = [SensorPointer, SignalDataCallbackHeadphones, c_void_p,
                                                               ctypes.py_object, POINTER(OpStatus)]
        _neuro_lib.addSignalDataCallbackHeadphones.restype = c_uint8
        _neuro_lib.removeSignalDataCallbackHeadphones.argtypes = [HeadphonesSignalDataListenerHandle]
        _neuro_lib.removeSignalDataCallbackHeadphones.restype = c_void_p

    def set_signal_callbacks(self):
        self.__add_signal_data_callback_headphones()

    def unset_signal_callbacks(self):
        _neuro_lib.removeSignalDataCallbackHeadphones(self.__signalDataCallbackHeadphonesHandle)

    def set_resist_callbacks(self):
        self.__add_resist_callback_headphones()

    def unset_resist_callbacks(self):
        _neuro_lib.removeResistCallbackHeadphones(self.__resistCallbackHeadphonesHandle)

    def __add_resist_callback_headphones(self):
        def __py_resist_callback_headphones(ptr, data, sz_data, user_data):
            resist_data = [HeadphonesResistData(PackNum=int(data[i].PackNum),
                                                Ch1=float(data[i].Ch1),
                                                Ch2=float(data[i].Ch2),
                                                Ch3=float(data[i].Ch3),
                                                Ch4=float(data[i].Ch4),
                                                Ch5=float(data[i].Ch5),
                                                Ch6=float(data[i].Ch6),
                                                Ch7=float(data[i].Ch7)) for i in range(sz_data)]
            if user_data.resistDataReceived is not None:
                user_data.resistDataReceived(user_data, resist_data)

        status = OpStatus()
        self.__resistCallbackHeadphones = ResistCallbackHeadphones(__py_resist_callback_headphones)
        self.__resistCallbackHeadphonesHandle = HeadphonesResistDataListenerHandle()
        _neuro_lib.addResistCallbackHeadphones(self.sensor_ptr, self.__resistCallbackHeadphones,
                                               byref(self.__resistCallbackHeadphonesHandle),
                                            py_object(self), byref(status))
        raise_exception_if(status)

    def __add_signal_data_callback_headphones(self):
        def __py_signal_data_callback_headphones(ptr, data, sz_data, user_data):
            signal_data = [HeadphonesSignalData(PackNum=int(data[i].PackNum),
                                                Marker=int(data[i].Marker),
                                                Ch1=float(data[i].Ch1),
                                                Ch2=float(data[i].Ch2),
                                                Ch3=float(data[i].Ch3),
                                                Ch4=float(data[i].Ch4),
                                                Ch5=float(data[i].Ch5),
                                                Ch6=float(data[i].Ch6),
                                                Ch7=float(data[i].Ch7)) for i in range(sz_data)]
            if user_data.signalDataReceived is not None:
                user_data.signalDataReceived(user_data, signal_data)

        status = OpStatus()
        self.__signalDataCallbackHeadphones = SignalDataCallbackHeadphones(__py_signal_data_callback_headphones)
        self.__signalDataCallbackHeadphonesHandle = HeadphonesSignalDataListenerHandle()
        _neuro_lib.addSignalDataCallbackHeadphones(self.sensor_ptr,
                                                   self.__signalDataCallbackHeadphones,
                                                   byref(self.__signalDataCallbackHeadphonesHandle),
                                                   py_object(self), byref(status))
        raise_exception_if(status)
