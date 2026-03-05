using Capsule.Utility;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Capsule
{
    public class PhysiologicalStates : IDisposable
    {
        [StructLayout(LayoutKind.Sequential)]
        public struct PhysiologicalStatesValue
        {
            public long Timestamp;
            public float Relaxation;
            public float Fatigue;
            public float None;
            public float Concentration;
            public float Involvement;
            public float Stress;
            [MarshalAs(UnmanagedType.I1)] public bool NfbArtifacts;
            [MarshalAs(UnmanagedType.I1)] public bool CardioArtifacts;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct PhysiologicalStatesBaselines
        {
            public long Timestamp;
            public float Alpha;
            public float Beta;
            public float AlphaGravity;
            public float BetaGravity;
            public float Concentration;
        }

        #region Members
        private HandleRef _handle;
        private bool _disposed;
        #endregion

        #region Constructors
        public PhysiologicalStates(Device device)
        {
            Device.AssertHandle(device.Handle, () => "Device has been disposed");
            
            var error = Error.Default;
            var psPtr = PhysiologicalStatesCreate(device.Handle, ref error);
            if (!error.Success || psPtr == IntPtr.Zero) throw new CapsuleException(error);

            Converter.CallbacksToOwners[psPtr] = this;
            _handle = new HandleRef(this, psPtr);

            _onPSUpdateEventDelegate = new Delegate<HandlerPSUpdate>(_handle.Handle, SetOnPSUpdateEvent);
            _onPSCalbratedEventDelegate = new Delegate<HandlerPSCalibrated>(_handle.Handle, SetOnPSCalibratedEvent);
            _onPSCalibrationProgressUpdateEventDelegate = new Delegate<HandlerPSCalibrationProgressUpdate>(_handle.Handle, SetOnPSCalibrationProgressUpdateEvent);
            _onPSIndividualNFBUpdateEventDelegate = new Delegate<HandlerPSIndividualNFBUpdate>(_handle.Handle, SetOnPSIndividualNFBUpdateEvent);

            device.HandlerAdapter.Attach(this);
        }
        #endregion

        #region Disposers
        private void Dispose(bool disposing)
        {
            if (_disposed) return;
            if (disposing)
            {
                Converter.CallbacksToOwners.Remove(_handle.Handle, out _);
                
                _onPSUpdateEventDelegate.Reset();
                _onPSCalbratedEventDelegate.Reset();
                _onPSCalibrationProgressUpdateEventDelegate.Reset();
                _onPSIndividualNFBUpdateEventDelegate.Reset();
            }

            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~PhysiologicalStates()
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
        public void ImportBaselines(PhysiologicalStatesBaselines baselines)
        {
            AssertHandle(_handle);
            PhysiologicalStatesImportBaselines(_handle, baselines);
        }

        public void StartBaselineCalibration()
        {
            AssertHandle(_handle);
            PhysiologicalStatesStartBaselineCalibration(_handle);
        }

        [DllImport(Device.LibraryName, EntryPoint = "clCPhysiologicalStates_Create")]
        private static extern IntPtr PhysiologicalStatesCreate(HandleRef device, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCPhysiologicalStates_ImportBaselines")]
        public static extern void PhysiologicalStatesImportBaselines(HandleRef ps, PhysiologicalStatesBaselines baselines);

        [DllImport(Device.LibraryName, EntryPoint = "clCPhysiologicalStates_StartBaselineCalibration")]
        public static extern void PhysiologicalStatesStartBaselineCalibration(HandleRef ps);

        private static void AssertHandle(HandleRef handle)
        {
            Device.AssertHandle(handle, () => "PS classifier has been disposed");
        }
        #endregion

        #region Events

        internal delegate void HandlerPSUpdate(IntPtr psPtr, PhysiologicalStatesValue arg);
        public Handler<PhysiologicalStates, PhysiologicalStatesValue>? OnPhysiologicalStatesUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCPhysiologicalStates_SetOnStatesUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnPSUpdateEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerPSUpdate handler, ref Error error);

        private readonly Delegate<HandlerPSUpdate> _onPSUpdateEventDelegate;
        internal void SetPSUpdateHandler(HandlerPSUpdate handler, ref Error error)
        {
            _onPSUpdateEventDelegate.Set(handler, ref error);
        }

        internal delegate void HandlerPSCalibrated(IntPtr psPtr, PhysiologicalStatesBaselines arg);
        public Handler<PhysiologicalStates, PhysiologicalStatesBaselines>? OnPhysiologicalStatesCalibratedEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCPhysiologicalStates_SetOnCalibratedEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnPSCalibratedEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerPSCalibrated handler, ref Error error);

        private readonly Delegate<HandlerPSCalibrated> _onPSCalbratedEventDelegate;
        internal void SetPSCalibratedHandler(HandlerPSCalibrated handler, ref Error error)
        {
            _onPSCalbratedEventDelegate.Set(handler, ref error);
        }

        internal delegate void HandlerPSCalibrationProgressUpdate(IntPtr psPtr, float arg);
        public Handler<PhysiologicalStates, float>? OnCalibrationProgressUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCPhysiologicalStates_SetOnCalibrationProgressUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnPSCalibrationProgressUpdateEvent(IntPtr ps, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerPSCalibrationProgressUpdate handler, ref Error error);

        private readonly Delegate<HandlerPSCalibrationProgressUpdate> _onPSCalibrationProgressUpdateEventDelegate;
        internal void SetPSCalibrationProgressUpdateHandler(HandlerPSCalibrationProgressUpdate handler, ref Error error)
        {
            _onPSCalibrationProgressUpdateEventDelegate.Set(handler, ref error);
        }

        internal delegate void HandlerPSIndividualNFBUpdate(IntPtr psPtr);
        public Handler<PhysiologicalStates>? OnIndividualNFBUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCPhysiologicalStates_SetOnIndividualNFBUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnPSIndividualNFBUpdateEvent(IntPtr ps, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerPSIndividualNFBUpdate handler, ref Error error);

        private readonly Delegate<HandlerPSIndividualNFBUpdate> _onPSIndividualNFBUpdateEventDelegate;
        internal void SetPSIndividualNFBUpdateHandler(HandlerPSIndividualNFBUpdate handler, ref Error error)
        {
            _onPSIndividualNFBUpdateEventDelegate.Set(handler, ref error);
        }

        #endregion
    }
}