// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System;
using Capsule.Utility;
using System.Runtime.InteropServices;
using System.Collections.Generic;

namespace Capsule
{
    public static class Capsule
    {
        public enum LogLevel
        {
            Trace, Debug, Info, Warning, Error, Fatal, Off
        }

        public static string Version {
            get
            {
                var ptr = GetVersion();
                return Marshal.PtrToStringAnsi(ptr);
            }
        }

        public static LogLevel Level
        {
            get { return GetLogLevel(); }
            set { SetLogLevel(value); }
        }

        [DllImport(Device.LibraryName, EntryPoint = "clCCapsule_GetVersionString")]
        private static extern IntPtr GetVersion();

        [DllImport(Device.LibraryName, EntryPoint = "clCCapsule_SetLogLevel")]
        private static extern void SetLogLevel(LogLevel logLevel);

        [DllImport(Device.LibraryName, EntryPoint = "clCCapsule_GetLogLevel")]
        private static extern LogLevel GetLogLevel();

    }

    public sealed class DeviceLocator : IDisposable
    {
        public enum FailReason
        {
            Ok, 
            BluetoothDisabled,
            Unknown
        }

        #region Members
        private HandleRef _handle;
        private bool _disposed;
        private readonly IHandlerAdapter _handlerAdapter;
        #endregion

        #region Constructors
        public DeviceLocator(IHandlerAdapter handlerAdapter)
        {
            var error = Error.Default;
            var locatorPtr = Create(ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
            _handlerAdapter = handlerAdapter;
            _handle = new HandleRef(this, locatorPtr);
            Converter.CallbacksToOwners[locatorPtr] = this;
            _onDeviceListEventDelegate = new Delegate<HandlerDeviceList>(_handle.Handle, SetOnDeviceListEvent);
            handlerAdapter.Attach(this);
        }
        
        public DeviceLocator(string logDirectory, IHandlerAdapter handlerAdapter)
        {
            var error = Error.Default;
            var locatorPtr = CreateWithLogDirectory(logDirectory, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
            _handlerAdapter = handlerAdapter;
            _handle = new HandleRef(this, locatorPtr);
            Converter.CallbacksToOwners[locatorPtr] = this;
            _onDeviceListEventDelegate = new Delegate<HandlerDeviceList>(_handle.Handle, SetOnDeviceListEvent);
            handlerAdapter.Attach(this);
        }
        #endregion

        #region Disposers
        private void Dispose(bool disposing)
        {
            if (_disposed) return;
            if (disposing)
            {
                Converter.CallbacksToOwners.Remove(_handle.Handle, out _);
                Destroy(_handle);
                _onDeviceListEventDelegate.Reset();
            }
            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~DeviceLocator()
        {
            // Do not change this code. Put cleanup code in 'Dispose(bool disposing)' method
            Dispose(disposing: false);
        }

        public void Dispose()
        {
            // Do not change this code. Put cleanup code in 'Dispose(bool disposing)' method
            Dispose(disposing: true);
            GC.SuppressFinalize(this);
        }
        #endregion

        #region Methods
        public void RequestDevices(DeviceType deviceType, int searchTimeSeconds)
        {
            AssertHandle(_handle);
            var error = Error.Default;
            RequestDevices(_handle, deviceType, searchTimeSeconds, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }
        internal static void AssertHandle(HandleRef handle, Func<string> messageProducer)
        {
            if (handle.Handle == IntPtr.Zero)
            {
                throw new InvalidOperationException(messageProducer());
            }
        }
        private static void AssertHandle(HandleRef handle)
        {
            AssertHandle(handle, () => "Device locator has been disposed");
        }
        public Device CreateDevice(string deviceId)
        {
            AssertHandle(_handle);
            var error = Error.Default;
            var devicePtr = CreateDevice(_handle, deviceId, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
            return new Device(devicePtr, _handlerAdapter);
        }
        [DllImport(Device.LibraryName, EntryPoint = "clCDeviceLocator_CreateDevice", CharSet = CharSet.Ansi)]
        private static extern IntPtr CreateDevice(HandleRef locatorPtr, string deviceID, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDeviceLocator_Create")]
        private static extern IntPtr Create(ref Error error);
        
        [DllImport(Device.LibraryName, EntryPoint = "clCDeviceLocator_CreateWithLogDirectory")]
        private static extern IntPtr CreateWithLogDirectory(string logDirectory, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDeviceLocator_RequestDevices")]
        private static extern void RequestDevices(HandleRef locatorPtr, DeviceType deviceType, int searchTime, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDeviceLocator_Destroy")]
        private static extern void Destroy(HandleRef locatorPtr);
        #endregion

        #region Events
        internal delegate void HandlerDeviceList(IntPtr owner, IntPtr infoList, FailReason error);
        public Handler<DeviceLocator, DeviceInfo[], FailReason>? OnDeviceListEvent { get; set; }
       
        [DllImport(Device.LibraryName, EntryPoint = "clCDeviceLocator_SetOnDeviceListEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnDeviceListEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerDeviceList handler);

        private readonly Delegate<HandlerDeviceList> _onDeviceListEventDelegate;
        
        internal void SetDeviceListHandler(HandlerDeviceList handler)
        {
            _onDeviceListEventDelegate.Set(handler);
        }
        #endregion
    }
}