// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System;
using Capsule.Utility;
using System.Runtime.InteropServices;
using System.Linq;
using System.Collections.Generic;

namespace Capsule
{
    public class Productivity
    {

        public enum FatigueGrowthRate
        {
            None = 0,
            Low = 1,
            Medium = 2,
            High = 3
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct MetricsInternal
        {
            public long Timestamp;
            public float FatigueScore;
            public float ReverseFatigueScore;
            public float GravityScore;
            public float RelaxationScore;
            public float ConcentrationScore;
            public float ProductivityScore;
            public float CurrentValue;
            public float Alpha;
            public float ProductivityBaseline;
            public float AccumulatedFatigue;
            public FatigueGrowthRate _FatigueGrowthRate;
            public IntPtr ArtifactsData;
            public ulong ArtifactsSize;
        }
        public struct Metrics
        {
            internal Metrics(MetricsInternal metrics)
            {
                Timestamp = metrics.Timestamp;
                FatigueScore = metrics.FatigueScore;
                ReverseFatigueScore = metrics.ReverseFatigueScore;
                GravityScore = metrics.GravityScore;
                RelaxationScore = metrics.RelaxationScore;
                ConcentrationScore = metrics.ConcentrationScore;
                ProductivityScore = metrics.ProductivityScore;
                CurrentValue = metrics.CurrentValue;
                Alpha = metrics.Alpha;
                ProductivityBaseline = metrics.ProductivityBaseline;
                AccumulatedFatigue = metrics.AccumulatedFatigue;
                _FatigueGrowthRate = metrics._FatigueGrowthRate;

                var bytes = new byte[metrics.ArtifactsSize];
                Marshal.Copy(metrics.ArtifactsData, bytes, 0, bytes.Length);
                ArtifactsData = bytes.ToArray();
            }
            public long Timestamp;
            public float FatigueScore;
            public float ReverseFatigueScore;
            public float GravityScore;
            public float RelaxationScore;
            public float ConcentrationScore;
            public float ProductivityScore;
            public float CurrentValue;
            public float Alpha;
            public float ProductivityBaseline;
            public float AccumulatedFatigue;
            public FatigueGrowthRate _FatigueGrowthRate;
            public byte[] ArtifactsData;
        }

        public enum RecommendationValue
        {
            NoRecommendation = 0,
            Involvement = 1,
            Relaxation = 2,
            SlightFatigue = 3,
            SevereFatigue = 4,
            ChronicFatigue = 5
        }

