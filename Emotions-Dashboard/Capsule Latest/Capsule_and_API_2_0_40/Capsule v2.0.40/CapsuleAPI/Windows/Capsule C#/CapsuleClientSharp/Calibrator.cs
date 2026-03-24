// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System;
using Capsule.Utility;
using System.Runtime.InteropServices;
using System.Collections.Generic;

namespace Capsule
{
    public class Calibrator : IDisposable
    {
        public enum CalibrationStage
        {
            Stage1,
            Stage2,
            Stage3,
            Stage4
        }

        public enum FailReason
        {
            None,
            TooManyArtifacts,
            PeakIsABorder
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct IndividualNfbData
        {
            public ulong Timestamp;
            public FailReason FailReason;
            public float IndividualFrequency;
            public float IndividualPeakFrequency;
            public float IndividualPeakFrequencyPower;
            public float IndividualPeakFrequencySuppression;
            public float IndividualBandwidth;
            public float IndividualNormalizedPower;
            public float LowerFrequency;
            public float UpperFrequency;
        }

        #region Members
        private HandleRef _handle;
        private bool _disposed;
        internal readonly IHandlerAdapter HandlerAdapter;
        #endregion

        #region Constructors
        public Calibrator(Device device)
        {
            Device.AssertHandle(device.Handle, () => "Device has been disposed");
            var calibratorPtr = CreateOrGetCalibrator(device.Handle);
            if (calibratorPtr == IntPtr.Zero)
            {
                throw new CapsuleException("Failed to create calibrator");
            }

            _handle = new HandleRef(this, calibratorPtr);
            Converter.CallbacksToOwners[calibratorPtr] = this;
            _onIndividualNfbStageFinishedEventDelegate = new Delegate<HandlerCalibrationStageFinished>(_handle.Handle, SetOnIndividualNFBStageFinishedEvent);
            _onCalibratedEventDelegate = new Delegate<HandlerCalibrated>(_handle.Handle, SetOnCalibratedEvent);

            device.HandlerAdapter.Attach(this);
            HandlerAdapter = device.HandlerAdapter;
        }
        #endregion

        #region Methods
        internal HandleRef Handle => _handle;
        public void CalibrateIndividualNfb(CalibrationStage stage)
        {
            AssertHandle(_handle);
            var error = Error.Default;
            CalibrateIndividualNFB(_handle, stage, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }
        public void CalibrateIndividualNfbQuick()
        {
            AssertHandle(_handle);
            var error = Error.Default;
            CalibrateIndividualNFBQuick(_handle, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }
        public void ImportIndividualNFBData(IndividualNfbData nfb)
        {
            AssertHandle(_handle);
            var error = Error.Default;
            ImportIndividualNFBData(_handle, nfb, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }
        public IndividualNfbData IndividualNfb
        {
            get
            {
                AssertHandle(_handle);
                var nfb = new IndividualNfbData();
                var error = Error.Default;
                GetIndividualNFB(_handle, ref nfb, ref error);
                if (!error.Success)
                {
                    throw new CapsuleException(error);
                }
                return nfb;
            }
        }
        public bool IsCalibrated
        {
            get
            {
                AssertHandle(_handle);
                return IsCalibratorCalibrated(_handle);
            }
        }
        public bool IsCalibrationFailed
        {
            get
            {
                AssertHandle(_handle);
                return HasCalibrationFailed(_handle);
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
            AssertHandle(handle, () => "Calibrator has been disposed");
        }

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_CreateOrGet")]
        private static extern IntPtr CreateOrGetCalibrator(HandleRef device);

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_CalibrateIndividualNFB")]
        private static extern void CalibrateIndividualNFB(HandleRef calibratorPtr, CalibrationStage stage, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_CalibrateIndividualNFBQuick")]
        private static extern void CalibrateIndividualNFBQuick(HandleRef calibratorPtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_ImportIndividualNFBData")]
        private static extern void ImportIndividualNFBData(HandleRef calibratorPtr, IndividualNfbData nfb, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_GetIndividualNFB")]
        private static extern void GetIndividualNFB(HandleRef calibratorPtr, ref IndividualNfbData nfb, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_IsCalibrated")]
        private static extern bool IsCalibratorCalibrated(HandleRef calibratorPtr);

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_HasCalibrationFailed")]
        private static extern bool HasCalibrationFailed(HandleRef calibratorPtr);
        #endregion



        #region Events
        internal delegate void HandlerCalibrationStageFinished(IntPtr calibrator);
        public Handler<Calibrator>? OnIndividualNfbStageFinishedEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_SetOnCalibrationStageFinishedEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnIndividualNFBStageFinishedEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerCalibrationStageFinished handler);

        private readonly Delegate<HandlerCalibrationStageFinished> _onIndividualNfbStageFinishedEventDelegate;
        internal void SetIndividualNfbStageFinishedHandler(HandlerCalibrationStageFinished handler)
        {
            _onIndividualNfbStageFinishedEventDelegate.Set(handler);
        }

        internal delegate void HandlerCalibrated(IntPtr calibrator, IndividualNfbData nfb);
        public Handler<Calibrator, IndividualNfbData>? OnCalibratedEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCNFBCalibrator_SetOnCalibratedEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnCalibratedEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerCalibrated handler);

        private readonly Delegate<HandlerCalibrated> _onCalibratedEventDelegate;
        internal void SetCalibratedHandler(HandlerCalibrated handler)
        {
            _onCalibratedEventDelegate.Set(handler);
        }
        #endregion

        #region Disposers
        private void Dispose(bool disposing)
        {
            if (_disposed) return;
            if (disposing)
            {
                Converter.CallbacksToOwners.Remove(_handle.Handle, out _);
                
                _onIndividualNfbStageFinishedEventDelegate.Reset();
                _onCalibratedEventDelegate.Reset();

                Converter.CallbacksToOwners.Remove(_handle.Handle, out _);
            }

            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~Calibrator()
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
    }
}