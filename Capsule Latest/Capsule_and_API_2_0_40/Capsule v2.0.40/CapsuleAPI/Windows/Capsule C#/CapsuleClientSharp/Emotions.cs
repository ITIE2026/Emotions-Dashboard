using Capsule.Utility;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Capsule
{
    public class Emotions : IDisposable
    {
        [StructLayout(LayoutKind.Sequential)]
        public struct EmotionalStates
        {
            public long Timestamp;
            public float Attention;
            public float Relaxation;
            public float CognitiveLoad;
            public float CognitiveControl;
            public float SelfControl;
        }
        #region Members
        private HandleRef _handle;
        private bool _disposed;
        #endregion

        #region Constructors
        public Emotions(Device device)
        {
            Device.AssertHandle(device.Handle, () => "Device has been disposed");
            var error = Error.Default;
            var ePtr = EmotionsCreate(device.Handle, ref error);
            if (!error.Success || ePtr == IntPtr.Zero)
            {
                throw new CapsuleException(error);
            }

            Converter.CallbacksToOwners[ePtr] = this;
            _handle = new HandleRef(this, ePtr);

            _onErrorEventDelegate = new Delegate<HandlerError>(_handle.Handle, SetOnErrorEvent);
            _onEmotionalStatesUpdateDelegate = new Delegate<HandlerEmotionsStatesUpdate>(_handle.Handle, SetEmotionsDelegateEmotionalStatesUpdate);
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

                _onErrorEventDelegate.Reset();
                _onEmotionalStatesUpdateDelegate.Reset();
            }
            _handle = new HandleRef(this, IntPtr.Zero);
            _disposed = true;
        }

        ~Emotions()
        {
            // Do not change this code. Put cleanup code in 'Dispose(bool disposing)' method
            Dispose(disposing: false);
        }

        public void Dispose()
        {
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

        [DllImport(Device.LibraryName, EntryPoint = "clCEmotions_Create")]
        private static extern IntPtr EmotionsCreate(HandleRef device, ref Error error);
        #endregion

        #region Events

        internal delegate void HandlerEmotionsStatesUpdate(IntPtr emotions, EmotionalStates states);
        public Handler<Emotions, EmotionalStates>? OnEmotionalStatesUpdateEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCEmotions_SetOnEmotionalStatesUpdateEvent", CallingConvention = CallingConvention.Cdecl)]
        private static extern void SetEmotionsDelegateEmotionalStatesUpdate(IntPtr emotions, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerEmotionsStatesUpdate handler);

        private readonly Delegate<HandlerEmotionsStatesUpdate> _onEmotionalStatesUpdateDelegate;
        internal void SetEmotionsStateDelegateFloatHandler(HandlerEmotionsStatesUpdate handler)
        {
            _onEmotionalStatesUpdateDelegate.Set(handler);
        }

        internal delegate void HandlerError(IntPtr emotions, string error);
        public Handler<Emotions, string>? OnErrorEvent { get; set; }

        [DllImport(Device.LibraryName, EntryPoint = "clCEmotions_SetOnErrorEvent")]
        private static extern void SetOnErrorEvent(IntPtr emotions, [MarshalAs(UnmanagedType.FunctionPtr)] HandlerError handler);

        private readonly Delegate<HandlerError> _onErrorEventDelegate;

        internal void SetErrorHandler(HandlerError handler)
        {
            _onErrorEventDelegate.Set(handler);
        }

        #endregion
    }
}