// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System;
using System.Runtime.InteropServices;

namespace Capsule
{
    public enum ErrorCode
    {
        Ok = 0,
        FailedToConnect,
        FailedToInitConnection,
        FailedToInitialize,
        DeviceError,
        IndividualNfbNotCalibrated,
        NotReceived,
        NullPointer,
        ModuleAlreadyExists,
        ModuleIsNotSupported,
        FailedToSendData,
        IndexOutOfRange,
        EmptyCollection,
        NotFound,
        SizeMismatch,
        Unknown = 255
    }
    
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    public struct Error
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Message;
        [MarshalAs(UnmanagedType.Bool)] public bool Success;
        public ErrorCode Code;
        
        public static readonly Error Default = new Error
        {
            Message = "",
            Success = true,
            Code = ErrorCode.Ok
        };
    }
    
    public class CapsuleException : Exception
    {
        public ErrorCode Code { get; }

        public CapsuleException()
            : base()
        {
            Code = ErrorCode.Ok;
        }
        
        public CapsuleException(Error error)
            : base(error.Message)
        {
            Code = error.Code;
        }
        
        public CapsuleException(string message)
            : base(message)
        {
            Code = ErrorCode.Ok;
        }

        public CapsuleException(ErrorCode code)
            : base()
        {
            Code = code;
        }

        public CapsuleException(string message, ErrorCode code)
            : base(message)
        {
            Code = code;
        }

        public CapsuleException(string message, ErrorCode code, Exception innerException)
            : base(message, innerException)
        {
            Code = code;
        }
    }
}