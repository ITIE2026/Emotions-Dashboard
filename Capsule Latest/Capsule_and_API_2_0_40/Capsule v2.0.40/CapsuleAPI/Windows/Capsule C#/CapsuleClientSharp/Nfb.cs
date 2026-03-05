// Copyright. 2019 - 2024 PSBD. All rights reserved.

using Capsule.Utility;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Capsule
{
    public sealed class Nfb : IDisposable
    {
        public enum CallResult
        {
            Success = 0,
            FailedToSendData
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct UserState
        {
            public long Timestamp;
            public float Delta;
            public float Theta;
            public float Alpha;
            public float SMR;
            public float Beta;
        }

        #region Members
        private HandleRef _handle;
        private bool _disposed;
        #endregion

        #region Constructors
        public Nfb(Device device)
        {
            Device.AssertHandle(device.Handle, () => "Device has been disposed");
            var error = Error.Default;
            var nfbPtr = NFBCreate(device.Handle, ref error);
            if (!error.Success || nfbPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }
            if (nfbPtr == IntPtr.Zero)
            {
                throw new CapsuleException("Failed to create NFB");
            }

            Converter.CallbacksToOwners[nfbPtr] = this;
            _handle = new HandleRef(this, nfbPtr);
            _onUserStateChangedEventDelegate = new Delegate<HandlerUserStateChanged>(_handle.Handle, SetOnUserStateChangedEvent);
            _onErrorEventDelegate = new Delegate<HandlerError>(_handle.Handle, SetOnErrorEvent);
            device.HandlerAdapter.Attach(this);
        }

        public Nfb(Device device, Calibrator calibrator)
        {
            Device.AssertHandle(device.Handle, () => "Device has been disposed");
            Calibrator.AssertHandle(calibrator.Handle, () => "Calibrator has been disposed");
            var error = Error.Default;
            var nfbPtr = NFBCreateCalibrated(device.Handle, calibrator.Handle, ref error);
            if (!error.Success || nfbPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[nfbPtr] = this;
            _handle = new HandleRef(this, nfbPtr);
            _onUserStateChangedEventDelegate = new Delegate<HandlerUserStateChanged>(_handle.Handle, SetOnUserStateChangedEvent);
            _onErrorEventDelegate = new Delegate<HandlerError>(_handle.Handle, SetOnErrorEvent);
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

                _onErrorEventDelegate.Reset();
                _onUserStateChangedEventDelegate.Reset();
            }
            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~Nfb()
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
        internal static void AssertHandle(HandleRef handle, Func<string> messageProducer)
        {
            if (handle.Handle == IntPtr.Zero)
            {
                throw new InvalidOperationException(messageProducer());
            }
        }

        [DllImport(Device.LibraryName, EntryPoint = "clCNFB_Create")]
        private static extern IntPtr NFBCreate(HandleRef device, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCNFB_CreateCalibrated")]
        private static extern IntPtr NFBCreateCalibrated(HandleRef device, HandleRef calibratorPtr, ref Error error);
        #endregion

        #region Events
        internal delegate void HandlerUserStateChanged(IntPtr nfb, UserState userState);
        public Handler<Nfb, UserState>? OnUserStateChangedEvent { get; set; }
        
        [DllImport(Device.LibraryName, EntryPoint = "clCNFB_SetOnUserStateChangedEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnUserStateChangedEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerUserStateChanged handler);

        private readonly Delegate<HandlerUserStateChanged> _onUserStateChangedEventDelegate;
        internal void SetUserStateChangedHandler(HandlerUserStateChanged handler)
        {
            _onUserStateChangedEventDelegate.Set(handler);
        }

        internal delegate void HandlerError(IntPtr nfb, string error);
        public Handler<Nfb, string>? OnErrorEvent { get; set; }
       
        [DllImport(Device.LibraryName, EntryPoint = "clCNFB_SetOnErrorEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnErrorEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerError handler);

        private readonly Delegate<HandlerError> _onErrorEventDelegate;
        
        internal void SetErrorHandler(HandlerError handler)
        {
            _onErrorEventDelegate.Set(handler);
        }
        #endregion
    }
}