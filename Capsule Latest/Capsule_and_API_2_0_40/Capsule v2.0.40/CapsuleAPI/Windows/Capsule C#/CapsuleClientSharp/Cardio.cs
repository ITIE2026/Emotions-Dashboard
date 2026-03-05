using Capsule.Utility;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using static Capsule.Device;

namespace Capsule
{
    public class Cardio : IDisposable
    {
        [StructLayout(LayoutKind.Sequential)]
        public struct CardioData
        {
            public long Timestamp;
            public float HeartRate;
            public float StressIndex;
            public float KaplanIndex;
            [MarshalAs(UnmanagedType.I1)] public bool Artifacted;
            [MarshalAs(UnmanagedType.I1)] public bool SkinContact;
            [MarshalAs(UnmanagedType.I1)] public bool MotionArtifacts;
            [MarshalAs(UnmanagedType.I1)] public bool MetricsAvailable;
        }

        #region Members
        public struct PPGData
        {
            public float[] Samples;
            public ulong[] TimestampMilli;
        }
        public PPGData PPGDataCurrent { set; get; }
        private HandleRef _handle;
        private bool _disposed;
        #endregion

        #region Constructors
        public Cardio(Device device)
        {
            AssertHandle(device.Handle, () => "Device has been disposed");
            var error = Error.Default;
            var cardioPtr = CardioCreate(device.Handle, ref error);
            if (!error.Success || cardioPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[cardioPtr] = this;
            _handle = new HandleRef(this, cardioPtr);

            _onIndexesUpdateEventDelegate = new Delegate<HandlerIndexesUpdate>(_handle.Handle, SetOnIndexesUpdate);
            _onCalibratedEventDelegate = new Delegate<HandlerCalibrated>(_handle.Handle, SetOnCalibrated);
            _onPPGDataEventDelegate = new Delegate<HandlerPPGData>(_handle.Handle, SetOnPPGDataEvent);
            device.HandlerAdapter.Attach(this, device);
        }
        public Cardio(Device device, Calibrator calibrator)
        {
            AssertHandle(device.Handle, () => "Device has been disposed");
            Calibrator.AssertHandle(calibrator.Handle, () => "Calibrator has been disposed");
            var error = Error.Default;
            var cardioPtr = CardioCreateCalibrated(device.Handle, calibrator.Handle, ref error);
            if (!error.Success || cardioPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[cardioPtr] = this;
            _handle = new HandleRef(this, cardioPtr);
            
            _onIndexesUpdateEventDelegate = new Delegate<HandlerIndexesUpdate>(_handle.Handle, SetOnIndexesUpdate);
            _onCalibratedEventDelegate = new Delegate<HandlerCalibrated>(_handle.Handle, SetOnCalibrated);
            _onPPGDataEventDelegate = new Delegate<HandlerPPGData>(_handle.Handle, SetOnPPGDataEvent);
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
                
                _onIndexesUpdateEventDelegate.Reset();
                _onCalibratedEventDelegate.Reset();
                _onPPGDataEventDelegate.Reset();
            }

            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~Cardio()
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

        [DllImport(LibraryName, EntryPoint = "clCCardio_Create")]
        private static extern IntPtr CardioCreate(HandleRef device, ref Error error);

        [DllImport(LibraryName, EntryPoint = "clCCardio_CreateCalibrated")]
        private static extern IntPtr CardioCreateCalibrated(HandleRef device, HandleRef calibratorPtr, ref Error error);

        #endregion

        #region Events

        internal delegate void HandlerIndexesUpdate(IntPtr cardio, CardioData indexes);
        public Handler<Cardio, CardioData>? OnIndexesUpdateEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCCardio_SetOnIndexesUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnIndexesUpdate(IntPtr cardio, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerIndexesUpdate handler, ref Error error);

        private readonly Delegate<HandlerIndexesUpdate> _onIndexesUpdateEventDelegate;
        internal void SetIndexesUpdateHandler(HandlerIndexesUpdate handler, ref Error error)
        {
            _onIndexesUpdateEventDelegate.Set(handler, ref error);
        }

        internal delegate void HandlerCalibrated(IntPtr cardio);
        public Handler<Cardio>? OnCalibratedEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCCardio_SetOnCalibratedEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnCalibrated(IntPtr cardio, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerCalibrated handler, ref Error error);

        private readonly Delegate<HandlerCalibrated> _onCalibratedEventDelegate;
        internal void SetCalibratedHandler(HandlerCalibrated handler, ref Error error)
        {
            _onCalibratedEventDelegate.Set(handler, ref error);
        }

        internal delegate void HandlerPPGData(IntPtr cardio, IntPtr ppgTimedData);
        public Handler<Cardio, PPGData>? OnPPGDataEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCCardio_SetOnPPGDataEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnPPGDataEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerPPGData handler, ref Error error);

        private readonly Delegate<HandlerPPGData> _onPPGDataEventDelegate;
        internal void SetPPGDataHandler(HandlerPPGData handler, ref Error error)
        {
            _onPPGDataEventDelegate.Set(handler, ref error);
        }

        #endregion
    }
}