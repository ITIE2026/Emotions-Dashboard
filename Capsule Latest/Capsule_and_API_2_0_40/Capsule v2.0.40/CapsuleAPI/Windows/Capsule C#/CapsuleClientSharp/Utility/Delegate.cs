// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System;

namespace Capsule.Utility
{
    /**
    * \brief Event delegate.
    */
    public delegate void Handler<Owner>(Owner owner);

    /**
    * \brief Typed event delegate.
    */
    public delegate void Handler<Owner, T>(Owner owner, T arg);

    /**
    * \brief Typed event delegate.
    */
    public delegate void Handler<Owner, T1, T2>(Owner owner, T1 arg1, T2 arg2);

    internal delegate void HandlerCallback(IntPtr owner);

    internal sealed class Delegate<THandler>
    {
        private bool _isAlive = true;
        private readonly IntPtr _handle;
        private THandler _handler; // To prevent GC and pass single function to unmanaged code
        private readonly Action<IntPtr, THandler> _delegateSet;

        internal delegate void DelegateSetErrorRef<IntPtr, TRHandler, Error>(IntPtr handle, THandler handler, ref Error error);
        private readonly DelegateSetErrorRef<IntPtr, THandler, Error> _delegateSetErrorRef;

        internal Delegate(IntPtr handle, Action<IntPtr, THandler> delegateSet)
        {
            _handle = handle;
            _delegateSet = delegateSet;
        }

        internal Delegate(IntPtr handle, DelegateSetErrorRef<IntPtr, THandler, Error> delegateSet)
        {
            _handle = handle;
            _delegateSetErrorRef = delegateSet;
        }

        internal void Set(THandler handler)
        {
            if (!_isAlive) return;
            _handler = handler;
            _delegateSet(_handle, _handler);
        }
        internal void Set(THandler handler, ref Error error)
        {
            if (!_isAlive) return;
            _handler = handler;
            _delegateSetErrorRef(_handle, _handler, ref error);
        }

        internal void Reset()
        {
            _isAlive = false;
        }
    }
}