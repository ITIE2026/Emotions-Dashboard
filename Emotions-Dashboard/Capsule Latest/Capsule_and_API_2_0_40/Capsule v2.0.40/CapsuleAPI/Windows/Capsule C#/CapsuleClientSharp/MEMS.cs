using Capsule.Utility;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using static Capsule.Device;

namespace Capsule
{
    public class MEMS : IDisposable
    {

        #region Members
        public struct MEMSData
        {
            public Point3D[] Accelerometer;
            public Point3D[] Gyroscope;
            public ulong[] TimestampMilli;
        }
        public MEMSData MEMSDataCurrent { set; get; }

        private HandleRef _handle;
        private bool _disposed;
        #endregion

        #region Constructors
        public MEMS(Device device)
        {
            AssertHandle(device.Handle, () => "Device has been disposed");
            var error = Error.Default;
            var memsPtr = MEMSCreate(device.Handle, ref error);
            if (!error.Success || memsPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[memsPtr] = this;
            _handle = new HandleRef(this, memsPtr);

            _onMEMSDataEventDelegate = new Delegate<HandlerMEMSData>(_handle.Handle, SetOnMEMSDataEvent);
            device.HandlerAdapter.Attach(this, device);
        }
        public MEMS(Device device, Calibrator calibrator)
        {
            AssertHandle(device.Handle, () => "Device has been disposed");
            Calibrator.AssertHandle(calibrator.Handle, () => "Calibrator has been disposed");
            var error = Error.Default;
            var memsPtr = MEMSCreateCalibrated(device.Handle, calibrator.Handle, ref error);
            if (!error.Success || memsPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[memsPtr] = this;
            _handle = new HandleRef(this, memsPtr);

            _onMEMSDataEventDelegate = new Delegate<HandlerMEMSData>(_handle.Handle, SetOnMEMSDataEvent);
            device.HandlerAdapter.Attach(this);
            calibrator.HandlerAdapter.Attach(this);
        }
        #endregion

        #region Disposers
        private void Dispose(bool disposing)
        {
            if (_disposed) return;
            if (disposing)
            {
                Converter.CallbacksToOwners.Remove(_handle.Handle, out _);

                _onMEMSDataEventDelegate.Reset();
            }

            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~MEMS()
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

        [DllImport(LibraryName, EntryPoint = "clCMEMS_Create")]
        private static extern IntPtr MEMSCreate(HandleRef device, ref Error error);

        [DllImport(LibraryName, EntryPoint = "clCMEMS_CreateCalibrated")]
        private static extern IntPtr MEMSCreateCalibrated(HandleRef device, HandleRef calibratorPtr, ref Error error);

        #endregion

        #region Events

        internal delegate void HandlerMEMSData(IntPtr mems, IntPtr memsTimedData);
        public Handler<MEMS, MEMSData>? OnMEMSDataEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCMEMS_SetOnMEMSTimedDataUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnMEMSDataEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerMEMSData handler, ref Error error);

        private readonly Delegate<HandlerMEMSData> _onMEMSDataEventDelegate;
        internal void SetMEMSDataHandler(HandlerMEMSData handler, ref Error error)
        {
            _onMEMSDataEventDelegate.Set(handler, ref error);
        }

        #endregion
    }
}
