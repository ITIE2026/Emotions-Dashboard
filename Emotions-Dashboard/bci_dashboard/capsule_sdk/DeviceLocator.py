import ctypes
from Error import *
from typing import Callable
from DeviceType import DeviceType
from DeviceInfo import DeviceInfo
from CapsulePointersImpl import capsule_pointers

class DeviceLocator:
    class FailReason(ctypes.c_int):
        OK = 0
        BluetoothDisabled = 1
        Unknown = 2

    class DeviceInfoList:
        def __init__(self, pointer, lib):
            self._pointer = pointer
            self._lib = lib
            # Guard: a NULL pointer means the BLE scan failed before producing a list.
            # Calling into the DLL with a NULL pointer would cause a segfault, so
            # we short-circuit here and report an empty list instead.
            if not pointer:
                self._len = 0
                return
            self._lib.clCDeviceInfoList_GetCount.restype = ctypes.c_int
            self._lib.clCDeviceInfoList_GetCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(Error)]
            
            self._lib.clCDeviceInfoList_GetDeviceInfo.restype = ctypes.POINTER(ctypes.c_int)
            self._lib.clCDeviceInfoList_GetDeviceInfo.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.POINTER(Error)]
            error = Error()
            self._len = self._lib.clCDeviceInfoList_GetCount(self._pointer, ctypes.byref(error))

        def __len__(self):
            return self._len
        
        def __getitem__(self, idx : int):
            error = Error()
            info = DeviceInfo(self._lib.clCDeviceInfoList_GetDeviceInfo(self._pointer, idx, ctypes.byref(error)), self._lib);
            if error.code is not Error_Code.OK:
                raise CapsuleException(error)
            return info


    _name_in_pointers_map = "DeviceLocator"

    def __init__(self, logs_path, lib):
        self._lib = lib
        self._lib.clCDeviceLocator_CreateWithLogDirectory.restype = ctypes.POINTER(ctypes.c_int)
        self._lib.clCDeviceLocator_CreateWithLogDirectory.argtypes = [ctypes.c_char_p, ctypes.POINTER(Error)]
        
        self._lib.clCDeviceLocator_Update.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self._lib.clCDeviceLocator_Destroy.argtypes = [ctypes.POINTER(ctypes.c_int)]

        self._lib.clCDeviceLocator_RequestDevices.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(Error)]
        error = Error()
        self._pointer = self._lib.clCDeviceLocator_CreateWithLogDirectory(logs_path.encode('utf-8'), ctypes.byref(error))
        if error.code is not Error_Code.OK:
            raise CapsuleException(error)

    def __del__(self):
        self._lib.clCDeviceLocator_Destroy(self._pointer)

    def update(self):
        self._lib.clCDeviceLocator_Update(self._pointer)

    def request_devices(self, device_type : DeviceType, seconds_to_search : int):
        error = Error()
        self._lib.clCDeviceLocator_RequestDevices(self._pointer, device_type, seconds_to_search, ctypes.byref(error))
        if error.code is not Error_Code.OK:
            raise CapsuleException(error)

    def set_on_devices_list(self, callback : Callable[['DeviceLocator', 'DeviceLocator.DeviceInfoList', 'DeviceLocator.FailReason'], None]):
        global device_list_lib
        global device_list_callback
        device_list_lib = self.get_lib()
        device_list_callback = callback
        self.__save_obj()
        self._lib.clCDeviceLocator_SetOnDeviceListEvent.argtypes = [
            ctypes.POINTER(ctypes.c_int), ctypes.c_void_p
        ]
        self._lib.clCDeviceLocator_SetOnDeviceListEvent(self._pointer, devices_list_impl)
    
    def get_c_pointer(self):
        return self._pointer

    def get_lib(self):
        return self._lib
    
    def __save_obj(self):
        global capsule_pointers
        capsule_pointers[self._name_in_pointers_map] = self


# impl details    
device_list_lib = None
device_list_callback = None
@ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), DeviceLocator.FailReason)
def devices_list_impl(_locator, info, fail_reason):
        global device_list_lib, device_list_callback, capsule_pointers
        # info may be NULL when the BLE scanner fails (e.g. Bluetooth disabled).
        # DeviceInfoList.__init__ guards against NULL internally, so this is safe;
        # the extra check here avoids constructing the object at all when unneeded.
        device_info_list = DeviceLocator.DeviceInfoList(info if info else None, device_list_lib)
        device_list_callback(capsule_pointers['DeviceLocator'], device_info_list, fail_reason)