// Copyright. 2019 - 2024 PSBD. All rights reserved.

using Capsule.Utility;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Capsule
{
    public sealed class Device : IDisposable
    {
        internal const string LibraryName =
        #if _WINDOWS
            "CapsuleClient";
        #elif _OSX || _LINUX
            "libCapsuleClient";
        #else
            "Platform is not supported.";
        #endif
        public enum DeviceMode
        {
            Resistance,
            Signal,
            SignalAndResist,
            StartMems,
            StopMems,
            StartPpg,
            StopPpg
        }

        public enum ConnectionStatus
        {
            Disconnected,
            Connected,
            UnsupportedConnection
        }
        
        public struct EegData
        {
            public float[,] RawSamples;
            public float[,] ProcessedSamples;
            public ulong[] TimestampsMilli;
        }
        public struct EegArtifacts
        {
            public int[] Artifacts;
            public float[] EegQuality;
        }
        [StructLayout(LayoutKind.Sequential)]
        public struct Point3D
        {
            public float X;
            public float Y;
            public float Z;
        }

        public struct HzRange
        {
            public HzRange(float lower, float upper)
            {
                Lower = lower;
                Upper = upper;
            }
            public float Lower;
            public float Upper;
        }

        public struct Bands
        {
            public Bands(HzRange delta, HzRange theta, HzRange alpha, HzRange smr, HzRange beta)
            {
                Delta = delta;
                Theta = theta;
                Alpha = alpha;
                Smr = smr;
                Beta = beta;
            }
            
            public HzRange Delta;
            public HzRange Theta;
            public HzRange Alpha;
            public HzRange Smr;
            public HzRange Beta;
        }

        public class PsdData
        {
            public ulong TimestampMilli;
            public double[] Frequencies = { };
            public double[,] Psd = { };
            public Bands Bands;
            public HzRange? IndividualAlpha;
            public HzRange? IndividualBeta;
        }


        public class Resistance
        {
            public string ChannelName { get; set; }
            public float ResistanceValue { get; set; }

            internal Resistance(string channelName, float value)
            {
                ChannelName = channelName;
                ResistanceValue = value;
            }
        }

        #region Members
        private HandleRef _handle;
        private bool _disposed;
        internal readonly IHandlerAdapter HandlerAdapter;
        public EegData EegDataCurrent { set; get; }
        public PsdData PsdDataCurrent { set; get; }
        public EegArtifacts _EegArtifacts { set; get; }
        #endregion
        internal Device(IntPtr devicePtr, IHandlerAdapter handlerAdapter)
        {
            HandlerAdapter = handlerAdapter;
            _handle = new HandleRef(this, devicePtr);
            Converter.CallbacksToOwners[devicePtr] = this;
            _onConnectionStatusChangedEventDelegate = new Delegate<HandlerConnectionStatusChanged>(_handle.Handle, SetOnConnectionStatusChangedEvent);
            _onResistanceUpdateEventDelegate = new Delegate<HandlerResistanceUpdate>(_handle.Handle, SetOnResistanceUpdateEvent);
            _onModeSwitchedEventDelegate = new Delegate<HandlerDeviceMode>(_handle.Handle, SetOnDeviceModeSwitchedEvent);
            _onErrorEventDelegate = new Delegate<HandlerError>(_handle.Handle, SetOnErrorEvent);
            _onEegDataEventDelegate = new Delegate<HandlerEegData>(_handle.Handle, SetOnEegDataEvent);
            _onPsdDataEventDelegate = new Delegate<HandlerPsdData>(_handle.Handle, SetOnPsdDataEvent);
            _onEegArtifactsEventDelegate = new Delegate<HandlerEegArtifacts>(_handle.Handle, SetOnEegArtifactsEvent);
            _onBatteryChargeUpdateEventDelegate = new Delegate<HandlerBatteryChargeUpdate>(_handle.Handle, SetOnBatteryChargeUpdateEvent);
            handlerAdapter.Attach(this);
        }

        #region Methods
        public void Connect(bool bipolarChannels)
        {
            AssertHandle(_handle);
            var error = Error.Default;
            Connect(_handle, bipolarChannels, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }
        public void Disconnect()
        {
            AssertHandle(_handle);
            var error = Error.Default;
            Disconnect(_handle, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
        }
        public bool IsConnected()
        {
            AssertHandle(_handle);
            var error = Error.Default;
            bool isConnected = DeviceIsConnected(_handle, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
            return isConnected;
        }
        public DeviceInfo Info()
        {
            AssertHandle(_handle);
            var error = Error.Default;
            DeviceInfo info = Converter.DeviceInfoInternal.ConvertDeviceInfo(GetInfo(_handle, ref error));
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
            return info;
        }
        public string[] ChannelNames()
        {
            AssertHandle(_handle);
            Error errorNames = Error.Default;
            Error errorCount = Error.Default;
            var channelsPtr = GetChannelNames(_handle, ref errorNames);
            if (!errorNames.Success) throw new CapsuleException(errorNames);

            var channelsCount = GetChannelsCount(channelsPtr, ref errorCount);
            if (!errorCount.Success) throw new CapsuleException(errorCount);

            Error errorChannels = Error.Default;
            var channelNames = new string[channelsCount];
            for (var i = 0; i < channelsCount; i++)
            {
                channelNames[i] = Marshal.PtrToStringAnsi(GetChannelNameByIndex(channelsPtr, i, ref errorChannels));
                if (!errorChannels.Success) throw new CapsuleException(errorChannels);
            }

            return channelNames;
        }
        public byte BatteryCharge()
        {
            AssertHandle(_handle);
            var error = Error.Default;
            byte batteryCharge = DeviceBatteryCharge(_handle, ref error);
            if (!error.Success)
            {
                throw new CapsuleException(error);
            }
            return batteryCharge;
        }
        public void Start()
        {
            AssertHandle(_handle);
            var error = new Error();
            Start(_handle, ref error);
            if (!error.Success)
            {
                throw new Exception($"Failed to start {error.Message}");
            }
        }
        public void Stop()
        {
            AssertHandle(_handle);
            var error = new Error();
            Stop(_handle, ref error);
            if (!error.Success)
            {
                throw new Exception($"Failed to stop {error.Message}");
            }
        }
        public DeviceMode Mode
        {
            get
            {
                AssertHandle(_handle);
                return GetMode(_handle);
            }
        }

        public float EegSampleRate
        {
            get
            {
                AssertHandle(_handle);
                var error = Error.Default;
                var sampleRate = GetEEGSampleRate(_handle, ref error);
                if (!error.Success) throw new CapsuleException(error);
                return sampleRate;
            }
        }

        public float PpgSampleRate
        {
            get
            {
                AssertHandle(_handle);
                var error = Error.Default;
                var sampleRate = GetPPGSampleRate(_handle, ref error);
                if (!error.Success) throw new CapsuleException(error);
                return sampleRate;
            }
        }

        public float MemsSampleRate
        {
            get
            {
                AssertHandle(_handle);
                var error = Error.Default;
                var sampleRate = GetMEMSSampleRate(_handle, ref error);
                if (!error.Success) throw new CapsuleException(error);
                return sampleRate;
            }
        }

        public int PpgIrAmplitude
        {
            get
            {
                AssertHandle(_handle);
                var error = Error.Default;
                var sampleRate = GetPPGIrAmplitude(_handle, ref error);
                if (!error.Success) throw new CapsuleException(error);
                return sampleRate;
            }
        }

        public int PpgRedAmplitude
        {
            get
            {
                AssertHandle(_handle);
                var error = Error.Default;
                var sampleRate = GetPPGRedAmplitude(_handle, ref error);
                if (!error.Success) throw new CapsuleException(error);
                return sampleRate;
            }
        }
        
        internal HandleRef Handle => _handle;
        internal static void AssertHandle(HandleRef handle, Func<string> messageProducer)
        {
            if (handle.Handle == IntPtr.Zero)
            {
                throw new InvalidOperationException(messageProducer());
            }
        }
        private static void AssertHandle(HandleRef handle)
        {
            AssertHandle(handle, () => "Device has been disposed");
        }

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_Release")]
        private static extern void Release(HandleRef devicePtr);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_Connect")]
        private static extern void Connect(HandleRef devicePtr, [MarshalAs(UnmanagedType.I1)] bool bipolarChannels, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_Disconnect")]
        private static extern void Disconnect(HandleRef devicePtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_IsConnected")]
        private static extern bool DeviceIsConnected(HandleRef devicePtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetInfo")]
        private static extern IntPtr GetInfo(HandleRef devicePtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetChannelNames")]
        private static extern IntPtr GetChannelNames(HandleRef devicePtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_ChannelNames_GetChannelsCount")]
        private static extern int GetChannelsCount(IntPtr deviceChannels, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_ChannelNames_GetChannelIndexByName", CharSet = CharSet.Ansi)]
        private static extern int GetChannelIndexByName(IntPtr deviceChannels, string channelName, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_ChannelNames_GetChannelNameByIndex", CharSet = CharSet.Ansi)]
        private static extern IntPtr GetChannelNameByIndex(IntPtr deviceChannels, int channelIndex, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetBatteryCharge")]
        private static extern byte DeviceBatteryCharge(HandleRef devicePtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_Start")]
        private static extern void Start(HandleRef devicePtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_Stop")]
        private static extern void Stop(HandleRef devicePtr, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetMode")]
        private static extern DeviceMode GetMode(HandleRef devicePtr);
        
        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetEEGSampleRate")]
        private static extern float GetEEGSampleRate(HandleRef devicePtr, ref Error error);
        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetPPGSampleRate")]
        private static extern float GetPPGSampleRate(HandleRef devicePtr, ref Error error);
        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetMEMSSampleRate")]
        private static extern float GetMEMSSampleRate(HandleRef devicePtr, ref Error error);
        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetPPGIrAmplitude")]
        private static extern int GetPPGIrAmplitude(HandleRef devicePtr, ref Error error);
        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_GetPPGRedAmplitude")]
        private static extern int GetPPGRedAmplitude(HandleRef devicePtr, ref Error error);
        #endregion

        #region Disposers
        private void Dispose(bool disposing)
        {
            if (_disposed) return;
            if (disposing)
            {
                Converter.CallbacksToOwners.Remove(_handle.Handle, out _);
                _onConnectionStatusChangedEventDelegate.Reset();
                _onResistanceUpdateEventDelegate.Reset();
                _onModeSwitchedEventDelegate.Reset();
                _onErrorEventDelegate.Reset();
                _onEegDataEventDelegate.Reset();
                _onPsdDataEventDelegate.Reset();
                _onEegArtifactsEventDelegate.Reset();
                _onBatteryChargeUpdateEventDelegate.Reset();
            }

            Release(_handle);
            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~Device()
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

        #region Events
        internal delegate void HandlerConnectionStatusChanged(IntPtr owner, ConnectionStatus state);
        public Handler<Device, ConnectionStatus>? OnConnectionStatusChangedEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCDevice_SetOnConnectionStatusChangedEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnConnectionStatusChangedEvent(IntPtr device, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerConnectionStatusChanged handler);

        private readonly Delegate<HandlerConnectionStatusChanged> _onConnectionStatusChangedEventDelegate;

        internal void SetConnectionStatusChangedHandler(HandlerConnectionStatusChanged handler)
        {
            _onConnectionStatusChangedEventDelegate.Set(handler);
        }

        internal delegate void HandlerResistanceUpdate(IntPtr owner, IntPtr resistance);
        public Handler<Device, Resistance[]>? OnResistanceUpdateEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCDevice_SetOnResistanceUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnResistanceUpdateEvent(IntPtr device, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerResistanceUpdate handler);

        private readonly Delegate<HandlerResistanceUpdate> _onResistanceUpdateEventDelegate;

        internal void SetResistanceUpdateHandler(HandlerResistanceUpdate handler)
        {
            _onResistanceUpdateEventDelegate.Set(handler);
        }

        internal delegate void HandlerBatteryChargeUpdate(IntPtr owner, byte charge);
        public Handler<Device, byte>? OnBatteryChargeUpdateEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCDevice_SetOnBatteryChargeUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnBatteryChargeUpdateEvent(IntPtr device, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerBatteryChargeUpdate handler);

        private readonly Delegate<HandlerBatteryChargeUpdate> _onBatteryChargeUpdateEventDelegate;

        internal void SetBatteryChargeUpdateHandler(HandlerBatteryChargeUpdate handler)
        {
            _onBatteryChargeUpdateEventDelegate.Set(handler);
        }

        internal delegate void HandlerDeviceMode(IntPtr device, DeviceMode value);
        public Handler<Device, DeviceMode>? OnModeSwitchedEvent { get; set; }
 
        [DllImport(LibraryName, EntryPoint = "clCDevice_SetOnModeSwitchedEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnDeviceModeSwitchedEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerDeviceMode handler);

        private readonly Delegate<HandlerDeviceMode> _onModeSwitchedEventDelegate;
        internal void SetModeSwitchedHandler(HandlerDeviceMode handler)
        {
            _onModeSwitchedEventDelegate.Set(handler);
        }
        internal delegate void HandlerError(IntPtr device, string error);
        public Handler<Device, string>? OnErrorEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCDevice_SetOnErrorEvent", CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)]
        private static extern void SetOnErrorEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerError handler);

        private readonly Delegate<HandlerError> _onErrorEventDelegate;
        internal void SetErrorHandler(HandlerError handler)
        {
            _onErrorEventDelegate.Set(handler);
        }

        internal delegate void HandlerEegData(IntPtr device, IntPtr eegTimedData);
        public Handler<Device, EegData>? OnEegDataEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCDevice_SetOnEEGDataEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnEegDataEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerEegData handler);

        private readonly Delegate<HandlerEegData> _onEegDataEventDelegate;
        internal void SetEegDataHandler(HandlerEegData handler)
        {
            _onEegDataEventDelegate.Set(handler);
        }
        
        internal delegate void HandlerPsdData(IntPtr device, IntPtr psdData);
        public Handler<Device, PsdData>? OnPsdDataEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCDevice_SetOnPSDDataEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnPsdDataEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerPsdData handler);

        private readonly Delegate<HandlerPsdData> _onPsdDataEventDelegate;
        internal void SetPsdDataHandler(HandlerPsdData handler)
        {
            _onPsdDataEventDelegate.Set(handler);
        }
        
        internal delegate void HandlerEegArtifacts(IntPtr device, IntPtr eegArtifacts);
        public Handler<Device, EegArtifacts>? OnEegArtifactsEvent { get; set; }

        [DllImport(LibraryName, EntryPoint = "clCDevice_SetOnEEGArtifactsEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetOnEegArtifactsEvent(IntPtr delegatePtr, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerEegArtifacts handler);

        private readonly Delegate<HandlerEegArtifacts> _onEegArtifactsEventDelegate;
        internal void SetEegArtifactsHandler(HandlerEegArtifacts handler)
        {
            _onEegArtifactsEventDelegate.Set(handler);
        }
        #endregion
    }
}