        public enum StressValue
        {
            NoStress = 0,
            Anxiety,
            Stress
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct Indexes
        {
            public ulong Timestamp;
            public RecommendationValue Relaxation;
            public StressValue Stress;
            public float GravityBaseline;
            public float ProductivityBaseline;
            public float FatigueBaseline;
            public float ReverseFatigueBaseline;
            public float RelaxationBaseline;
            public float ConcentrationBaseline;
            [MarshalAs(UnmanagedType.I1)] public bool HasArtifacts;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct Baselines
        {
            public ulong Timestamp;
            public float Gravity;
            public float Productivity;
            public float Fatigue;
            public float ReverseFatigue;
            public float Relaxation;
            public float Concentration;
        }

        #region Members
        private HandleRef _handle;
        private bool _disposed;
        #endregion

        #region Constructors
        public Productivity(Device device)
        {
            Device.AssertHandle(device.Handle, () => "Device has been disposed");
            var error = Error.Default;
            var productivityPtr = ProductivityCreate(device.Handle, ref error);
            if (!error.Success || productivityPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[productivityPtr] = this;
            _handle = new HandleRef(this, productivityPtr);

            _onBaselineUpdateEventDelegate = new Delegate<HandlerBaselineUpdate>(_handle.Handle, SetOnBaselineUpdateEvent);
            _onMetricsUpdateEventDelegate = new Delegate<HandlerMetricsUpdate>(_handle.Handle, SetOnMetricsUpdateEvent);
            _onIndexesEventDelegate = new Delegate<HandlerIndexesUpdate>(_handle.Handle, SetOnIndexeslEvent);
            _onCalibrationProgressUpdateEventDelegate = new Delegate<HandlerCalibrationProgressUpdate>(_handle.Handle, SetOnCalibrationProgressUpdateEvent);
            _onIndividualNFBUpdateEventDelegate = new Delegate<HandlerIndividualNFBUpdate>(_handle.Handle, SetOnIndividualNFBUpdateEvent);
            device.HandlerAdapter.Attach(this);
        }

        public Productivity(Device device, Calibrator.IndividualNfbData data)
        {
            Device.AssertHandle(device.Handle, () => "Device has been disposed");
            var error = Error.Default;
            var productivityPtr = ProductivityCreateWithIndividualData(device.Handle, data, ref error);
            if (!error.Success || productivityPtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[productivityPtr] = this;
            _handle = new HandleRef(this, productivityPtr);

            _onBaselineUpdateEventDelegate = new Delegate<HandlerBaselineUpdate>(_handle.Handle, SetOnBaselineUpdateEvent);
            _onMetricsUpdateEventDelegate = new Delegate<HandlerMetricsUpdate>(_handle.Handle, SetOnMetricsUpdateEvent);
            _onIndexesEventDelegate = new Delegate<HandlerIndexesUpdate>(_handle.Handle, SetOnIndexeslEvent);
            _onCalibrationProgressUpdateEventDelegate = new Delegate<HandlerCalibrationProgressUpdate>(_handle.Handle, SetOnCalibrationProgressUpdateEvent);
            _onIndividualNFBUpdateEventDelegate = new Delegate<HandlerIndividualNFBUpdate>(_handle.Handle, SetOnIndividualNFBUpdateEvent);
            device.HandlerAdapter.Attach(this);
        }
        #endregion

        #region Disposers
        private void Dispose(bool disposing)
        {
            if (_disposed) return;
            if (disposing)
            {
                _onBaselineUpdateEventDelegate.Reset();
                _onMetricsUpdateEventDelegate.Reset();
                _onIndexesEventDelegate.Reset();
                _onCalibrationProgressUpdateEventDelegate.Reset();
                _onIndividualNFBUpdateEventDelegate.Reset();

                Converter.CallbacksToOwners.Remove(_handle.Handle, out _);
            }
            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~Productivity()
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
        public void ResetAccumulatedFatigue()
        {
            AssertHandle(_handle);
            var error = Error.Default;
            ResetAccumulatedFatigue(_handle, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }

        public void ImportBaselines(Baselines baselines)
        {
            AssertHandle(_handle);
            var error = Error.Default;
            ImportBaselines(_handle, baselines, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }
        public void StartBaselineCalibration()
        {
            AssertHandle(_handle);
            StartBaselineCalibration(_handle);
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

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_Create")]
        private static extern IntPtr ProductivityCreate(HandleRef device, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_CreateWithIndividualData")]
        private static extern IntPtr ProductivityCreateWithIndividualData(HandleRef device, Calibrator.IndividualNfbData nfb, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_ImportBaselines")]
        private static extern void ImportBaselines(HandleRef productivityPtr, Baselines baselines, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_ResetAccumulatedFatigue")]
        private static extern void ResetAccumulatedFatigue(HandleRef nfbPtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_StartBaselineCalibration")]
        private static extern void StartBaselineCalibration(HandleRef nfbPtr);

        #endregion

        #region Events
        internal delegate void HandlerBaselineUpdate(IntPtr productivity, Baselines baseline);
        public Handler<Productivity, Baselines>? OnBaselineUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_SetOnBaselineUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnBaselineUpdateEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerBaselineUpdate handler);

        private readonly Delegate<HandlerBaselineUpdate> _onBaselineUpdateEventDelegate;
        internal void SetBaselineUpdateHandler(HandlerBaselineUpdate handler)
        {
            _onBaselineUpdateEventDelegate.Set(handler);
        }

        internal delegate void HandlerMetricsUpdate(IntPtr productivity, MetricsInternal baseline);
        public Handler<Productivity, Metrics>? OnMetricsUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_SetOnMetricsUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnMetricsUpdateEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerMetricsUpdate handler);

        private readonly Delegate<HandlerMetricsUpdate> _onMetricsUpdateEventDelegate;
        internal void SetMetricsUpdateHandler(HandlerMetricsUpdate handler)
        {
            _onMetricsUpdateEventDelegate.Set(handler);
        }

        internal delegate void HandlerIndexesUpdate(IntPtr owner, Indexes indexes);
        public Handler<Productivity, Indexes>? OnIndexesEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_SetOnIndexesUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnIndexeslEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerIndexesUpdate handler);

        private readonly Delegate<HandlerIndexesUpdate> _onIndexesEventDelegate;
        internal void SetIndexesHandler(HandlerIndexesUpdate handler)
        {
            _onIndexesEventDelegate.Set(handler);
        }

        internal delegate void HandlerCalibrationProgressUpdate(IntPtr productivity, float values);
        public Handler<Productivity, float>? OnCalibrationProgressUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_SetOnCalibrationProgressUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnCalibrationProgressUpdateEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerCalibrationProgressUpdate handler);

        private readonly Delegate<HandlerCalibrationProgressUpdate> _onCalibrationProgressUpdateEventDelegate;

        internal void SetCalibrationProgressUpdateHandler(HandlerCalibrationProgressUpdate handler)
        {
            _onCalibrationProgressUpdateEventDelegate.Set(handler);
        }

        internal delegate void HandlerIndividualNFBUpdate(IntPtr productivity);
        public Handler<Productivity>? OnIndividualNFBUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCProductivity_SetOnIndividualNFBUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnIndividualNFBUpdateEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerIndividualNFBUpdate handler);

        private readonly Delegate<HandlerIndividualNFBUpdate> _onIndividualNFBUpdateEventDelegate;

        internal void SetIndividualNFBUpdateHandler(HandlerIndividualNFBUpdate handler)
        {
            _onIndividualNFBUpdateEventDelegate.Set(handler);
        }
        #endregion
    }
}